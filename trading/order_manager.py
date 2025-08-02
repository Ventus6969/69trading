"""
訂單管理模組
包含所有訂單相關操作，修正重複處理和止盈邏輯問題
🔥 完整修復版本：結合舊版本功能 + 新版本安全性改進 + 數據庫記錄功能
=============================================================================
"""
import time
import logging
import traceback
import sqlite3  # 🔥 新增：用於數據庫操作
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
                
            return order_result
            
        except Exception as e:
            logger.error(f"創建訂單時出錯: {str(e)}")
            return None

    def handle_order_filled(self, client_order_id, symbol, side, order_type, price, quantity, executed_qty, position_side='BOTH', is_add_position=False):
        """
        處理訂單成交事件 - 🔥 修復版本：防止重複處理 + 統一止盈邏輯
        
        Args:
            client_order_id: 客戶訂單ID
            symbol: 交易對
            side: 買賣方向
            order_type: 訂單類型
            price: 成交價格
            quantity: 訂單數量
            executed_qty: 實際成交數量
            position_side: 持倉方向
            is_add_position: 是否為加倉操作
        """
        try:
            # 🔥 新增：防止重複處理機制
            if client_order_id in self.processing_orders:
                logger.info(f"訂單 {client_order_id} 正在處理中，跳過重複處理")
                return
            
            self.processing_orders.add(client_order_id)
            
            try:
                # 檢查是否在本地記錄中
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
        下止盈單 - 🔥 完善版本（結合舊版本功能 + 數據庫記錄）
        
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
                    logger.info(f"訂單 {original_client_id} 已設置止盈單，跳過重複設置")
                    return

            # 根據是否加倉決定計算基準
            if is_add_position:
                # 加倉情況：獲取平均成本
                calculation_price = position_manager.get_average_cost(symbol)
                if calculation_price is None:
                    calculation_price = entry_price
                    logger.warning(f"無法獲取 {symbol} 平均成本，使用入場價格 {entry_price}")
                else:
                    logger.info(f"加倉操作 - 使用平均成本價格 {calculation_price} 計算止盈")
                    
                # 獲取總持倉量
                actual_quantity = position_manager.get_total_position_size(symbol)
                if actual_quantity is None:
                    actual_quantity = quantity
                    logger.warning(f"無法獲取 {symbol} 總持倉量，使用當前訂單數量 {quantity}")
            else:
                # 新開倉情況：使用入場價格
                calculation_price = entry_price
                actual_quantity = quantity
                logger.info(f"新開倉操作 - 使用入場價格 {entry_price} 計算止盈")

            # 計算止盈偏移量
            tp_price_offset = self._calculate_tp_offset(entry_order, calculation_price)

            # 計算止盈價格
            precision = get_symbol_precision(symbol)
            
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
            tp_order_result = self.create_order(
                symbol=symbol,
                side=tp_side,
                order_type='LIMIT',
                quantity=str(actual_quantity),
                price=tp_price,
                time_in_force='GTC',
                client_order_id=tp_client_id,
                position_side=position_side
            )

            # 🔥 新增：記錄止盈單到資料庫
            if tp_order_result:
                self._record_tp_sl_order_to_db(
                    signal_id=self._get_signal_id_from_main_order(original_client_id),
                    client_order_id=tp_client_id,
                    symbol=symbol,
                    side=tp_side,
                    order_type='LIMIT',
                    quantity=actual_quantity,
                    price=tp_price,
                    binance_order_id=tp_order_result.get('orderId'),
                    status='NEW'
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

            logger.info(f"✅ 止盈單處理完成 - 止盈價: {tp_price}, 數量: {actual_quantity}")

            # 如果啟用止損功能，同時下止損單
            if ENABLE_STOP_LOSS:
                self.place_sl_order(entry_order, calculation_price, actual_quantity, is_add_position)

        except Exception as e:
            logger.error(f"❌ 下止盈單時出錯: {str(e)}")
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
        根據入場單信息下止損單（修正版本：避免重複ID + 數據庫記錄）
        
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
            else:  # SELL
                sl_price = round(calculation_price + sl_price_offset, precision)
                sl_side = 'BUY'

            logger.info(f"訂單 {original_client_id} 止損設置:")
            logger.info(f"  計算基準價: {calculation_price} ({'平均成本' if is_add_position else '入場價'})")
            logger.info(f"  止損百分比: {STOP_LOSS_PERCENTAGE * 100}%")
            logger.info(f"  止損價: {sl_price}")
            logger.info(f"  總持倉量: {actual_quantity}")
            logger.info(f"  精度: {precision}")

            # 生成止損訂單ID
            sl_client_id = self._generate_sl_order_id(original_client_id)

            # 下止損單
            sl_order_result = self.create_order(
                symbol=symbol,
                side=sl_side,
                order_type='STOP_MARKET',
                quantity=str(actual_quantity),
                stop_price=sl_price,
                client_order_id=sl_client_id,
                position_side=position_side
            )

            # 🔥 新增：記錄止損單到資料庫
            if sl_order_result:
                self._record_tp_sl_order_to_db(
                    signal_id=self._get_signal_id_from_main_order(original_client_id),
                    client_order_id=sl_client_id,
                    symbol=symbol,
                    side=sl_side,
                    order_type='STOP_MARKET',
                    quantity=actual_quantity,
                    price=sl_price,
                    binance_order_id=sl_order_result.get('orderId'),
                    status='NEW'
                )

            # 更新訂單狀態
            if original_client_id in self.orders:
                if sl_order_result is not None:
                    self.orders[original_client_id]['sl_client_id'] = sl_client_id
                    self.orders[original_client_id]['sl_price'] = sl_price
                    self.orders[original_client_id]['sl_placed'] = True

            logger.info(f"已為訂單 {original_client_id} 下達止損單 - 止損價: {sl_price}, 數量: {actual_quantity}")

        except Exception as e:
            logger.error(f"❌ 下止損單時出錯: {str(e)}")
            logger.error(traceback.format_exc())

    def _record_tp_sl_order_to_db(self, signal_id, client_order_id, symbol, side, 
                              order_type, quantity, price, binance_order_id, status):
    """
    🔥 新增：記錄止盈止損單到資料庫 - 增強版本
    """
    try:
        from database import trading_data_manager
        
        # 🔥 新增：防護性檢查signal_id
        if signal_id is None:
            logger.warning(f"⚠️ 止盈止損單 {client_order_id} 的signal_id為None，可能主訂單尚未記錄完成")
            # 嘗試等待並重試
            import time
            time.sleep(0.5)  # 等待500ms
            signal_id = self._get_signal_id_from_main_order(client_order_id.split('_')[0])
            
            if signal_id is None:
                logger.error(f"❌ 無法獲取止盈止損單 {client_order_id} 的signal_id，跳過資料庫記錄")
                return False
            else:
                logger.info(f"✅ 重試後成功獲取signal_id: {signal_id}")
        
        order_data = {
            'client_order_id': client_order_id,
            'symbol': symbol,
            'side': side,
            'order_type': order_type,
            'quantity': quantity,
            'price': price,
            'leverage': 30,  # 預設槓桿
            'binance_order_id': binance_order_id,
            'status': status,
            'is_add_position': False,  # 止盈止損不是加倉
        }
        
        success = trading_data_manager.record_order_execution(signal_id, order_data)
        
        if success:
            logger.info(f"✅ 止盈止損單已記錄到資料庫: {client_order_id}, signal_id: {signal_id}")
        else:
            logger.error(f"❌ 止盈止損單記錄失敗: {client_order_id}, signal_id: {signal_id}")
            
        return success
        
    except Exception as e:
        logger.error(f"記錄止盈止損單到資料庫時出錯: {str(e)}")
        logger.error(traceback.format_exc())
        return False

    def _get_signal_id_from_main_order(self, main_client_order_id):
        """
        🔥 新增：從主訂單獲取signal_id
        """
        try:
            from database import trading_data_manager
            
            # 查詢主訂單的signal_id
            with sqlite3.connect(trading_data_manager.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT signal_id FROM orders_executed WHERE client_order_id = ?",
                    (main_client_order_id,)
                )
                result = cursor.fetchone()
                return result[0] if result else None
                
        except Exception as e:
            logger.error(f"獲取signal_id失敗: {str(e)}")
            return None

    def _generate_tp_order_id(self, original_order_id):
        """生成止盈訂單ID"""
        timestamp = str(int(time.time()))[-5:]
        return f"{original_order_id}_{timestamp}T"

    def _generate_sl_order_id(self, original_order_id):
        """生成止損訂單ID"""
        timestamp = str(int(time.time()))[-5:]
        return f"{original_order_id}_{timestamp}S"

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
                'exit_method': 'TAKE_PROFIT',
                'entry_price': entry_price,
                'exit_price': tp_price,
                'total_quantity': quantity,
                'result_timestamp': int(time.time()),
                'is_successful': True,  # 止盈表示成功
                'holding_time_minutes': holding_time
            }

            # 寫入資料庫
            from database import trading_data_manager
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
                'exit_method': 'STOP_LOSS',
                'entry_price': entry_price,
                'exit_price': sl_price,
                'total_quantity': quantity,
                'result_timestamp': int(time.time()),
                'is_successful': False,  # 止損表示失敗
                'holding_time_minutes': holding_time
            }

            # 寫入資料庫
            from database import trading_data_manager
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

    def update_order_status(self, client_order_id, status, executed_qty=None):
        """更新訂單狀態"""
        if client_order_id in self.orders:
            self.orders[client_order_id]['status'] = status
            if executed_qty is not None:
                self.orders[client_order_id]['executed_qty'] = executed_qty
            logger.info(f"訂單狀態已更新: {client_order_id} -> {status}")

    def cancel_existing_tp_orders_for_symbol(self, symbol):
        """取消指定交易對的所有止盈單"""
        try:
            cancelled_count = 0
            for order_id, order_info in self.orders.items():
                if (order_info.get('symbol') == symbol and 
                    order_info.get('tp_client_id') and 
                    order_info.get('tp_placed', False)):
                    
                    tp_client_id = order_info['tp_client_id']
                    cancel_result = binance_client.cancel_order(symbol, tp_client_id)
                    if cancel_result:
                        logger.info(f"已取消 {symbol} 的止盈單: {tp_client_id}")
                        order_info['tp_placed'] = False
                        cancelled_count += 1
                    else:
                        logger.warning(f"取消 {symbol} 止盈單失敗: {tp_client_id}")
            
            logger.info(f"已取消 {symbol} 的 {cancelled_count} 個止盈單")
            return cancelled_count
            
        except Exception as e:
            logger.error(f"取消 {symbol} 止盈單時出錯: {str(e)}")
            return 0

    def cancel_existing_sl_orders_for_symbol(self, symbol):
        """取消指定交易對的所有止損單"""
        try:
            cancelled_count = 0
            for order_id, order_info in self.orders.items():
                if (order_info.get('symbol') == symbol and 
                    order_info.get('sl_client_id') and 
                    order_info.get('sl_placed', False)):
                    
                    sl_client_id = order_info['sl_client_id']
                    cancel_result = binance_client.cancel_order(symbol, sl_client_id)
                    if cancel_result:
                        logger.info(f"已取消 {symbol} 的止損單: {sl_client_id}")
                        order_info['sl_placed'] = False
                        cancelled_count += 1
                    else:
                        logger.warning(f"取消 {symbol} 止損單失敗: {sl_client_id}")
            
            logger.info(f"已取消 {symbol} 的 {cancelled_count} 個止損單")
            return cancelled_count
            
        except Exception as e:
            logger.error(f"取消 {symbol} 止損單時出錯: {str(e)}")
            return 0

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

    def handle_new_order(self, parsed_signal):
        """
        處理新開倉訂單 - 🔥 修復 order_type 硬編碼問題
        
        Args:
            parsed_signal: 解析後的信號數據
            
        Returns:
            dict: 統一格式的訂單結果
        """
        try:
            from utils.helpers import generate_order_id
            
            # 生成訂單ID
            client_order_id = generate_order_id(
                parsed_signal.get('strategy_name', parsed_signal.get('signal_type', 'trading')),
                parsed_signal['symbol'], 
                parsed_signal['side']
            )
            
            # 🔥 修復：正確使用信號中的 order_type，不再硬編碼
            order_type = parsed_signal.get('order_type', 'MARKET').upper()
            
            # 準備訂單參數
            order_params = {
                'symbol': parsed_signal['symbol'],
                'side': parsed_signal['side'].upper(),
                'order_type': order_type,  # 🔥 修復：使用正確的 order_type
                'quantity': parsed_signal['quantity'],
                'client_order_id': client_order_id,
                'position_side': 'BOTH'
            }
            
            # 🔥 新增：如果是限價單，添加價格參數
            if order_type == 'LIMIT' and parsed_signal.get('price'):
                order_params['price'] = parsed_signal['price']
                order_params['time_in_force'] = 'GTC'
                logger.info(f"🔍 創建限價單: {parsed_signal['symbol']} {parsed_signal['side']} {parsed_signal['quantity']}@{parsed_signal['price']}")
            else:
                logger.info(f"🔍 創建市價單: {parsed_signal['symbol']} {parsed_signal['side']} {parsed_signal['quantity']}")
            
            # 執行下單
            order_result = self.create_order(**order_params)
            
            if order_result and order_result.get('status') in ['FILLED', 'NEW', 'PARTIALLY_FILLED']:
                # 返回統一格式的成功結果
                return {
                    'status': 'success',
                    'client_order_id': client_order_id,
                    'binance_order_id': order_result.get('orderId'),
                    'quantity': order_result.get('executedQty', parsed_signal['quantity']),
                    'filled_price': self._extract_fill_price(order_result),
                    'order_type': order_type,  # 🔥 新增：返回實際的訂單類型
                    'tp_client_id': None,  # 止盈單ID稍後由WebSocket處理設置
                    'tp_price': None       # 止盈價格稍後計算
                }
            else:
                # 返回錯誤結果
                return {
                    'status': 'error',
                    'message': f'{order_type} order execution failed',
                    'client_order_id': client_order_id,
                    'order_type': order_type
                }
                
        except Exception as e:
            logger.error(f"處理新開倉訂單時出錯: {str(e)}")
            logger.error(traceback.format_exc())
            return {
                'status': 'error',
                'message': str(e),
                'client_order_id': client_order_id if 'client_order_id' in locals() else None,
                'order_type': order_type if 'order_type' in locals() else 'UNKNOWN'
            }

    def handle_new_position_order(self, parsed_signal, tp_percentage):
        """
        處理新開倉訂單 - 🔥 支援 tp_percentage 參數的版本
        
        Args:
            parsed_signal: 解析後的信號數據
            tp_percentage: 止盈百分比
            
        Returns:
            dict: 統一格式的訂單結果
        """
        try:
            from utils.helpers import generate_order_id
            
            # 生成訂單ID
            client_order_id = generate_order_id(
                parsed_signal.get('strategy_name', parsed_signal.get('signal_type', 'trading')),
                parsed_signal['symbol'], 
                parsed_signal['side']
            )
            
            # 🔥 修復：正確使用信號中的 order_type，不再硬編碼
            order_type = parsed_signal.get('order_type', 'MARKET').upper()
            
            # 🔥 方案1：預先記錄訂單到本地，避免WebSocket競爭條件
            logger.info(f"🔄 預先記錄訂單到本地: {client_order_id}")
            self.orders[client_order_id] = {
                'symbol': parsed_signal['symbol'],
                'side': parsed_signal['side'].upper(),
                'quantity': parsed_signal['quantity'],
                'price': parsed_signal.get('price'),
                'type': order_type,
                'status': 'PENDING',  # 標記為等待發送狀態
                'entry_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'tp_placed': False,
                'sl_placed': False,
                'tp_percentage': tp_percentage,
                'position_side': 'BOTH',
                'atr': parsed_signal.get('atr'),
                'tp_multiplier': parsed_signal.get('tp_multiplier'),
                'waiting_for_api_response': True,  # 標記正在等待API響應
                'created_at': time.time()
            }
            
            # 準備訂單參數
            order_params = {
                'symbol': parsed_signal['symbol'],
                'side': parsed_signal['side'].upper(),
                'order_type': order_type,  # 🔥 修復：使用正確的 order_type
                'quantity': parsed_signal['quantity'],
                'client_order_id': client_order_id,
                'position_side': 'BOTH'
            }
            
            # 🔥 新增：如果是限價單，添加價格參數
            if order_type == 'LIMIT' and parsed_signal.get('price'):
                order_params['price'] = parsed_signal['price']
                order_params['time_in_force'] = 'GTC'
                logger.info(f"🔍 創建限價單: {parsed_signal['symbol']} {parsed_signal['side']} {parsed_signal['quantity']}@{parsed_signal['price']}")
            else:
                logger.info(f"🔍 創建市價單: {parsed_signal['symbol']} {parsed_signal['side']} {parsed_signal['quantity']}")
            
            # 執行下單
            order_result = self.create_order(**order_params)
            
            if order_result and order_result.get('status') in ['FILLED', 'NEW', 'PARTIALLY_FILLED']:
                # 返回統一格式的成功結果
                return {
                    'status': 'success',
                    'client_order_id': client_order_id,
                    'binance_order_id': order_result.get('orderId'),
                    'quantity': order_result.get('executedQty', parsed_signal['quantity']),
                    'filled_price': self._extract_fill_price(order_result),
                    'order_type': order_type,  # 🔥 新增：返回實際的訂單類型
                    'tp_client_id': None,  # 止盈單ID稍後由WebSocket處理設置
                    'tp_price': None,      # 止盈價格稍後計算
                    'tp_percentage': tp_percentage  # 🔥 新增：保存 tp_percentage 以供後續使用
                }
            else:
                # 返回錯誤結果
                return {
                    'status': 'error',
                    'message': f'{order_type} order execution failed',
                    'client_order_id': client_order_id,
                    'order_type': order_type
                }
                
        except Exception as e:
            logger.error(f"處理新開倉訂單時出錯: {str(e)}")
            logger.error(traceback.format_exc())
            return {
                'status': 'error',
                'message': str(e),
                'client_order_id': client_order_id if 'client_order_id' in locals() else None,
                'order_type': order_type if 'order_type' in locals() else 'UNKNOWN'
            }

    def handle_add_position_order(self, parsed_signal, tp_percentage):
        """
        處理加倉訂單 - 🔥 修復 order_type 硬編碼問題
        
        Args:
            parsed_signal: 解析後的信號數據
            tp_percentage: 止盈百分比
            
        Returns:
            dict: 統一格式的訂單結果
        """
        try:
            from utils.helpers import generate_order_id
            
            # 生成訂單ID
            client_order_id = generate_order_id(
                parsed_signal.get('strategy_name', parsed_signal.get('signal_type', 'trading')),
                parsed_signal['symbol'], 
                parsed_signal['side']
            )
            
            # 🔥 修復：正確使用信號中的 order_type，不再硬編碼
            order_type = parsed_signal.get('order_type', 'MARKET').upper()
            
            # 準備訂單參數
            order_params = {
                'symbol': parsed_signal['symbol'],
                'side': parsed_signal['side'].upper(),
                'order_type': order_type,  # 🔥 修復：使用正確的 order_type
                'quantity': parsed_signal['quantity'],
                'client_order_id': client_order_id,
                'position_side': 'BOTH'
            }
            
            # 🔥 新增：如果是限價單，添加價格參數
            if order_type == 'LIMIT' and parsed_signal.get('price'):
                order_params['price'] = parsed_signal['price']
                order_params['time_in_force'] = 'GTC'
                logger.info(f"🔍 創建加倉限價單: {parsed_signal['symbol']} {parsed_signal['side']} {parsed_signal['quantity']}@{parsed_signal['price']}")
            else:
                logger.info(f"🔍 創建加倉市價單: {parsed_signal['symbol']} {parsed_signal['side']} {parsed_signal['quantity']}")
            
            # 執行下單
            order_result = self.create_order(**order_params)
            
            if order_result and order_result.get('status') in ['FILLED', 'NEW', 'PARTIALLY_FILLED']:
                # 返回統一格式的成功結果
                return {
                    'status': 'success',
                    'client_order_id': client_order_id,
                    'binance_order_id': order_result.get('orderId'),
                    'quantity': order_result.get('executedQty', parsed_signal['quantity']),
                    'filled_price': self._extract_fill_price(order_result),
                    'order_type': order_type,  # 🔥 新增：返回實際的訂單類型
                    'tp_client_id': None,  # 止盈單ID稍後由WebSocket處理設置
                    'tp_price': None,      # 止盈價格稍後計算
                    'is_add_position': True
                }
            else:
                # 返回錯誤結果
                return {
                    'status': 'error',
                    'message': f'{order_type} add position order execution failed',
                    'client_order_id': client_order_id,
                    'order_type': order_type,
                    'is_add_position': True
                }
                
        except Exception as e:
            logger.error(f"處理加倉訂單時出錯: {str(e)}")
            logger.error(traceback.format_exc())
            return {
                'status': 'error',
                'message': str(e),
                'client_order_id': client_order_id if 'client_order_id' in locals() else None,
                'order_type': order_type if 'order_type' in locals() else 'UNKNOWN',
                'is_add_position': True
            }

    def _extract_fill_price(self, order_result):
        """從訂單結果中提取成交價格"""
        try:
            # 嘗試從不同字段獲取價格
            if order_result.get('fills') and len(order_result['fills']) > 0:
                # 如果有成交記錄，使用第一筆成交的價格
                return float(order_result['fills'][0]['price'])
            elif order_result.get('price') and float(order_result['price']) > 0:
                # 限價單的設定價格
                return float(order_result['price'])
            elif order_result.get('avgPrice') and float(order_result['avgPrice']) > 0:
                # 平均成交價
                return float(order_result['avgPrice'])
            else:
                # 預設值
                return 0.0
        except (ValueError, TypeError, KeyError):
            return 0.0

# 創建全局訂單管理器實例
order_manager = OrderManager()
