"""
倉位管理模組
包含倉位計算、平均成本計算等功能
=============================================================================
"""
import logging
from api.binance_client import binance_client

# 設置logger
logger = logging.getLogger(__name__)

class PositionManager:
    """倉位管理類"""
    
    def __init__(self):
        pass
    
    def calculate_average_cost_and_quantity(self, symbol, new_price, new_quantity):
        """
        計算加倉後的平均成本和總數量
        
        Args:
            symbol: 交易對
            new_price: 新加倉價格
            new_quantity: 新加倉數量
            
        Returns:
            tuple: (平均成本, 總數量, 是否成功)
        """
        try:
            # 獲取當前持倉信息
            current_positions = binance_client.get_current_positions()
            
            if symbol not in current_positions:
                logger.warning(f"計算平均成本時未找到 {symbol} 的現有持倉")
                return float(new_price), float(new_quantity), False
            
            current_position = current_positions[symbol]
            current_quantity = abs(float(current_position['positionAmt']))  # 取絕對值
            current_avg_price = float(current_position['entryPrice'])
            
            # 計算新的總數量
            total_quantity = current_quantity + float(new_quantity)
            
            # 計算加權平均成本
            total_cost = (current_quantity * current_avg_price) + (float(new_quantity) * float(new_price))
            average_cost = total_cost / total_quantity
            
            logger.info(f"平均成本計算 - {symbol}:")
            logger.info(f"  原持倉: {current_quantity} @ {current_avg_price}")
            logger.info(f"  新加倉: {new_quantity} @ {new_price}")
            logger.info(f"  總持倉: {total_quantity}")
            logger.info(f"  平均成本: {average_cost}")
            
            return average_cost, total_quantity, True
            
        except Exception as e:
            logger.error(f"計算平均成本時出錯: {str(e)}")
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
        is_same = current_side == new_direction
        
        return is_same, current_side
    
    def calculate_position_summary(self):
        """計算持倉摘要信息"""
        try:
            current_positions = self.get_current_positions()
            
            summary = {
                'total_positions': len(current_positions),
                'long_positions': 0,
                'short_positions': 0,
                'total_unrealized_pnl': 0.0,
                'positions_detail': {}
            }
            
            for symbol, position in current_positions.items():
                side = position['side']
                unrealized_pnl = position['unRealizedProfit']
                
                if side == 'LONG':
                    summary['long_positions'] += 1
                elif side == 'SHORT':
                    summary['short_positions'] += 1
                
                summary['total_unrealized_pnl'] += unrealized_pnl
                
                summary['positions_detail'][symbol] = {
                    'side': side,
                    'amount': position['positionAmt'],
                    'entry_price': position['entryPrice'],
                    'mark_price': position['markPrice'],
                    'unrealized_pnl': unrealized_pnl
                }
            
            summary['total_unrealized_pnl'] = round(summary['total_unrealized_pnl'], 4)
            
            return summary
            
        except Exception as e:
            logger.error(f"計算持倉摘要時出錯: {str(e)}")
            return {
                'total_positions': 0,
                'long_positions': 0,
                'short_positions': 0,
                'total_unrealized_pnl': 0.0,
                'positions_detail': {}
            }

# 創建全局倉位管理器實例
position_manager = PositionManager()
