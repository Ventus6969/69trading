"""
訂單管理模組
包含所有訂單相關操作，保持與原程式完全相同的邏輯
=============================================================================
"""
import time
import logging
import traceback
from datetime import datetime
from api.binance_client import binance_client
from trading.position_manager import position_manager
from utils.helpers import get_symbol_precision
from config.settings import (
    MIN_TP_PROFIT_PERCENTAGE, TP_PERCENTAGE, 
    STOP_LOSS_PERCENTAGE, ENABLE_STOP_LOSS,
    DEFAULT_TP_MULTIPLIER
)

# 設置logger
logger = logging.getLogger(__name__)

class OrderManager:
    """訂單管理類"""
    
    def __init__(self):
        # 用於存儲訂單信息的字典
        # 格式: {client_order_id: {order_info, status, filled_amount, entry_time, tp_placed}}
        self.orders = {}
        # 訂單ID計數器
        self.order_counter = 1
        
    def create_order(self, symbol, side, order_type, quantity, price=None, **kwargs):
        """
        創建訂單
        
        Args:
            symbol: 交易對
            side: 買賣方向
            order_type: 訂單類型
            quantity: 數量
            price: 價格
            **kwargs: 其他參數
            
        Returns:
            dict: 訂單信息
        """
        try:
            # 準備下單參數
            order_params = {
                "symbol": symbol,
                "side": side,
                "order_type": order_type,
                "quantity": quantity,
                "position_side": kwargs.get('position_side', 'BOTH'),
                "client_order_id": kwargs.get('client_order_id')
            }
            
            # 添加可選參數
            if price:
                order_params["price"] = price
            if kwargs.get('stop_price'):
                order_params["stop_price"] = kwargs.get('stop_price')
            if kwargs.get('time_in_force'):
                order_params["time_in_force"] = kwargs.get('time_in_force')
            if kwargs.get('good_till_date'):
                order_params["good_till_date"] = kwargs.get('good_till_date')
            
            # 執行下單
            order_result = binance_client.place_order(**order_params)
            
            # 檢查是否有等待API響應的臨時訂單記錄
            client_order_id = kwargs.get('client_order_id')
            if order_result and client_order_id in self.orders and self.orders[client_order_id].get('waiting_for_api_response', False):
                logger.info(f"API響應已返回，更新訂單 {client_order_id} 的完整信息")
                
                # 嘗試從最近的webhook數據恢復ATR信息
                self._try_recover_webhook_data_for_api_response(client_order_id, symbol, side, price, quantity)
            
            return order_result
            
        except Exception as e:
            logger.error(f"創建訂單時出錯: {str(e)}")
            logger.error(traceback.format_exc())
            return None
    
    def _try_recover_webhook_data_for_api_response(self, client_order_id, symbol, side, price, quantity):
        """為API響應恢復webhook數據"""
        try:
            # 這裡需要獲取最近的webhook數據
            # 由於模組分離，我們暫時使用保守設置
            # 在實際使用中，可以通過signal_processor獲取
            
            # 檢查訂單是否已經被填充，且尚未設置止盈單
            if self.orders[client_order_id].get('status') == 'FILLED' and not self.orders[client_order_id].get('tp_placed', False):
                logger.info(f"重新設置訂單 {client_order_id} 的止盈單")
                
                # 檢查是否為加倉操作
                current_positions_check = binance_client.get_current_positions()
                is_add_position_check = symbol in current_positions_check
                
                # 準備下止盈單
                entry_order = {
                    'symbol': symbol,
                    'side': side,
                    'quantity': quantity,
                    'price': float(price) if price else 0,
                    'client_order_id': client_order_id,
                    'position_side': 'BOTH'
                }
                
                # 如果有存儲的ATR值，加入
                if 'atr' in self.orders[client_order_id]:
                    entry_order['atr'] = self.orders[client_order_id]['atr']
                if 'tp_price_offset' in self.orders[client_order_id]:
                    entry_order['tp_price_offset'] = self.orders[client_order_id]['tp_price_offset']
                
                # 如果已經下過止盈單，先取消它
                if self.orders[client_order_id].get('tp_client_id'):
                    logger.info(f"取消之前使用默認比例下的止盈單")
                    binance_client.cancel_order(symbol, self.orders[client_order_id].get('tp_client_id'))
                
                # 重新設置止盈狀態
                self.orders[client_order_id]['tp_placed'] = False
                self.orders[client_order_id]['waiting_for_api_response'] = False
                
                # 下新的止盈單
                self.place_tp_order(entry_order, is_add_position_check)
                
        except Exception as e:
            logger.error(f"恢復API響應webhook數據時出錯: {str(e)}")
    
    def save_order_info(self, client_order_id, order_data):
        """保存訂單信息到本地記錄"""
        self.orders[client_order_id] = order_data
        logger.info(f"已保存訂單信息: {client_order_id}")
    
    def update_order_status(self, client_order_id, status, filled_amount=None):
        """更新訂單狀態"""
        if client_order_id in self.orders:
            self.orders[client_order_id]['status'] = status
            if filled_amount:
                self.orders[client_order_id]['filled_amount'] = filled_amount
    
    def handle_order_filled(self, client_order_id, symbol, side, order_type, price, 
                          quantity, executed_qty, position_side, is_add_position):
        """處理訂單成交事件"""
        try:
            # 檢查訂單是否已在本地記錄中
            if client_order_id in self.orders:
                # 如果已經在orders中且尚未下止盈單
                if not self.orders[client_order_id].get('tp_placed', False):
                    logger.info(f"入場訂單 {client_order_id} 已成交，準備下止盈單")
                    
                    # 更新訂單信息
                    self.orders[client_order_id].update({
                        'status': 'FILLED',
                        'filled_amount': executed_qty,
                        'fill_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        'is_add_position': is_add_position
                    })
                    
                    # 構造入場訂單信息，準備下止盈單
                    entry_order = {
                        'symbol': symbol,
                        'side': side,
                        'quantity': quantity,
                        'price': price,
                        'client_order_id': client_order_id,
                        'position_side': position_side
                    }
                    
                    # 如果存在自定義止盈偏移量，也加入
                    if client_order_id in self.orders:
                        entry_order['tp_price_offset'] = self.orders[client_order_id].get('tp_price_offset', None)
                        entry_order['atr'] = self.orders[client_order_id].get('atr')
                    
                    # 下止盈單
                    self.place_tp_order(entry_order, is_add_position)
            else:
                # === 處理WebSocket比API響應更快的情況 ===
                logger.warning(f"收到訂單 {client_order_id} 成交通知，但訂單未在本地記錄中找到，將創建臨時記錄")
                
                # 創建臨時訂單記錄
                self.orders[client_order_id] = {
                    'symbol': symbol,
                    'side': side,
                    'quantity': quantity,
                    'price': price,
                    'type': order_type,
                    'status': 'FILLED',
                    'entry_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'tp_placed': False,
                    'waiting_for_api_response': True,
                    'webhook_time': int(time.time()),
                    'is_add_position': is_add_position
                }
                
                # 嘗試從最近的webhook請求中獲取ATR數據
                self._try_recover_webhook_data(client_order_id, symbol, side, price, 
                                             quantity, position_side, is_add_position)
                
        except Exception as e:
            logger.error(f"處理訂單成交時出錯: {str(e)}")
            logger.error(traceback.format_exc())
    
    def _try_recover_webhook_data(self, client_order_id, symbol, side, price, 
                                quantity, position_side, is_add_position):
        """嘗試從webhook數據恢復ATR信息"""
        try:
            # 嘗試獲取最近的webhook數據
            # 在模組化版本中，這需要通過其他方式獲取
            # 暫時使用保守的止盈設置
            logger.warning(f"無法獲取最近webhook數據，使用保守止盈設置")
            
            # 使用保守的止盈設置
            conservative_tp_offset = float(price) * 0.02 if price else 100  # 2%或100點
            
            # 準備下止盈單
            entry_order = {
                'symbol': symbol,
                'side': side,
                'quantity': quantity,
                'price': price,
                'client_order_id': client_order_id,
                'position_side': position_side,
                'tp_price_offset': conservative_tp_offset
            }
            
            self.place_tp_order(entry_order, is_add_position)
            
        except Exception as e:
            logger.error(f"恢復webhook數據時出錯: {str(e)}")
    
    def place_tp_order(self, entry_order, is_add_position=False):
        """
        根據入場單信息下止盈單（加倉時使用平均成本計算）
        
        Args:
            entry_order: 入場訂單信息
            is_add_position: 是否為加倉操作
        """
        try:
            symbol = entry_order['symbol']
            side = entry_order['side']
            quantity = entry_order['quantity']
            entry_price = float(entry_order['price'])
            position_side = entry_order.get('position_side', 'BOTH')
            original_client_id = entry_order['client_order_id']
            
            # 獲取交易對的價格精度
            precision = get_symbol_precision(symbol)
            
            # 確定用於計算止盈的基準價格
            calculation_price = entry_price
            actual_quantity = quantity
            
            if is_add_position:
                # 如果是加倉，計算平均成本
                avg_cost, total_qty, success = position_manager.calculate_average_cost_and_quantity(
                    symbol, entry_price, quantity)
                
                if success:
                    calculation_price = avg_cost
                    actual_quantity = total_qty
                    logger.info(f"加倉操作 - 使用平均成本 {avg_cost} 計算止盈，總持倉量: {total_qty}")
                else:
                    logger.warning(f"加倉操作 - 平均成本計算失敗，使用新倉位價格 {entry_price}")
            else:
                logger.info(f"新開倉操作 - 使用入場價格 {entry_price} 計算止盈")
            
            # 計算止盈價格偏移量
            tp_price_offset = self._calculate_tp_offset(entry_order, calculation_price)
            
            # 檢查最小獲利保護
            min_tp_offset = calculation_price * MIN_TP_PROFIT_PERCENTAGE
            if tp_price_offset < min_tp_offset:
                logger.info(f"止盈偏移量 {tp_price_offset} 小於最小獲利要求 {min_tp_offset} (0.5%)，調整為最小值")
                tp_price_offset = min_tp_offset
            else:
                logger.info(f"止盈偏移量 {tp_price_offset} 滿足最小獲利要求 {min_tp_offset} (0.5%)")
            
            # 計算止盈價格
            if side == 'BUY':
                tp_price = round(calculation_price + tp_price_offset, precision)
                tp_side = 'SELL'
            else:  # SELL
                tp_price = round(calculation_price - tp_price_offset, precision)
                tp_side = 'BUY'
            
            logger.info(f"訂單 {original_client_id} 止盈設置:")
            logger.info(f"  計算基準價: {calculation_price} ({'平均成本' if is_add_position else '入場價'})")
            logger.info(f"  偏移量: +/-{tp_price_offset}")
            logger.info(f"  止盈價: {tp_price}")
            logger.info(f"  總持倉量: {actual_quantity}")
            logger.info(f"  精度: {precision}")
            
            # 生成止盈訂單ID
            tp_client_id = self._generate_tp_order_id(original_client_id)
            
            # 下止盈單 (限價單)
            tp_order_result = binance_client.place_order(
                symbol=symbol,
                side=tp_side,
                order_type='LIMIT',
                quantity=str(actual_quantity),
                price=tp_price,
                time_in_force='GTC',
                client_order_id=tp_client_id,
                position_side=position_side
            )
            
            # 更新訂單狀態
            if original_client_id in self.orders:
                self.orders[original_client_id]['tp_placed'] = (tp_order_result is not None)
                
                if tp_order_result is not None:
                    self.orders[original_client_id]['tp_client_id'] = tp_client_id
                    self.orders[original_client_id]['tp_price'] = tp_price
                    self.orders[original_client_id]['calculation_price'] = calculation_price
                    self.orders[original_client_id]['is_add_position'] = is_add_position
                    self.orders[original_client_id]['total_quantity'] = actual_quantity
                
                self.orders[original_client_id]['actual_tp_offset'] = tp_price_offset
                
            logger.info(f"已為訂單 {original_client_id} 下達止盈單 - 止盈價: {tp_price}, 數量: {actual_quantity}")
            
            # 如果啟用止損功能，同時下止損單
            if ENABLE_STOP_LOSS:
                self.place_sl_order(entry_order, calculation_price, actual_quantity, is_add_position)
            
        except Exception as e:
            logger.error(f"下止盈單時出錯: {str(e)}")
            logger.error(traceback.format_exc())
    
    def _calculate_tp_offset(self, entry_order, calculation_price):
        """計算止盈價格偏移量"""
        tp_price_offset = None
        
        # 優先使用預設的價格偏移量
        if 'tp_price_offset' in entry_order and entry_order['tp_price_offset'] is not None:
            tp_price_offset = entry_order['tp_price_offset']
            logger.info(f"使用預先計算的止盈偏移量: {tp_price_offset}")
        else:
            # 嘗試用ATR計算
            atr_value = entry_order.get('atr')
            if atr_value and str(atr_value).replace('.', '', 1).isdigit():
                try:
                    atr_value_float = float(atr_value)
                    tp_multiplier = entry_order.get('tp_multiplier', DEFAULT_TP_MULTIPLIER)
                    tp_price_offset = atr_value_float * tp_multiplier
                    logger.info(f"使用ATR計算止盈偏移量 - ATR: {atr_value_float}, 倍數: {tp_multiplier}, 偏移量: {tp_price_offset}")
                except Exception as e:
                    logger.error(f"計算ATR止盈偏移量時出錯: {str(e)}")
            
            # 如果還是沒有偏移量，使用默認百分比
            if tp_price_offset is None:
                tp_price_offset = calculation_price * TP_PERCENTAGE
                logger.info(f"使用默認百分比計算止盈偏移量: {tp_price_offset}")
        
        return tp_price_offset
    
    def place_sl_order(self, entry_order, calculation_price=None, actual_quantity=None, is_add_position=False):
        """
        根據入場單信息下止損單（使用平均成本計算）
        
        Args:
            entry_order: 入場訂單信息
            calculation_price: 計算基準價格（平均成本或入場價）
            actual_quantity: 實際持倉數量
            is_add_position: 是否為加倉操作
        """
        try:
            symbol = entry_order['symbol']
            side = entry_order['side']
            quantity = entry_order['quantity']
            entry_price = float(entry_order['price'])
            position_side = entry_order.get('position_side', 'BOTH')
            original_client_id = entry_order['client_order_id']
            
            if calculation_price is None:
                calculation_price = entry_price
            if actual_quantity is None:
                actual_quantity = quantity
            
            precision = get_symbol_precision(symbol)
            sl_price_offset = calculation_price * STOP_LOSS_PERCENTAGE
            
            if side == 'BUY':
                sl_price = round(calculation_price - sl_price_offset, precision)
                sl_side = 'SELL'
            else:
                sl_price = round(calculation_price + sl_price_offset, precision)
                sl_side = 'BUY'
            
            logger.info(f"訂單 {original_client_id} 止損設置:")
            logger.info(f"  計算基準價: {calculation_price} ({'平均成本' if is_add_position else '入場價'})")
            logger.info(f"  止損百分比: {STOP_LOSS_PERCENTAGE:.1%}")
            logger.info(f"  止損價: {sl_price}")
            logger.info(f"  總持倉量: {actual_quantity}")
            logger.info(f"  精度: {precision}")
            
            sl_client_id = self._generate_sl_order_id(original_client_id)
            
            sl_order_result = binance_client.place_order(
                symbol=symbol,
                side=sl_side,
                order_type='STOP_MARKET',
                quantity=str(actual_quantity),
                stop_price=sl_price,
                time_in_force='GTC',
                client_order_id=sl_client_id,
                position_side=position_side
            )
            
            if original_client_id in self.orders:
                self.orders[original_client_id]['sl_placed'] = (sl_order_result is not None)
                if sl_order_result is not None:
                    self.orders[original_client_id]['sl_client_id'] = sl_client_id
                    self.orders[original_client_id]['sl_price'] = sl_price
                self.orders[original_client_id]['actual_sl_offset'] = sl_price_offset
                
            logger.info(f"已為訂單 {original_client_id} 下達止損單 - 止損價: {sl_price}, 數量: {actual_quantity}")
            
        except Exception as e:
            logger.error(f"下止損單時出錯: {str(e)}")
            logger.error(traceback.format_exc())
    
    def _generate_tp_order_id(self, original_client_id):
        """生成止盈訂單ID"""
        base_id_len = len(original_client_id)
        if base_id_len > 32:
            short_id = original_client_id[:20] + str(int(time.time()) % 1000)
            return f"{short_id}T"
        else:
            return f"{original_client_id}T"
    
    def _generate_sl_order_id(self, original_client_id):
        """生成止損訂單ID"""
        base_id_len = len(original_client_id)
        if base_id_len > 32:
            short_id = original_client_id[:20] + str(int(time.time()) % 1000)
            return f"{short_id}S"
        else:
            return f"{original_client_id}S"
    
    def cancel_existing_tp_orders_for_symbol(self, symbol):
        """取消指定交易對所有現存的止盈單"""
        cancelled_count = 0
        
        for order_id, order_info in self.orders.items():
            if order_info.get('symbol') == symbol:
                tp_client_id = order_info.get('tp_client_id')
                if tp_client_id:
                    logger.info(f"取消現存止盈單: {tp_client_id}")
                    cancel_result = binance_client.cancel_order(symbol, tp_client_id)
                    if cancel_result:
                        cancelled_count += 1
                        order_info['tp_placed'] = False
                        order_info['tp_client_id'] = None
        
        logger.info(f"已取消 {symbol} 的 {cancelled_count} 個止盈單")
        return cancelled_count
    
    def cancel_existing_sl_orders_for_symbol(self, symbol):
        """取消指定交易對所有現存的止損單"""
        cancelled_count = 0
        
        for order_id, order_info in self.orders.items():
            if order_info.get('symbol') == symbol:
                sl_client_id = order_info.get('sl_client_id')
                if sl_client_id:
                    logger.info(f"取消現存止損單: {sl_client_id}")
                    cancel_result = binance_client.cancel_order(symbol, sl_client_id)
                    if cancel_result:
                        cancelled_count += 1
                        order_info['sl_placed'] = False
                        order_info['sl_client_id'] = None
        
        logger.info(f"已取消 {symbol} 的 {cancelled_count} 個止損單")
        return cancelled_count
    
    def handle_tp_filled(self, tp_client_order_id):
        """處理止盈單成交"""
        for order_id, order_info in self.orders.items():
            if order_info.get('tp_client_id') == tp_client_order_id:
                self.orders[order_id]['status'] = 'TP_FILLED'
                logger.info(f"原始訂單 {order_id} 已通過止盈完成")
                break
    
    def handle_sl_filled(self, sl_client_order_id):
        """處理止損單成交"""
        for order_id, order_info in self.orders.items():
            if order_info.get('sl_client_id') == sl_client_order_id:
                self.orders[order_id]['status'] = 'SL_FILLED'
                logger.info(f"原始訂單 {order_id} 已通過止損完成")
                break
    
    def get_orders(self):
        """獲取所有訂單"""
        return self.orders
    
    def get_order(self, client_order_id):
        """獲取特定訂單"""
        return self.orders.get(client_order_id)
    
    def set_webhook_data_recovery_callback(self, callback):
        """設置webhook數據恢復回調函數"""
        self.webhook_data_recovery_callback = callback

# 創建全局訂單管理器實例
order_manager = OrderManager()