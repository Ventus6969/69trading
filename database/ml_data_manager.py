"""
ML數據管理模組 v2.0 - 36特徵架構
負責ML特徵存儲、預測記錄和特徵重要性追蹤
=============================================================================
"""
import sqlite3
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List

# 設置logger
logger = logging.getLogger(__name__)

class MLDataManager:
    """ML數據管理類 - 36特徵版本"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        # 初始化ML表格
        self._init_ml_tables()
        logger.info(f"ML數據管理器已初始化，資料庫路徑: {self.db_path}")
    
    def _init_ml_tables(self):
        """初始化ML相關表格 - 36特徵架構"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 1. ML特徵表 (36個特徵)
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS ml_features_v2 (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_id TEXT NOT NULL,
                        signal_id INTEGER,
                        
                        -- 信號品質核心特徵 (15個)
                        strategy_win_rate_recent REAL,
                        strategy_win_rate_overall REAL,
                        strategy_market_fitness REAL,
                        volatility_match_score REAL,
                        time_slot_match_score REAL,
                        symbol_match_score REAL,
                        price_momentum_strength REAL,
                        atr_relative_position REAL,
                        risk_reward_ratio REAL,
                        execution_difficulty REAL,
                        consecutive_win_streak INTEGER,
                        consecutive_loss_streak INTEGER,
                        system_overall_performance REAL,
                        signal_confidence_score REAL,
                        market_condition_fitness REAL,
                        
                        -- 價格關係特徵 (12個)
                        price_deviation_percent REAL,
                        price_deviation_abs REAL,
                        atr_normalized_deviation REAL,
                        candle_direction INTEGER,
                        candle_body_size REAL,
                        candle_wick_ratio REAL,
                        price_position_in_range REAL,
                        upward_adjustment_space REAL,
                        downward_adjustment_space REAL,
                        historical_best_adjustment REAL,
                        price_reachability_score REAL,
                        entry_price_quality_score REAL,
                        
                        -- 市場環境特徵 (9個)
                        hour_of_day INTEGER,
                        trading_session INTEGER,
                        weekend_factor INTEGER,
                        symbol_category INTEGER,
                        current_positions INTEGER,
                        margin_ratio REAL,
                        atr_normalized REAL,
                        volatility_regime INTEGER,
                        market_trend_strength REAL,
                        
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (signal_id) REFERENCES signals_received (id)
                    )
                ''')
                
                # 2. ML預測表
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS ml_signal_quality (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_id TEXT NOT NULL,
                        signal_id INTEGER,
                        
                        -- 預測結果
                        profit_probability REAL,
                        quality_score REAL,
                        confidence_level REAL,
                        
                        -- 決策
                        recommendation TEXT,  -- 'EXECUTE' or 'SKIP'
                        reasoning TEXT,
                        model_version TEXT,
                        
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (signal_id) REFERENCES signals_received (id)
                    )
                ''')
                
                # 3. 價格優化表
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS ml_price_optimization (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_id TEXT NOT NULL,
                        signal_id INTEGER,
                        
                        -- 價格分析
                        original_entry_price REAL,
                        suggested_adjustment_percent REAL,
                        optimized_entry_price REAL,
                        
                        -- 預期效果
                        execution_probability_original REAL,
                        execution_probability_optimized REAL,
                        optimization_reasoning TEXT,
                        
                        model_version TEXT,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (signal_id) REFERENCES signals_received (id)
                    )
                ''')
                
                # 建立索引
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_ml_features_signal_id ON ml_features_v2(signal_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_ml_features_session_id ON ml_features_v2(session_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_ml_quality_signal_id ON ml_signal_quality(signal_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_ml_price_signal_id ON ml_price_optimization(signal_id)')
                
                conn.commit()
                logger.info("ML資料庫表格初始化完成 - 36特徵架構")
                
        except Exception as e:
            logger.error(f"初始化ML表格時出錯: {str(e)}")
            raise
    
    def record_ml_features(self, session_id: str, signal_id: int, features: Dict[str, Any]) -> bool:
        """
        記錄ML特徵數據 - 36個特徵
        
        Args:
            session_id: 會話ID
            signal_id: 信號ID
            features: 36個特徵的字典
            
        Returns:
            bool: 是否記錄成功
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 36個特徵欄位列表
                feature_columns = [
                    'session_id', 'signal_id',
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
                
                # 準備數據值
                feature_values = [session_id, signal_id]
                for col in feature_columns[2:]:  # 跳過session_id和signal_id
                    feature_values.append(features.get(col))
                
                # 生成SQL語句
                placeholders = ','.join(['?'] * len(feature_columns))
                columns_str = ','.join(feature_columns)
                
                cursor.execute(f"""
                    INSERT INTO ml_features_v2 ({columns_str})
                    VALUES ({placeholders})
                """, feature_values)
                
                conn.commit()
                logger.info(f"已記錄ML特徵: session_id={session_id}, signal_id={signal_id}")
                return True
                
        except Exception as e:
            logger.error(f"記錄ML特徵時出錯: {str(e)}")
            return False
    
    def record_signal_quality(self, session_id: str, signal_id: int, quality_result: Dict[str, Any]) -> bool:
        """
        記錄信號品質評估結果
        
        Args:
            session_id: 會話ID
            signal_id: 信號ID
            quality_result: 品質評估結果
            
        Returns:
            bool: 是否記錄成功
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    INSERT INTO ml_signal_quality (
                        session_id, signal_id, profit_probability, quality_score, confidence_level,
                        recommendation, reasoning, model_version
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    session_id, signal_id,
                    quality_result.get('profit_probability'),
                    quality_result.get('quality_score'),
                    quality_result.get('confidence_level'),
                    quality_result.get('recommendation'),
                    quality_result.get('reasoning'),
                    quality_result.get('model_version', 'v1.0')
                ))
                
                conn.commit()
                logger.info(f"已記錄信號品質評估: session_id={session_id}, signal_id={signal_id}")
                return True
                
        except Exception as e:
            logger.error(f"記錄信號品質評估時出錯: {str(e)}")
            return False
    
    def record_price_optimization(self, session_id: str, signal_id: int, optimization_result: Dict[str, Any]) -> bool:
        """
        記錄價格優化結果
        
        Args:
            session_id: 會話ID
            signal_id: 信號ID
            optimization_result: 價格優化結果
            
        Returns:
            bool: 是否記錄成功
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    INSERT INTO ml_price_optimization (
                        session_id, signal_id, original_entry_price, suggested_adjustment_percent,
                        optimized_entry_price, execution_probability_original, execution_probability_optimized,
                        optimization_reasoning, model_version
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    session_id, signal_id,
                    optimization_result.get('original_entry_price'),
                    optimization_result.get('suggested_adjustment_percent'),
                    optimization_result.get('optimized_entry_price'),
                    optimization_result.get('execution_probability_original'),
                    optimization_result.get('execution_probability_optimized'),
                    optimization_result.get('optimization_reasoning'),
                    optimization_result.get('model_version', 'v1.0')
                ))
                
                conn.commit()
                logger.info(f"已記錄價格優化: session_id={session_id}, signal_id={signal_id}")
                return True
                
        except Exception as e:
            logger.error(f"記錄價格優化時出錯: {str(e)}")
            return False
    
    def get_ml_features_by_signal(self, signal_id: int) -> Optional[Dict[str, Any]]:
        """根據信號ID獲取ML特徵"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                cursor.execute('SELECT * FROM ml_features_v2 WHERE signal_id = ?', (signal_id,))
                row = cursor.fetchone()
                
                return dict(row) if row else None
                
        except Exception as e:
            logger.error(f"獲取ML特徵時出錯: {str(e)}")
            return None
    
    def get_quality_assessment_by_signal(self, signal_id: int) -> Optional[Dict[str, Any]]:
        """根據信號ID獲取品質評估結果"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                cursor.execute('SELECT * FROM ml_signal_quality WHERE signal_id = ?', (signal_id,))
                row = cursor.fetchone()
                
                return dict(row) if row else None
                
        except Exception as e:
            logger.error(f"獲取品質評估時出錯: {str(e)}")
            return None
    
    def get_price_optimization_by_signal(self, signal_id: int) -> Optional[Dict[str, Any]]:
        """根據信號ID獲取價格優化結果"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                cursor.execute('SELECT * FROM ml_price_optimization WHERE signal_id = ?', (signal_id,))
                row = cursor.fetchone()
                
                return dict(row) if row else None
                
        except Exception as e:
            logger.error(f"獲取價格優化時出錯: {str(e)}")
            return None
    
    def get_ml_table_stats(self) -> Dict[str, int]:
        """獲取ML表格統計"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                stats = {}
                
                cursor.execute('SELECT COUNT(*) FROM ml_features_v2')
                stats['total_ml_features'] = cursor.fetchone()[0]
                
                cursor.execute('SELECT COUNT(*) FROM ml_signal_quality')
                stats['total_signal_quality'] = cursor.fetchone()[0]
                
                cursor.execute('SELECT COUNT(*) FROM ml_price_optimization')
                stats['total_price_optimization'] = cursor.fetchone()[0]
                
                return stats
                
        except Exception as e:
            logger.error(f"獲取ML表格統計時出錯: {str(e)}")
            return {'total_ml_features': 0, 'total_signal_quality': 0, 'total_price_optimization': 0}
    
    def calculate_basic_features(self, signal_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        計算基礎特徵 - 初始版本
        TODO: 後續逐步完善每個特徵的計算邏輯
        """
        features = {}
        
        try:
            # 從信號數據中提取基本信息
            signal_type = signal_data.get('signal_type', '')
            opposite = signal_data.get('opposite', 0)
            symbol = signal_data.get('symbol', '')
            current_time = datetime.now()
            
            # 信號品質核心特徵 (15個) - 先設定預設值
            features.update({
                'strategy_win_rate_recent': 0.5,  # TODO: 計算近期勝率
                'strategy_win_rate_overall': 0.5,  # TODO: 計算整體勝率
                'strategy_market_fitness': 0.5,  # TODO: 計算市場適配度
                'volatility_match_score': 0.5,
                'time_slot_match_score': 0.5,
                'symbol_match_score': 0.5,
                'price_momentum_strength': 0.5,
                'atr_relative_position': 0.5,
                'risk_reward_ratio': 1.5,  # 固定風險報酬比
                'execution_difficulty': 0.5,
                'consecutive_win_streak': 0,
                'consecutive_loss_streak': 0,
                'system_overall_performance': 0.5,
                'signal_confidence_score': 0.5,
                'market_condition_fitness': 0.5
            })
            
            # 價格關係特徵 (12個)
            features.update({
                'price_deviation_percent': 0.0,
                'price_deviation_abs': 0.0,
                'atr_normalized_deviation': 0.0,
                'candle_direction': 1 if signal_type.endswith('_buy') else -1,
                'candle_body_size': 0.5,
                'candle_wick_ratio': 0.5,
                'price_position_in_range': 0.5,
                'upward_adjustment_space': 0.02,
                'downward_adjustment_space': 0.02,
                'historical_best_adjustment': 0.0,
                'price_reachability_score': 0.5,
                'entry_price_quality_score': 0.5
            })
            
            # 市場環境特徵 (9個)
            features.update({
                'hour_of_day': current_time.hour,
                'trading_session': self._get_trading_session(current_time.hour),
                'weekend_factor': 1 if current_time.weekday() >= 5 else 0,
                'symbol_category': self._get_symbol_category(symbol),
                'current_positions': 0,  # TODO: 獲取當前持倉
                'margin_ratio': 0.5,
                'atr_normalized': 0.5,
                'volatility_regime': 1,  # 1=正常, 2=高波動, 0=低波動
                'market_trend_strength': 0.5
            })
            
            logger.info(f"已計算基礎特徵，共36個特徵")
            return features
            
        except Exception as e:
            logger.error(f"計算基礎特徵時出錯: {str(e)}")
            # 返回預設特徵值
            return self._get_default_features()
    
    def _get_trading_session(self, hour: int) -> int:
        """獲取交易時段"""
        if 0 <= hour < 8:
            return 1  # 亞洲時段
        elif 8 <= hour < 16:
            return 2  # 歐洲時段
        else:
            return 3  # 美洲時段
    
    def _get_symbol_category(self, symbol: str) -> int:
        """獲取交易對分類"""
        if 'BTC' in symbol:
            return 1  # BTC類
        elif 'ETH' in symbol:
            return 2  # ETH類
        else:
            return 3  # 其他山寨幣
    
    def _get_default_features(self) -> Dict[str, Any]:
        """獲取預設特徵值"""
        return {f'feature_{i}': 0.5 for i in range(1, 37)}

# 創建ML數據管理器實例（需要傳入資料庫路徑）
def create_ml_data_manager(db_path: str) -> MLDataManager:
    """創建ML數據管理器實例"""
    return MLDataManager(db_path)
