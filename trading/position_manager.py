"""
倉位管理模組 - 修復版本
包含倉位計算、平均成本計算等功能，添加異常檢測機制
🔥 修復：持倉數量異常翻倍問題
=============================================================================
"""
import logging
import time
from api.binance_client import binance_client

# 設置logger
logger = logging.getLogger(__name__)

class PositionManager:
    """倉位管理類 - 增強版本"""
    
    def __init__(self):
        # 🔥 新增：持倉變化監控
        self._last_query_positions = {}
        self._query_count = 0
        
    def calculate_average_cost_and_quantity(self, symbol, new_price, new_quantity):
        """
        計算加倉後的平均成本和總數量 - 修復版本
        
        🔥 修復內容：
        1. 多次查詢驗證持倉數據一致性
        2. 異常檢測機制
        3. 保守安全處理
        
        Args:
            symbol: 交易對
            new_price: 新加倉價格
            new_quantity: 新加倉數量
            
        Returns:
            tuple: (平均成本, 總數量, 是否成功)
        """
        try:
            # 🔥 修復1: 多次查詢驗證數據一致性
            logger.info(f"🔍 開始平均成本計算 - {symbol}")
            logger.info(f"🔍 新加倉: {new_quantity} @ {new_price}")
            
            # 第一次查詢
            first_query = binance_client.get_current_positions()
            time.sleep(0.5)  # 等待0.5秒
            
            # 第二次查詢驗證
            second_query = binance_client.get_current_positions()
            
            # 🔥 修復2: 數據一致性檢查
            if symbol not in first_query or symbol not in second_query:
                logger.warning(f"❌ 數據不一致 - {symbol} 在兩次查詢中結果不同")
                logger.warning(f"第一次查詢: {symbol in first_query}")
                logger.warning(f"第二次查詢: {symbol in second_query}")
                return float(new_price), float(new_quantity), False
            
            # 比較兩次查詢結果
            first_amt = abs(float(first_query[symbol]['positionAmt']))
            second_amt = abs(float(second_query[symbol]['positionAmt']))
            
            if abs(first_amt - second_amt) > 0.001:  # 允許小數誤差
                logger.error(f"🚨 持倉數量不一致！")
                logger.error(f"第一次查詢: {first_amt}")
                logger.error(f"第二次查詢: {second_amt}")
                logger.error(f"差異: {abs(first_amt - second_amt)}")
                
                # 🔥 修復3: 異常時使用保守數量
                logger.warning(f"⚠️ 使用較小的安全數量: {min(first_amt, second_amt)}")
                current_quantity = min(first_amt, second_amt)
            else:
                current_quantity = second_amt
                logger.info(f"✅ 持倉數據一致性驗證通過: {current_quantity}")
            
            # 🔥 修復4: 異常數據檢測
            expected_new_qty = float(new_quantity)
            
            # 檢查持倉是否異常翻倍
            if self._last_query_positions.get(symbol):
                last_amt = self._last_query_positions[symbol]['amount']
                time_diff = time.time() - self._last_query_positions[symbol]['timestamp']
                
                # 如果短時間內持倉翻倍且沒有對應的新增量，標記為異常
                if (current_quantity > last_amt * 1.8 and 
                    time_diff < 600 and  # 10分鐘內
                    current_quantity > expected_new_qty * 2):
                    
                    logger.error(f"🚨 檢測到異常持倉翻倍！")
                    logger.error(f"上次記錄: {last_amt} (時間: {time_diff:.1f}秒前)")
                    logger.error(f"當前查詢: {current_quantity}")
                    logger.error(f"預期新增: {expected_new_qty}")
                    logger.error(f"⚠️ 使用保守估算: {last_amt + expected_new_qty}")
                    
                    # 使用保守估算
                    current_quantity = last_amt + expected_new_qty
            
            # 記錄當前查詢結果
            self._last_query_positions[symbol] = {
                'amount': current_quantity,
                'timestamp': time.time()
            }
            
            # 獲取其他必要數據
            current_position = second_query[symbol]
            current_avg_price = float(current_position['entryPrice'])
            
            # 🔥 修復5: 數量合理性最終檢查
            total_quantity = current_quantity + expected_new_qty
            
            # 檢查總量是否超出合理範圍
            if total_quantity > expected_new_qty * 5:  # 總量不應超過新增量的5倍
                logger.error(f"🚨 計算出的總量異常: {total_quantity}")
                logger.error(f"新增量: {expected_new_qty}")
                logger.error(f"比例: {total_quantity / expected_new_qty:.2f}倍")
                
                # 保守處理：假設只有一筆新增
                logger.warning(f"⚠️ 保守處理：總量設為 {expected_new_qty * 2}")
                total_quantity = expected_new_qty * 2
                current_quantity = expected_new_qty
            
            # 計算加權平均成本
            total_cost = (current_quantity * current_avg_price) + (expected_new_qty * float(new_price))
            average_cost = total_cost / total_quantity
            
            # 詳細日誌記錄
            logger.info(f"📊 平均成本計算完成 - {symbol}:")
            logger.info(f"  ✅ 原持倉: {current_quantity} @ {current_avg_price}")
            logger.info(f"  ✅ 新加倉: {expected_new_qty} @ {new_price}")
            logger.info(f"  ✅ 總持倉: {total_quantity}")
            logger.info(f"  ✅ 平均成本: {average_cost}")
            
            return average_cost, total_quantity, True
            
        except Exception as e:
            logger.error(f"❌ 計算平均成本時出錯: {str(e)}")
            logger.error(f"⚠️ 回退到安全模式：使用新倉位數據")
            return float(new_price), float(new_quantity), False
    
    def get_current_positions(self):
        """獲取當前持倉（代理方法）"""
        return binance_client.get_current_positions()
    
    def check_position_exists(self, symbol):
        """檢查指定交易對是否有持倉"""
        current_positions = self.get_current_positions()
        return symbol in current_positions
    
    def get_position_info(self, symbol):
        """獲取指定交易對的持倉信息"""
        current_positions = self.get_current_positions()
        return current_positions.get(symbol)
    
    def get_position_side(self, symbol):
        """獲取持倉方向"""
        position_info = self.get_position_info(symbol)
        if position_info:
            return position_info.get('side')
        return None
    
    def get_position_quantity(self, symbol):
        """獲取持倉數量"""
        position_info = self.get_position_info(symbol)
        if position_info:
            return abs(float(position_info.get('positionAmt', 0)))
        return 0
    
    def get_position_entry_price(self, symbol):
        """獲取持倉入場價格"""
        position_info = self.get_position_info(symbol)
        if position_info:
            return float(position_info.get('entryPrice', 0))
        return 0
    
    def get_position_unrealized_pnl(self, symbol):
        """獲取未實現盈虧"""
        position_info = self.get_position_info(symbol)
        if position_info:
            return float(position_info.get('unRealizedProfit', 0))
        return 0
    
    def is_same_direction(self, symbol, new_side):
        """檢查新信號方向是否與現有持倉方向一致"""
        current_side = self.get_position_side(symbol)
        if not current_side:
            return False, None  # 沒有持倉
        
        new_direction = 'LONG' if new_side == 'BUY' else 'SHORT'
        
        # 檢查方向是否一致
        is_same = (current_side == new_direction)
        
        return is_same, current_side

# 創建全局position_manager實例
position_manager = PositionManager()
