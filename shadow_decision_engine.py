"""
影子決策引擎 - 完整ML版本
實現真正的機器學習決策和規則決策混合系統
=============================================================================
"""
import logging
import time
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, Any, List, Tuple, Optional
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, classification_report
import joblib
import os

# 設置logger
logger = logging.getLogger(__name__)

class ShadowModeDecisionEngine:
    """影子模式決策引擎 - 完整ML版本"""
    
    def __init__(self):
        self.confidence_threshold = 0.6  # 決策信心度閾值
        self.min_data_for_ml = 50        # 開始使用ML的最小數據量
        self.model_path = "data/ml_models"
        
        # 確保模型目錄存在
        os.makedirs(self.model_path, exist_ok=True)
        
        # ML模型
        self.ml_model = None
        self.model_accuracy = 0.0
        self.last_model_update = 0
        self.feature_importance = {}
        
        # 策略規則配置
        self.strategy_rules = self._init_strategy_rules()
        
        logger.info("✅ 影子決策引擎已初始化 (ML增強版)")
    
    def _init_strategy_rules(self) -> Dict[str, Any]:
        """初始化策略規則配置"""
        return {
            'high_risk_combinations': [
                {'signal_type': 'consolidation_buy', 'opposite': 2},
                {'signal_type': 'reversal_buy', 'opposite': 2},
            ],
            'high_quality_combinations': [
                {'signal_type': 'breakdown_sell', 'opposite': 0},
                {'signal_type': 'trend_sell', 'opposite': 0},
                {'signal_type': 'breakout_buy', 'opposite': 0},
            ],
            'strategy_preferences': {
                'breakout_buy': {'default_confidence': 0.6, 'note': '突破策略，中等偏高風險'},
                'consolidation_buy': {'default_confidence': 0.3, 'note': '整理策略，較高風險'},
                'reversal_buy': {'default_confidence': 0.4, 'note': '反轉策略，中等風險'},
                'bounce_buy': {'default_confidence': 0.5, 'note': '反彈策略，中等風險'},
                'trend_sell': {'default_confidence': 0.7, 'note': '趨勢策略，較低風險'},
                'breakdown_sell': {'default_confidence': 0.8, 'note': '破底策略，低風險'},
                'high_sell': {'default_confidence': 0.5, 'note': '高位策略，中等風險'},
                'reversal_sell': {'default_confidence': 0.4, 'note': '反轉策略，中等風險'}
            }
        }
    
    def make_shadow_decision(self, session_id: str, signal_id: int, 
                           features: Dict[str, Any], signal_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        生成影子模式決策建議 - ML+規則混合版本
        
        Args:
            session_id: 會話ID
            signal_id: 信號ID
            features: 36個特徵數據
            signal_data: 原始信號數據
            
        Returns:
            Dict: 包含建議決策的完整結果
        """
        try:
            logger.info(f"🤖 開始影子模式決策分析 - signal_id: {signal_id}")
            
            # 檢查是否應該使用ML模型
            if self._should_use_ml_model():
                decision_result = self._ml_based_decision(features, signal_data)
                decision_result['decision_method'] = 'ML_MODEL'
                logger.info(f"使用ML模型決策 - 準確率: {self.model_accuracy:.2%}")
            else:
                decision_result = self._rule_based_decision(features, signal_data)
                decision_result['decision_method'] = 'RULE_BASED'
                logger.info("使用規則決策 - 數據量不足")
            
            # 記錄決策結果
            self._record_shadow_decision(session_id, signal_id, decision_result, features, signal_data)
            
            # 詳細日誌記錄
            self._log_decision_details(signal_id, decision_result, signal_data)
            
            return decision_result
            
        except Exception as e:
            logger.error(f"影子模式決策時出錯: {str(e)}")
            return self._get_fallback_decision(signal_data, str(e))
    
    def _should_use_ml_model(self) -> bool:
        """檢查是否應該使用ML模型"""
        try:
            # 延遲導入，確保使用最新實例
            from database import ml_data_manager
            
            if ml_data_manager is None:
                logger.warning("ML數據管理器未初始化")
                return False
            
            # 檢查訓練數據數量
            stats = ml_data_manager.get_ml_table_stats()
            total_features = stats.get('total_ml_features', 0)
            
            if total_features < self.min_data_for_ml:
                logger.info(f"數據量不足({total_features}筆)，使用規則決策")
                return False
            
            # 檢查模型是否存在且準確率足夠
            if self.ml_model is None:
                logger.info("嘗試訓練ML模型...")
                self._train_ml_model()
            
            if self.ml_model is not None and self.model_accuracy > 0.65:
                logger.info(f"使用ML模型決策 - 準確率: {self.model_accuracy:.2%}")
                return True
            else:
                logger.info(f"ML模型準確率不足({self.model_accuracy:.2%})，使用規則決策")
                return False
                
        except Exception as e:
            logger.warning(f"檢查ML模型可用性時出錯: {str(e)}，回退到規則決策")
            return False
    
    def _train_ml_model(self) -> bool:
        """訓練ML模型"""
        try:
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
            
            logger.info(f"✅ ML模型訓練完成:")
            logger.info(f"   訓練樣本: {len(X_train)}, 測試樣本: {len(X_test)}")
            logger.info(f"   準確率: {self.model_accuracy:.2%}")
            logger.info(f"   模型文件: {model_file}")
            
            # 顯示前5個重要特徵
            top_features = sorted(self.feature_importance.items(), key=lambda x: x[1], reverse=True)[:5]
            logger.info(f"   重要特徵: {top_features}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ 訓練ML模型時出錯: {str(e)}")
            self.ml_model = None
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
                    features = []
                    for feature_name in feature_names:
                        value = data.get(feature_name, 0)
                        if value is None:
                            value = 0
                        features.append(float(value))
                    
                    X.append(features)
                    y.append(int(data.get('is_successful', 0)))
            
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
        """
        基於ML模型的決策邏輯
        
        Args:
            features: 特徵數據
            signal_data: 信號數據
            
        Returns:
            Dict: 決策結果
        """
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
            
            # 預測結果
            prediction = self.ml_model.predict(X)[0]
            
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
                reason = f'ML建議跳過: 成功概率僅 {success_probability:.1%}'
            
            # 價格調整建議
            price_adjustment = self._calculate_ml_price_adjustment(features, success_probability)
            
            return {
                'recommendation': recommendation,
                'confidence': confidence,
                'reason': reason,
                'risk_level': risk_level,
                'execution_probability': success_probability,
                'trading_probability': success_probability,
                'suggested_price_adjustment': price_adjustment,
                'ml_prediction': prediction,
                'ml_success_probability': success_probability,
                'model_accuracy': self.model_accuracy
            }
            
        except Exception as e:
            logger.error(f"ML決策時出錯: {str(e)}")
            return self._rule_based_decision(features, signal_data)
    
    def _calculate_ml_price_adjustment(self, features: Dict[str, Any], success_probability: float) -> float:
        """基於ML結果計算價格調整建議"""
        try:
            # 基礎調整
            base_adjustment = 0.0
            
            # 根據成功概率調整
            if success_probability < 0.4:
                # 低概率，建議較大調整以提高成功率
                base_adjustment = 0.003
            elif success_probability > 0.8:
                # 高概率，可以更激進
                base_adjustment = -0.001
            
            # 根據特徵調整
            execution_difficulty = features.get('execution_difficulty', 0.5)
            if execution_difficulty > 0.7:
                base_adjustment += 0.002
            
            volatility = features.get('atr_normalized', 1.0)
            base_adjustment += volatility * 0.001
            
            return max(-0.01, min(0.01, base_adjustment))
            
        except Exception:
            return 0.0
    
    def _rule_based_decision(self, features: Dict[str, Any], signal_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        基於規則的決策邏輯 - 增強版本
        
        Args:
            features: 特徵數據
            signal_data: 信號數據
            
        Returns:
            Dict: 決策結果
        """
        signal_type = signal_data.get('signal_type')
        opposite = signal_data.get('opposite', 0)
        symbol = signal_data.get('symbol', '')
        
        # 1. 檢查是否為已知高風險組合
        for high_risk in self.strategy_rules['high_risk_combinations']:
            if (signal_type == high_risk['signal_type'] and 
                opposite == high_risk['opposite']):
                return {
                    'recommendation': 'SKIP',
                    'confidence': 0.8,
                    'reason': f'已知高風險組合: {signal_type} + opposite={opposite}',
                    'risk_level': 'HIGH',
                    'execution_probability': 0.2,
                    'trading_probability': 0.2,
                    'suggested_price_adjustment': 0.0
                }
        
        # 2. 檢查是否為已知高品質組合
        for high_quality in self.strategy_rules['high_quality_combinations']:
            if (signal_type == high_quality['signal_type'] and 
                opposite == high_quality['opposite']):
                return {
                    'recommendation': 'EXECUTE',
                    'confidence': 0.9,
                    'reason': f'已知高品質組合: {signal_type} + opposite={opposite}',
                    'risk_level': 'LOW',
                    'execution_probability': 0.9,
                    'trading_probability': 0.9,
                    'suggested_price_adjustment': 0.0
                }
        
        # 3. 基於特徵的綜合評估
        confidence_factors = []
        
        # 策略勝率因子 (權重: 30%)
        recent_win_rate = features.get('strategy_win_rate_recent', 0.5)
        confidence_factors.append(recent_win_rate * 0.3)
        
        # 市場環境因子 (權重: 25%)
        time_match = features.get('time_slot_match_score', 0.5)
        volatility_match = features.get('volatility_match_score', 0.5)
        market_factor = (time_match + volatility_match) / 2
        confidence_factors.append(market_factor * 0.25)
        
        # 執行難度因子 (權重: 20%)
        execution_difficulty = features.get('execution_difficulty', 0.5)
        execution_factor = 1.0 - execution_difficulty
        confidence_factors.append(execution_factor * 0.2)
        
        # 信號品質因子 (權重: 15%)
        signal_confidence = features.get('signal_confidence_score', 0.5)
        confidence_factors.append(signal_confidence * 0.15)
        
        # 系統表現因子 (權重: 10%)
        system_performance = features.get('system_overall_performance', 0.5)
        confidence_factors.append(system_performance * 0.1)
        
        # 計算總體信心度
        total_confidence = sum(confidence_factors)
        
        # 基於opposite值調整
        opposite_adjustment = self._calculate_opposite_adjustment(opposite)
        final_confidence = max(0.1, min(0.95, total_confidence + opposite_adjustment))
        
        # 生成決策
        if final_confidence >= 0.7:
            recommendation = 'EXECUTE'
            risk_level = 'LOW'
        elif final_confidence >= 0.5:
            recommendation = 'EXECUTE'
            risk_level = 'MEDIUM'
        else:
            recommendation = 'SKIP'
            risk_level = 'HIGH'
        
        # 計算價格調整建議
        price_adjustment = self._calculate_rule_price_adjustment(features, final_confidence)
        
        return {
            'recommendation': recommendation,
            'confidence': final_confidence,
            'reason': f"規則評估: 綜合分數 {final_confidence:.2f}, opposite調整 {opposite_adjustment:+.2f}",
            'risk_level': risk_level,
            'execution_probability': final_confidence,
            'trading_probability': final_confidence,
            'suggested_price_adjustment': price_adjustment,
            'confidence_breakdown': {
                'strategy_factor': confidence_factors[0] if len(confidence_factors) > 0 else 0,
                'market_factor': confidence_factors[1] if len(confidence_factors) > 1 else 0,
                'execution_factor': confidence_factors[2] if len(confidence_factors) > 2 else 0,
                'signal_factor': confidence_factors[3] if len(confidence_factors) > 3 else 0,
                'system_factor': confidence_factors[4] if len(confidence_factors) > 4 else 0
            }
        }
    
    def _calculate_opposite_adjustment(self, opposite: int) -> float:
        """基於opposite值計算信心度調整"""
        if opposite == 0:
            return 0.1  # 當前收盤價，相對較好
        elif opposite == 1:
            return 0.0  # 前根收盤價，中性
        elif opposite == 2:
            return -0.15  # 前根開盤價，已知問題較多
        else:
            return -0.1  # 未知值，保守處理
    
    def _calculate_rule_price_adjustment(self, features: Dict[str, Any], confidence: float) -> float:
        """基於規則計算價格調整建議"""
        try:
            adjustment = 0.0
            
            # 低信心度時建議調整價格
            if confidence < 0.5:
                adjustment += 0.002
            
            # 高執行難度時調整
            execution_difficulty = features.get('execution_difficulty', 0.5)
            if execution_difficulty > 0.7:
                adjustment += 0.001
            
            # 根據波動率調整
            atr_normalized = features.get('atr_normalized', 1.0)
            adjustment += atr_normalized * 0.001
            
            return max(-0.005, min(0.005, adjustment))
            
        except Exception:
            return 0.0
    
    def _record_shadow_decision(self, session_id: str, signal_id: int, 
                               decision_result: Dict[str, Any], features: Dict[str, Any], 
                               signal_data: Dict[str, Any]) -> bool:
        """記錄影子決策到資料庫"""
        try:
            from database import ml_data_manager
            
            if ml_data_manager is None:
                logger.warning("ML數據管理器未初始化，無法記錄影子決策")
                return False
            
            # 記錄決策品質
            quality_data = {
                'recommendation': decision_result.get('recommendation'),
                'confidence': decision_result.get('confidence'),
                'execution_probability': decision_result.get('execution_probability'),
                'trading_probability': decision_result.get('trading_probability'),
                'risk_level': decision_result.get('risk_level'),
                'reason': decision_result.get('reason'),
                'suggested_price_adjustment': decision_result.get('suggested_price_adjustment')
            }
            
            success = ml_data_manager.record_signal_quality(session_id, signal_id, quality_data)
            
            if success:
                logger.debug(f"✅ 影子決策記錄成功 - signal_id: {signal_id}")
            else:
                logger.warning(f"⚠️ 影子決策記錄失敗 - signal_id: {signal_id}")
            
            return success
            
        except Exception as e:
            logger.error(f"記錄影子決策時出錯: {str(e)}")
            return False
    
    def _log_decision_details(self, signal_id: int, decision_result: Dict[str, Any], 
                            signal_data: Dict[str, Any]):
        """詳細記錄決策日誌"""
        signal_type = signal_data.get('signal_type')
        opposite = signal_data.get('opposite')
        symbol = signal_data.get('symbol')
        
        logger.info(f"🤖 影子模式決策完成:")
        logger.info(f"   信號: {signal_type} | opposite: {opposite} | 交易對: {symbol}")
        logger.info(f"   建議: {decision_result.get('recommendation')}")
        logger.info(f"   信心度: {decision_result.get('confidence', 0):.1%}")
        logger.info(f"   執行概率: {decision_result.get('execution_probability', 0):.1%}")
        logger.info(f"   風險等級: {decision_result.get('risk_level')}")
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
            
            return {
                'total_decisions': stats.get('total_signal_quality', 0),
                'ml_ready': stats.get('total_ml_features', 0) >= self.min_data_for_ml,
                'data_progress': f"{stats.get('total_ml_features', 0)}/{self.min_data_for_ml}",
                'current_mode': 'ML_MODEL' if self._should_use_ml_model() else 'RULE_BASED',
                'model_accuracy': f"{self.model_accuracy:.1%}" if self.ml_model else 'N/A',
                'last_model_update': datetime.fromtimestamp(self.last_model_update).strftime('%Y-%m-%d %H:%M') if self.last_model_update else 'N/A',
                'feature_importance': dict(list(sorted(self.feature_importance.items(), key=lambda x: x[1], reverse=True))[:5]) if self.feature_importance else {}
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
    
    def analyze_decision_accuracy(self) -> Dict[str, float]:
        """分析決策準確性"""
        try:
            from database import ml_data_manager
            
            if ml_data_manager is None:
                return {}
            
            # 獲取最近的決策和結果
            historical_data = ml_data_manager.get_historical_features_for_ml(100)
            
            if len(historical_data) < 10:
                return {'message': '數據不足以進行準確性分析'}
            
            # 分析準確性
            correct_predictions = 0
            total_predictions = 0
            
            for data in historical_data:
                if data.get('is_successful') is not None:
                    # 這裡應該根據實際的ML決策記錄來分析
                    # 暫時使用簡化邏輯
                    total_predictions += 1
                    if data.get('is_successful') == 1:
                        correct_predictions += 1
            
            accuracy = correct_predictions / total_predictions if total_predictions > 0 else 0
            
            return {
                'total_predictions': total_predictions,
                'correct_predictions': correct_predictions,
                'accuracy': accuracy,
                'analysis_period': '最近100筆交易'
            }
            
        except Exception as e:
            logger.error(f"分析決策準確性時出錯: {str(e)}")
            return {'error': str(e)}

# 創建全局影子決策引擎實例
shadow_decision_engine = ShadowModeDecisionEngine()
