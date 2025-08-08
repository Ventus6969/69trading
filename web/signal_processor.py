"""
交易信號處理模組 - 完整ML集成版本
修復所有ML功能，實現真正的智能學習系統
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
    """交易信號處理器 - 完整ML集成版本"""
    
    def __init__(self):
        # 用於存儲最近的webhook數據
        self.last_webhook_data = None
        # 用於追蹤信號ID和訂單ID的對應關係
        self.signal_order_mapping = {}
        
        # 延遲導入影子決策引擎，避免循環依賴
        self.shadow_engine = None
        self._init_shadow_engine()
        
        # ML系統狀態
        self.ml_initialized = False
        self._check_ml_system()
    
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
    
    def _check_ml_system(self):
        """檢查ML系統狀態"""
        try:
            if ml_data_manager is not None:
                # 測試ML功能
                test_features = ml_data_manager._get_default_features()
                if len(test_features) == 36:
                    self.ml_initialized = True
                    logger.info("✅ ML系統已初始化並可用")
                else:
                    logger.warning("⚠️ ML系統特徵數量不正確")
            else:
                logger.warning("⚠️ ML數據管理器未初始化")
                self._retry_ml_initialization()
        except Exception as e:
            logger.error(f"❌ 檢查ML系統時出錯: {str(e)}")
            self._retry_ml_initialization()
    
    def _retry_ml_initialization(self):
        """重新嘗試初始化ML系統"""
        try:
            logger.info("🔄 嘗試重新初始化ML系統...")
            
            # 重新檢查ML數據管理器
            global ml_data_manager
            from database import ml_data_manager
            
            if ml_data_manager is not None:
                # 測試ML功能
                test_features = ml_data_manager._get_default_features()
                if len(test_features) == 36:
                    self.ml_initialized = True
                    logger.info("✅ ML系統重新初始化成功")
                    return True
                else:
                    logger.warning("⚠️ ML系統特徵數量仍不正確")
                    return False
            else:
                logger.warning("⚠️ ML數據管理器仍未可用")
                return False
                
        except Exception as e:
            logger.error(f"❌ ML系統重新初始化失敗: {str(e)}")
            return False
    
    def process_signal(self, signal_data):
        """
        處理TradingView交易信號 - 🛡️ 強化錯誤處理避免HTTP 500
        """
        signal_start_time = time.time()
        signal_id = None
        
        try:
            logger.info("🚀 開始處理交易信號...")
            
            # === 1. 驗證數據 ===
            logger.info("🔍 步驟1: 開始驗證數據...")
            is_valid, error_msg = validate_signal_data(signal_data)
            if not is_valid:
                logger.error(f"❌ 數據驗證失敗: {error_msg}")
                return {"status": "error", "message": f"數據驗證失敗: {error_msg}", "error_type": "validation"}
            logger.info("✅ 步驟1: 數據驗證通過")
            
            # === 2. 立即記錄接收到的信號 ===
            logger.info("🔍 步驟2: 開始記錄信號...")
            try:
                signal_id = trading_data_manager.record_signal_received(signal_data)
                logger.info(f"✅ 步驟2: 信號已記錄到資料庫，ID: {signal_id}")
            except Exception as e:
                logger.error(f"⚠️ 信號記錄失敗但繼續處理: {e}")
                # 信號記錄失敗不應該阻止後續處理
            
            # === 3. 🧠 ML特徵計算和記錄 ===
            logger.info("🔍 步驟3: 開始ML特徵計算...")
            session_id = f"session_{int(time.time())}"
            try:
                features = self._calculate_and_record_ml_features(session_id, signal_id, signal_data)
                logger.info("✅ 步驟3: ML特徵計算完成")
            except Exception as e:
                logger.warning(f"⚠️ ML特徵計算失敗，使用默認特徵: {e}")
                features = self._get_safe_default_features()
            
            # === 4. 🤖 影子模式決策分析 ===
            logger.info("🔍 步驟4: 開始影子決策分析...")
            try:
                shadow_result = self._execute_shadow_decision(session_id, signal_id, features, signal_data)
                logger.info("✅ 步驟4: 影子決策分析完成")
            except Exception as e:
                logger.warning(f"⚠️ 影子決策失敗，使用默認決策: {e}")
                shadow_result = self._get_fallback_shadow_result()
            
            # === 5. 解析和處理信號 ===
            logger.info("🔍 步驟5: 開始解析信號數據...")
            try:
                parsed_signal = self._parse_signal_data(signal_data)
                logger.info("✅ 步驟5: 信號解析完成")
            except ValueError as ve:
                # 業務邏輯錯誤 - 返回400避免重試
                logger.error(f"❌ 信號解析失敗: {ve}")
                return {"status": "error", "message": str(ve), "error_type": "business", "signal_id": signal_id}
            except Exception as e:
                # 系統錯誤
                logger.error(f"❌ 信號解析系統錯誤: {e}")
                return {"status": "error", "message": f"信號解析系統錯誤: {str(e)}", "error_type": "system", "signal_id": signal_id}
            
            # === 6. 檢查交易時間 ===
            logger.info("🔍 步驟6: 開始檢查交易時間...")
            if not self._check_trading_time():
                logger.warning("⚠️ 當前時間不允許交易，返回blocked狀態")
                return {"status": "blocked", "message": "當前時間不允許交易", "signal_id": signal_id}
            logger.info("✅ 步驟6: 交易時間檢查通過")
            
            # === 7. 決定持倉動作 ===
            logger.info("🔍 步驟7: 開始決定持倉動作...")
            try:
                position_decision = self._decide_position_action(parsed_signal)
                logger.info(f"✅ 步驟7: 持倉動作決定完成 - {position_decision}")
            except Exception as e:
                logger.warning(f"⚠️ 持倉檢查失敗，使用默認開倉: {e}")
                position_decision = 'open'
            
            # === 8. 設置交易參數 ===
            logger.info("🔍 步驟8: 開始設置交易參數...")
            try:
                self._setup_trading_parameters(parsed_signal)
                logger.info("✅ 步驟8: 交易參數設置完成")
            except Exception as e:
                logger.warning(f"⚠️ 交易參數設置失敗但繼續: {e}")
            
            # === 9. 計算止盈參數 ===
            logger.info("🔍 步驟9: 開始計算止盈參數...")
            try:
                tp_params = self._calculate_tp_parameters(parsed_signal)
                logger.info("✅ 步驟9: 止盈參數計算完成")
            except Exception as e:
                logger.warning(f"⚠️ 止盈參數計算失敗，使用默認值: {e}")
                tp_params = {'tp_percentage': TP_PERCENTAGE, 'min_tp_percentage': MIN_TP_PROFIT_PERCENTAGE}
            
            # === 10. 🔄 ML模型維護 ===
            logger.info("🔍 步驟10: 開始ML模型維護...")
            try:
                self._maintain_ml_system()
                logger.info("✅ 步驟10: ML模型維護完成")
            except Exception as e:
                logger.warning(f"⚠️ ML模型維護失敗: {e}")
            
            # === 11. 保存webhook數據 ===
            logger.info("🔍 步驟11: 開始保存webhook數據...")
            try:
                self._save_webhook_data(parsed_signal, tp_params, shadow_result)
                logger.info("✅ 步驟11: webhook數據保存完成")
            except Exception as e:
                logger.warning(f"⚠️ webhook數據保存失敗: {e}")
            
            # === 12. 生成訂單（實際交易邏輯不變） ===
            logger.info("🔍 步驟12: 開始創建和執行訂單...")
            try:
                order_result = self._create_and_execute_order(parsed_signal, tp_params, position_decision, signal_id, signal_start_time)
                logger.info("✅ 步驟12: 訂單創建和執行完成")
            except Exception as e:
                logger.error(f"❌ 訂單執行失敗: {e}")
                return {"status": "error", "message": f"訂單執行失敗: {str(e)}", "error_type": "trading", "signal_id": signal_id}
            
            # === 13. 在結果中包含ML信息 ===
            logger.info("🔍 步驟13: 開始處理返回結果...")
            if isinstance(order_result, dict):
                order_result['shadow_decision'] = shadow_result
                order_result['ml_features_count'] = len([k for k, v in features.items() if v is not None])
                order_result['ml_system_ready'] = self.ml_initialized
            
            logger.info(f"🎯 信號處理完成 - 耗時: {(time.time() - signal_start_time)*1000:.0f}ms")
            logger.info(f"🔍 最終返回結果: {order_result}")
            return order_result
            
        except ValueError as ve:
            # 業務邏輯錯誤 - 返回400狀態避免TradingView重試
            logger.error(f"❌ 業務邏輯錯誤: {str(ve)}")
            return {"status": "error", "message": str(ve), "error_type": "business", "signal_id": signal_id}
        except Exception as e:
            # 系統錯誤 - 返回500但已有去重機制防護
            logger.error(f"❌ 處理交易信號時出錯: {str(e)}")
            logger.error(traceback.format_exc())
            return {"status": "error", "message": f"系統錯誤: {str(e)}", "error_type": "system", "signal_id": signal_id}
    
    def _calculate_and_record_ml_features(self, session_id: str, signal_id: int, signal_data: dict):
        """
        🧠 計算並記錄ML特徵 - 完整功能版本
        
        Args:
            session_id: 會話ID
            signal_id: 信號ID
            signal_data: 原始信號數據
            
        Returns:
            dict: 計算的特徵字典
        """
        try:
            logger.info(f"🧠 開始計算ML特徵 - session_id: {session_id}, signal_id: {signal_id}")
            
            # 🔥 檢查ML系統狀態
            if not self.ml_initialized or ml_data_manager is None:
                logger.warning("⚠️ ML數據管理器未初始化，嘗試重新初始化...")
                if not self._retry_ml_initialization():
                    logger.error("❌ ML重新初始化失敗，使用默認特徵")
                    return self._get_safe_default_features()

            # 🧠 計算完整的36個特徵
            features = ml_data_manager.calculate_basic_features(signal_data)
            
            # 🔍 驗證特徵完整性
            expected_features = 36
            actual_features = len([k for k, v in features.items() if v is not None])
            
            if actual_features < expected_features:
                logger.warning(f"⚠️ 特徵計算不完整: {actual_features}/{expected_features}")
                # 補充缺失特徵
                default_features = ml_data_manager._get_default_features()
                for key, default_value in default_features.items():
                    if key not in features or features[key] is None:
                        features[key] = default_value
            
            # 📊 記錄特徵到資料庫
            success = ml_data_manager.record_ml_features(session_id, signal_id, features)
            
            if success:
                logger.info(f"✅ ML特徵計算並記錄成功 - 信號ID: {signal_id}")
                
                # 記錄關鍵特徵值用於調試
                key_features = {
                    'strategy_win_rate_recent': features.get('strategy_win_rate_recent'),
                    'hour_of_day': features.get('hour_of_day'),
                    'symbol_category': features.get('symbol_category'),
                    'candle_direction': features.get('candle_direction'),
                    'risk_reward_ratio': features.get('risk_reward_ratio'),
                    'execution_difficulty': features.get('execution_difficulty'),
                    'signal_confidence_score': features.get('signal_confidence_score')
                }
                logger.info(f"🔍 關鍵特徵值: {key_features}")
            else:
                logger.warning(f"⚠️ ML特徵記錄失敗 - 信號ID: {signal_id}")
            
            return features
                
        except Exception as e:
            logger.error(f"❌ 計算ML特徵時出錯: {str(e)}")
            logger.error(traceback.format_exc())
            return self._get_safe_default_features()
    
    def _execute_shadow_decision(self, session_id: str, signal_id: int, features: dict, signal_data: dict):
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
            logger.info(f"🤖 開始影子模式決策分析...")
            
            if self.shadow_engine is None:
                logger.warning("⚠️ 影子決策引擎未初始化")
                return self._get_fallback_shadow_result()
            
            # 執行影子決策
            shadow_result = self.shadow_engine.make_shadow_decision(
                session_id, signal_id, features, signal_data
            )
            
            # 記錄決策統計
            self._log_shadow_decision_summary(shadow_result, signal_data)
            
            return shadow_result
            
        except Exception as e:
            logger.error(f"❌ 影子決策分析時出錯: {str(e)}")
            return self._get_fallback_shadow_result()
    
    def _maintain_ml_system(self):
        """🔄 ML系統維護"""
        try:
            if self.shadow_engine is not None:
                # 檢查是否需要重新訓練模型
                self.shadow_engine.retrain_model_if_needed()
                
        except Exception as e:
            logger.error(f"ML系統維護時出錯: {str(e)}")
    
    def _log_shadow_decision_summary(self, shadow_result: dict, signal_data: dict):
        """記錄影子決策摘要"""
        try:
            signal_type = signal_data.get('signal_type', 'unknown')
            symbol = signal_data.get('symbol', 'unknown')
            recommendation = shadow_result.get('recommendation', 'UNKNOWN')
            confidence = shadow_result.get('confidence', 0)
            method = shadow_result.get('decision_method', 'UNKNOWN')
            
            logger.info(f"🤖 影子決策摘要:")
            logger.info(f"   策略: {signal_type} | 交易對: {symbol}")
            logger.info(f"   建議: {recommendation} | 信心度: {confidence:.1%}")
            logger.info(f"   方法: {method}")
            
            # 如果是SKIP建議，記錄原因
            if recommendation == 'SKIP':
                reason = shadow_result.get('reason', '未知原因')
                logger.info(f"   跳過原因: {reason}")
            
            # 如果有價格調整建議
            price_adj = shadow_result.get('suggested_price_adjustment', 0)
            if abs(price_adj) > 0.001:
                logger.info(f"   價格調整建議: {price_adj:+.3%}")
                
        except Exception as e:
            logger.debug(f"記錄影子決策摘要時出錯: {str(e)}")
    
    def _get_safe_default_features(self):
        """獲取安全的默認特徵（當ML系統失敗時使用）"""
        return {
            # 信號品質核心特徵 (15個)
            'strategy_win_rate_recent': 0.5,
            'strategy_win_rate_overall': 0.5,
            'strategy_market_fitness': 0.5,
            'volatility_match_score': 0.5,
            'time_slot_match_score': 0.5,
            'symbol_match_score': 0.5,
            'price_momentum_strength': 0.5,
            'atr_relative_position': 0.5,
            'risk_reward_ratio': 2.5,
            'execution_difficulty': 0.5,
            'consecutive_win_streak': 0,
            'consecutive_loss_streak': 0,
            'system_overall_performance': 0.5,
            'signal_confidence_score': 0.5,
            'market_condition_fitness': 0.5,
            # 價格關係特徵 (12個)
            'price_deviation_percent': 0.0,
            'price_deviation_abs': 0.0,
            'atr_normalized_deviation': 0.0,
            'candle_direction': 0,
            'candle_body_size': 0.0,
            'candle_wick_ratio': 0.5,
            'price_position_in_range': 0.5,
            'upward_adjustment_space': 0.02,
            'downward_adjustment_space': 0.02,
            'historical_best_adjustment': 0.0,
            'price_reachability_score': 0.7,
            'entry_price_quality_score': 0.6,
            # 市場環境特徵 (9個)
            'hour_of_day': datetime.now().hour,
            'trading_session': 1,
            'weekend_factor': 1 if datetime.now().weekday() >= 5 else 0,
            'symbol_category': 4,
            'current_positions': 0,
            'margin_ratio': 0.5,
            'atr_normalized': 0.01,
            'volatility_regime': 1,
            'market_trend_strength': 0.5
        }
    
    def _get_fallback_shadow_result(self):
        """獲取回退的影子決策結果"""
        return {
            'recommendation': 'EXECUTE',
            'confidence': 0.5,
            'reason': '影子系統未初始化，使用默認決策',
            'risk_level': 'MEDIUM',
            'execution_probability': 0.5,
            'trading_probability': 0.5,
            'suggested_price_adjustment': 0.0,
            'decision_method': 'FALLBACK'
        }
    
    # === 核心信號處理方法 ===
    
    def _parse_signal_data(self, signal_data):
        """解析信號數據 - 🛡️ 強化錯誤處理"""
        try:
            # 🛡️ 1: 確保 side 轉為大寫（Binance API要求）
            side = signal_data.get('side', '').upper()
            if side not in ['BUY', 'SELL']:
                raise ValueError(f"無效的交易方向: {signal_data.get('side')}")
            
            # 🛡️ 2: 正確提取和轉換 opposite 參數
            opposite_raw = signal_data.get('opposite', 0)
            try:
                if isinstance(opposite_raw, str):
                    opposite = int(opposite_raw)
                else:
                    opposite = int(opposite_raw)
            except (ValueError, TypeError):
                logger.warning(f"⚠️ 無效的opposite值: {opposite_raw}，使用默認值0")
                opposite = 0
            
            # 🛡️ 3: 提取其他必要參數
            symbol = signal_data.get('symbol')
            signal_type = signal_data.get('signal_type')
            
            if not symbol:
                raise ValueError("缺少必要的symbol參數")
            if not signal_type:
                raise ValueError("缺少必要的signal_type參數")
            
            # 🛡️ 4: 正確提取 order_type
            order_type = signal_data.get('order_type', 'MARKET').upper()
            
            # 🛡️ 5: 根據 order_type 和 opposite 決定價格 - 增強錯誤處理
            price = None
            price_source = "市價單"
            
            if order_type == 'LIMIT':
                # 限價單需要價格，根據 opposite 參數選擇正確的價格欄位
                if opposite == 0:
                    # 當前收盤價模式
                    raw_price = signal_data.get('close')
                    if raw_price:
                        try:
                            price = float(raw_price)
                            price_source = "close (當前收盤價)"
                        except (ValueError, TypeError):
                            logger.warning(f"⚠️ 無效的close價格: {raw_price}")
                            
                elif opposite == 1:
                    # 🎯 reversal_buy專用：前根收盤價-1%折扣策略
                    raw_base_price = signal_data.get('prev_close')
                    if raw_base_price:
                        try:
                            base_price = float(raw_base_price)
                            if base_price > 0 and signal_type == 'reversal_buy':
                                # reversal_buy策略使用1%折扣
                                discount_amount = base_price * 0.01
                                price = base_price - discount_amount
                                
                                # 🛡️ 根據交易對調整價格精度 - 防止精度錯誤
                                try:
                                    precision = get_symbol_precision(symbol)
                                    price = round(price, precision)  # 使用正確的交易對精度
                                        
                                    price_source = f"reversal_buy低1%策略 ({base_price:.6f} - {discount_amount:.6f} = {price:.{precision}f})"
                                except Exception as pe:
                                    logger.error(f"❌ 價格精度處理錯誤: {pe}")
                                    price = base_price  # 回退到原價
                                    price_source = "prev_close (回退)"
                            else:
                                # 其他策略使用前根收盤價
                                price = base_price
                                price_source = "prev_close (前根收盤價)"
                        except (ValueError, TypeError):
                            logger.warning(f"⚠️ 無效的prev_close價格: {raw_base_price}")
                            
                elif opposite == 2:
                    # 前根開盤價模式
                    raw_price = signal_data.get('prev_open')
                    if raw_price:
                        try:
                            price = float(raw_price)
                            price_source = "prev_open (前根開盤價)"
                        except (ValueError, TypeError):
                            logger.warning(f"⚠️ 無效的prev_open價格: {raw_price}")
                else:
                    # 未知模式，使用當前收盤價作為備案
                    raw_price = signal_data.get('close')
                    if raw_price:
                        try:
                            price = float(raw_price)
                            price_source = "close (備案:當前收盤價)"
                        except (ValueError, TypeError):
                            pass
                    logger.warning(f"⚠️ 未知的opposite值: {opposite}，嘗試使用當前收盤價作為備案")
                
                # 🛡️ 價格有效性檢查
                if not price or price <= 0:
                    logger.warning(f"⚠️ 限價單缺少有效價格 (來源: {price_source})，改為市價單")
                    order_type = 'MARKET'
                    price = None
                    price_source = "市價單 (限價失效回退)"
                else:
                    logger.info(f"🔍 限價單價格來源: {price_source} = {price}")
            
            # 記錄調試信息
            logger.info(f"🔍 opposite 原始值: {opposite_raw} -> 解析值: {opposite}")
            logger.info(f"🔍 order_type 原始值: {signal_data.get('order_type')} -> 解析值: {order_type}")
            logger.info(f"🔍 調用 get_tp_multiplier({symbol}, opposite={opposite}, signal_type={signal_type})")
            
            # 🛡️ 6: 正確調用 get_tp_multiplier 並傳遞所有參數
            try:
                tp_multiplier = get_tp_multiplier(symbol, opposite, signal_type)
            except Exception as e:
                logger.error(f"❌ 計算tp_multiplier時出錯: {e}")
                tp_multiplier = 1.0  # 使用默認倍數
            
            parsed = {
                'symbol': symbol,
                'side': side,  # 🛡️ 使用大寫的 side
                'signal_type': signal_type,
                'strategy_name': signal_data.get('strategy_name'),  # 🛡️ 新增：strategy_name 字段
                'quantity': signal_data.get('quantity'),
                'price': price,  # 🛡️ 根據 order_type 決定價格
                'order_type': order_type,  # 🛡️ 新增：order_type 字段
                'opposite': opposite,  # 🛡️ 使用正確轉換的 opposite
                'atr': float(signal_data.get('ATR', 0)) if signal_data.get('ATR') else None,
                'precision': get_symbol_precision(symbol),
                'tp_multiplier': tp_multiplier  # 🛡️ 使用正確計算的倍數
            }
            
            logger.info(f"📋 信號解析完成: {parsed['symbol']} {parsed['side']} {parsed['signal_type']} ({parsed['order_type']}) - 價格來源: {price_source}")
            return parsed
            
        except ValueError as ve:
            # 業務邏輯錯誤，返回明確的錯誤信息
            logger.error(f"❌ 信號數據驗證失敗: {str(ve)}")
            raise ValueError(f"信號數據驗證失敗: {str(ve)}")
        except Exception as e:
            # 系統錯誤
            logger.error(f"❌ 解析信號數據時出錯: {str(e)}")
            logger.error(traceback.format_exc())
            raise RuntimeError(f"信號處理系統錯誤: {str(e)}")

    def _check_trading_time(self):
        """檢查是否在允許交易的時間內 - 🔥 修復邏輯和參數"""
        try:
            # 🔥 修復：移除多餘的 TW_TIMEZONE 參數
            is_blocked = is_within_time_range(
                TRADING_BLOCK_START_HOUR, 
                TRADING_BLOCK_START_MINUTE,
                TRADING_BLOCK_END_HOUR, 
                TRADING_BLOCK_END_MINUTE
            )
            
            # 🔥 注意：is_within_time_range 返回 True 表示在禁止時間內
            # 所以我們需要反轉邏輯
            if is_blocked:
                logger.warning("⚠️ 當前時間處於禁止交易時段，返回blocked狀態")
                return False
            else:
                logger.info("✅ 當前時間允許交易")
                return True
                
        except Exception as e:
            logger.error(f"檢查交易時間時出錯: {str(e)}")
            return True  # 默認允許交易
    
    def _decide_position_action(self, parsed_signal):
        """決定持倉動作"""
        try:
            # 獲取當前持倉
            current_positions = binance_client.get_current_positions()
            symbol = parsed_signal['symbol']
            
            logger.info(f"🔍 持倉查詢完成 - 檢查 {symbol} 持倉狀態")
            
            current_position = next((pos for pos in current_positions if pos['symbol'] == symbol), None)
            
            if current_position and float(current_position['positionAmt']) != 0:
                position_amt = float(current_position['positionAmt'])
                logger.info(f"🔍 檢測到現有持倉: {position_amt}, 執行加倉邏輯")
                return 'add'
            else:
                logger.info(f"🔍 持倉查詢完成 - 無活躍持倉")
                logger.info("無現有持倉，執行開倉邏輯")
                return 'open'
                
        except Exception as e:
            logger.error(f"決定持倉動作時出錯: {str(e)}")
            return 'open'  # 默認開倉
    
    def _setup_trading_parameters(self, parsed_signal):
        """設置交易參數"""
        try:
            # 設置槓桿
            leverage_result = binance_client.set_leverage(parsed_signal['symbol'], DEFAULT_LEVERAGE)
            logger.info(f"槓桿設置: {leverage_result}")  # ✅ 直接記錄 bool 結果
            
            # 設置保證金模式為逐倉
            margin_result = binance_client.set_margin_type(parsed_signal['symbol'], 'ISOLATED')
            logger.info(f"保證金模式: {margin_result}")  # ✅ 直接記錄 bool 結果
            
        except Exception as e:
            logger.warning(f"設置交易參數時出錯: {str(e)}")
    
    def _calculate_tp_parameters(self, parsed_signal):
        """計算止盈參數"""
        try:
            tp_percentage = TP_PERCENTAGE * parsed_signal['tp_multiplier']
            min_tp_percentage = MIN_TP_PROFIT_PERCENTAGE
            
            if tp_percentage < min_tp_percentage:
                tp_percentage = min_tp_percentage
                logger.warning(f"止盈百分比過低，調整為最小值: {min_tp_percentage}%")
            
            return {
                'tp_percentage': tp_percentage,
                'min_tp_percentage': min_tp_percentage
            }
            
        except Exception as e:
            logger.error(f"計算止盈參數時出錯: {str(e)}")
            return {'tp_percentage': TP_PERCENTAGE, 'min_tp_percentage': MIN_TP_PROFIT_PERCENTAGE}
    
    def _save_webhook_data(self, parsed_signal, tp_params, shadow_result):
        """保存webhook數據"""
        try:
            self.last_webhook_data = {
                'signal': parsed_signal,
                'tp_params': tp_params,
                'shadow_result': shadow_result,
                'timestamp': time.time()
            }
            logger.debug("Webhook數據已保存")
            
        except Exception as e:
            logger.warning(f"保存webhook數據時出錯: {str(e)}")
    
    def _create_and_execute_order(self, parsed_signal, tp_params, position_decision, signal_id, signal_start_time):
        """創建和執行訂單"""
        try:
            # 記錄訂單信息
            logger.info(f"已保存訂單信息: {parsed_signal.get('symbol')}_{parsed_signal.get('side')}")
            
            # 根據持倉決策選擇訂單管理方法
            if position_decision == 'add':
                result = order_manager.handle_add_position_order(parsed_signal, tp_params['tp_percentage'])
            else:
                result = order_manager.handle_new_position_order(parsed_signal, tp_params['tp_percentage'])
            
            # 記錄訂單執行
            if result.get('status') == 'success' and signal_id:
                order_data = {
                    'client_order_id': result.get('client_order_id'),
                    'symbol': parsed_signal['symbol'],
                    'side': parsed_signal['side'],
                    'order_type': 'MARKET',
                    'quantity': result.get('quantity'),
                    'price': result.get('filled_price'),
                    'leverage': DEFAULT_LEVERAGE,
                    'execution_delay_ms': int((time.time() - signal_start_time) * 1000),
                    'binance_order_id': result.get('binance_order_id'),
                    'status': result.get('status').upper(),
                    'is_add_position': position_decision == 'add',
                    'tp_client_id': result.get('tp_client_id'),
                    'tp_price': result.get('tp_price')
                }
                
                trading_data_manager.record_order_executed(signal_id, order_data)
                self.signal_order_mapping[signal_id] = result.get('client_order_id')
            
            return result
            
        except Exception as e:
            logger.error(f"創建和執行訂單時出錯: {str(e)}")
            return {"status": "error", "message": str(e)}
    
    def get_last_webhook_data(self):
        """獲取最後的webhook數據"""
        return self.last_webhook_data
    
    def get_ml_system_status(self):
        """獲取ML系統狀態"""
        try:
            status = {
                'ml_initialized': self.ml_initialized,
                'ml_data_manager_available': ml_data_manager is not None,
                'shadow_engine_available': self.shadow_engine is not None
            }
            
            if self.shadow_engine:
                shadow_stats = self.shadow_engine.get_shadow_statistics()
                status.update(shadow_stats)
            
            if ml_data_manager:
                ml_stats = ml_data_manager.get_ml_table_stats()
                status.update(ml_stats)
            
            return status
            
        except Exception as e:
            logger.error(f"獲取ML系統狀態時出錯: {str(e)}")
            return {'error': str(e)}

# 創建全局信號處理器實例
signal_processor = SignalProcessor()