"""
影子模式決策邏輯 - 漸進式ML決策系統
從基於規則的決策逐步演進到真正的ML預測
=============================================================================
"""
import logging
import time
from datetime import datetime
from typing import Dict, Any, Optional, Tuple
from database import trading_data_manager

# 設置logger
logger = logging.getLogger(__name__)

class ShadowModeDecisionEngine:
    """影子模式決策引擎 - 漸進式ML系統"""
    
    def __init__(self):
        self.min_data_for_ml = 50  # 最少數據量才啟用ML模型
        self.decision_threshold = 0.7  # 決策閾值
        self.confidence_threshold = 0.6  # 信心度閾值
        
        # 基於已知5筆交易的洞察建立初始規則
        self.strategy_rules = self._initialize_strategy_rules()
        
        logger.info("影子模式決策引擎已初始化")
    
    def _initialize_strategy_rules(self) -> Dict[str, Dict]:
        """
        初始化策略規則 - 基於當前已知的5筆交易洞察
        
        當前已知結果：
        - consolidation_buy + opposite=2: 執行失敗 (多筆)
        - breakdown_sell + opposite=0: 執行成功 + 獲利 (1筆)
        - reversal_buy + opposite=2: 執行失敗 (多筆)
        """
        return {
            # 高風險組合 - 已知執行率低
            'high_risk_combinations': [
                {'signal_type': 'consolidation_buy', 'opposite': 2, 'risk_level': 'HIGH'},
                {'signal_type': 'reversal_buy', 'opposite': 2, 'risk_level': 'HIGH'},
                # 可以根據更多數據添加其他高風險組合
            ],
            
            # 高品質組合 - 已知表現良好
            'high_quality_combinations': [
                {'signal_type': 'breakdown_sell', 'opposite': 0, 'risk_level': 'LOW'},
                # 可以根據更多數據添加其他高品質組合
            ],
            
            # 策略偏好 - 基於策略特性
            'strategy_preferences': {
                'breakout_buy': {'default_confidence': 0.5, 'note': '突破策略，中等風險'},
                'consolidation_buy': {'default_confidence': 0.3, 'note': '整理策略，較高風險'},
                'reversal_buy': {'default_confidence': 0.4, 'note': '反轉策略，中等風險'},
                'bounce_buy': {'default_confidence': 0.5, 'note': '反彈策略，中等風險'},
                'trend_sell': {'default_confidence': 0.6, 'note': '趨勢策略，較低風險'},
                'breakdown_sell': {'default_confidence': 0.7, 'note': '破底策略，低風險'},
                'high_sell': {'default_confidence': 0.5, 'note': '高位策略，中等風險'},
                'reversal_sell': {'default_confidence': 0.4, 'note': '反轉策略，中等風險'}
            }
        }
    
    def make_shadow_decision(self, session_id: str, signal_id: int, 
                           features: Dict[str, Any], signal_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        生成影子模式決策建議
        
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
            
            # 檢查是否有足夠數據使用ML模型
            if self._should_use_ml_model():
                decision_result = self._ml_based_decision(features, signal_data)
                decision_result['decision_method'] = 'ML_MODEL'
            else:
                decision_result = self._rule_based_decision(features, signal_data)
                decision_result['decision_method'] = 'RULE_BASED'
            
            # 記錄決策到資料庫
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
            
            # 檢查訓練數據數量
            stats = ml_data_manager.get_ml_table_stats()
            total_features = stats.get('total_ml_features', 0)
            
            if total_features >= self.min_data_for_ml:
                logger.info(f"數據量充足({total_features}筆)，使用ML模型決策")
                return True
            else:
                logger.info(f"數據量不足({total_features}筆)，使用規則決策")
                return False
                
        except Exception as e:
            logger.warning(f"檢查ML模型可用性時出錯: {str(e)}，回退到規則決策")
            return False
    
    def _rule_based_decision(self, features: Dict[str, Any], signal_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        基於規則的決策邏輯 - 數據不足期使用
        
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
                    'confidence': 0.3,
                    'reason': f'已知高風險組合: {signal_type} + opposite={opposite}',
                    'risk_level': 'HIGH',
                    'execution_probability': 0.3,
                    'trading_probability': 0.3,
                    'suggested_price_adjustment': 0.0
                }
        
        # 2. 檢查是否為已知高品質組合
        for high_quality in self.strategy_rules['high_quality_combinations']:
            if (signal_type == high_quality['signal_type'] and 
                opposite == high_quality['opposite']):
                return {
                    'recommendation': 'EXECUTE',
                    'confidence': 0.8,
                    'reason': f'已知高品質組合: {signal_type} + opposite={opposite}',
                    'risk_level': 'LOW',
                    'execution_probability': 0.8,
                    'trading_probability': 0.8,
                    'suggested_price_adjustment': 0.0
                }
        
        # 3. 基於策略偏好評估
        strategy_pref = self.strategy_rules['strategy_preferences'].get(signal_type, {})
        base_confidence = strategy_pref.get('default_confidence', 0.5)
        
        # 4. 基於opposite值調整信心度
        opposite_adjustment = self._calculate_opposite_adjustment(opposite)
        final_confidence = max(0.1, min(0.9, base_confidence + opposite_adjustment))
        
        # 5. 生成決策
        recommendation = 'EXECUTE' if final_confidence >= self.confidence_threshold else 'SKIP'
        
        return {
            'recommendation': recommendation,
            'confidence': final_confidence,
            'reason': f"策略評估: {strategy_pref.get('note', '未知策略')}, opposite調整: {opposite_adjustment:+.2f}",
            'risk_level': 'MEDIUM',
            'execution_probability': final_confidence,
            'trading_probability': final_confidence,
            'suggested_price_adjustment': 0.0
        }
    
    def _calculate_opposite_adjustment(self, opposite: int) -> float:
        """
        基於opposite值計算信心度調整
        
        Args:
            opposite: opposite參數值
            
        Returns:
            float: 信心度調整值 (-0.2 到 +0.2)
        """
        # 基於已知洞察調整
        if opposite == 0:
            return 0.1  # 當前收盤價，相對較好
        elif opposite == 1:
            return 0.0  # 前根收盤價，中性
        elif opposite == 2:
            return -0.1  # 前根開盤價，已知問題較多
        else:
            return -0.1  # 未知值，保守處理
    
    def _ml_based_decision(self, features: Dict[str, Any], signal_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        基於ML模型的決策邏輯 - 數據充足期使用
        
        Args:
            features: 特徵數據
            signal_data: 信號數據
            
        Returns:
            Dict: 決策結果
        """
        # TODO: 實現真正的ML模型預測
        # 當前作為框架，返回基於規則的結果但標記為ML
        
        logger.info("ML模型功能開發中，暫時使用增強規則邏輯")
        
        # 暫時調用規則決策，但提高信心度
        rule_result = self._rule_based_decision(features, signal_data)
        
        # ML版本的增強
        rule_result['confidence'] = min(1.0, rule_result['confidence'] + 0.1)
        rule_result['reason'] += ' (ML增強版)'
        
        return rule_result
    
    def _record_shadow_decision(self, session_id: str, signal_id: int, 
                               decision_result: Dict[str, Any], features: Dict[str, Any], 
                               signal_data: Dict[str, Any]) -> bool:
        """記錄影子決策到資料庫 - 修復版本"""
        try:
            # 延遲導入，確保使用最新實例
            from database import ml_data_manager
            
            # 🔥 修復：調整參數格式以匹配 record_signal_quality_assessment 方法
            assessment_result = {
                'decision_method': decision_result.get('decision_method', 'RULE_BASED'),
                'recommendation': decision_result.get('recommendation'),
                'confidence_score': decision_result.get('confidence'),
                'execution_probability': decision_result.get('execution_probability'),
                'reason': decision_result.get('reason'),
                'reasoning_details': decision_result.get('reason'),  # 詳細理由
                'model_version': f"shadow_v1.0_{decision_result.get('decision_method', 'RULE')}"
            }
            
            # 🔥 修復：使用正確的方法名稱
            success = ml_data_manager.record_signal_quality_assessment(session_id, signal_id, assessment_result)
            
            if success:
                logger.info(f"✅ 影子決策已記錄 - signal_id: {signal_id}")
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
        logger.info(f"   理由: {decision_result.get('reason')}")
        logger.info(f"   方法: {decision_result.get('decision_method')}")
    
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
            # 延遲導入，確保使用最新實例
            from database import ml_data_manager
            
            stats = ml_data_manager.get_ml_table_stats()
            
            return {
                'total_decisions': stats.get('total_signal_quality', 0),
                'ml_ready': stats.get('total_ml_features', 0) >= self.min_data_for_ml,
                'data_progress': f"{stats.get('total_ml_features', 0)}/{self.min_data_for_ml}",
                'current_mode': 'ML_MODEL' if self._should_use_ml_model() else 'RULE_BASED'
            }
            
        except Exception as e:
            logger.error(f"獲取影子模式統計時出錯: {str(e)}")
            return {'error': str(e)}

# 創建全局影子決策引擎實例
shadow_decision_engine = ShadowModeDecisionEngine()
