"""
幣安API客戶端模組
包含所有與幣安API交互的功能，保持與原程式完全相同的邏輯
=============================================================================
"""
import hmac
import hashlib
import time
import requests
import logging
from config.settings import API_KEY, API_SECRET, BASE_URL

# 設置logger
logger = logging.getLogger(__name__)

class BinanceClient:
    """幣安API客戶端"""
    
    def __init__(self):
        self.api_key = API_KEY
        self.api_secret = API_SECRET
        self.base_url = BASE_URL
        
        if not self.api_key or not self.api_secret:
            raise ValueError("API密鑰未正確配置")
            
        logger.info(f"幣安API客戶端初始化成功，使用密鑰ID: {self.api_key[:4]}...")
    
    def _sign_request(self, params):
        """為請求添加簽名"""
        query_string = '&'.join([f"{key}={params[key]}" for key in params])
        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        params["signature"] = signature
        return params
    
    def get_listen_key(self):
        """獲取用戶數據流的listenKey"""
        endpoint = "/fapi/v1/listenKey"
        headers = {"X-MBX-APIKEY": self.api_key}
        
        response = requests.post(f"{self.base_url}{endpoint}", headers=headers)
        if response.status_code == 200:
            return response.json()["listenKey"]
        else:
            logger.error(f"獲取listenKey失敗: {response.text}")
            return None
    
    def keep_listen_key_alive(self, listen_key):
        """定期發送請求以保持listenKey有效"""
        endpoint = "/fapi/v1/listenKey"
        headers = {"X-MBX-APIKEY": self.api_key}
        
        while True:
            try:
                response = requests.put(f"{self.base_url}{endpoint}", headers=headers)
                if response.status_code == 200:
                    logger.info("成功續期listenKey")
                else:
                    logger.warning(f"續期listenKey失敗: {response.text}")
                    # 如果返回-1125錯誤，表示listenKey不存在，需要重新獲取
                    if '"code":-1125' in response.text:
                        logger.warning("listenKey不存在，需要重新獲取")
                        return False
            except Exception as e:
                logger.error(f"續期listenKey出錯: {str(e)}")
            
            time.sleep(30 * 60)  # 30分鐘
    
    def set_leverage(self, symbol, leverage):
        """設置指定交易對的槓桿倍數"""
        endpoint = "/fapi/v1/leverage"
        headers = {"X-MBX-APIKEY": self.api_key}
        
        params = {
            "symbol": symbol,
            "leverage": leverage,
            "timestamp": int(time.time() * 1000)
        }
        
        # 簽名
        params = self._sign_request(params)
        
        # 發送請求
        response = requests.post(f"{self.base_url}{endpoint}", headers=headers, params=params)
        logger.info(f"設置槓桿響應: {response.text}")
        
        return response.status_code == 200
    
    def set_margin_type(self, symbol, margin_type="ISOLATED"):
        """設置指定交易對的保證金模式: ISOLATED(逐倉) 或 CROSSED(全倉)"""
        endpoint = "/fapi/v1/marginType"
        headers = {"X-MBX-APIKEY": self.api_key}
        
        params = {
            "symbol": symbol,
            "marginType": margin_type,
            "timestamp": int(time.time() * 1000)
        }
        
        # 簽名
        params = self._sign_request(params)
        
        # 發送請求
        response = requests.post(f"{self.base_url}{endpoint}", headers=headers, params=params)
        logger.info(f"設置保證金模式響應: {response.text}")
        
        # 如果已經是該模式，API會返回錯誤，但這不是真正的錯誤
        return response.status_code == 200 or "already" in response.text.lower()
    
    def get_current_positions(self):
        """獲取當前所有持倉信息（優化版本 - 減少log輸出）"""
        endpoint = "/fapi/v2/positionRisk"
        headers = {"X-MBX-APIKEY": self.api_key}
        
        params = {
            "timestamp": int(time.time() * 1000)
        }
        
        # 簽名
        params = self._sign_request(params)
        
        # 發送請求
        try:
            response = requests.get(f"{self.base_url}{endpoint}", headers=headers, params=params)
            
            if response.status_code == 200:
                positions = response.json()
                # 過濾出有效持倉（持倉數量不為零）
                active_positions = {}
                zero_positions_count = 0
                
                for position in positions:
                    symbol = position.get('symbol')
                    position_amt = float(position.get('positionAmt', 0))
                    
                    if position_amt != 0:
                        # 正值為多單，負值為空單
                        position_side = 'LONG' if position_amt > 0 else 'SHORT'
                        active_positions[symbol] = {
                            'symbol': symbol,
                            'positionAmt': position_amt,
                            'side': position_side,
                            'entryPrice': float(position.get('entryPrice', 0)),
                            'markPrice': float(position.get('markPrice', 0)),
                            'unRealizedProfit': float(position.get('unRealizedProfit', 0))
                        }
                    else:
                        zero_positions_count += 1
                
                # 優化的log輸出 - 只顯示摘要信息
                if active_positions:
                    logger.info(f"查詢持倉完成 - 活躍持倉: {len(active_positions)}個, 零持倉: {zero_positions_count}個")
                    for symbol, pos in active_positions.items():
                        logger.info(f"  {symbol}: {pos['side']} {abs(pos['positionAmt'])}, 未實現盈虧: {pos['unRealizedProfit']:.4f}")
                else:
                    logger.info(f"查詢持倉完成 - 無活躍持倉, 總計查詢{zero_positions_count}個交易對")
                    
                return active_positions
            else:
                logger.error(f"查詢持倉失敗 - 狀態碼: {response.status_code}, 錯誤: {response.text[:200]}...")
                return {}
        except Exception as e:
            logger.error(f"查詢持倉出錯: {str(e)}")
            return {}
    
    def place_order(self, symbol, side, order_type, quantity, price=None, stop_price=None, 
                    time_in_force=None, client_order_id=None, position_side='BOTH', good_till_date=None):
        """調用幣安API下單"""
        endpoint = "/fapi/v1/order"
        headers = {"X-MBX-APIKEY": self.api_key}
        
        # 準備參數
        params = {
            "symbol": symbol,
            "side": side,
            "type": order_type,
            "quantity": quantity,
            "positionSide": position_side,
            "newClientOrderId": client_order_id,
            "timestamp": int(time.time() * 1000)
        }
        
        # 添加可選參數
        if price:
            params["price"] = price
        if stop_price:
            params["stopPrice"] = stop_price
        if time_in_force:
            params["timeInForce"] = time_in_force
        if good_till_date:
            params["goodTillDate"] = good_till_date
        
        # 簽名
        params = self._sign_request(params)
        
        # 發送請求
        response = requests.post(f"{self.base_url}{endpoint}", headers=headers, params=params)
        logger.info(f"下單響應: {response.text}")
        
        if response.status_code == 200:
            order_info = response.json()
            return order_info
        else:
            logger.error(f"下單失敗: {response.text}")
            return None
    
    def cancel_order(self, symbol, client_order_id):
        """取消指定的訂單"""
        if not client_order_id:
            return None
        
        endpoint = "/fapi/v1/order"
        headers = {"X-MBX-APIKEY": self.api_key}
        
        params = {
            "symbol": symbol,
            "origClientOrderId": client_order_id,
            "timestamp": int(time.time() * 1000)
        }
        
        # 簽名
        params = self._sign_request(params)
        
        # 發送請求
        response = requests.delete(f"{self.base_url}{endpoint}", headers=headers, params=params)
        logger.info(f"取消訂單響應: {response.text}")
        
        if response.status_code == 200:
            order_info = response.json()
            return order_info
        else:
            logger.error(f"取消訂單失敗: {response.text}")
            return None

# 創建全局客戶端實例
binance_client = BinanceClient()