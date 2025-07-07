"""
交易信號處理模組 - 影子模式完整整合版本
處理來自TradingView的交易信號，並實施影子模式ML決策
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
    TRADING_BLOCK_END_HOUR, TRADING_BLOCK_END_MINUTE, 
    ORDER_TIMEOUT_MINUTES, get_strategy_timeout
)

# 導入數據管理器
from database import trading_data_manager, ml_data_manager

# 設置logger
logger = logging.getLogger(__name__)

class SignalProcessor:
    """交易信號處理器 - 影子模式完整版本"""
    
    def __init__(self):
        # 用於存儲最近的webhook數據
        self.last_webhook_data = None
        # 用於追蹤信號ID和訂單ID的對應關係
        self.signal_order_mapping = {}
        
        # 延遲導入影子決策引擎，避免循環依賴
        self.shadow_engine = None
        self._init_shadow_engine()
    
    def _init_shadow_engine(self):
        """初始化影子決策引擎"""
        try:
            # 避免循環導入，在這裡導入
            from shadow_decision_engine import shadow_decision_engine
            self.shadow_engine = shadow_decision_engine
            logger.info("✅ 影子決策引擎已載入")
        except Exception as e:
            logger.error(f"❌ 影子決策引擎載入失敗: {str(e)}")
            self.shadow_engine = None
    
    def process_signal(self, signal_data):
        """
        處理TradingView交易信號 - 包含ML特徵計算和影子決策
        
        Args:
            signal_data: 來自TradingView的信號數據
            
        Returns:
            dict: 處理結果
        """
        signal_start_time = time.time()
        signal_id = None
        
        try:
            # === 1. 驗證數據 ===
            is_valid, error_msg = validate_signal_data(signal_data)
            if not is_valid:
                return {"status": "error", "message": error_msg}
            
            # === 2. 立即記錄接收到的信號 ===
            signal_id = trading_data_manager.record_signal_received(signal_data)
            logger.info(f"信號已記錄到資料庫，ID: {signal_id}")
            
            # === 3. 🔥 ML特徵計算和記錄 ===
            session_id = f"session_{int(time.time())}"
            features = self._calculate_and_record_ml_features(session_id, signal_id, signal_data)
            
            # === 4. 🤖 影子模式決策分析 ===
            shadow_result = self._execute_shadow_decision(session_id, signal_id, features, signal_data)
            
            # === 5. 檢查交易時間限制 ===
            if is_within_time_range(TRADING_BLOCK_START_HOUR, TRADING_BLOCK_START_MINUTE, 
                                   TRADING_BLOCK_END_HOUR, TRADING_BLOCK_END_MINUTE):
                logger.info("當前時間為台灣時間20:00-23:50之間，根據設定不執行下單操作")
                return {
                    "status": "ignored", 
                    "message": "當前時間為台灣時間20:00-23:50之間，根據設定不執行下單操作",
                    "current_time": datetime.now(TW_TIMEZONE).strftime('%Y-%m-%d %H:%M:%S'),
                    "signal_id": signal_id,
                    "shadow_decision": shadow_result
                }
            
            # === 6. 解析信號數據 ===
            parsed_signal = self._parse_signal_data(signal_data)
            
            # === 7. 檢查現有倉位 ===
            position_decision = self._check_position_conflict(parsed_signal)
            if position_decision['action'] == 'ignore':
                position_decision['signal_id'] = signal_id
                position_decision['shadow_decision'] = shadow_result
                return position_decision
            
            # === 8. 設置交易參數 ===
            self._setup_trading_parameters(parsed_signal)
            
            # === 9. 計算止盈參數 ===
            tp_params = self._calculate_tp_parameters(parsed_signal)
            
            # === 10. 保存webhook數據 ===
            self._save_webhook_data(parsed_signal, tp_params, shadow_result)
            
            # === 11. 生成訂單（實際交易邏輯不變） ===
            order_result = self._create_and_execute_order(parsed_signal, tp_params, position_decision, signal_id, signal_start_time)
            
            # === 12. 在結果中包含影子決策信息 ===
            if isinstance(order_result, dict):
                order_result['shadow_decision'] = shadow_result
            
            return order_result
            
        except Exception as e:
            logger.error(f"處理交易信號時出錯: {str(e)}")
            logger.error(traceback.format_exc())
            return {"status": "error", "message": str(e), "signal_id": signal_id}
    
    def _calculate_and_record_ml_features(self, session_id: str, signal_id: int, signal_data: dict):
        """
        🔥 計算並記錄ML特徵
        
        Args:
            session_id: 會話ID
            signal_id: 信號ID
            signal_data: 原始信號數據
            
        Returns:
            dict: 計算的特徵字典
        """
        try:
            logger.info(f"開始計算ML特徵 - session_id: {session_id}, signal_id: {signal_id}")
            
            # 計算36個特徵
            features = ml_data_manager.calculate_basic_features(signal_data)
            
            # 記錄特徵到資料庫
            success = ml_data_manager.record_ml_features(session_id, signal_id, features)
            
            if success:
                logger.info(f"✅ ML特徵計算並記錄成功 - 信號ID: {signal_id}")
                
                # 記錄特徵統計
                feature_count = len([k for k, v in features.items() if v is not None])
                logger.info(f"📊 特徵統計: 計算了 {feature_count}/36 個特徵")
                
                # 記錄關鍵特徵值
                key_features = {
                    'strategy_win_rate_recent': features.get('strategy_win_rate_recent'),
                    'hour_of_day': features.get('hour_of_day'),
                    'symbol_category': features.get('symbol_category'),
                    'candle_direction': features.get('candle_direction'),
                    'risk_reward_ratio': features.get('risk_reward_ratio')
                }
                logger.info(f"🔍 關鍵特徵值: {key_features}")
            else:
                logger.warning(f"⚠️ ML特徵記錄失敗 - 信號ID: {signal_id}")
            
            return features
                
        except Exception as e:
            logger.error(f"❌ ML特徵計算時出錯: {str(e)}")
            logger.error(f"詳細錯誤: {traceback.format_exc()}")
            # ML錯誤不影響正常交易流程
            logger.info("🔄 ML錯誤不影響正常交易，繼續執行交易邏輯")
            return {}
    
    def _execute_shadow_decision(self, session_id: str, signal_id: int, 
                               features: dict, signal_data: dict) -> dict:
        """
        🤖 執行影子模式決策分析
        
        Args:
            session_id: 會話ID
            signal_id: 信號ID  
            features: ML特徵數據
            signal_data: 原始信號數據
            
        Returns:
            dict: 影子決策結果
        """
        try:
            if not self.shadow_engine:
                logger.warning("影子決策引擎未載入，跳過影子決策")
                return {"status": "engine_not_loaded"}
            
            logger.info(f"🤖 開始影子模式決策分析 - signal_id: {signal_id}")
            
            # 執行影子決策
            shadow_result = self.shadow_engine.make_shadow_decision(
                session_id, signal_id, features, signal_data
            )
            
            # 記錄影子決策結果到日誌
            self._log_shadow_decision_comparison(signal_data, shadow_result)
            
            return shadow_result
            
        except Exception as e:
            logger.error(f"❌ 影子模式決策時出錯: {str(e)}")
            logger.error(f"詳細錯誤: {traceback.format_exc()}")
            return {"status": "error", "message": str(e)}
    
    def _log_shadow_decision_comparison(self, signal_data: dict, shadow_result: dict):
        """記錄影子決策與實際決策的對比"""
        signal_type = signal_data.get('signal_type')
        opposite = signal_data.get('opposite')
        symbol = signal_data.get('symbol')
        
        logger.info(f"📊 影子vs實際決策對比:")
        logger.info(f"   信號: {symbol} {signal_type} (opposite={opposite})")
        logger.info(f"   🤖 影子建議: {shadow_result.get('recommendation', 'N/A')}")
        logger.info(f"   🎯 實際決策: EXECUTE (系統總是執行)")
        logger.info(f"   🔍 影子理由: {shadow_result.get('reason', 'N/A')}")
        logger.info(f"   📈 信心度: {shadow_result.get('confidence', 0):.1%}")
        
        # 特別標記意見分歧的情況
        if shadow_result.get('recommendation') == 'SKIP':
            logger.warning(f"⚠️ 影子建議跳過但系統將執行 - 需要關注結果")
        elif shadow_result.get('recommendation') == 'EXECUTE':
            logger.info(f"✅ 影子建議與實際決策一致")
    
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
        
        # 計算開倉價格（包含reversal_buy特殊處理）
        price, price_info = self._calculate_entry_price_with_discount(
            open_price, close_price, prev_close, prev_open, 
            opposite, precision, signal_type
        )
        
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
            'price_info': price_info,
            'order_type': order_type,
            'position_side': position_side,
            'strategy_name': strategy_name,
            'atr_value': atr_value,
            'margin_type': margin_type,
            'opposite': opposite,
            'precision': precision,
            'tp_multiplier': tp_multiplier
        }
    
    def _calculate_entry_price_with_discount(self, open_price, close_price, prev_close, prev_open, opposite, precision, signal_type):
        """
        計算開倉價格，包含reversal_buy特殊處理
        
        Returns:
            tuple: (計算後的價格, 價格信息字典)
        """
        price_info = {
            'is_discount_strategy': False,
            'strategy_description': '',
            'base_price': 0,
            'discount_percentage': 0,
            'discount_amount': 0
        }
        
        # 🔥 reversal_buy + opposite=1 的特殊處理
        if signal_type == 'reversal_buy' and opposite == 1:
            if prev_close:
                base_price = float(prev_close)
                discount_percentage = 1.0  # 1%折扣
                discount_amount = base_price * (discount_percentage / 100)
                final_price = base_price - discount_amount
                
                # 記錄價格信息
                price_info.update({
                    'is_discount_strategy': True,
                    'strategy_description': 'reversal_buy低1%策略',
                    'base_price': base_price,
                    'discount_percentage': discount_percentage,
                    'discount_amount': discount_amount
                })
                
                logger.info(f"🎯 啟用reversal_buy低1%策略:")
                logger.info(f"   前根收盤價: {base_price}")
                logger.info(f"   折扣後價格: {final_price}")
                logger.info(f"   節省成本: {discount_amount:.6f}")
                
                return calculate_price_with_precision(final_price, precision), price_info
        
        # 原有的價格計算邏輯
        if opposite == 2:
            # 使用前根開盤價
            if prev_open:
                price = float(prev_open)
                price_info['strategy_description'] = '使用前根開盤價'
            else:
                price = open_price
                price_info['strategy_description'] = '前根開盤價不可用，使用當前開盤價'
        elif opposite == 1:
            # 使用前根收盤價（非reversal_buy情況）
            if prev_close:
                price = float(prev_close)
                price_info['strategy_description'] = '使用前根收盤價'
            else:
                price = close_price
                price_info['strategy_description'] = '前根收盤價不可用，使用當前收盤價'
        else:
            # opposite == 0，使用當前收盤價
            price = close_price
            price_info['strategy_description'] = '使用當前收盤價'
        
        price_info['base_price'] = price
        return calculate_price_with_precision(price, precision), price_info
    
    def _check_position_conflict(self, parsed_signal):
        """檢查倉位衝突"""
        symbol = parsed_signal['symbol']
        side = parsed_signal['side']
        
        # 獲取當前持倉
        current_position = position_manager.get_position(symbol)
        
        if current_position and float(current_position.get('positionAmt', 0)) != 0:
            position_amt = float(current_position['positionAmt'])
            current_side = 'LONG' if position_amt > 0 else 'SHORT'
            is_same_direction = (current_side == 'LONG' and side == 'BUY') or (current_side == 'SHORT' and side == 'SELL')

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
        
        if atr_value and str(atr_value).replace('.', '').replace('-', '').isdigit():
            atr_value = float(atr_value)
            tp_price_offset = atr_value * tp_multiplier
            logger.info(f"使用ATR止盈: ATR={atr_value}, 倍數={tp_multiplier}, 偏移={tp_price_offset}")
        else:
            logger.info(f"未提供有效ATR值({atr_value})，將使用百分比止盈")
        
        return {
            'tp_price_offset': tp_price_offset,
            'tp_multiplier': tp_multiplier
        }
    
    def _save_webhook_data(self, parsed_signal, tp_params, shadow_result=None):
        """保存webhook數據，包含影子決策結果"""
        webhook_data = {
            'symbol': parsed_signal['symbol'],
            'side': parsed_signal['side'],
            'signal_type': parsed_signal['signal_type'],
            'quantity': parsed_signal['quantity'],
            'price': parsed_signal['price'],
            'open_price': parsed_signal['open_price'],
            'close_price': parsed_signal['close_price'],
            'prev_close': parsed_signal['prev_close'],
            'prev_open': parsed_signal['prev_open'],
            'order_type': parsed_signal['order_type'],
            'position_side': parsed_signal['position_side'],
            'strategy_name': parsed_signal['strategy_name'],
            'atr_value': parsed_signal['atr_value'],
            'margin_type': parsed_signal['margin_type'],
            'opposite': parsed_signal['opposite'],
            'precision': parsed_signal['precision'],
            'tp_multiplier': parsed_signal['tp_multiplier'],
            'tp_price_offset': tp_params['tp_price_offset'],
            'price_info': parsed_signal['price_info'],
            'timestamp': datetime.now().isoformat()
        }
        
        # 🔥 新增：包含影子決策結果
        if shadow_result:
            webhook_data['shadow_decision'] = shadow_result
        
        self.last_webhook_data = webhook_data
        logger.info("Webhook數據已保存（包含影子決策）")
    
    def _create_and_execute_order(self, parsed_signal, tp_params, position_decision, signal_id, signal_start_time):
        """創建並執行訂單"""
        try:
            # 生成訂單ID
            client_order_id = self._generate_order_id(parsed_signal)
            
            # 記錄信號ID和訂單ID的對應關係
            self.signal_order_mapping[client_order_id] = signal_id
            
            # 根據策略類型計算訂單過期時間
            signal_type = parsed_signal.get('signal_type')
            timeout_minutes = get_strategy_timeout(signal_type)
            expiry_time = int(time.time() * 1000) + (timeout_minutes * 60 * 1000)
            
            # 記錄下單詳情
            entry_mode = get_entry_mode_name(parsed_signal['opposite'])
            price_info = parsed_signal.get('price_info', {})
            
            logger.info(f"準備下單詳情 - 交易對: {parsed_signal['symbol']}, "
                       f"方向: {parsed_signal['side']}, 設定精度: {parsed_signal['precision']}")
            logger.info(f"開倉價格: {parsed_signal['price']}, 數量: {parsed_signal['quantity']}, "
                       f"槓桿: {DEFAULT_LEVERAGE}x")
            logger.info(f"止盈倍數: {parsed_signal['tp_multiplier']}, 開倉模式: {entry_mode}")
            
            # 🔥 新增：影子決策信息日誌
            logger.info(f"🤖 本次交易的影子決策建議已記錄，後續將對比實際結果")
            
            # 記錄特殊策略信息
            if price_info.get('is_discount_strategy'):
                logger.info(f"🎯 使用reversal_buy低1%策略:")
                logger.info(f"   策略描述: {price_info['strategy_description']}")
                logger.info(f"   基準價格: {price_info['base_price']}")
                logger.info(f"   折扣幅度: -{price_info['discount_percentage']}%")
                logger.info(f"   節省成本: {price_info['discount_amount']:.6f}")
            
            # 記錄使用的超時設定
            if timeout_minutes != ORDER_TIMEOUT_MINUTES:
                logger.info(f"策略 {signal_type} 使用專屬超時: {timeout_minutes}分鐘 (默認: {ORDER_TIMEOUT_MINUTES}分鐘)")
            
            # 提前保存訂單記錄
            order_data = {
                'symbol': parsed_signal['symbol'],
                'side': parsed_signal['side'],
                'quantity': parsed_signal['quantity'],
                'price': parsed_signal['price'],
                'type': parsed_signal['order_type'],
                'status': 'PENDING',
                'entry_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'tp_placed': False,
                'atr': parsed_signal['atr_value'],
                'tp_price_offset': tp_params['tp_price_offset'],
                'tp_multiplier': tp_params['tp_multiplier'],
                'leverage': DEFAULT_LEVERAGE,
                'margin_type': parsed_signal['margin_type'],
                'opposite': parsed_signal['opposite'],
                'precision': parsed_signal['precision'],
                'strategy_name': parsed_signal['strategy_name'],
                'client_order_id': client_order_id,
                'signal_id': signal_id,
                'timeout_minutes': timeout_minutes
            }
            
            # 創建訂單
            order_result = order_manager.create_futures_order_with_tp_sl(
                symbol=parsed_signal['symbol'],
                side=parsed_signal['side'],
                quantity=parsed_signal['quantity'],
                price=parsed_signal['price'],
                order_type=parsed_signal['order_type'],
                client_order_id=client_order_id,
                atr_value=parsed_signal['atr_value'],
                tp_price_offset=tp_params['tp_price_offset'],
                tp_multiplier=tp_params['tp_multiplier'],
                signal_id=signal_id,
                leverage=DEFAULT_LEVERAGE,
                margin_type=parsed_signal['margin_type'],
                opposite=parsed_signal['opposite'],
                precision=parsed_signal['precision'],
                position_side=parsed_signal['position_side'],
                strategy_name=parsed_signal['strategy_name'],
                is_add_position=position_decision['is_add_position'],
                expiry_time=expiry_time
            )
            
            # 計算執行延遲
            execution_delay_ms = int((time.time() - signal_start_time) * 1000)
            
            if order_result and order_result.get('status') == 'success':
                return {
                    "status": "success",
                    "message": f"訂單創建成功 - {parsed_signal['symbol']} {parsed_signal['side']}",
                    "symbol": parsed_signal['symbol'],
                    "side": parsed_signal['side'],
                    "quantity": parsed_signal['quantity'],
                    "price": parsed_signal['price'],
                    "order_id": order_result['order_id'],
                    "client_order_id": client_order_id,
                    "atr_value": parsed_signal['atr_value'],
                    "tp_price_offset": tp_params['tp_price_offset'],
                    "tp_multiplier": tp_params['tp_multiplier'],
                    "operation_type": "加倉" if position_decision['is_add_position'] else "新開倉",
                    "expiry_time": datetime.fromtimestamp(expiry_time/1000).strftime('%Y-%m-%d %H:%M:%S'),
                    "execution_delay_ms": execution_delay_ms,
                    "timeout_minutes": timeout_minutes,
                    "signal_id": signal_id,
                    "is_discount_strategy": price_info.get('is_discount_strategy', False),
                    "cost_savings": price_info.get('discount_amount', 0)
                }
            else:
                # 下單失敗，更新狀態
                order_manager.orders[client_order_id]['status'] = 'FAILED'
                return {"status": "error", "message": "下單失敗", "signal_id": signal_id}
                
        except Exception as e:
            logger.error(f"創建訂單時出錯: {str(e)}")
            logger.error(traceback.format_exc())
            return {"status": "error", "message": str(e), "signal_id": signal_id}
    
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
    
    def get_signal_id_by_order_id(self, client_order_id):
        """根據訂單ID獲取信號ID"""
        return self.signal_order_mapping.get(client_order_id)
    
    def get_shadow_statistics(self):
        """獲取影子模式統計"""
        try:
            if self.shadow_engine:
                return self.shadow_engine.get_shadow_statistics()
            else:
                return {"error": "影子決策引擎未載入"}
        except Exception as e:
            logger.error(f"獲取影子統計時出錯: {str(e)}")
            return {"error": str(e)}

# 創建全局信號處理器實例
signal_processor = SignalProcessor()
