"""
ML數據管理模組
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
    """ML數據管理類"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        # 初始化ML表格
        self._init_ml_tables()
        logger.info(f"ML數據管理器已初始化，資料庫路徑: {self.db_path}")
    
    def _init_ml_tables(self):
        """初始化ML相關表格"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 1. ML特徵表 (48個特徵)
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS ml_features_v2 (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_id TEXT NOT NULL,
                        signal_id INTEGER,
                        
                        -- 開倉價格品質特徵 (10個)
                        entry_price_gap REAL,
                        entry_price_gap_abs REAL, 
                        entry_price_gap_direction INTEGER,
                        price_gap_atr_ratio REAL,
                        price_reachability_5m REAL,
                        price_reachability_45m REAL,
                        price_reachability_score REAL,
                        strategy_combo_execution_rate REAL,
                        strategy_combo_avg_gap REAL,
                        strategy_combo_gap_variance REAL,
                        
                        -- 信號策略組合特徵 (12個)
                        signal_breakout_buy INTEGER DEFAULT 0,
                        signal_consolidation_buy INTEGER DEFAULT 0,
                        signal_reversal_buy INTEGER DEFAULT 0,
                        signal_bounce_buy INTEGER DEFAULT 0,
                        signal_trend_sell INTEGER DEFAULT 0,
                        signal_breakdown_sell INTEGER DEFAULT 0,
                        signal_high_sell INTEGER DEFAULT 0,
                        signal_reversal_sell INTEGER DEFAULT 0,
                        combo_conservative_long INTEGER DEFAULT 0,
                        combo_aggressive_long INTEGER DEFAULT 0,
                        combo_conservative_short INTEGER DEFAULT 0,
                        combo_aggressive_short INTEGER DEFAULT 0,
                        
                        -- 市場微觀結構特徵 (8個)
                        candle_wick_ratio REAL,
                        candle_body_position REAL,
                        price_volatility_intrabar REAL,
                        price_momentum_strength REAL,
                        market_liquidity_score REAL,
                        price_jump_risk REAL,
                        market_depth_proxy REAL,
                        liquidity_time_factor REAL,
                        
                        -- 時間序列特徵 (8個)
                        hour_of_day INTEGER,
                        minute_of_hour INTEGER,
                        time_slot_15m INTEGER,
                        time_to_major_open REAL,
                        timeslot_execution_rate REAL,
                        timeslot_trading_success_rate REAL,
                        is_asian_session INTEGER DEFAULT 0,
                        is_overlap_session INTEGER DEFAULT 0,
                        
                        -- 市場環境特徵 (6個)
                        atr_normalized REAL,
                        atr_percentile_rank REAL,
                        volatility_regime TEXT,
                        trend_strength_5m REAL,
                        trend_consistency REAL,
                        market_state TEXT,
                        
                        -- 交易對特徵 (4個)
                        symbol_btc_like INTEGER DEFAULT 0,
                        symbol_eth_like INTEGER DEFAULT 0,
                        symbol_alt_major INTEGER DEFAULT 0,
                        symbol_others INTEGER DEFAULT 0,
                        
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (signal_id) REFERENCES signals_received (id)
                    )
                ''')
                
                # 2. ML預測記錄表
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS ml_predictions_v2 (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_id TEXT NOT NULL,
                        signal_id INTEGER,
                        
                        -- 執行預測
                        execution_probability REAL,
                        execution_confidence REAL,
                        execution_model_version TEXT,
                        
                        -- 交易預測  
                        trading_success_probability REAL,
                        trading_confidence REAL,
                        trading_model_version TEXT,
                        risk_group TEXT,
                        
                        -- 價格優化
                        original_entry_price REAL,
                        suggested_price_adjustment REAL,
                        optimized_entry_price REAL,
                        optimization_reason TEXT,
                        
                        -- 最終決策
                        final_decision TEXT,
                        decision_confidence REAL,
                        decision_reasoning TEXT,
                        
                        -- 實際結果對比
                        actual_execution_result TEXT,
                        actual_trading_result INTEGER,
                        execution_prediction_accuracy REAL,
                        trading_prediction_accuracy REAL,
                        
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (signal_id) REFERENCES signals_received (id)
                    )
                ''')
                
                # 3. 特徵重要性追蹤表
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS feature_importance (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        model_type TEXT NOT NULL,
                        model_version TEXT NOT NULL,
                        feature_name TEXT NOT NULL,
                        importance_score REAL NOT NULL,
                        feature_rank INTEGER,
                        evaluation_date TEXT NOT NULL,
                        sample_size INTEGER,
                        model_accuracy REAL,
                        notes TEXT,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # 建立ML表格索引
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_ml_features_signal_id ON ml_features_v2(signal_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_ml_features_session_id ON ml_features_v2(session_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_ml_predictions_signal_id ON ml_predictions_v2(signal_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_ml_predictions_session_id ON ml_predictions_v2(session_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_feature_importance_model ON feature_importance(model_type, model_version)')
                
                conn.commit()
                logger.info("ML資料庫表格初始化完成")
                
        except Exception as e:
            logger.error(f"初始化ML表格時出錯: {str(e)}")
            raise
    
    def record_ml_features(self, session_id: str, signal_id: int, features: Dict[str, Any]) -> bool:
        """
        記錄ML特徵數據
        
        Args:
            session_id: 會話ID
            signal_id: 信號ID
            features: 48個特徵的字典
            
        Returns:
            bool: 是否記錄成功
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 準備特徵欄位列表（48個特徵）
                feature_columns = [
                    'session_id', 'signal_id',
                    # 開倉價格品質特徵 (10個)
                    'entry_price_gap', 'entry_price_gap_abs', 'entry_price_gap_direction', 'price_gap_atr_ratio',
                    'price_reachability_5m', 'price_reachability_45m', 'price_reachability_score',
                    'strategy_combo_execution_rate', 'strategy_combo_avg_gap', 'strategy_combo_gap_variance',
                    # 信號策略組合特徵 (12個)
                    'signal_breakout_buy', 'signal_consolidation_buy', 'signal_reversal_buy', 'signal_bounce_buy',
                    'signal_trend_sell', 'signal_breakdown_sell', 'signal_high_sell', 'signal_reversal_sell',
                    'combo_conservative_long', 'combo_aggressive_long', 'combo_conservative_short', 'combo_aggressive_short',
                    # 市場微觀結構特徵 (8個)
                    'candle_wick_ratio', 'candle_body_position', 'price_volatility_intrabar', 'price_momentum_strength',
                    'market_liquidity_score', 'price_jump_risk', 'market_depth_proxy', 'liquidity_time_factor',
                    # 時間序列特徵 (8個)
                    'hour_of_day', 'minute_of_hour', 'time_slot_15m', 'time_to_major_open',
                    'timeslot_execution_rate', 'timeslot_trading_success_rate', 'is_asian_session', 'is_overlap_session',
                    # 市場環境特徵 (6個)
                    'atr_normalized', 'atr_percentile_rank', 'volatility_regime', 'trend_strength_5m',
                    'trend_consistency', 'market_state',
                    # 交易對特徵 (4個)
                    'symbol_btc_like', 'symbol_eth_like', 'symbol_alt_major', 'symbol_others'
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
    
    def record_ml_prediction(self, session_id: str, signal_id: int, prediction: Dict[str, Any]) -> bool:
        """
        記錄ML預測結果
        
        Args:
            session_id: 會話ID
            signal_id: 信號ID
            prediction: 預測結果字典
            
        Returns:
            bool: 是否記錄成功
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    INSERT INTO ml_predictions_v2 (
                        session_id, signal_id, execution_probability, execution_confidence, execution_model_version,
                        trading_success_probability, trading_confidence, trading_model_version, risk_group,
                        original_entry_price, suggested_price_adjustment, optimized_entry_price, optimization_reason,
                        final_decision, decision_confidence, decision_reasoning
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    session_id, signal_id,
                    prediction.get('execution_probability'),
                    prediction.get('execution_confidence'),
                    prediction.get('execution_model_version'),
                    prediction.get('trading_success_probability'),
                    prediction.get('trading_confidence'),
                    prediction.get('trading_model_version'),
                    prediction.get('risk_group'),
                    prediction.get('original_entry_price'),
                    prediction.get('suggested_price_adjustment'),
                    prediction.get('optimized_entry_price'),
                    prediction.get('optimization_reason'),
                    prediction.get('final_decision'),
                    prediction.get('decision_confidence'),
                    prediction.get('decision_reasoning')
                ))
                
                conn.commit()
                logger.info(f"已記錄ML預測: session_id={session_id}, 決策={prediction.get('final_decision')}")
                return True
                
        except Exception as e:
            logger.error(f"記錄ML預測時出錯: {str(e)}")
            return False
    
    def get_ml_features_by_signal_id(self, signal_id: int) -> Dict[str, Any]:
        """根據信號ID獲取ML特徵"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                cursor.execute("SELECT * FROM ml_features_v2 WHERE signal_id = ?", (signal_id,))
                result = cursor.fetchone()
                
                return dict(result) if result else {}
                
        except Exception as e:
            logger.error(f"獲取ML特徵時出錯: {str(e)}")
            return {}
    
    def get_ml_prediction_by_signal_id(self, signal_id: int) -> Dict[str, Any]:
        """根據信號ID獲取ML預測"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                cursor.execute("SELECT * FROM ml_predictions_v2 WHERE signal_id = ?", (signal_id,))
                result = cursor.fetchone()
                
                return dict(result) if result else {}
                
        except Exception as e:
            logger.error(f"獲取ML預測時出錯: {str(e)}")
            return {}
    
    def get_strategy_execution_stats(self, signal_type: str, opposite: int) -> Dict[str, Any]:
        """獲取特定策略組合的執行統計"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 查詢該策略組合的歷史執行情況
                cursor.execute("""
                    SELECT 
                        COUNT(*) as total_signals,
                        SUM(CASE WHEN o.status IN ('FILLED', 'TP_FILLED', 'SL_FILLED') THEN 1 ELSE 0 END) as executed_orders,
                        AVG(ABS(s.close_price - o.price) / s.close_price) as avg_price_gap
                    FROM signals_received s
                    JOIN orders_executed o ON s.id = o.signal_id
                    WHERE s.signal_type = ? AND s.opposite = ?
                """, (signal_type, opposite))
                
                result = cursor.fetchone()
                total_signals, executed_orders, avg_price_gap = result
                
                execution_rate = (executed_orders / total_signals) if total_signals > 0 else 0
                
                return {
                    'total_signals': total_signals or 0,
                    'executed_orders': executed_orders or 0,
                    'execution_rate': round(execution_rate, 3),
                    'avg_price_gap': round(avg_price_gap or 0, 6)
                }
                
        except Exception as e:
            logger.error(f"獲取策略執行統計時出錯: {str(e)}")
            return {'total_signals': 0, 'executed_orders': 0, 'execution_rate': 0, 'avg_price_gap': 0}
    
    def update_ml_prediction_result(self, session_id: str, actual_execution: str, actual_trading: int = None) -> bool:
        """更新ML預測的實際結果"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                if actual_trading is not None:
                    cursor.execute("""
                        UPDATE ml_predictions_v2 
                        SET actual_execution_result = ?, actual_trading_result = ?
                        WHERE session_id = ?
                    """, (actual_execution, actual_trading, session_id))
                else:
                    cursor.execute("""
                        UPDATE ml_predictions_v2 
                        SET actual_execution_result = ?
                        WHERE session_id = ?
                    """, (actual_execution, session_id))
                
                conn.commit()
                return cursor.rowcount > 0
                
        except Exception as e:
            logger.error(f"更新ML預測結果時出錯: {str(e)}")
            return False
    
    def record_feature_importance(self, model_type: str, model_version: str, feature_scores: Dict[str, float], 
                                 model_accuracy: float = None, notes: str = None) -> bool:
        """記錄特徵重要性"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                evaluation_date = datetime.now().strftime('%Y-%m-%d')
                
                # 清除舊的記錄
                cursor.execute("""
                    DELETE FROM feature_importance 
                    WHERE model_type = ? AND model_version = ?
                """, (model_type, model_version))
                
                # 插入新的特徵重要性記錄
                for rank, (feature_name, importance_score) in enumerate(
                    sorted(feature_scores.items(), key=lambda x: x[1], reverse=True), 1
                ):
                    cursor.execute("""
                        INSERT INTO feature_importance (
                            model_type, model_version, feature_name, importance_score,
                            feature_rank, evaluation_date, sample_size, model_accuracy, notes
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        model_type, model_version, feature_name, importance_score,
                        rank, evaluation_date, len(feature_scores), model_accuracy, notes
                    ))
                
                conn.commit()
                logger.info(f"已記錄特徵重要性: {model_type} v{model_version}, {len(feature_scores)}個特徵")
                return True
                
        except Exception as e:
            logger.error(f"記錄特徵重要性時出錯: {str(e)}")
            return False
    
    def get_feature_importance(self, model_type: str, model_version: str = None, top_n: int = 10) -> List[Dict]:
        """獲取特徵重要性排序"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                if model_version:
                    cursor.execute("""
                        SELECT feature_name, importance_score, feature_rank
                        FROM feature_importance 
                        WHERE model_type = ? AND model_version = ?
                        ORDER BY feature_rank
                        LIMIT ?
                    """, (model_type, model_version, top_n))
                else:
                    # 獲取最新版本的特徵重要性
                    cursor.execute("""
                        SELECT feature_name, importance_score, feature_rank
                        FROM feature_importance 
                        WHERE model_type = ? AND model_version = (
                            SELECT model_version FROM feature_importance 
                            WHERE model_type = ? 
                            ORDER BY created_at DESC LIMIT 1
                        )
                        ORDER BY feature_rank
                        LIMIT ?
                    """, (model_type, model_type, top_n))
                
                return [dict(row) for row in cursor.fetchall()]
                
        except Exception as e:
            logger.error(f"獲取特徵重要性時出錯: {str(e)}")
            return []
    
    def get_ml_table_stats(self) -> Dict[str, int]:
        """獲取ML表格統計"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                stats = {}
                
                cursor.execute('SELECT COUNT(*) FROM ml_features_v2')
                stats['total_ml_features'] = cursor.fetchone()[0]
                
                cursor.execute('SELECT COUNT(*) FROM ml_predictions_v2')
                stats['total_ml_predictions'] = cursor.fetchone()[0]
                
                cursor.execute('SELECT COUNT(*) FROM feature_importance')
                stats['total_feature_importance'] = cursor.fetchone()[0]
                
                return stats
                
        except Exception as e:
            logger.error(f"獲取ML表格統計時出錯: {str(e)}")
            return {'total_ml_features': 0, 'total_ml_predictions': 0, 'total_feature_importance': 0}

# 創建ML數據管理器實例（需要傳入資料庫路徑）
def create_ml_data_manager(db_path: str) -> MLDataManager:
    """創建ML數據管理器實例"""
    return MLDataManager(db_path)