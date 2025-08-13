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
from typing import List, Dict, Any
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
            """
            獲取當前所有持倉信息 - 修復版本
            
            🔥 修復內容：
            1. 原始數據記錄
            2. 異常檢測
            3. 持倉變化追蹤
            """
            endpoint = "/fapi/v2/positionRisk"
            headers = {"X-MBX-APIKEY": self.api_key}
            
            params = {
                "timestamp": int(time.time() * 1000)
            }
            
            # 簽名
            params = self._sign_request(params)
            
            try:
                response = requests.get(f"{self.base_url}{endpoint}", headers=headers, params=params)
                
                if response.status_code == 200:
                    positions = response.json()
                    active_positions = {}
                    zero_positions_count = 0
                    
                    # 🔥 修復1: 記錄原始API數據（僅活躍持倉）
                    raw_data_log = []
                    
                    for position in positions:
                        symbol = position.get('symbol')
                        position_amt = float(position.get('positionAmt', 0))
                        
                        if position_amt != 0:
                            # 🔥 修復2: 記錄原始數據用於調試
                            raw_data = {
                                'symbol': symbol,
                                'positionAmt': position_amt,
                                'entryPrice': position.get('entryPrice'),
                                'markPrice': position.get('markPrice'),
                                'unRealizedProfit': position.get('unRealizedProfit')
                            }
                            raw_data_log.append(raw_data)
                            
                            # 處理持倉數據
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
                    
                    # 🔥 修復3: 詳細日誌記錄
                    if active_positions:
                        logger.info(f"🔍 持倉查詢完成 - 活躍: {len(active_positions)}個, 零持倉: {zero_positions_count}個")
                        
                        # 🔥 修復4: 持倉變化檢測
                        if hasattr(self, '_last_positions'):
                            for symbol, current_pos in active_positions.items():
                                if symbol in self._last_positions:
                                    old_amt = self._last_positions[symbol]['positionAmt']
                                    new_amt = current_pos['positionAmt']
                                    
                                    if abs(abs(old_amt) - abs(new_amt)) > 0.001:
                                        change = abs(new_amt) - abs(old_amt)
                                        logger.info(f"📊 {symbol} 持倉變化: {abs(old_amt)} → {abs(new_amt)} (變化: {change:+.4f})")
                                        
                                        # 🔥 修復5: 異常變化檢測
                                        if abs(new_amt) > abs(old_amt) * 2:
                                            logger.warning(f"⚠️ {symbol} 持倉異常增長！可能存在問題")
                                else:
                                    logger.info(f"📊 {symbol} 新增持倉: {abs(current_pos['positionAmt'])}")
                        
                        # 記錄當前持倉用於下次對比
                        self._last_positions = active_positions.copy()
                        
                        # 顯示持倉摘要
                        for symbol, pos in active_positions.items():
                            logger.info(f"  {symbol}: {pos['side']} {abs(pos['positionAmt'])}, 盈虧: {pos['unRealizedProfit']:.4f}")
                            
                        # 🔥 修復6: 調試模式下記錄原始數據
                        if logger.getEffectiveLevel() <= logging.DEBUG:
                            logger.debug(f"🔍 原始API數據: {raw_data_log}")
                    else:
                        logger.info(f"🔍 持倉查詢完成 - 無活躍持倉")
                        
                    return active_positions
                else:
                    logger.error(f"❌ 查詢持倉失敗 - 狀態碼: {response.status_code}")
                    logger.error(f"❌ 錯誤詳情: {response.text[:200]}...")
                    return {}
            except Exception as e:
                logger.error(f"❌ 查詢持倉出錯: {str(e)}")
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

    def cancel_order_by_client_id(self, client_order_id):
        """
        按client_order_id取消訂單（不需要symbol）
        
        Args:
            client_order_id: 客戶訂單ID
            
        Returns:
            dict: 取消結果
        """
        try:
            # 使用新的符號提取函數
            from utils.helpers import extract_symbol_from_order_id
            
            symbol = extract_symbol_from_order_id(client_order_id)
            if not symbol:
                logger.error(f"無法從訂單ID提取交易對: {client_order_id}")
                return None
            
            # 呼叫原有的取消方法
            return self.cancel_order(symbol, client_order_id)
            
        except Exception as e:
            logger.error(f"按client_id取消訂單失敗: {client_order_id} - {str(e)}")
            return None

    def get_order_by_client_id(self, client_order_id):
        """
        按client_order_id查詢訂單
        
        Args:
            client_order_id: 客戶訂單ID
            
        Returns:
            dict: 訂單資訊
        """
        try:
            # 使用新的符號提取函數
            from utils.helpers import extract_symbol_from_order_id
            
            symbol = extract_symbol_from_order_id(client_order_id)
            if not symbol:
                logger.error(f"無法從訂單ID提取交易對: {client_order_id}")
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
            response = requests.get(f"{self.base_url}{endpoint}", headers=headers, params=params)
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"查詢訂單失敗: {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"按client_id查詢訂單失敗: {client_order_id} - {str(e)}")
            return None

    def get_all_open_orders(self, symbol: str = None) -> List[Dict[str, Any]]:
        """
        獲取所有開放的訂單
        
        Args:
            symbol: 可選，指定交易對
            
        Returns:
            List[Dict]: 開放訂單列表
        """
        try:
            timestamp = int(time.time() * 1000)
            params = {
                'timestamp': timestamp
            }
            
            if symbol:
                params['symbol'] = symbol.upper()
            
            query_string = '&'.join([f"{k}={v}" for k, v in params.items()])
            signature = self._sign_request(query_string)
            params['signature'] = signature
            
            response = requests.get(
                f"{self.base_url}/fapi/v1/openOrders",
                params=params,
                headers={'X-MBX-APIKEY': self.api_key}
            )
            
            if response.status_code == 200:
                try:
                    orders = response.json()
                    # 驗證返回數據格式
                    if isinstance(orders, list):
                        logger.debug(f"獲取開放訂單成功: {len(orders)} 筆")
                        return orders
                    else:
                        logger.error(f"API返回格式異常: {type(orders)} - {orders}")
                        return []
                except (ValueError, TypeError) as json_error:
                    logger.error(f"JSON解析失敗: {json_error} - Response: {response.text[:200]}")
                    return []
            else:
                logger.error(f"獲取開放訂單失敗: {response.status_code} - {response.text}")
                return []
                
        except Exception as e:
            logger.error(f"獲取開放訂單時出錯: {str(e)}")
            logger.error(f"請求URL: {params}")
            return []

# 創建全局客戶端實例
binance_client = BinanceClient()

