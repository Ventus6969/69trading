"""
ML數據管理模組
負責ML特徵計算、存儲和影子決策記錄
🔥 完整修復版本：解決所有特徵計算錯誤
=============================================================================
"""
import sqlite3
import logging
import traceback
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple
import json

# 設置logger
logger = logging.getLogger(__name__)

class MLDataManager:
    """ML數據管理類"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_ml_tables()
        logger.info(f"ML數據管理器已初始化，資料庫路徑: {self.db_path}")
    
    def _init_ml_tables(self):
        """初始化ML相關表格"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 1. ML特徵表 (完整36個特徵)
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS ml_features_v2 (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_id TEXT NOT NULL,
                        signal_id INTEGER,
                        
                        -- 信號品質核心特徵 (15個)
                        strategy_win_rate_recent REAL DEFAULT 0.0,
                        strategy_win_rate_overall REAL DEFAULT 0.0,
                        strategy_market_fitness REAL DEFAULT 0.0,
                        volatility_match_score REAL DEFAULT 0.0,
                        time_slot_match_score REAL DEFAULT 0.0,
                        symbol_match_score REAL DEFAULT 0.0,
                        price_momentum_strength REAL DEFAULT 0.0,
                        atr_relative_position REAL DEFAULT 0.0,
                        risk_reward_ratio REAL DEFAULT 0.0,
                        execution_difficulty REAL DEFAULT 0.0,
                        consecutive_win_streak INTEGER DEFAULT 0,
                        consecutive_loss_streak INTEGER DEFAULT 0,
                        system_overall_performance REAL DEFAULT 0.0,
                        signal_confidence_score REAL DEFAULT 0.0,
                        market_condition_fitness REAL DEFAULT 0.0,
                        
                        -- 價格關係特徵 (12個)
                        price_deviation_percent REAL DEFAULT 0.0,
                        price_deviation_abs REAL DEFAULT 0.0,
                        atr_normalized_deviation REAL DEFAULT 0.0,
                        candle_direction INTEGER DEFAULT 0,
                        candle_body_size REAL DEFAULT 0.0,
                        candle_wick_ratio REAL DEFAULT 0.0,
                        price_position_in_range REAL DEFAULT 0.0,
                        upward_adjustment_space REAL DEFAULT 0.0,
                        downward_adjustment_space REAL DEFAULT 0.0,
                        historical_best_adjustment REAL DEFAULT 0.0,
                        price_reachability_score REAL DEFAULT 0.0,
                        entry_price_quality_score REAL DEFAULT 0.0,
                        
                        -- 市場環境特徵 (9個)
                        hour_of_day INTEGER DEFAULT 0,
                        trading_session INTEGER DEFAULT 0,
                        weekend_factor INTEGER DEFAULT 0,
                        symbol_category INTEGER DEFAULT 0,
                        current_positions INTEGER DEFAULT 0,
                        margin_ratio REAL DEFAULT 0.0,
                        atr_normalized REAL DEFAULT 0.0,
                        volatility_regime INTEGER DEFAULT 0,
                        market_trend_strength REAL DEFAULT 0.0,
                        
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (signal_id) REFERENCES signals_received (id)
                    )
                ''')
                
                # 2. ML影子決策記錄表
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS ml_signal_quality (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_id TEXT NOT NULL,
                        signal_id INTEGER,
                        decision_method TEXT DEFAULT 'RULE_BASED',
                        recommendation TEXT,
                        confidence_score REAL,
                        execution_probability REAL,
                        trading_probability REAL,
                        risk_level TEXT,
                        reason TEXT,
                        suggested_price_adjustment REAL DEFAULT 0.0,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (signal_id) REFERENCES signals_received (id)
                    )
                ''')
                
                # 3. ML價格優化記錄表
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS ml_price_optimization (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_id TEXT NOT NULL,
                        signal_id INTEGER,
                        original_price REAL,
                        suggested_price REAL,
                        price_adjustment REAL,
                        adjustment_reason TEXT,
                        success_probability REAL,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (signal_id) REFERENCES signals_received (id)
                    )
                ''')
                
                conn.commit()
                logger.info("✅ ML表格初始化完成")
                
        except Exception as e:
            logger.error(f"❌ 初始化ML表格時出錯: {str(e)}")
            logger.error(traceback.format_exc())
            raise
    
    def calculate_basic_features(self, signal_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        計算基礎的36個ML特徵 - 🔥 完整修復版本
        
        Args:
            signal_data: 原始信號數據
            
        Returns:
            dict: 包含36個特徵的字典
        """
        try:
            logger.info("🧠 開始計算36個ML特徵...")
            
            # 🔥 修復：確保所有基本變量都正確定義
            features = {}
            
            # 從信號數據中提取基本信息
            symbol = signal_data.get('symbol', '')
            side = signal_data.get('side', '')
            signal_type = signal_data.get('signal_type', '')
            close_price = self._safe_float(signal_data.get('close', 0))
            open_price = self._safe_float(signal_data.get('open', 0))
            prev_close = self._safe_float(signal_data.get('prev_close', 0))
            prev_open = self._safe_float(signal_data.get('prev_open', 0))
            atr = self._safe_float(signal_data.get('ATR', 0))
            opposite = self._safe_int(signal_data.get('opposite', 0))
            
            # 🔥 修復：確保時間相關特徵正確計算
            current_time = datetime.now()
            current_hour = current_time.hour
            
            # === 第一類：信號品質核心特徵 (15個) ===
            features.update({
                'strategy_win_rate_recent': self._calculate_strategy_win_rate(signal_type, days=7),
                'strategy_win_rate_overall': self._calculate_strategy_win_rate(signal_type, days=30),
                'strategy_market_fitness': self._calculate_strategy_fitness(signal_type, symbol),
                'volatility_match_score': self._calculate_volatility_match(atr, symbol),
                'time_slot_match_score': self._calculate_time_slot_match(current_hour),
                'symbol_match_score': self._calculate_symbol_match(symbol, signal_type),
                'price_momentum_strength': self._calculate_price_momentum(close_price, open_price, prev_close),
                'atr_relative_position': self._calculate_atr_relative_position(atr, symbol),
                'risk_reward_ratio': 2.5,  # 默認風險回報比
                'execution_difficulty': self._calculate_execution_difficulty(symbol, atr),
                'consecutive_win_streak': self._get_consecutive_streak(signal_type, True),
                'consecutive_loss_streak': self._get_consecutive_streak(signal_type, False),
                'system_overall_performance': self._calculate_system_performance(),
                'signal_confidence_score': self._calculate_signal_confidence(signal_data),
                'market_condition_fitness': self._calculate_market_fitness(current_hour)
            })
            
            # === 第二類：價格關係特徵 (12個) ===
            features.update({
                'price_deviation_percent': self._calculate_price_deviation_percent(close_price, open_price),
                'price_deviation_abs': abs(close_price - open_price),
                'atr_normalized_deviation': self._calculate_atr_normalized_deviation(close_price, open_price, atr),
                'candle_direction': self._calculate_candle_direction(close_price, open_price),
                'candle_body_size': abs(close_price - open_price),
                'candle_wick_ratio': self._calculate_candle_wick_ratio(signal_data),
                'price_position_in_range': self._calculate_price_position_in_range(close_price, signal_data),
                'upward_adjustment_space': self._calculate_upward_adjustment_space(close_price, atr),
                'downward_adjustment_space': self._calculate_downward_adjustment_space(close_price, atr),
                'historical_best_adjustment': self._calculate_historical_best_adjustment(signal_type, symbol),
                'price_reachability_score': self._calculate_price_reachability_score(close_price, atr, side),
                'entry_price_quality_score': self._calculate_entry_price_quality_score(signal_data)
            })
            
            # === 第三類：市場環境特徵 (9個) ===
            # 🔥 修復：確保 hour_of_day 正確設置
            features.update({
                'hour_of_day': current_hour,  # 🔥 修復：直接使用計算好的 current_hour
                'trading_session': self._get_trading_session(current_hour),
                'weekend_factor': 1 if current_time.weekday() >= 5 else 0,
                'symbol_category': self._get_symbol_category(symbol),
                'current_positions': self._get_current_positions_count(),
                'margin_ratio': self._calculate_margin_ratio(),
                'atr_normalized': self._normalize_atr(atr, symbol),
                'volatility_regime': self._get_volatility_regime(atr, symbol),
                'market_trend_strength': self._calculate_market_trend_strength()
            })
            
            # 🔥 修復：驗證特徵完整性
            expected_features = 36
            actual_features = len(features)
            
            if actual_features != expected_features:
                logger.warning(f"特徵數量不匹配: 期望{expected_features}個，實際{actual_features}個")
                # 補充缺失的特徵
                missing_features = expected_features - actual_features
                for i in range(missing_features):
                    features[f'missing_feature_{i}'] = 0.0
            
            logger.info(f"✅ 已計算ML特徵，共{len(features)}個特徵")
            return features
            
        except Exception as e:
            logger.error(f"❌ 計算ML特徵時出錯: {str(e)}")
            logger.error(f"信號數據: {signal_data}")
            logger.error(traceback.format_exc())
            
            # 🔥 修復：返回完整的默認特徵
            return self._get_default_features()
    
    def _get_default_features(self) -> Dict[str, Any]:
        """獲取默認的36個特徵值 - 🔥 完整版本"""
        current_time = datetime.now()
        current_hour = current_time.hour
        
        return {
            # 信號品質核心特徵 (15個)
            'strategy_win_rate_recent': 0.5,
            'strategy_win_rate_overall': 0.5,
            'strategy_market_fitness': 0.5,
            'volatility_match_score': 0.5,
            'time_slot_match_score': 0.5,
            'symbol_match_score': 0.5,
            'price_momentum_strength': 0.0,
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
            'candle_wick_ratio': 0.0,
            'price_position_in_range': 0.5,
            'upward_adjustment_space': 0.0,
            'downward_adjustment_space': 0.0,
            'historical_best_adjustment': 0.0,
            'price_reachability_score': 0.5,
            'entry_price_quality_score': 0.5,
            
            # 市場環境特徵 (9個)
            'hour_of_day': current_hour,  # 🔥 修復：確保總是有值
            'trading_session': self._get_trading_session(current_hour),
            'weekend_factor': 1 if current_time.weekday() >= 5 else 0,
            'symbol_category': 4,  # 默認為山寨幣
            'current_positions': 0,
            'margin_ratio': 0.5,
            'atr_normalized': 0.01,
            'volatility_regime': 1,
            'market_trend_strength': 0.5
        }
    
    def record_ml_features(self, session_id: str, signal_id: int, features: Dict[str, Any]) -> bool:
        """記錄ML特徵到資料庫"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 構建SQL插入語句
                feature_columns = list(features.keys())
                feature_values = list(features.values())
                
                # 基本欄位
                columns = ['session_id', 'signal_id'] + feature_columns
                values = [session_id, signal_id] + feature_values
                
                placeholders = ', '.join(['?' for _ in values])
                columns_str = ', '.join(columns)
                
                sql = f"INSERT OR REPLACE INTO ml_features_v2 ({columns_str}) VALUES ({placeholders})"
                cursor.execute(sql, values)
                
                conn.commit()
                logger.info(f"✅ ML特徵記錄成功 - session_id: {session_id}, signal_id: {signal_id}")
                return True
                
        except Exception as e:
            logger.error(f"❌ 記錄ML特徵時出錯: {str(e)}")
            logger.error(traceback.format_exc())
            return False
    
    def record_shadow_decision(self, session_id: str, signal_id: int, decision_result: Dict[str, Any]) -> bool:
        """記錄影子決策結果到資料庫"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    INSERT OR REPLACE INTO ml_signal_quality (
                        session_id, signal_id, decision_method, recommendation,
                        confidence_score, execution_probability, trading_probability,
                        risk_level, reason, suggested_price_adjustment
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    session_id, signal_id,
                    decision_result.get('decision_method', 'RULE_BASED'),
                    decision_result.get('recommendation', 'EXECUTE'),
                    decision_result.get('confidence', 0.5),
                    decision_result.get('execution_probability', 0.5),
                    decision_result.get('trading_probability', 0.5),
                    decision_result.get('risk_level', 'MEDIUM'),
                    decision_result.get('reason', ''),
                    decision_result.get('suggested_price_adjustment', 0.0)
                ))
                
                conn.commit()
                logger.info(f"✅ 影子決策記錄成功 - session_id: {session_id}, signal_id: {signal_id}")
                return True
                
        except Exception as e:
            logger.error(f"❌ 記錄影子決策時出錯: {str(e)}")
            logger.error(traceback.format_exc())
            return False
    
    def get_ml_table_stats(self) -> Dict[str, int]:
        """獲取ML表格統計"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                stats = {}
                
                cursor.execute('SELECT COUNT(*) FROM ml_features_v2')
                stats['total_ml_features'] = cursor.fetchone()[0]
                
                cursor.execute('SELECT COUNT(*) FROM ml_signal_quality')
                stats['total_ml_decisions'] = cursor.fetchone()[0]
                
                cursor.execute('SELECT COUNT(*) FROM ml_price_optimization')
                stats['total_price_optimizations'] = cursor.fetchone()[0]
                
                return stats
                
        except Exception as e:
            logger.error(f"❌ 獲取ML表格統計時出錯: {str(e)}")
            return {'total_ml_features': 0, 'total_ml_decisions': 0, 'total_price_optimizations': 0}
    
    # === 🔥 輔助方法實現 ===
    
    def _safe_float(self, value: Any, default: float = 0.0) -> float:
        """安全的浮點數轉換"""
        try:
            return float(value) if value is not None else default
        except (ValueError, TypeError):
            return default
    
    def _safe_int(self, value: Any, default: int = 0) -> int:
        """安全的整數轉換"""
        try:
            return int(value) if value is not None else default
        except (ValueError, TypeError):
            return default
    
    def _get_trading_session(self, hour: int) -> int:
        """獲取交易時段"""
        try:
            if 0 <= hour < 8:
                return 1  # 亞洲時段
            elif 8 <= hour < 16:
                return 2  # 歐洲時段
            else:
                return 3  # 美洲時段
        except:
            return 1
    
    def _get_symbol_category(self, symbol: str) -> int:
        """獲取交易對分類"""
        try:
            symbol_upper = symbol.upper()
            if 'BTC' in symbol_upper:
                return 1
            elif 'ETH' in symbol_upper:
                return 2
            elif symbol_upper in ['BNBUSDT', 'ADAUSDT', 'DOTUSDT', 'LINKUSDT']:
                return 3  # 主流幣
            else:
                return 4  # 山寨幣
        except:
            return 4
    
    def _calculate_candle_direction(self, close_price: float, open_price: float) -> int:
        """計算K線方向"""
        try:
            if close_price > open_price:
                return 1  # 上漲
            elif close_price < open_price:
                return -1  # 下跌
            else:
                return 0  # 平盤
        except:
            return 0
    
    def _calculate_strategy_win_rate(self, signal_type: str, days: int = 7) -> float:
        """計算策略勝率"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 查詢最近N天的交易結果
                cursor.execute('''
                    SELECT COUNT(*) as total, SUM(is_successful) as wins
                    FROM trading_results tr
                    JOIN orders_executed oe ON tr.order_id = oe.id
                    JOIN signals_received sr ON oe.signal_id = sr.id
                    WHERE sr.signal_type = ? 
                    AND tr.created_at >= datetime('now', '-{} days')
                '''.format(days), (signal_type,))
                
                result = cursor.fetchone()
                if result and result[0] > 0:
                    return result[1] / result[0]
                return 0.5  # 默認50%
                
        except Exception as e:
            logger.debug(f"計算策略勝率時出錯: {str(e)}")
            return 0.5
    
    def _calculate_strategy_fitness(self, signal_type: str, symbol: str) -> float:
        """計算策略適應性"""
        try:
            # 簡化實現：根據策略類型和交易對返回適應性分數
            fitness_map = {
                'reversal_buy': 0.6,
                'reversal_sell': 0.6,
                'bounce_buy': 0.7,
                'bounce_sell': 0.7,
                'breakout_buy': 0.8,
                'breakout_sell': 0.8,
                'consolidation_buy': 0.5,
                'consolidation_sell': 0.5
            }
            return fitness_map.get(signal_type, 0.5)
        except:
            return 0.5
    
    def _calculate_volatility_match(self, atr: float, symbol: str) -> float:
        """計算波動率匹配度"""
        try:
            # 根據ATR值和交易對計算匹配度
            if atr <= 0:
                return 0.5
            
            # 不同交易對的ATR正常範圍
            atr_ranges = {
                'BTCUSDT': (0.015, 0.06),
                'ETHUSDT': (0.02, 0.08),
                'BNBUSDT': (0.025, 0.1),
                'ADAUSDT': (0.03, 0.12)
            }
            
            range_info = atr_ranges.get(symbol, (0.01, 0.1))
            if range_info[0] <= atr <= range_info[1]:
                return 0.8  # 在正常範圍內
            else:
                return 0.3  # 超出正常範圍
        except:
            return 0.5
    
    def _calculate_time_slot_match(self, current_hour: int) -> float:
        """計算時段匹配度"""
        try:
            # 根據交易活躍時段評分
            if 8 <= current_hour <= 12:  # 亞洲時段
                return 0.7
            elif 13 <= current_hour <= 17:  # 歐洲時段
                return 0.9
            elif 18 <= current_hour <= 22:  # 美國時段
                return 0.8
            elif 1 <= current_hour <= 6:   # 深夜時段
                return 0.4
            else:  # 其他時段
                return 0.6
        except:
            return 0.6
    
    def _calculate_symbol_match(self, symbol: str, signal_type: str) -> float:
        """計算交易對匹配度"""
        try:
            # 不同策略對不同交易對的適應性
            if 'BTC' in symbol:
                return 0.9  # BTC適合大多數策略
            elif 'ETH' in symbol:
                return 0.8  # ETH適合大多數策略
            elif signal_type in ['reversal_buy', 'reversal_sell']:
                return 0.6  # 反轉策略對山寨幣風險較高
            else:
                return 0.7  # 其他策略對山寨幣適中
        except:
            return 0.5
    
    def _calculate_price_momentum(self, close_price: float, open_price: float, prev_close: float) -> float:
        """計算價格動量"""
        try:
            if prev_close > 0:
                return (close_price - prev_close) / prev_close
            return 0.0
        except:
            return 0.0
    
    def _calculate_atr_relative_position(self, atr: float, symbol: str) -> float:
        """計算ATR相對位置"""
        try:
            # 簡化實現：ATR相對於平均值的位置
            if atr <= 0:
                return 0.5
            
            # 假設正常ATR範圍
            normal_atr = 0.03  # 假設正常ATR為3%
            if atr < normal_atr:
                return 0.3  # 低波動
            elif atr > normal_atr * 2:
                return 0.8  # 高波動
            else:
                return 0.5  # 正常波動
        except:
            return 0.5
    
    def _calculate_execution_difficulty(self, symbol: str, atr: float) -> float:
        """計算執行難度"""
        try:
            # 根據ATR和交易對計算執行難度
            if atr > 0.05:  # 高波動
                return 0.7
            elif atr < 0.02:  # 低波動
                return 0.3
            else:
                return 0.5
        except:
            return 0.5
    
    def _get_consecutive_streak(self, signal_type: str, is_win: bool) -> int:
        """獲取連續勝負紀錄"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 查詢最近的交易記錄
                cursor.execute('''
                    SELECT is_successful
                    FROM trading_results tr
                    JOIN orders_executed oe ON tr.order_id = oe.id
                    JOIN signals_received sr ON oe.signal_id = sr.id
                    WHERE sr.signal_type = ?
                    ORDER BY tr.created_at DESC
                    LIMIT 10
                ''', (signal_type,))
                
                results = cursor.fetchall()
                streak = 0
                
                for result in results:
                    if (result[0] == 1) == is_win:
                        streak += 1
                    else:
                        break
                
                return streak
        except:
            return 0
    
    def _calculate_system_performance(self) -> float:
        """計算系統整體表現"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 查詢最近30天的整體表現
                cursor.execute('''
                    SELECT AVG(is_successful) as win_rate
                    FROM trading_results
                    WHERE created_at >= datetime('now', '-30 days')
                ''')
                
                result = cursor.fetchone()
                if result and result[0] is not None:
                    return result[0]
                return 0.5
        except:
            return 0.5
    
    def _calculate_signal_confidence(self, signal_data: Dict[str, Any]) -> float:
        """計算信號信心度"""
        try:
            confidence = 0.5
            
            # 根據ATR調整信心度
            atr = self._safe_float(signal_data.get('ATR', 0))
            if 0.02 <= atr <= 0.05:
                confidence += 0.1
            elif atr > 0.05:
                confidence -= 0.1
            
            # 根據價格變化調整信心度
            close_price = self._safe_float(signal_data.get('close', 0))
            open_price = self._safe_float(signal_data.get('open', 0))
            
            if abs(close_price - open_price) / open_price > 0.01:
                confidence += 0.1
            
            return max(0.1, min(1.0, confidence))
        except:
            return 0.5
    
    def _calculate_market_fitness(self, current_hour: int) -> float:
        """計算市場適應性"""
        try:
            # 根據時段計算市場適應性
            if 9 <= current_hour <= 16:  # 市場活躍時段
                return 0.8
            elif 0 <= current_hour <= 5:  # 深夜時段
                return 0.3
            else:
                return 0.6
        except:
            return 0.5
    
    def _calculate_price_deviation_percent(self, close_price: float, open_price: float) -> float:
        """計算價格偏差百分比"""
        try:
            if open_price > 0:
                return (close_price - open_price) / open_price
            return 0.0
        except:
            return 0.0
    
    def _calculate_atr_normalized_deviation(self, close_price: float, open_price: float, atr: float) -> float:
        """計算ATR標準化偏差"""
        try:
            if atr > 0:
                return abs(close_price - open_price) / atr
            return 0.0
        except:
            return 0.0
    
    def _calculate_candle_wick_ratio(self, signal_data: Dict[str, Any]) -> float:
        """計算K線影線比例"""
        try:
            open_price = self._safe_float(signal_data.get('open', 0))
            close_price = self._safe_float(signal_data.get('close', 0))
            high_price = self._safe_float(signal_data.get('high', close_price))
            low_price = self._safe_float(signal_data.get('low', close_price))
            
            body_size = abs(close_price - open_price)
            total_range = high_price - low_price
            
            if total_range > 0:
                return (total_range - body_size) / total_range
            return 0.0
        except:
            return 0.0
    
    def _calculate_price_position_in_range(self, close_price: float, signal_data: Dict[str, Any]) -> float:
        """計算價格在區間中的位置"""
        try:
            high_price = self._safe_float(signal_data.get('high', close_price))
            low_price = self._safe_float(signal_data.get('low', close_price))
            
            if high_price > low_price:
                return (close_price - low_price) / (high_price - low_price)
            return 0.5
        except:
            return 0.5
    
    def _calculate_upward_adjustment_space(self, close_price: float, atr: float) -> float:
        """計算向上調整空間"""
        try:
            # 簡化實現：基於ATR計算向上調整空間
            return atr * 0.5 if atr > 0 else 0.02
        except:
            return 0.02
    
    def _calculate_downward_adjustment_space(self, close_price: float, atr: float) -> float:
        """計算向下調整空間"""
        try:
            # 簡化實現：基於ATR計算向下調整空間
            return atr * 0.5 if atr > 0 else 0.02
        except:
            return 0.02
    
    def _calculate_historical_best_adjustment(self, signal_type: str, symbol: str) -> float:
        """計算歷史最佳調整"""
        try:
            # 簡化實現：根據策略類型返回歷史最佳調整
            adjustment_map = {
                'reversal_buy': 0.005,
                'reversal_sell': 0.005,
                'bounce_buy': 0.003,
                'bounce_sell': 0.003,
                'breakout_buy': 0.008,
                'breakout_sell': 0.008
            }
            return adjustment_map.get(signal_type, 0.005)
        except:
            return 0.005
    
    def _calculate_price_reachability_score(self, close_price: float, atr: float, side: str) -> float:
        """計算價格可達性分數"""
        try:
            # 根據ATR和交易方向計算可達性
            if atr > 0:
                reachability = min(1.0, atr / 0.05)  # 5% ATR為滿分
                return reachability
            return 0.5
        except:
            return 0.5
    
    def _calculate_entry_price_quality_score(self, signal_data: Dict[str, Any]) -> float:
        """計算開倉價格品質分數"""
        try:
            # 綜合價格品質評分
            score = 0.5
            
            # 根據K線形態調整
            open_price = self._safe_float(signal_data.get('open', 0))
            close_price = self._safe_float(signal_data.get('close', 0))
            
            if open_price > 0:
                price_change = abs(close_price - open_price) / open_price
                if price_change > 0.01:  # 大於1%的變化
                    score += 0.2
                elif price_change < 0.005:  # 小於0.5%的變化
                    score -= 0.1
            
            return max(0.1, min(1.0, score))
        except:
            return 0.5
    
    def _get_current_positions_count(self) -> int:
        """獲取當前持倉數量"""
        try:
            # 這裡應該查詢實際的持倉數量
            # 暫時返回默認值
            return 0
        except:
            return 0
    
    def _calculate_margin_ratio(self) -> float:
        """計算保證金比例"""
        try:
            # 這裡應該查詢實際的保證金比例
            # 暫時返回默認值
            return 0.5
        except:
            return 0.5
    
    def _normalize_atr(self, atr: float, symbol: str) -> float:
        """標準化ATR"""
        try:
            if atr <= 0:
                return 0.01
            
            # 根據交易對標準化ATR
            symbol_multipliers = {
                'BTCUSDT': 1.0,
                'ETHUSDT': 1.2,
                'BNBUSDT': 1.5,
                'ADAUSDT': 2.0
            }
            
            multiplier = symbol_multipliers.get(symbol, 1.0)
            return atr * multiplier
        except:
            return 0.01
    
    def _get_volatility_regime(self, atr: float, symbol: str) -> int:
        """獲取波動率制度"""
        try:
            if atr <= 0:
                return 1
            
            # 根據ATR判斷波動率制度
            if atr < 0.02:
                return 1  # 低波動
            elif atr > 0.05:
                return 3  # 高波動
            else:
                return 2  # 正常波動
        except:
            return 1
    
    def _calculate_market_trend_strength(self) -> float:
        """計算市場趨勢強度"""
        try:
            # 這裡應該分析市場趨勢強度
            # 暫時返回默認值
            return 0.5
        except:
            return 0.5
    
    # === 🔥 數據查詢方法 ===
    
    def get_historical_features_for_ml(self, limit: int = 100) -> List[Dict[str, Any]]:
        """獲取歷史特徵數據用於ML訓練"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 查詢歷史ML特徵和對應的交易結果
                cursor.execute('''
                    SELECT 
                        mf.*,
                        tr.is_successful,
                        tr.final_pnl,
                        tr.holding_time_minutes
                    FROM ml_features_v2 mf
                    LEFT JOIN orders_executed oe ON mf.signal_id = oe.signal_id
                    LEFT JOIN trading_results tr ON oe.id = tr.order_id
                    ORDER BY mf.created_at DESC
                    LIMIT ?
                ''', (limit,))
                
                columns = [desc[0] for desc in cursor.description]
                results = []
                
                for row in cursor.fetchall():
                    row_dict = dict(zip(columns, row))
                    results.append(row_dict)
                
                return results
                
        except Exception as e:
            logger.error(f"❌ 獲取歷史特徵數據時出錯: {str(e)}")
            return []
    
    def get_recent_ml_decisions(self, limit: int = 50) -> List[Dict[str, Any]]:
        """獲取最近的ML決策記錄"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT 
                        msq.*,
                        sr.symbol,
                        sr.signal_type,
                        sr.side
                    FROM ml_signal_quality msq
                    LEFT JOIN signals_received sr ON msq.signal_id = sr.id
                    ORDER BY msq.created_at DESC
                    LIMIT ?
                ''', (limit,))
                
                columns = [desc[0] for desc in cursor.description]
                results = []
                
                for row in cursor.fetchall():
                    row_dict = dict(zip(columns, row))
                    results.append(row_dict)
                
                return results
                
        except Exception as e:
            logger.error(f"❌ 獲取ML決策記錄時出錯: {str(e)}")
            return []
    
    def get_feature_statistics(self) -> Dict[str, Any]:
        """獲取特徵統計信息"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 獲取特徵統計
                cursor.execute('''
                    SELECT 
                        COUNT(*) as total_features,
                        AVG(strategy_win_rate_recent) as avg_win_rate,
                        AVG(risk_reward_ratio) as avg_risk_reward,
                        AVG(signal_confidence_score) as avg_confidence
                    FROM ml_features_v2
                ''')
                
                result = cursor.fetchone()
                if result:
                    return {
                        'total_features': result[0],
                        'avg_win_rate': result[1] or 0.0,
                        'avg_risk_reward': result[2] or 0.0,
                        'avg_confidence': result[3] or 0.0
                    }
                
                return {}
                
        except Exception as e:
            logger.error(f"❌ 獲取特徵統計時出錯: {str(e)}")
            return {}
    
    def cleanup_old_data(self, days: int = 30) -> bool:
        """清理舊的ML數據"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 清理舊的ML特徵記錄
                cursor.execute('''
                    DELETE FROM ml_features_v2 
                    WHERE created_at < datetime('now', '-{} days')
                '''.format(days))
                
                # 清理舊的ML決策記錄
                cursor.execute('''
                    DELETE FROM ml_signal_quality 
                    WHERE created_at < datetime('now', '-{} days')
                '''.format(days))
                
                # 清理舊的價格優化記錄
                cursor.execute('''
                    DELETE FROM ml_price_optimization 
                    WHERE created_at < datetime('now', '-{} days')
                '''.format(days))
                
                conn.commit()
                
                deleted_features = cursor.rowcount
                logger.info(f"✅ 清理完成，刪除了 {deleted_features} 條舊記錄")
                return True
                
        except Exception as e:
            logger.error(f"❌ 清理舊數據時出錯: {str(e)}")
            return False
    
    def export_ml_data(self, output_file: str = None) -> bool:
        """導出ML數據"""
        try:
            if output_file is None:
                output_file = f"ml_data_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            
            # 獲取所有ML數據
            features = self.get_historical_features_for_ml(1000)
            decisions = self.get_recent_ml_decisions(1000)
            stats = self.get_feature_statistics()
            
            export_data = {
                'export_time': datetime.now().isoformat(),
                'features': features,
                'decisions': decisions,
                'statistics': stats
            }
            
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"✅ ML數據已導出到: {output_file}")
            return True
            
        except Exception as e:
            logger.error(f"❌ 導出ML數據時出錯: {str(e)}")
            return False

# === 🔥 創建ML數據管理器實例的函數 ===
def create_ml_data_manager(db_path: str) -> MLDataManager:
    """創建ML數據管理器實例"""
    return MLDataManager(db_path)
