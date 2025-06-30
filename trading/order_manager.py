"""
訂單管理模組
包含所有訂單相關操作，修正重複處理和止盈邏輯問題
🔥 修正版本：添加trading_results記錄功能
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
        # 🔥 新增：處理狀態追蹤，避免重複處理
        self.processing_orders = set()
        
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
                
                # 🔥 修正：不再自動重新設置止盈，由WebSocket統一處理
                self.orders[client_order_id]['waiting_for_api_response'] = False
                logger.info(f"訂單 {client_order_id} API響應完成，等待WebSocket處理止盈")
            
            return order_result
            
        except Exception as e:
            logger.error(f"創建訂單時出錯: {str(e)}")
            logger.error(traceback.format_exc())
            return None
    
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
        """處理訂單成交事件 - 修正版本：添加重複處理保護"""
        try:
            # 🔥 新增：防止重複處理
            if client_order_id in self.processing_orders:
                logger.info(f"訂單 {client_order_id} 正在處理中，跳過重複處理")
                return
                
            # 添加到處理中集合
            self.processing_orders.add(client_order_id)
            
            try:
                # 檢查訂單是否已在本地記錄中
                if client_order_id in self.orders:
                    current_status = self.orders[client_order_id].get('status')
                    tp_placed = self.orders[client_order_id].get('tp_placed', False)
                    
                    # 🔥 新增：重複處理檢查
                    if current_status == 'FILLED' and tp_placed:
                        logger.info(f"訂單 {client_order_id} 已經處理過成交和止盈設置，跳過重複處理")
                        return
                        
                    # 如果只是更新狀態但還沒設置止盈，繼續處理
                    if current_status == 'FILLED' and not tp_placed:
                        logger.info(f"訂單 {client_order_id} 狀態已更新為FILLED，開始設置止盈止損")
                    else:
                        logger.info(f"訂單 {client_order_id} 首次處理成交事件")
                    
                    # 更新訂單信息
                    self.orders[client_order_id].update({
                        'status': 'FILLED',
                        'filled_amount': executed_qty,
                        'fill_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        'actual_fill_price': price,
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
                        entry_order['tp_multiplier'] = self.orders[client_order_id].get('tp_multiplier')
                    
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
                    
                    # 🔥 修正：使用保守的止盈設置，不依賴webhook數據
                    self._handle_early_websocket_fill(client_order_id, symbol, side, price, 
                                                     quantity, position_side, is_add_position)
            finally:
                # 無論如何都要移除處理標記
                self.processing_orders.discard(client_order_id)
                
        except Exception as e:
            logger.error(f"處理訂單成交時出錯: {str(e)}")
            logger.error(traceback.format_exc())
            # 確保移除處理標記
            self.processing_orders.discard(client_order_id)
    
    def _handle_early_websocket_fill(self, client_order_id, symbol, side, price, 
                                   quantity, position_side, is_add_position):
        """處理WebSocket提前收到的成交通知"""
        try:
            logger.info(f"處理提前到達的WebSocket成交通知: {client_order_id}")
            
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
            logger.error(f"處理提前WebSocket成交通知時出錯: {str(e)}")
    
    def place_tp_order(self, entry_order, is_add_position=False):
        """
        根據入場單信息下止盈單（修正版本：避免重複下單和加倉誤判）
        
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
            
            # 🔥 新增：檢查是否已經有止盈單
            if original_client_id in self.orders:
                if self.orders[original_client_id].get('tp_placed'):
                    logger.info(f"訂單 {original_client_id} 已經設置過止盈單，跳過重複設置")
                    return
                    
                # 檢查是否有有效的止盈單ID
                existing_tp_id = self.orders[original_client_id].get('tp_client_id')
                if existing_tp_id:
                    logger.info(f"訂單 {original_client_id} 已有止盈單 {existing_tp_id}，先取消再重新設置")
                    binance_client.cancel_order(symbol, existing_tp_id)
            
            # 獲取交易對的價格精度
            precision = get_symbol_precision(symbol)
            
            # 確定用於計算止盈的基準價格
            calculation_price = entry_price
            actual_quantity = quantity
            
            # 🔥 修正：更嚴格的加倉判斷
            if is_add_position:
                # 檢查是否真的有現有持倉（排除剛成交的這筆）
                current_positions = binance_client.get_current_positions()
                if symbol in current_positions:
                    current_qty = abs(float(current_positions[symbol]['positionAmt']))
                    expected_qty = float(quantity)
                    
                    # 如果持倉數量大於當前訂單數量，才是真正的加倉
                    if current_qty > expected_qty:
                        avg_cost, total_qty, success = position_manager.calculate_average_cost_and_quantity(
                            symbol, entry_price, quantity)
                        
                        if success:
                            calculation_price = avg_cost
                            actual_quantity = total_qty
                            logger.info(f"確認加倉操作 - 使用平均成本 {avg_cost} 計算止盈，總持倉量: {total_qty}")
                        else:
                            logger.warning(f"加倉操作 - 平均成本計算失敗，使用新倉位價格 {entry_price}")
                            is_add_position = False
                    else:
                        logger.info(f"持倉數量 {current_qty} 等於訂單數量 {expected_qty}，判斷為新開倉，不是加倉")
                        is_add_position = False
                else:
                    logger.info(f"查詢不到 {symbol} 的現有持倉，判斷為新開倉")
                    is_add_position = False
            
            if not is_add_position:
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
            
            # 生成止盈訂單ID（添加時間戳避免重複）
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
                    self.orders[original_client_id]['final_is_add_position'] = is_add_position
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
        根據入場單信息下止損單（修正版本：避免重複ID）
        
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
            
            # 🔥 新增：檢查是否已經有止損單
            if original_client_id in self.orders:
                existing_sl_id = self.orders[original_client_id].get('sl_client_id')
                if existing_sl_id:
                    logger.info(f"訂單 {original_client_id} 已有止損單 {existing_sl_id}，跳過重複設置")
                    return
            
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
            
            # 生成止損訂單ID（添加時間戳避免重複）
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
        """生成止盈訂單ID（添加時間戳避免重複）"""
        timestamp_ms = int(time.time() * 1000) % 10000  # 取最後4位毫秒
        base_id_len = len(original_client_id)
        
        if base_id_len > 26:  # 預留空間給時間戳和T後綴
            short_id = original_client_id[:22] + str(timestamp_ms)
            return f"{short_id}T"
        else:
            return f"{original_client_id}{timestamp_ms}T"
    
    def _generate_sl_order_id(self, original_client_id):
        """生成止損訂單ID（添加時間戳避免重複）"""
        timestamp_ms = int(time.time() * 1000) % 10000  # 取最後4位毫秒
        base_id_len = len(original_client_id)
        
        if base_id_len > 26:  # 預留空間給時間戳和S後綴
            short_id = original_client_id[:22] + str(timestamp_ms)
            return f"{short_id}S"
        else:
            return f"{original_client_id}{timestamp_ms}S"
    
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
    
    # 🔥 關鍵修正：添加trading_results記錄功能
    def handle_tp_filled(self, tp_client_order_id):
        """處理止盈單成交 - 修正版本：記錄trading_results + 取消止損單"""
        for order_id, order_info in self.orders.items():
            if order_info.get('tp_client_id') and tp_client_order_id.startswith(order_info.get('tp_client_id', '')[:20]):
                
                # 🔥 關鍵新增：記錄交易結果到trading_results表
                try:
                    self._record_tp_result(order_info)
                    logger.info(f"✅ 止盈交易結果已記錄: {order_id}")
                except Exception as e:
                    logger.error(f"❌ 記錄止盈結果失敗: {str(e)}")
                
                # 更新訂單狀態（原有邏輯）
                self.orders[order_id]['status'] = 'TP_FILLED'
                
                # 🔥 新增：取消對應的止損單
                sl_client_id = order_info.get('sl_client_id')
                if sl_client_id:
                    symbol = order_info.get('symbol')
                    logger.info(f"止盈單 {tp_client_order_id} 已成交，正在取消對應的止損單 {sl_client_id}")
                    
                    cancel_result = binance_client.cancel_order(symbol, sl_client_id)
                    if cancel_result:
                        logger.info(f"成功取消止損單 {sl_client_id}")
                        # 更新止損單狀態
                        order_info['sl_placed'] = False
                        order_info['sl_cancelled_by_tp'] = True  # 標記是由止盈觸發的取消
                    else:
                        logger.warning(f"取消止損單 {sl_client_id} 失敗，可能已經被取消或成交")
                else:
                    logger.info(f"原始訂單 {order_id} 沒有對應的止損單")
                
                logger.info(f"原始訂單 {order_id} 已通過止盈完成，相關止損單已處理")
                break

    def handle_sl_filled(self, sl_client_order_id):
        """處理止損單成交 - 修正版本：記錄trading_results + 取消止盈單"""
        for order_id, order_info in self.orders.items():
            if order_info.get('sl_client_id') and sl_client_order_id.startswith(order_info.get('sl_client_id', '')[:20]):
                
                # 🔥 關鍵新增：記錄交易結果到trading_results表
                try:
                    self._record_sl_result(order_info)
                    logger.info(f"✅ 止損交易結果已記錄: {order_id}")
                except Exception as e:
                    logger.error(f"❌ 記錄止損結果失敗: {str(e)}")
                
                # 更新訂單狀態（原有邏輯）
                self.orders[order_id]['status'] = 'SL_FILLED'
                
                # 🔥 新增：取消對應的止盈單
                tp_client_id = order_info.get('tp_client_id')
                if tp_client_id:
                    symbol = order_info.get('symbol')
                    logger.info(f"止損單 {sl_client_order_id} 已成交，正在取消對應的止盈單 {tp_client_id}")
                    
                    cancel_result = binance_client.cancel_order(symbol, tp_client_id)
                    if cancel_result:
                        logger.info(f"成功取消止盈單 {tp_client_id}")
                        # 更新止盈單狀態
                        order_info['tp_placed'] = False
                        order_info['tp_cancelled_by_sl'] = True  # 標記是由止損觸發的取消
                    else:
                        logger.warning(f"取消止盈單 {tp_client_id} 失敗，可能已經被取消或成交")
                else:
                    logger.info(f"原始訂單 {order_id} 沒有對應的止盈單")
                
                logger.info(f"原始訂單 {order_id} 已通過止損完成，相關止盈單已處理")
                break
    
    # 🔥 新增：交易結果記錄方法
    def _record_tp_result(self, order_info):
        """記錄止盈結果到trading_results表"""
        try:
            # 計算基本數據
            entry_price = float(order_info.get('price', 0))
            tp_price = float(order_info.get('tp_price', entry_price * 1.01))  # 使用記錄的止盈價
            quantity = float(order_info.get('total_quantity') or order_info.get('quantity', 0))
            side = order_info.get('side')
            entry_time_str = order_info.get('entry_time')
            
            # 計算盈虧
            if side == 'BUY':
                pnl = (tp_price - entry_price) * quantity
            else:  # SELL
                pnl = (entry_price - tp_price) * quantity
            
            # 計算持有時間
            holding_time = self._calculate_holding_time(entry_time_str)
            
            # 準備結果數據
            result_data = {
                'client_order_id': order_info.get('client_order_id'),
                'symbol': order_info.get('symbol'),
                'final_pnl': round(pnl, 4),
                'pnl_percentage': round((pnl / (entry_price * quantity)) * 100, 2),
                'exit_method': 'TP_FILLED',
                'entry_price': entry_price,
                'exit_price': tp_price,
                'total_quantity': quantity,
                'result_timestamp': int(time.time()),
                'is_successful': True,  # 止盈表示成功
                'holding_time_minutes': holding_time
            }
            
            # 寫入資料庫
            from trading_data_manager import trading_data_manager
            success = trading_data_manager.record_trading_result_by_client_id(
                order_info.get('client_order_id'), result_data
            )
            
            if success:
                logger.info(f"止盈結果記錄成功: 盈利 +{pnl:.4f} USDT, 持有時間: {holding_time}分鐘")
            else:
                logger.error(f"止盈結果記錄失敗")
                
            return success
            
        except Exception as e:
            logger.error(f"記錄止盈結果時出錯: {str(e)}")
            return False
    
    def _record_sl_result(self, order_info):
        """記錄止損結果到trading_results表"""
        try:
            # 計算基本數據
            entry_price = float(order_info.get('price', 0))
            sl_price = float(order_info.get('sl_price', entry_price * 0.98))  # 使用記錄的止損價
            quantity = float(order_info.get('total_quantity') or order_info.get('quantity', 0))
            side = order_info.get('side')
            entry_time_str = order_info.get('entry_time')
            
            # 計算盈虧
            if side == 'BUY':
                pnl = (sl_price - entry_price) * quantity
            else:  # SELL
                pnl = (entry_price - sl_price) * quantity
            
            # 計算持有時間
            holding_time = self._calculate_holding_time(entry_time_str)
            
            # 準備結果數據
            result_data = {
                'client_order_id': order_info.get('client_order_id'),
                'symbol': order_info.get('symbol'),
                'final_pnl': round(pnl, 4),
                'pnl_percentage': round((pnl / (entry_price * quantity)) * 100, 2),
                'exit_method': 'SL_FILLED',
                'entry_price': entry_price,
                'exit_price': sl_price,
                'total_quantity': quantity,
                'result_timestamp': int(time.time()),
                'is_successful': False,  # 止損表示失敗
                'holding_time_minutes': holding_time
            }
            
            # 寫入資料庫
            from trading_data_manager import trading_data_manager
            success = trading_data_manager.record_trading_result_by_client_id(
                order_info.get('client_order_id'), result_data
            )
            
            if success:
                logger.info(f"止損結果記錄成功: 虧損 {pnl:.4f} USDT, 持有時間: {holding_time}分鐘")
            else:
                logger.error(f"止損結果記錄失敗")
                
            return success
            
        except Exception as e:
            logger.error(f"記錄止損結果時出錯: {str(e)}")
            return False
    
    def _calculate_holding_time(self, entry_time_str):
        """計算持有時間（分鐘）"""
        try:
            if not entry_time_str:
                return 120  # 預設2小時
            
            # 解析入場時間
            entry_time = datetime.strptime(entry_time_str, '%Y-%m-%d %H:%M:%S')
            current_time = datetime.now()
            
            # 計算時間差
            time_diff = current_time - entry_time
            holding_minutes = int(time_diff.total_seconds() / 60)
            
            return max(holding_minutes, 1)  # 至少1分鐘
            
        except Exception as e:
            logger.error(f"計算持有時間時出錯: {str(e)}")
            return 120  # 預設2小時
    
    def get_orders(self):
        """獲取所有訂單"""
        return self.orders
    
    def get_order(self, client_order_id):
        """獲取特定訂單"""
        return self.orders.get(client_order_id)
    
    def set_webhook_data_recovery_callback(self, callback):
        """設置webhook數據恢復回調函數"""
        self.webhook_data_recovery_callback = callback
    
    def get_processing_orders(self):
        """獲取正在處理的訂單列表（用於調試）"""
        return list(self.processing_orders)
    
    def clear_processing_order(self, client_order_id):
        """清除處理標記（緊急使用）"""
        self.processing_orders.discard(client_order_id)
        logger.info(f"已清除訂單 {client_order_id} 的處理標記")
    
    def get_order_summary(self, client_order_id):
        """獲取訂單摘要信息"""
        if client_order_id not in self.orders:
            return None
            
        order = self.orders[client_order_id]
        return {
            'symbol': order.get('symbol'),
            'side': order.get('side'),
            'status': order.get('status'),
            'quantity': order.get('quantity'),
            'price': order.get('price'),
            'tp_placed': order.get('tp_placed', False),
            'sl_placed': order.get('sl_placed', False),
            'is_add_position': order.get('is_add_position', False),
            'fill_time': order.get('fill_time'),
            'tp_price': order.get('tp_price'),
            'sl_price': order.get('sl_price')
        }

# 創建全局訂單管理器實例
order_manager = OrderManager()
