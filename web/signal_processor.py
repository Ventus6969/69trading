"""
交易信號處理模組 - 完整修復版本
處理來自TradingView的交易信號，修復所有方法錯誤，整合ML特徵計算和影子決策
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
    """交易信號處理器 - 完整修復版本"""
    
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
    
    def _execute_shadow_decision(self, session_id: str, signal_id: int, features: dict, signal_data: dict):
        """
        🤖 執行影子模式決策分析
        
        Args:
            session_id: 會話ID
            signal_id: 信號ID  
            features: ML特徵字典
            signal_data: 原始信號數據
            
        Returns:
            dict: 影子決策結果
        """
        try:
            logger.info(f"🤖 開始影子模式決策分析 - signal_id: {signal_id}")
            
            # 檢查影子決策引擎是否可用
            if not self.shadow_engine:
                logger.warning("影子決策引擎未載入，跳過影子決策")
                return {"error": "影子決策引擎未載入"}
            
            # 執行影子決策
            shadow_result = self.shadow_engine.make_shadow_decision(session_id, signal_id, features, signal_data)
            
            # 🔥 修復：使用正確的方法名稱
            success = ml_data_manager.record_signal_quality_assessment(
                session_id, signal_id, shadow_result
            )
            
            if success:
                logger.info(f"✅ 影子決策已記錄 - signal_id: {signal_id}")
            else:
                logger.warning(f"⚠️ 影子決策記錄失敗 - signal_id: {signal_id}")
            
            # 詳細的影子決策日誌
            self._log_shadow_decision(shadow_result, signal_data)
            
            return shadow_result
            
        except Exception as e:
            logger.error(f"❌ 影子決策時出錯: {str(e)}")
            logger.error(f"詳細錯誤: {traceback.format_exc()}")
            # 影子決策錯誤不影響正常交易
            return {"error": str(e)}
    
    def _log_shadow_decision(self, shadow_result: dict, signal_data: dict):
        """記錄詳細的影子決策日誌"""
        try:
            # 基本決策信息
            logger.info(f"🤖 影子模式決策完成:")
            logger.info(f"   信號: {signal_data.get('signal_type')} | opposite: {signal_data.get('opposite')} | 交易對: {signal_data.get('symbol')}")
            logger.info(f"   建議: {shadow_result.get('recommendation', 'UNKNOWN')}")
            logger.info(f"   信心度: {shadow_result.get('confidence_score', 0):.1%}")
            logger.info(f"   執行概率: {shadow_result.get('execution_probability', 0):.1%}")
            logger.info(f"   理由: {shadow_result.get('reason', '無理由')}")
            logger.info(f"   方法: {shadow_result.get('decision_method', 'UNKNOWN')}")
            
            # 對比實際決策
            logger.info(f"📊 影子vs實際決策對比:")
            logger.info(f"   信號: {signal_data.get('symbol')} {signal_data.get('signal_type')} (opposite={signal_data.get('opposite')})")
            logger.info(f"   🤖 影子建議: {shadow_result.get('recommendation', 'UNKNOWN')}")
            logger.info(f"   🎯 實際決策: EXECUTE (系統總是執行)")
            logger.info(f"   🔍 影子理由: {shadow_result.get('reason', '無理由')}")
            logger.info(f"   📈 信心度: {shadow_result.get('confidence_score', 0):.1%}")
            
            # 根據一致性給出不同的警告
            if shadow_result.get('recommendation') == 'SKIP':
                logger.warning(f"⚠️ 影子建議跳過但系統將執行 - 需要關注結果")
            else:
                logger.info(f"✅ 影子建議與實際決策一致")
                
            logger.info(f"🤖 本次交易的影子決策建議已記錄，後續將對比實際結果")
            
        except Exception as e:
            logger.error(f"記錄影子決策日誌時出錯: {str(e)}")
    
    def _parse_signal_data(self, signal_data):
        """解析和處理信號數據"""
        try:
            # 提取基本信號信息
            symbol = signal_data['symbol']
            side = signal_data['side']
            signal_type = signal_data.get('signal_type', '')
            quantity = signal_data['quantity']
            opposite = int(signal_data.get('opposite', 0))
            strategy_name = signal_data.get('strategy_name', 'UNKNOWN')
            
            # 獲取價格數據
            open_price = float(signal_data['open'])
            close_price = float(signal_data['close'])
            prev_close = float(signal_data.get('prev_close', close_price))
            prev_open = float(signal_data.get('prev_open', open_price))
            atr_value = float(signal_data.get('ATR', 1.0))
            
            # 獲取交易對精度
            precision = get_symbol_precision(symbol)
            
            # 計算開倉價格
            price_info = self._calculate_entry_price(signal_type, opposite, open_price, close_price, prev_close, prev_open, precision)
            
            # 獲取止盈倍數
            tp_multiplier = get_tp_multiplier(signal_type)
            
            return {
                'symbol': symbol,
                'side': side,
                'signal_type': signal_type,
                'quantity': quantity,
                'price': price_info['price'],
                'order_type': 'LIMIT',
                'opposite': opposite,
                'strategy_name': strategy_name,
                'open_price': open_price,
                'close_price': close_price,
                'prev_close': prev_close,
                'prev_open': prev_open,
                'atr_value': atr_value,
                'precision': precision,
                'tp_multiplier': tp_multiplier,
                'position_side': 'BOTH',
                'margin_type': 'isolated',
                'price_info': price_info
            }
            
        except Exception as e:
            logger.error(f"解析信號數據時出錯: {str(e)}")
            raise
    
    def _calculate_entry_price(self, signal_type, opposite, open_price, close_price, prev_close, prev_open, precision):
        """計算開倉價格"""
        price_info = {
            'is_discount_strategy': False,
            'strategy_description': '',
            'base_price': 0,
            'discount_percentage': 0,
            'discount_amount': 0
        }
        
        try:
            if opposite == 0:
                # 使用當前收盤價
                calculated_price = close_price
                price_info['strategy_description'] = '當前收盤價'
                price_info['base_price'] = close_price
                
            elif opposite == 1:
                # reversal_buy專用：前根收盤價-1%
                if signal_type == 'reversal_buy':
                    base_price = prev_close
                    discount_percentage = 1.0
                    discount_amount = base_price * (discount_percentage / 100)
                    calculated_price = base_price - discount_amount
                    
                    # 記錄價格信息
                    price_info.update({
                        'is_discount_strategy': True,
                        'strategy_description': 'reversal_buy低1%策略',
                        'base_price': base_price,
                        'discount_percentage': discount_percentage,
                        'discount_amount': discount_amount
                    })
                else:
                    # 其他策略使用前根收盤價
                    calculated_price = prev_close
                    price_info['strategy_description'] = '前根收盤價'
                    price_info['base_price'] = prev_close
                    
            elif opposite == 2:
                # 使用前根開盤價
                calculated_price = prev_open
                price_info['strategy_description'] = '前根開盤價'
                price_info['base_price'] = prev_open
                
            else:
                # 默認使用當前收盤價
                calculated_price = close_price
                price_info['strategy_description'] = '默認當前收盤價'
                price_info['base_price'] = close_price
            
            # 四捨五入到指定精度
            final_price = calculate_price_with_precision(calculated_price, precision)
            price_info['price'] = final_price
            
            return price_info
            
        except Exception as e:
            logger.error(f"計算開倉價格時出錯: {str(e)}")
            # 返回安全的默認價格
            price_info['price'] = calculate_price_with_precision(close_price, precision)
            price_info['strategy_description'] = '錯誤時默認價格'
            return price_info
    
    def _check_position_conflict(self, parsed_signal):
        """檢查現有倉位衝突"""
        try:
            symbol = parsed_signal['symbol']
            side = parsed_signal['side']
            
            # 檢查是否已有持倉
            current_position = position_manager.get_position_info(symbol)
            
            if current_position is None:
                # 沒有持倉，可以正常開倉
                return {
                    'action': 'execute',
                    'is_add_position': False,
                    'reason': f'{symbol} 無現有持倉，準備新開倉'
                }
            
            current_side = current_position.get('side')
            new_direction = 'LONG' if side == 'BUY' else 'SHORT'
            
            if current_side == new_direction:
                # 同方向，執行加倉
                logger.info(f"{symbol} 檢測到同方向持倉，執行加倉操作")
                return {
                    'action': 'execute',
                    'is_add_position': True,
                    'reason': f'{symbol} 同方向持倉，執行加倉'
                }
            else:
                # 反方向，忽略信號
                logger.warning(f"{symbol} 檢測到反方向持倉，忽略信號")
                return {
                    'action': 'ignore',
                    'message': f'{symbol} 存在反方向持倉 ({current_side})，忽略 {new_direction} 信號',
                    'status': 'ignored',
                    'current_position': current_side,
                    'signal_direction': new_direction
                }
                
        except Exception as e:
            logger.error(f"檢查倉位衝突時出錯: {str(e)}")
            # 發生錯誤時，為安全起見，假設無持倉
            return {
                'action': 'execute',
                'is_add_position': False,
                'reason': f'檢查持倉時出錯，假設無持倉執行'
            }
    
    def _setup_trading_parameters(self, parsed_signal):
        """設置交易參數"""
        try:
            symbol = parsed_signal['symbol']
            
            # 設置槓桿
            leverage_result = binance_client.set_leverage(symbol, DEFAULT_LEVERAGE)
            if leverage_result:
                logger.info(f"設置槓桿響應: {leverage_result}")
            
            # 設置保證金模式
            margin_result = binance_client.set_margin_type(symbol, parsed_signal['margin_type'])
            if margin_result:
                logger.info(f"設置保證金模式響應: {margin_result}")
                
        except Exception as e:
            logger.error(f"設置交易參數時出錯: {str(e)}")
    
    def _calculate_tp_parameters(self, parsed_signal):
        """計算止盈參數"""
        try:
            atr_value = parsed_signal['atr_value']
            tp_multiplier = parsed_signal['tp_multiplier']
            
            # 使用ATR計算止盈偏移量
            tp_price_offset = atr_value * tp_multiplier
            
            logger.info(f"使用ATR止盈: ATR={atr_value}, 倍數={tp_multiplier}, 偏移={tp_price_offset}")
            
            return {
                'tp_price_offset': tp_price_offset,
                'tp_multiplier': tp_multiplier
            }
            
        except Exception as e:
            logger.error(f"計算止盈參數時出錯: {str(e)}")
            # 返回默認值
            return {
                'tp_price_offset': float(parsed_signal['price']) * TP_PERCENTAGE,
                'tp_multiplier': 1.0
            }
    
    def _save_webhook_data(self, parsed_signal, tp_params, shadow_result):
        """保存webhook數據"""
        try:
            self.last_webhook_data = {
                'signal': parsed_signal,
                'tp_params': tp_params,
                'shadow_decision': shadow_result,
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            
            logger.info("Webhook數據已保存（包含影子決策）")
            
        except Exception as e:
            logger.error(f"保存webhook數據時出錯: {str(e)}")
    
    def _create_and_execute_order(self, parsed_signal, tp_params, position_decision, signal_id, signal_start_time):
        """創建並執行訂單 - 修復HTTP 500錯誤版本"""
        try:
            # 🔥 修復1：確保交易方向是大寫
            parsed_signal['side'] = parsed_signal['side'].upper()

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
                'timeout_minutes': timeout_minutes,
                'position_side': parsed_signal['position_side'],
                'is_add_position': position_decision['is_add_position'],
                'expiry_time': expiry_time
            }
            
            # 保存訂單信息到order_manager
            order_manager.save_order_info(client_order_id, order_data)
            
            # 🔥 修復2：使用正確的方法名稱和參數，添加必要的 time_in_force
            order_result = order_manager.create_order(
                symbol=parsed_signal['symbol'],
                side=parsed_signal['side'],
                order_type=parsed_signal['order_type'],
                quantity=parsed_signal['quantity'],
                price=parsed_signal['price'],
                client_order_id=client_order_id,
                position_side=parsed_signal['position_side'],
                time_in_force='GTC'  # 🔥 添加必要的參數
            )
            
            # 計算執行延遲
            execution_delay_ms = int((time.time() - signal_start_time) * 1000)
            
            # 🔥 修復3：正確判斷API返回結果
            if order_result:  # 只要API有返回就算成功
                # 記錄詳細的成功信息
                logger.info(f"✅ 下單成功 - 訂單ID: {order_result.get('orderId')}, 狀態: {order_result.get('status')}")
                
                # 記錄訂單到資料庫
                trading_data_manager.record_order_executed(signal_id, order_data)
                
                return {
                    "status": "success",
                    "message": f"訂單創建成功 - {parsed_signal['symbol']} {parsed_signal['side']}",
                    "symbol": parsed_signal['symbol'],
                    "side": parsed_signal['side'],
                    "quantity": parsed_signal['quantity'],
                    "price": parsed_signal['price'],
                    "order_id": order_result.get('orderId', 'UNKNOWN'),  # 🔥 使用正確的字段名
                    "client_order_id": client_order_id,
                    "binance_status": order_result.get('status', 'UNKNOWN'),  # 🔥 記錄實際API狀態
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
                logger.error(f"❌ 下單失敗 - API無返回")
                if client_order_id in order_manager.orders:
                    order_manager.orders[client_order_id]['status'] = 'FAILED'
                return {
                    "status": "error", 
                    "message": "下單失敗 - API無返回", 
                    "signal_id": signal_id,
                    "client_order_id": client_order_id,
                    "error_type": "API_NO_RESPONSE"
                }
        
        except Exception as e:
            logger.error(f"❌ 創建訂單時出錯: {str(e)}")
            logger.error(traceback.format_exc())
            return {
                "status": "error", 
                "message": f"下單異常: {str(e)}", 
                "signal_id": signal_id,
                "error_type": "EXCEPTION",
                "error_details": str(e)
            }
    
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

