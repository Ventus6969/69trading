"""
交易信號處理模組
處理來自TradingView的交易信號
=============================================================================
"""
import time
import logging
import traceback
from datetime import datetime
from api.binance_client import binance_client
from trading.order_manager import order_manager
from trading.position_manager import position_manager
from utils.helpers import (
    get_symbol_precision, get_tp_multiplier, is_within_time_range,
    validate_signal_data, calculate_price_with_precision, get_entry_mode_name
)
from config.settings import (
    DEFAULT_LEVERAGE, TP_PERCENTAGE, MIN_TP_PROFIT_PERCENTAGE,
    TW_TIMEZONE, TRADING_BLOCK_START_HOUR, TRADING_BLOCK_START_MINUTE,
    TRADING_BLOCK_END_HOUR, TRADING_BLOCK_END_MINUTE, ORDER_TIMEOUT_MINUTES
)

# 設置logger
logger = logging.getLogger(__name__)

class SignalProcessor:
    """交易信號處理器"""
    
    def __init__(self):
        # 用於存儲最近的webhook數據
        self.last_webhook_data = None
    
    def process_signal(self, signal_data):
        """
        處理TradingView交易信號
        
        Args:
            signal_data: 來自TradingView的信號數據
            
        Returns:
            dict: 處理結果
        """
        try:
            # === 1. 驗證數據 ===
            is_valid, error_msg = validate_signal_data(signal_data)
            if not is_valid:
                return {"status": "error", "message": error_msg}
            
            # === 2. 檢查交易時間限制 ===
            if is_within_time_range(TRADING_BLOCK_START_HOUR, TRADING_BLOCK_START_MINUTE, 
                                   TRADING_BLOCK_END_HOUR, TRADING_BLOCK_END_MINUTE):
                logger.info("當前時間為台灣時間20:00-23:50之間，根據設定不執行下單操作")
                return {
                    "status": "ignored", 
                    "message": "當前時間為台灣時間20:00-23:50之間，根據設定不執行下單操作",
                    "current_time": datetime.now(TW_TIMEZONE).strftime('%Y-%m-%d %H:%M:%S')
                }
            
            # === 3. 解析信號數據 ===
            parsed_signal = self._parse_signal_data(signal_data)
            
            # === 4. 檢查現有倉位 ===
            position_decision = self._check_position_conflict(parsed_signal)
            if position_decision['action'] == 'ignore':
                return position_decision
            
            # === 5. 設置交易參數 ===
            self._setup_trading_parameters(parsed_signal)
            
            # === 6. 計算止盈參數 ===
            tp_params = self._calculate_tp_parameters(parsed_signal)
            
            # === 7. 保存webhook數據 ===
            self._save_webhook_data(parsed_signal, tp_params)
            
            # === 8. 生成訂單 ===
            order_result = self._create_and_execute_order(parsed_signal, tp_params, position_decision)
            
            return order_result
            
        except Exception as e:
            logger.error(f"處理交易信號時出錯: {str(e)}")
            logger.error(traceback.format_exc())
            return {"status": "error", "message": str(e)}
    
    def _parse_signal_data(self, data):
        """解析信號數據"""
        symbol = data.get('symbol', '').upper()
        side = data.get('side', '').upper()
        signal_type = data.get('signal_type')
        
        # 獲取價格數據
        quantity = data.get('quantity', '1')
        open_price = float(data.get('open'))
        close_price = float(data.get('close'))
        prev_close = data.get('prev_close')
        prev_open = data.get('prev_open')
        
        # 其他參數
        order_type = data.get('order_type', 'LIMIT').upper()
        position_side = data.get('position_side', 'BOTH').upper()
        strategy_name = data.get('strategy_name', 'TV_STRAT')
        atr_value = data.get('ATR')
        margin_type = data.get('margin_type', 'ISOLATED').upper()
        opposite = int(data.get('opposite', 0))
        
        # 獲取交易對配置
        precision = get_symbol_precision(symbol)
        tp_multiplier = get_tp_multiplier(symbol, opposite, signal_type)
        
        # 計算開倉價格
        price = self._calculate_entry_price(open_price, close_price, prev_close, prev_open, 
                                           opposite, precision)
        
        return {
            'symbol': symbol,
            'side': side,
            'signal_type': signal_type,
            'quantity': quantity,
            'open_price': open_price,
            'close_price': close_price,
            'prev_close': prev_close,
            'prev_open': prev_open,
            'price': price,
            'order_type': order_type,
            'position_side': position_side,
            'strategy_name': strategy_name,
            'atr_value': atr_value,
            'margin_type': margin_type,
            'opposite': opposite,
            'precision': precision,
            'tp_multiplier': tp_multiplier
        }
    
    def _calculate_entry_price(self, open_price, close_price, prev_close, prev_open, 
                              opposite, precision):
        """計算開倉價格"""
        if opposite == 0:
            # 模式0: 使用當前收盤價作為開倉價
            price = close_price
            logger.info(f"模式0 - 使用當前收盤價開倉: {price}")
        elif opposite == 1:
            # 模式1: 使用前根K線收盤價作為開倉價
            if prev_close is not None:
                price = float(prev_close)
                logger.info(f"模式1 - 使用前根K線收盤價開倉: {price}")
            else:
                price = close_price
                logger.warning(f"未提供前根收盤價，回退使用當前收盤價: {price}")
        elif opposite == 2:
            # 模式2: 使用前根K線開盤價作為開倉價
            if prev_open is not None:
                price = float(prev_open)
                logger.info(f"模式2 - 使用前根K線開盤價開倉: {price}")
            else:
                price = close_price
                logger.warning(f"未提供前根開盤價，回退使用當前收盤價: {price}")
        else:
            # 未知模式，使用默認的當前收盤價
            price = close_price
            logger.warning(f"未知opposite模式: {opposite}，使用當前收盤價: {price}")
        
        # 根據交易對精度四捨五入價格
        price = round(price, precision)
        
        logger.info(f"開倉價格計算 - 模式: {opposite}, 當前收盤: {close_price}, "
                   f"前根收盤: {prev_close}, 前根開盤: {prev_open}, 最終開倉價: {price}")
        
        return price
    
    def _check_position_conflict(self, parsed_signal):
        """檢查倉位衝突"""
        symbol = parsed_signal['symbol']
        side = parsed_signal['side']
        
        # 檢查現有倉位
        is_same_direction, current_side = position_manager.is_same_direction(symbol, side)
        
        if current_side:  # 有現有持倉
            new_side = 'LONG' if side == 'BUY' else 'SHORT'
            logger.info(f"檢測到 {symbol} 現有{current_side}倉位, 新信號方向: {new_side}")
            
            if is_same_direction:
                # 方向一致：加倉邏輯
                logger.info(f"方向一致，執行加倉操作")
                
                # 取消現有的止盈單和止損單，準備加倉後重新設置
                order_manager.cancel_existing_tp_orders_for_symbol(symbol)
                order_manager.cancel_existing_sl_orders_for_symbol(symbol)
                
                logger.info(f"準備加倉 {symbol} {new_side} 倉位")
                return {'action': 'add_position', 'is_add_position': True}
            else:
                # 方向不一致：完全忽略
                logger.info(f"方向不一致，完全忽略新信號，保持現有倉位不變")
                return {
                    "status": "ignored",
                    "message": f"方向不一致，已忽略信號",
                    "symbol": symbol,
                    "current_side": current_side,
                    "signal_side": new_side,
                    "action": "ignore"
                }
        else:
            logger.info(f"{symbol} 無現有持倉，準備新開倉")
            return {'action': 'new_position', 'is_add_position': False}
    
    def _setup_trading_parameters(self, parsed_signal):
        """設置交易參數"""
        symbol = parsed_signal['symbol']
        margin_type = parsed_signal['margin_type']
        
        # 設置槓桿和保證金模式
        binance_client.set_leverage(symbol, DEFAULT_LEVERAGE)
        binance_client.set_margin_type(symbol, margin_type)
    
    def _calculate_tp_parameters(self, parsed_signal):
        """計算止盈參數"""
        symbol = parsed_signal['symbol']
        price = parsed_signal['price']
        atr_value = parsed_signal['atr_value']
        tp_multiplier = parsed_signal['tp_multiplier']
        
        tp_price_offset = None
        
        if atr_value and str(atr_value).replace('.', '', 1).isdigit():
            atr_value_float = float(atr_value)
            # 直接使用ATR值乘以倍數作為價格偏移
            tp_price_offset = atr_value_float * tp_multiplier
            
            logger.info(f"基於ATR直接計算止盈偏移 - ATR: {atr_value_float}, "
                       f"倍數: {tp_multiplier}, 偏移量: {tp_price_offset}")
        else:
            # 如果沒有ATR值，使用默認百分比
            if price > 0:
                tp_price_offset = price * TP_PERCENTAGE
                logger.info(f"使用默認百分比計算止盈偏移 - 價格: {price}, "
                           f"百分比: {TP_PERCENTAGE:.1%}, 偏移量: {tp_price_offset}")
            else:
                tp_price_offset = 0
        
        # 檢查最小獲利保護
        if tp_price_offset is not None and tp_price_offset > 0:
            min_tp_offset = price * MIN_TP_PROFIT_PERCENTAGE
            if tp_price_offset < min_tp_offset:
                logger.info(f"止盈偏移量 {tp_price_offset} 小於最小獲利要求 {min_tp_offset} (0.5%)，調整為最小值")
                tp_price_offset = min_tp_offset
            else:
                logger.info(f"止盈偏移量 {tp_price_offset} 滿足最小獲利要求 {min_tp_offset} (0.5%)")
        
        return {
            'tp_price_offset': tp_price_offset,
            'tp_multiplier': tp_multiplier
        }
    
    def _save_webhook_data(self, parsed_signal, tp_params):
        """保存webhook數據供WebSocket使用"""
        self.last_webhook_data = {
            'timestamp': int(time.time()),
            'symbol': parsed_signal['symbol'],
            'side': parsed_signal['side'],
            'open_price': parsed_signal['open_price'],
            'close_price': parsed_signal['close_price'],
            'prev_close': parsed_signal['prev_close'],
            'prev_open': parsed_signal['prev_open'],
            'ATR': parsed_signal['atr_value'],
            'tp_price_offset': tp_params['tp_price_offset'],
            'tp_multiplier': tp_params['tp_multiplier'],
            'opposite': parsed_signal['opposite'],
            'precision': parsed_signal['precision']
        }
    
    def _create_and_execute_order(self, parsed_signal, tp_params, position_decision):
        """創建並執行訂單"""
        try:
            # 生成訂單ID
            client_order_id = self._generate_order_id(parsed_signal)
            
            # 計算訂單過期時間
            expiry_time = int(time.time() * 1000) + (ORDER_TIMEOUT_MINUTES * 60 * 1000)
            
            # 準備下單參數
            order_params = {
                "symbol": parsed_signal['symbol'],
                "side": parsed_signal['side'],
                "order_type": parsed_signal['order_type'],
                "quantity": parsed_signal['quantity'],
                "position_side": parsed_signal['position_side'],
                "client_order_id": client_order_id
            }
            
            # 如果是限價單，添加價格和GTD參數
            if parsed_signal['order_type'] == 'LIMIT' and parsed_signal['price']:
                order_params["price"] = parsed_signal['price']
                order_params["time_in_force"] = 'GTD'
                order_params["good_till_date"] = expiry_time
            
            # 記錄下單詳情
            entry_mode = get_entry_mode_name(parsed_signal['opposite'])
            logger.info(f"準備下單詳情 - 交易對: {parsed_signal['symbol']}, "
                       f"方向: {parsed_signal['side']}, 設定精度: {parsed_signal['precision']}")
            logger.info(f"開倉價格: {parsed_signal['price']}, 數量: {parsed_signal['quantity']}, "
                       f"槓桿: {DEFAULT_LEVERAGE}x")
            logger.info(f"止盈倍數: {parsed_signal['tp_multiplier']}, 開倉模式: {entry_mode}")
            
            # 執行下單
            order_result = order_manager.create_order(**order_params)
            
            if order_result:
                # 保存訂單信息
                order_data = {
                    'symbol': parsed_signal['symbol'],
                    'side': parsed_signal['side'],
                    'quantity': parsed_signal['quantity'],
                    'price': parsed_signal['price'],
                    'type': parsed_signal['order_type'],
                    'status': 'NEW',
                    'entry_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'tp_placed': False,
                    'atr': parsed_signal['atr_value'],
                    'tp_price_offset': tp_params['tp_price_offset'],
                    'tp_multiplier': tp_params['tp_multiplier'],
                    'leverage': DEFAULT_LEVERAGE,
                    'margin_type': parsed_signal['margin_type'],
                    'open_price': parsed_signal['open_price'],
                    'close_price': parsed_signal['close_price'],
                    'opposite': parsed_signal['opposite'],
                    'expiry_time': datetime.fromtimestamp(expiry_time/1000).strftime('%Y-%m-%d %H:%M:%S'),
                    'is_add_position': position_decision['is_add_position']
                }
                
                order_manager.save_order_info(client_order_id, order_data)
                
                # 記錄成功日誌
                logger.info(f"接收到TradingView信號，已下單: {client_order_id}, "
                           f"倉位大小: {parsed_signal['quantity']}, 槓桿: {DEFAULT_LEVERAGE}x, "
                           f"訂單將在 {datetime.fromtimestamp(expiry_time/1000).strftime('%Y-%m-%d %H:%M:%S')} 自動取消(如果未成交), "
                           f"開倉模式: {entry_mode}, "
                           f"策略類型: {parsed_signal['signal_type'] or '未指定'}, "
                           f"止盈倍數: {parsed_signal['tp_multiplier']}, "
                           f"操作類型: {'加倉' if position_decision['is_add_position'] else '新開倉'}")
                
                return {
                    "status": "success", 
                    "message": "訂單已提交",
                    "order_id": order_result.get("orderId"),
                    "client_order_id": client_order_id,
                    "quantity": parsed_signal['quantity'],
                    "leverage": f"{DEFAULT_LEVERAGE}x",
                    "entry_mode": entry_mode,
                    "signal_type": parsed_signal['signal_type'] or "未指定",
                    "tp_multiplier": parsed_signal['tp_multiplier'],
                    "operation_type": "加倉" if position_decision['is_add_position'] else "新開倉",
                    "expiry_time": datetime.fromtimestamp(expiry_time/1000).strftime('%Y-%m-%d %H:%M:%S')
                }
            else:
                return {"status": "error", "message": "下單失敗"}
                
        except Exception as e:
            logger.error(f"創建訂單時出錯: {str(e)}")
            logger.error(traceback.format_exc())
            return {"status": "error", "message": str(e)}
    
    def _generate_order_id(self, parsed_signal):
        """生成訂單ID"""
        timestamp = int(time.time()) % 10000
        strategy_name = parsed_signal['strategy_name']
        symbol = parsed_signal['symbol']
        side = parsed_signal['side']
        
        # 縮短策略名稱和交易對
        short_strategy = strategy_name[:3] if len(strategy_name) > 3 else strategy_name
        short_symbol = symbol[:6]
        side_char = "B" if side == "BUY" else "S"
        
        client_order_id = f"{short_strategy}_{short_symbol}_{side_char}{timestamp}_{order_manager.order_counter}"
        order_manager.order_counter += 1
        
        # 確保ID不超過30個字符
        if len(client_order_id) > 30:
            short_strategy = short_strategy[:2]
            short_symbol = symbol[:4]
            client_order_id = f"{short_strategy}_{short_symbol}_{side_char}{timestamp}_{order_manager.order_counter}"
        
        logger.info(f"生成的訂單ID: {client_order_id}, 長度: {len(client_order_id)}")
        return client_order_id
    
    def get_last_webhook_data(self):
        """獲取最近的webhook數據"""
        return self.last_webhook_data

# 創建全局信號處理器實例
signal_processor = SignalProcessor()