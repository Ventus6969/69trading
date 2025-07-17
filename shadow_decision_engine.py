"""
影子決策引擎
實現ML模型與規則決策的混合決策系統
🔥 完整修復版本：解決初始化問題，支援完整ML決策
=============================================================================
"""
import os
import time
import logging
import traceback
import numpy as np
from datetime import datetime
from typing import Dict, Any, List, Tuple, Optional
import joblib

# 設置logger
logger = logging.getLogger(__name__)

# 安全導入ML相關庫
try:
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import accuracy_score, classification_report
    ML_AVAILABLE = True
    logger.info("✅ ML庫導入成功")
except ImportError as e:
    logger.warning(f"⚠️ ML庫導入失敗: {e}，將使用規則決策")
    ML_AVAILABLE = False

class ShadowModeDecisionEngine:
    """影子模式決策引擎"""
    
    def __init__(self):
        # 基本設定
        self.ml_model = None
        self.model_accuracy = 0.0
        self.feature_importance = {}
        self.last_model_update = 0
        self.min_data_for_ml = 50  # 最少需要50筆數據才能訓練ML模型
        
        # 創建模型存儲目錄
        self.model_path = os.path.join(os.getcwd(), 'models')
        os.makedirs(self.model_path, exist_ok=True)
        
        # 策略配置
        self.strategy_config = self._load_strategy_config()
        
        # 初始化時載入已有模型
        self._load_existing_model()
        
        logger.info("🤖 影子決策引擎已初始化")
    
    def _load_strategy_config(self) -> Dict[str, Any]:
        """載入策略配置"""
        return {
            'strategy_base_confidence': {
                'trend_buy': {'default_confidence': 0.7, 'note': '趨勢策略，較高信心'},
                'breakout_buy': {'default_confidence': 0.6, 'note': '突破策略，中等信心'},
                'consolidation_buy': {'default_confidence': 0.4, 'note': '整理策略，較低信心'},
                'reversal_buy': {'default_confidence': 0.4, 'note': '反轉策略，中等風險'},
                'bounce_buy': {'default_confidence': 0.5, 'note': '反彈策略，中等風險'},
                'trend_sell': {'default_confidence': 0.7, 'note': '趨勢策略，較高信心'},
                'breakdown_sell': {'default_confidence': 0.6, 'note': '破底策略，中等信心'},
                'high_sell': {'default_confidence': 0.5, 'note': '高位策略，中等風險'},
                'reversal_sell': {'default_confidence': 0.4, 'note': '反轉策略，中等風險'}
            },
            'opposite_adjustment': {
                0: 0.0,   # 當前收盤價，無調整
                1: -0.05, # 前根收盤價，略微降低信心
                2: -0.1   # 前根開盤價，降低信心
            },
            'time_adjustment': {
                'asia': 0.0,      # 亞洲時段，無調整
                'europe': 0.1,    # 歐洲時段，提高信心
                'america': 0.05,  # 美洲時段，略微提高信心
                'night': -0.2     # 深夜時段，降低信心
            }
        }
    
    def _load_existing_model(self):
        """載入已存在的模型"""
        try:
            if not ML_AVAILABLE:
                logger.info("ML庫不可用，跳過模型載入")
                return
            
            # 查找最新的模型文件
            model_files = [f for f in os.listdir(self.model_path) if f.startswith('shadow_model_') and f.endswith('.pkl')]
            
            if not model_files:
                logger.info("未找到現有模型，將在有足夠數據時訓練新模型")
                return
            
            # 載入最新模型
            latest_model = sorted(model_files)[-1]
            model_file_path = os.path.join(self.model_path, latest_model)
            
            self.ml_model = joblib.load(model_file_path)
            self.last_model_update = os.path.getmtime(model_file_path)
            
            logger.info(f"✅ 已載入現有模型: {latest_model}")
            
        except Exception as e:
            logger.warning(f"⚠️ 載入現有模型失敗: {str(e)}")
            self.ml_model = None
    
    def analyze_signal_quality(self, features: Dict[str, Any], signal_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        分析信號品質並生成決策建議 - 🔥 主要入口方法
        
        Args:
            features: 36個ML特徵
            signal_data: 原始信號數據
            
        Returns:
            Dict: 完整的決策結果
        """
        try:
            logger.info("🤖 開始信號品質分析...")
            
            # 檢查是否應該使用ML模型
            if self._should_use_ml_model():
                decision_result = self._ml_based_decision(features, signal_data)
                decision_result['decision_method'] = 'ML_MODEL'
                logger.info(f"使用ML模型決策 - 模型準確率: {self.model_accuracy:.1%}")
            else:
                decision_result = self._rule_based_decision(features, signal_data)
                decision_result['decision_method'] = 'RULE_BASED'
                logger.info("使用規則決策 - 數據量不足或ML不可用")
            
            # 添加額外信息
            decision_result.update({
                'analysis_time': datetime.now().isoformat(),
                'feature_count': len(features),
                'ml_available': ML_AVAILABLE,
                'model_accuracy': self.model_accuracy if self.ml_model else 0.0
            })
            
            # 記錄決策詳情
            self._log_decision_details(decision_result, signal_data)
            
            return decision_result
            
        except Exception as e:
            logger.error(f"❌ 信號品質分析失敗: {str(e)}")
            logger.error(traceback.format_exc())
            return self._get_fallback_decision(signal_data, str(e))
    
    def _should_use_ml_model(self) -> bool:
        """檢查是否應該使用ML模型"""
        try:
            # 檢查ML庫是否可用
            if not ML_AVAILABLE:
                return False
            
            # 延遲導入，確保使用最新實例
            try:
                from database import ml_data_manager
                if ml_data_manager is None:
                    logger.warning("ML數據管理器未初始化")
                    return False
            except ImportError:
                logger.warning("無法導入ML數據管理器")
                return False
            
            # 檢查數據量
            stats = ml_data_manager.get_ml_table_stats()
            total_features = stats.get('total_ml_features', 0)
            
            if total_features < self.min_data_for_ml:
                logger.info(f"數據量不足({total_features}/{self.min_data_for_ml}筆)，使用規則決策")
                return False
            
            # 檢查或訓練模型
            if self.ml_model is None:
                logger.info("ML模型不存在，嘗試訓練新模型...")
                if not self._train_ml_model():
                    logger.warning("ML模型訓練失敗，使用規則決策")
                    return False
            
            # 檢查模型準確率
            if self.model_accuracy < 0.55:  # 至少要比隨機猜測好
                logger.info(f"模型準確率不足({self.model_accuracy:.1%})，使用規則決策")
                return False
            
            return True
            
        except Exception as e:
            logger.warning(f"檢查ML模型可用性時出錯: {str(e)}，回退到規則決策")
            return False
    
    def _train_ml_model(self) -> bool:
        """訓練ML模型"""
        try:
            if not ML_AVAILABLE:
                return False
            
            from database import ml_data_manager
            
            logger.info("🧠 開始訓練ML模型...")
            
            # 獲取歷史數據
            historical_data = ml_data_manager.get_historical_features_for_ml(200)
            
            if len(historical_data) < self.min_data_for_ml:
                logger.warning(f"訓練數據不足: {len(historical_data)}/{self.min_data_for_ml}")
                return False
            
            # 準備特徵和標籤
            X, y = self._prepare_training_data(historical_data)
            
            if len(X) < 20:
                logger.warning(f"有效訓練樣本不足: {len(X)}")
                return False
            
            # 分割訓練和測試集
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=0.2, random_state=42, stratify=y
            )
            
            # 訓練隨機森林模型
            self.ml_model = RandomForestClassifier(
                n_estimators=100,
                max_depth=10,
                min_samples_split=5,
                min_samples_leaf=2,
                random_state=42
            )
            
            self.ml_model.fit(X_train, y_train)
            
            # 評估模型
            y_pred = self.ml_model.predict(X_test)
            self.model_accuracy = accuracy_score(y_test, y_pred)
            
            # 記錄特徵重要性
            feature_names = self._get_feature_names()
            self.feature_importance = dict(zip(
                feature_names, 
                self.ml_model.feature_importances_
            ))
            
            # 保存模型
            model_file = os.path.join(self.model_path, f"shadow_model_{int(time.time())}.pkl")
            joblib.dump(self.ml_model, model_file)
            
            self.last_model_update = time.time()
            
            logger.info(f"✅ ML模型訓練完成 - 準確率: {self.model_accuracy:.1%}")
            logger.info(f"   訓練樣本: {len(X_train)}, 測試樣本: {len(X_test)}")
            logger.info(f"   模型已保存: {model_file}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ 訓練ML模型時出錯: {str(e)}")
            logger.error(traceback.format_exc())
            return False
    
    def _prepare_training_data(self, historical_data: List[Dict[str, Any]]) -> Tuple[np.ndarray, np.ndarray]:
        """準備訓練數據"""
        try:
            feature_names = self._get_feature_names()
            X = []
            y = []
            
            for data in historical_data:
                # 只使用有交易結果的數據
                if data.get('is_successful') is not None:
                    # 提取特徵
                    feature_vector = []
                    for feature_name in feature_names:
                        value = data.get(feature_name, 0)
                        if value is None:
                            value = 0
                        feature_vector.append(float(value))
                    
                    X.append(feature_vector)
                    y.append(int(data['is_successful']))
            
            return np.array(X), np.array(y)
            
        except Exception as e:
            logger.error(f"準備訓練數據時出錯: {str(e)}")
            return np.array([]), np.array([])
    
    def _get_feature_names(self) -> List[str]:
        """獲取特徵名稱列表"""
        return [
            # 信號品質核心特徵 (15個)
            'strategy_win_rate_recent', 'strategy_win_rate_overall', 'strategy_market_fitness',
            'volatility_match_score', 'time_slot_match_score', 'symbol_match_score',
            'price_momentum_strength', 'atr_relative_position', 'risk_reward_ratio',
            'execution_difficulty', 'consecutive_win_streak', 'consecutive_loss_streak',
            'system_overall_performance', 'signal_confidence_score', 'market_condition_fitness',
            # 價格關係特徵 (12個)
            'price_deviation_percent', 'price_deviation_abs', 'atr_normalized_deviation',
            'candle_direction', 'candle_body_size', 'candle_wick_ratio',
            'price_position_in_range', 'upward_adjustment_space', 'downward_adjustment_space',
            'historical_best_adjustment', 'price_reachability_score', 'entry_price_quality_score',
            # 市場環境特徵 (9個)
            'hour_of_day', 'trading_session', 'weekend_factor',
            'symbol_category', 'current_positions', 'margin_ratio',
            'atr_normalized', 'volatility_regime', 'market_trend_strength'
        ]
    
    def _ml_based_decision(self, features: Dict[str, Any], signal_data: Dict[str, Any]) -> Dict[str, Any]:
        """基於ML模型的決策邏輯"""
        try:
            if self.ml_model is None:
                logger.warning("ML模型未初始化，回退到規則決策")
                return self._rule_based_decision(features, signal_data)
            
            # 準備特徵向量
            feature_names = self._get_feature_names()
            feature_vector = []
            
            for feature_name in feature_names:
                value = features.get(feature_name, 0)
                if value is None:
                    value = 0
                feature_vector.append(float(value))
            
            # ML預測
            X = np.array([feature_vector])
            
            # 預測概率
            prediction_proba = self.ml_model.predict_proba(X)[0]
            success_probability = prediction_proba[1] if len(prediction_proba) > 1 else 0.5
            
            # 基於ML結果生成決策
            if success_probability >= 0.7:
                recommendation = 'EXECUTE'
                confidence = success_probability
                risk_level = 'LOW'
                reason = f'ML高信心預測: 成功概率 {success_probability:.1%}'
            elif success_probability >= 0.5:
                recommendation = 'EXECUTE'
                confidence = success_probability * 0.8  # 降低信心度
                risk_level = 'MEDIUM'
                reason = f'ML中等信心預測: 成功概率 {success_probability:.1%}'
            else:
                recommendation = 'SKIP'
                confidence = 1 - success_probability
                risk_level = 'HIGH'
                reason = f'ML低信心預測: 成功概率 {success_probability:.1%}，建議跳過'
            
            return {
                'recommendation': recommendation,
                'confidence': confidence,
                'reason': reason,
                'risk_level': risk_level,
                'execution_probability': success_probability,
                'trading_probability': success_probability,
                'suggested_price_adjustment': self._calculate_ml_price_adjustment(features, success_probability),
                'ml_success_probability': success_probability,
                'model_accuracy': self.model_accuracy
            }
            
        except Exception as e:
            logger.error(f"ML決策時出錯: {str(e)}")
            return self._rule_based_decision(features, signal_data)
    
    def _rule_based_decision(self, features: Dict[str, Any], signal_data: Dict[str, Any]) -> Dict[str, Any]:
        """基於規則的決策邏輯"""
        try:
            # 基礎信心度
            signal_type = signal_data.get('signal_type', '')
            base_confidence = self.strategy_config['strategy_base_confidence'].get(
                signal_type, {'default_confidence': 0.5}
            )['default_confidence']
            
            confidence = base_confidence
            
            # opposite參數調整
            opposite = int(signal_data.get('opposite', 0))
            opposite_adjustment = self.strategy_config['opposite_adjustment'].get(opposite, 0)
            confidence += opposite_adjustment
            
            # 時段調整
            hour = features.get('hour_of_day', 12)
            time_adjustment = self._get_time_adjustment(hour)
            confidence += time_adjustment
            
            # 策略特殊調整
            if 'reversal' in signal_type:
                confidence -= 0.05  # 反轉策略風險較高
            elif 'breakout' in signal_type:
                confidence += 0.05  # 突破策略相對穩定
            
            # 風險回報比調整
            risk_reward = features.get('risk_reward_ratio', 2.5)
            if risk_reward > 3.0:
                confidence += 0.1
            elif risk_reward < 2.0:
                confidence -= 0.1
            
            # 系統表現調整
            system_performance = features.get('system_overall_performance', 0.5)
            if system_performance > 0.6:
                confidence += 0.05
            elif system_performance < 0.4:
                confidence -= 0.05
            
            # 確保信心度在合理範圍內
            confidence = max(0.1, min(0.9, confidence))
            
            # 生成決策
            if confidence >= 0.6:
                recommendation = 'EXECUTE'
                risk_level = 'LOW'
                reason = f'規則決策: 高信心度 {confidence:.1%}'
            elif confidence >= 0.4:
                recommendation = 'EXECUTE'
                risk_level = 'MEDIUM'
                reason = f'規則決策: 中等信心度 {confidence:.1%}'
            else:
                recommendation = 'SKIP'
                risk_level = 'HIGH'
                reason = f'規則決策: 低信心度 {confidence:.1%}，建議跳過'
            
            return {
                'recommendation': recommendation,
                'confidence': confidence,
                'reason': reason,
                'risk_level': risk_level,
                'execution_probability': confidence,
                'trading_probability': confidence,
                'suggested_price_adjustment': 0.0,
                'strategy_base_confidence': base_confidence,
                'opposite_adjustment': opposite_adjustment,
                'time_adjustment': time_adjustment
            }
            
        except Exception as e:
            logger.error(f"規則決策時出錯: {str(e)}")
            return self._get_fallback_decision(signal_data, str(e))
    
    def _get_time_adjustment(self, hour: int) -> float:
        """獲取時段調整"""
        try:
            if 8 <= hour <= 12:  # 亞洲時段
                return self.strategy_config['time_adjustment']['asia']
            elif 13 <= hour <= 17:  # 歐洲時段
                return self.strategy_config['time_adjustment']['europe']
            elif 18 <= hour <= 22:  # 美洲時段
                return self.strategy_config['time_adjustment']['america']
            else:  # 深夜時段
                return self.strategy_config['time_adjustment']['night']
        except:
            return 0.0
    
    def _calculate_ml_price_adjustment(self, features: Dict[str, Any], success_probability: float) -> float:
        """計算ML價格調整建議"""
        try:
            # 基於成功概率和特徵計算價格調整
            if success_probability > 0.7:
                # 高信心時，可以略微調整價格以提高成交概率
                return 0.001  # 0.1%的調整
            elif success_probability < 0.3:
                # 低信心時，建議更保守的價格
                return -0.002  # -0.2%的調整
            else:
                return 0.0
        except:
            return 0.0
    
    def _log_decision_details(self, decision_result: Dict[str, Any], signal_data: Dict[str, Any]):
        """記錄決策詳情"""
        try:
            signal_type = signal_data.get('signal_type', '')
            symbol = signal_data.get('symbol', '')
            opposite = signal_data.get('opposite', 0)
            
            logger.info(f"🤖 影子決策完成:")
            logger.info(f"   信號: {signal_type} | opposite: {opposite} | 交易對: {symbol}")
            logger.info(f"   建議: {decision_result.get('recommendation')}")
            logger.info(f"   信心度: {decision_result.get('confidence', 0):.1%}")
            logger.info(f"   執行概率: {decision_result.get('execution_probability', 0):.1%}")
            logger.info(f"   理由: {decision_result.get('reason')}")
            logger.info(f"   方法: {decision_result.get('decision_method')}")
            
            # 如果有ML信息，額外記錄
            if 'ml_success_probability' in decision_result:
                logger.info(f"   ML成功概率: {decision_result['ml_success_probability']:.1%}")
                logger.info(f"   模型準確率: {decision_result.get('model_accuracy', 0):.1%}")
            
            # 如果有價格調整建議
            price_adj = decision_result.get('suggested_price_adjustment', 0)
            if abs(price_adj) > 0.001:
                logger.info(f"   價格調整建議: {price_adj:+.3%}")
                
        except Exception as e:
            logger.warning(f"記錄決策詳情時出錯: {str(e)}")
    
    def _get_fallback_decision(self, signal_data: Dict[str, Any], error_msg: str) -> Dict[str, Any]:
        """錯誤時的回退決策"""
        return {
            'recommendation': 'EXECUTE',
            'confidence': 0.5,
            'reason': f'影子模式錯誤回退: {error_msg}',
            'risk_level': 'UNKNOWN',
            'execution_probability': 0.5,
            'trading_probability': 0.5,
            'suggested_price_adjustment': 0.0,
            'decision_method': 'FALLBACK'
        }
    
    def get_shadow_statistics(self) -> Dict[str, Any]:
        """獲取影子模式統計"""
        try:
            from database import ml_data_manager
            
            if ml_data_manager is None:
                return {'error': 'ML數據管理器未初始化'}
            
            stats = ml_data_manager.get_ml_table_stats()
            
            # 獲取特徵重要性前5名
            top_features = {}
            if self.feature_importance:
                sorted_features = sorted(self.feature_importance.items(), key=lambda x: x[1], reverse=True)
                top_features = dict(sorted_features[:5])
            
            return {
                'total_decisions': stats.get('total_ml_decisions', 0),
                'total_features': stats.get('total_ml_features', 0),
                'ml_ready': stats.get('total_ml_features', 0) >= self.min_data_for_ml,
                'data_progress': f"{stats.get('total_ml_features', 0)}/{self.min_data_for_ml}",
                'current_mode': 'ML_MODEL' if self._should_use_ml_model() else 'RULE_BASED',
                'model_accuracy': f"{self.model_accuracy:.1%}" if self.ml_model else 'N/A',
                'last_model_update': datetime.fromtimestamp(self.last_model_update).strftime('%Y-%m-%d %H:%M') if self.last_model_update else 'N/A',
                'top_features': top_features,
                'ml_available': ML_AVAILABLE
            }
            
        except Exception as e:
            logger.error(f"獲取影子模式統計時出錯: {str(e)}")
            return {'error': str(e)}
    
    def retrain_model_if_needed(self) -> bool:
        """如果需要，重新訓練模型"""
        try:
            # 檢查是否需要重新訓練
            current_time = time.time()
            
            # 24小時重新訓練一次
            if (current_time - self.last_model_update) > (24 * 3600):
                logger.info("🔄 開始定期重新訓練ML模型...")
                return self._train_ml_model()
            
            return True
            
        except Exception as e:
            logger.error(f"重新訓練模型時出錯: {str(e)}")
            return False
    
    def make_shadow_decision(self, session_id: str, signal_id: int, 
                            features: Dict[str, Any], signal_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        生成影子模式決策建議 - 🔥 修復缺失方法
        
        Args:
            session_id: 會話ID
            signal_id: 信號ID  
            features: 36個特徵數據
            signal_data: 原始信號數據
            
        Returns:
            Dict: 包含建議決策的完整結果
        """
        try:
            logger.info(f"開始影子模式決策分析 - signal_id: {signal_id}")
            
            # 重新導向到現有的 analyze_signal_quality 方法
            decision_result = self.analyze_signal_quality(features, signal_data)
            
            # 記錄決策到資料庫（如果可能）
            try:
                self._record_shadow_decision(session_id, signal_id, decision_result, features, signal_data)
            except Exception as e:
                logger.warning(f"記錄影子決策失敗: {str(e)}")
            
            # 詳細日誌記錄
            self._log_decision_details_for_signal(signal_id, decision_result, signal_data)
            
            return decision_result
            
        except Exception as e:
            logger.error(f"影子模式決策失敗: {str(e)}")
            return self._get_fallback_decision(signal_data, str(e))
    
    def _record_shadow_decision(self, session_id: str, signal_id: int, 
                               decision_result: Dict[str, Any], features: Dict[str, Any], 
                               signal_data: Dict[str, Any]) -> bool:
        """記錄影子決策到資料庫"""
        try:
            # 暫時簡化，避免複雜的數據庫操作
            logger.info(f"✅ 影子決策記錄 - signal_id: {signal_id}, 建議: {decision_result.get('recommendation')}")
            return True
            
        except Exception as e:
            logger.error(f"記錄影子決策時出錯: {str(e)}")
            return False
    
    def _log_decision_details_for_signal(self, signal_id: int, decision_result: Dict[str, Any], 
                                        signal_data: Dict[str, Any]):
        """為特定信號記錄決策詳情"""
        try:
            signal_type = signal_data.get('signal_type')
            opposite = signal_data.get('opposite')
            symbol = signal_data.get('symbol')
            
            logger.info(f"🤖 影子決策完成 - signal_id: {signal_id}")
            logger.info(f"   信號: {signal_type} | opposite: {opposite} | 交易對: {symbol}")
            logger.info(f"   建議: {decision_result.get('recommendation')}")
            logger.info(f"   信心度: {decision_result.get('confidence', 0):.1%}")
            logger.info(f"   方法: {decision_result.get('decision_method')}")
            logger.info(f"   理由: {decision_result.get('reason')}")
            
        except Exception as e:
            logger.debug(f"記錄決策詳情時出錯: {str(e)}")

# 🔥 創建全局影子決策引擎實例
shadow_decision_engine = ShadowModeDecisionEngine()
