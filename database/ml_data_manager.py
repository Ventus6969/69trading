"""
ML數據管理模組 v2.1 - 完整修復版
解決表格欄位缺失和特徵計算錯誤
=============================================================================
"""
import sqlite3
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List

# 設置logger
logger = logging.getLogger(__name__)

class MLDataManager:
    """ML數據管理類 - 完整修復版"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        # 初始化ML表格
        self._init_ml_tables()
        logger.info(f"ML數據管理器已初始化，資料庫路徑: {self.db_path}")
    
    def _init_ml_tables(self):
        """初始化ML相關表格 - 強制重建確保完整"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 🔥 強制重建表格，確保包含所有36個特徵欄位
                logger.info("正在重建ML表格，確保36個特徵欄位完整...")
                
                cursor.execute('DROP TABLE IF EXISTS ml_features_v2')
                cursor.execute('DROP TABLE IF EXISTS ml_signal_quality') 
                cursor.execute('DROP TABLE IF EXISTS ml_price_optimization')
                
                # 1. ML特徵表 (完整36個特徵)
                cursor.execute('''
                    CREATE TABLE ml_features_v2 (
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
                
                # 2. 信號品質評估表
                cursor.execute('''
                    CREATE TABLE ml_signal_quality (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_id TEXT NOT NULL,
                        signal_id INTEGER,
                        decision_method TEXT DEFAULT 'RULE_BASED',
                        recommendation TEXT,
                        confidence_score REAL,
                        execution_probability REAL,
                        reason TEXT,
                        reasoning_details TEXT,
                        model_version TEXT DEFAULT 'v1.0',
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (signal_id) REFERENCES signals_received (id)
                    )
                ''')
                
                # 3. 價格優化表
                cursor.execute('''
                    CREATE TABLE ml_price_optimization (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_id TEXT NOT NULL,
                        signal_id INTEGER,
                        original_price REAL,
                        optimized_price REAL,
                        price_adjustment_percent REAL,
                        optimization_reason TEXT,
                        expected_improvement REAL,
                        confidence_level REAL,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (signal_id) REFERENCES signals_received (id)
                    )
                ''')
                
                # 創建索引
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_ml_features_signal_id ON ml_features_v2(signal_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_ml_features_session_id ON ml_features_v2(session_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_ml_quality_signal_id ON ml_signal_quality(signal_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_ml_price_signal_id ON ml_price_optimization(signal_id)')
                
                conn.commit()
                logger.info("ML資料庫表格初始化完成 - 36特徵架構（完整重建版本）")
                
        except Exception as e:
            logger.error(f"初始化ML表格時出錯: {str(e)}")
            raise
    
    def record_ml_features(self, session_id: str, signal_id: int, features: Dict[str, Any]) -> bool:
        """記錄ML特徵數據 - 36個特徵完整版本"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 36個特徵欄位列表（與表格結構完全一致）
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
                
                # 準備數據值，確保完整性
                feature_values = [session_id, signal_id]
                for col in feature_columns[2:]:  # 跳過session_id和signal_id
                    value = features.get(col, 0.0)
                    # 確保數值類型正確
                    if col in ['consecutive_win_streak', 'consecutive_loss_streak', 'candle_direction', 
                               'hour_of_day', 'trading_session', 'weekend_factor', 'symbol_category',
                               'current_positions', 'volatility_regime']:
                        feature_values.append(int(value) if value is not None else 0)
                    else:
                        feature_values.append(float(value) if value is not None else 0.0)
                
                # 生成SQL語句
                placeholders = ','.join(['?'] * len(feature_columns))
                columns_str = ','.join(feature_columns)
                
                cursor.execute(f'''
                    INSERT INTO ml_features_v2 ({columns_str})
                    VALUES ({placeholders})
                ''', feature_values)
                
                conn.commit()
                return True
                
        except Exception as e:
            logger.error(f"記錄ML特徵時出錯: {str(e)}")
            return False
    
    def record_signal_quality_assessment(self, session_id: str, signal_id: int, 
                                       assessment: Dict[str, Any]) -> bool:
        """記錄信號品質評估結果 - 修正方法名稱"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    INSERT INTO ml_signal_quality 
                    (session_id, signal_id, decision_method, recommendation, confidence_score,
                     execution_probability, reason, reasoning_details, model_version)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    session_id,
                    signal_id,
                    assessment.get('decision_method', 'RULE_BASED'),
                    assessment.get('recommendation', 'EXECUTE'),
                    assessment.get('confidence_score', 0.5),
                    assessment.get('execution_probability', 0.5),
                    assessment.get('reason', ''),
                    assessment.get('reasoning_details', ''),
                    assessment.get('model_version', 'v1.0')
                ))
                
                conn.commit()
                return True
                
        except Exception as e:
            logger.error(f"記錄信號品質評估時出錯: {str(e)}")
            return False
    
    def record_price_optimization(self, session_id: str, signal_id: int, 
                                optimization: Dict[str, Any]) -> bool:
        """記錄價格優化結果"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    INSERT INTO ml_price_optimization 
                    (session_id, signal_id, original_price, optimized_price, price_adjustment_percent,
                     optimization_reason, expected_improvement, confidence_level)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    session_id,
                    signal_id,
                    optimization.get('original_price', 0.0),
                    optimization.get('optimized_price', 0.0),
                    optimization.get('price_adjustment_percent', 0.0),
                    optimization.get('optimization_reason', ''),
                    optimization.get('expected_improvement', 0.0),
                    optimization.get('confidence_level', 0.0)
                ))
                
                conn.commit()
                return True
                
        except Exception as e:
            logger.error(f"記錄價格優化時出錯: {str(e)}")
            return False
    
    def get_recent_signal_quality(self, limit: int = 10) -> List[Dict]:
        """獲取最近的信號品質評估"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT * FROM ml_signal_quality 
                    ORDER BY created_at DESC 
                    LIMIT ?
                ''', (limit,))
                
                return [dict(row) for row in cursor.fetchall()]
                
        except Exception as e:
            logger.error(f"獲取信號品質評估時出錯: {str(e)}")
            return []
    
    def get_ml_features_by_signal(self, signal_id: int) -> Optional[Dict]:
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
    
    def get_price_optimization_by_signal(self, signal_id: int) -> Optional[Dict]:
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
        計算基礎特徵 - 完全修復版本
        解決數據類型錯誤、除零問題和所有異常情況
        """
        features = {}
        
        try:
            # 🔥 完全安全的數值轉換函數
            def safe_float(value, default=0.0):
                """安全的浮點數轉換，處理所有可能的異常情況"""
                try:
                    if value is None:
                        return float(default)
                    if isinstance(value, (int, float)):
                        return float(value)
                    # 處理字符串中的逗號和空格
                    str_value = str(value).replace(',', '').replace(' ', '').strip()
                    if str_value == '' or str_value == 'None':
                        return float(default)
                    return float(str_value)
                except (ValueError, TypeError, AttributeError):
                    logger.warning(f"數值轉換失敗: {value} -> 使用默認值 {default}")
                    return float(default)
            
            def safe_int(value, default=0):
                """安全的整數轉換"""
                try:
                    return int(safe_float(value, default))
                except:
                    return int(default)
            
            # 提取基本信息
            signal_type = str(signal_data.get('signal_type', '')).strip()
            opposite = safe_int(signal_data.get('opposite', 0))
            symbol = str(signal_data.get('symbol', '')).strip().upper()
            
            # 🔥 完全安全的價格數據處理
            open_price = safe_float(signal_data.get('open'), 100.0)
            close_price = safe_float(signal_data.get('close'), 100.0)
            prev_close = safe_float(signal_data.get('prev_close'), close_price)
            prev_open = safe_float(signal_data.get('prev_open'), open_price)
            atr = safe_float(signal_data.get('ATR'), 1.0)
            
            # 🔥 防止除零和無效值
            if atr <= 0:
                atr = 1.0
            if close_price <= 0:
                close_price = 100.0
            if prev_close <= 0:
                prev_close = close_price
            if open_price <= 0:
                open_price = close_price
                
            # === 信號品質核心特徵 (15個) - 安全計算 ===
            features.update({
                'strategy_win_rate_recent': 0.5,  # TODO: 實際計算策略近期勝率
                'strategy_win_rate_overall': 0.5,  # TODO: 實際計算策略整體勝率
                'strategy_market_fitness': 0.5,  # TODO: 策略市場適配度
                'volatility_match_score': 0.5,  # TODO: 波動率匹配分數
                'time_slot_match_score': 0.5,  # TODO: 時段匹配分數
                'symbol_match_score': 0.5,  # TODO: 交易對匹配分數
                'price_momentum_strength': abs(close_price - open_price) / atr,  # 價格動量強度
                'atr_relative_position': 0.5,  # TODO: ATR相對位置
                'risk_reward_ratio': 2.5,  # 風險報酬比（固定值）
                'execution_difficulty': max(0.1, min(0.9, 0.5 + (opposite * 0.1))),  # 執行難度
                'consecutive_win_streak': 0,  # TODO: 連勝記錄
                'consecutive_loss_streak': 0,  # TODO: 連敗記錄
                'system_overall_performance': 0.5,  # TODO: 系統整體表現
                'signal_confidence_score': 0.5,  # TODO: 信號信心分數
                'market_condition_fitness': 0.5  # TODO: 市場條件適配度
            })
            
            # === 價格關係特徵 (12個) - 安全計算 ===
            price_deviation_percent = ((close_price - prev_close) / prev_close * 100) if prev_close > 0 else 0.0
            price_deviation_abs = abs(close_price - prev_close)
            candle_direction = 1 if close_price > open_price else (-1 if close_price < open_price else 0)
            candle_body_size = abs(close_price - open_price) / atr
            
            features.update({
                'price_deviation_percent': price_deviation_percent,
                'price_deviation_abs': price_deviation_abs,
                'atr_normalized_deviation': price_deviation_abs / atr,
                'candle_direction': candle_direction,
                'candle_body_size': candle_body_size,
                'candle_wick_ratio': 0.5,  # TODO: 計算影線比例
                'price_position_in_range': 0.5,  # TODO: 價格在區間中的位置
                'upward_adjustment_space': 0.02,  # 向上調整空間（2%）
                'downward_adjustment_space': 0.02,  # 向下調整空間（2%）
                'historical_best_adjustment': 0.0,  # TODO: 歷史最佳調整
                'price_reachability_score': 0.7,  # 價格可達性評分
                'entry_price_quality_score': 0.6  # 入場價格品質評分
            })
            
            # === 市場環境特徵 (9個) - 安全計算 ===
            current_time = datetime.now()
            hour = current_time.hour
            trading_session = self._get_trading_session(hour)
            weekend_factor = 1 if current_time.weekday() >= 5 else 0
            symbol_category = self._get_symbol_category(symbol)
            atr_normalized = atr / close_price if close_price > 0 else 0.01
            
            features.update({
                'hour_of_day': hour,
                'trading_session': trading_session,
                'weekend_factor': weekend_factor,
                'symbol_category': symbol_category,
                'current_positions': 0,  # TODO: 獲取當前持倉數
                'margin_ratio': 0.5,  # TODO: 保證金比例
                'atr_normalized': atr_normalized,
                'volatility_regime': 1,  # TODO: 波動率制度識別（1=正常）
                'market_trend_strength': 0.5  # TODO: 市場趨勢強度
            })
            
            # 驗證特徵完整性
            expected_features = 36  # 15 + 12 + 9
            actual_features = len(features)
            
            if actual_features != expected_features:
                logger.warning(f"特徵數量不匹配: 期望{expected_features}個，實際{actual_features}個")
            
            logger.info(f"已計算基礎特徵，共{actual_features}個特徵")
            return features
            
        except Exception as e:
            logger.error(f"計算基礎特徵時出錯: {str(e)}")
            logger.error(f"詳細錯誤信息: {traceback.format_exc()}")
            # 返回安全的默認特徵值
            return self._get_default_features()
    
    def _get_trading_session(self, hour: int) -> int:
        """獲取交易時段 (1=亞洲, 2=歐洲, 3=美洲)"""
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
        """獲取交易對分類 (1=BTC, 2=ETH, 3=主流, 4=山寨)"""
        try:
            symbol_upper = symbol.upper()
            if 'BTC' in symbol_upper:
                return 1
            elif 'ETH' in symbol_upper:
                return 2
            elif symbol_upper in ['ADAUSDT', 'DOTUSDT', 'LINKUSDT', 'SOLUSDT', 'AVAXUSDT']:
                return 3  # 主流幣
            else:
                return 4  # 山寨幣
        except:
            return 4
    
    def _get_default_features(self) -> Dict[str, Any]:
        """獲取安全的默認特徵值 - 確保36個特徵"""
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
            'hour_of_day': 12,
            'trading_session': 1,
            'weekend_factor': 0,
            'symbol_category': 4,
            'current_positions': 0,
            'margin_ratio': 0.5,
            'atr_normalized': 0.01,
            'volatility_regime': 1,
            'market_trend_strength': 0.5
        }

def create_ml_data_manager(db_path: str) -> MLDataManager:
    """創建ML數據管理器實例"""
    return MLDataManager(db_path)
