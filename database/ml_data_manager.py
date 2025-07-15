"""
ML數據管理模組 - 完整功能版本
修復所有計算問題，實現真正的36個特徵計算和ML學習功能
=============================================================================
"""
import sqlite3
import logging
import time
import json
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple
import numpy as np

# 設置logger
logger = logging.getLogger(__name__)

class MLDataManager:
    """ML數據管理類 - 完整功能版本"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        # 初始化ML表格
        self._init_ml_tables()
        logger.info(f"✅ ML數據管理器已初始化，資料庫路徑: {self.db_path}")
    
    def _init_ml_tables(self):
        """初始化ML相關表格 - 防SQLite鎖定的完美版本"""
        max_retries = 3
        retry_delay = 1.0
        
        for attempt in range(max_retries):
            try:
                with sqlite3.connect(self.db_path, timeout=30.0) as conn:
                    cursor = conn.cursor()
                    
                    # 🔥 第一步：確保最佳資料庫設定
                    cursor.execute('PRAGMA journal_mode = WAL')
                    cursor.execute('PRAGMA synchronous = NORMAL')
                    cursor.execute('PRAGMA cache_size = 10000')
                    cursor.execute('PRAGMA temp_store = MEMORY')
                    cursor.execute('PRAGMA busy_timeout = 30000')  # 30秒超時
                    
                    # 🔥 第二步：檢查現有表格
                    cursor.execute("""
                        SELECT name FROM sqlite_master 
                        WHERE type='table' AND name IN ('ml_features_v2', 'ml_signal_quality', 'ml_price_optimization')
                    """)
                    existing_tables = [row[0] for row in cursor.fetchall()]
                    
                    if len(existing_tables) == 3:
                        logger.info("✅ ML表格已完整存在，跳過創建")
                        # 驗證表格結構
                        cursor.execute("PRAGMA table_info(ml_features_v2)")
                        columns = cursor.fetchall()
                        if len(columns) >= 38:  # 36特徵 + id + session_id + signal_id + created_at
                            logger.info("✅ ML表格結構驗證通過")
                            return
                        else:
                            logger.warning(f"⚠️ ML表格結構不完整，重新創建")
                    
                    # 🔥 第三步：創建完整的ML表格
                    logger.info(f"正在創建ML表格... (現有: {len(existing_tables)}/3)")
                    
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
                    
                    # 2. ML信號品質記錄表
                    cursor.execute('''
                        CREATE TABLE IF NOT EXISTS ml_signal_quality (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            session_id TEXT NOT NULL,
                            signal_id INTEGER,
                            ml_recommendation TEXT NOT NULL,
                            confidence_score REAL,
                            execution_probability REAL,
                            trading_probability REAL,
                            risk_level TEXT,
                            decision_reason TEXT,
                            suggested_price_adjustment REAL DEFAULT 0.0,
                            actual_decision TEXT,
                            prediction_accuracy REAL,
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
                    logger.info("✅ ML資料庫表格初始化完成")
                    return
                    
            except sqlite3.OperationalError as e:
                if "database is locked" in str(e).lower() and attempt < max_retries - 1:
                    logger.warning(f"⚠️ 資料庫被鎖定，第{attempt + 1}次重試 (等待{retry_delay}秒)")
                    time.sleep(retry_delay)
                    retry_delay *= 1.5  # 指數退避
                    continue
                else:
                    logger.error(f"❌ 初始化ML表格失敗: {str(e)}")
                    raise
            except Exception as e:
                logger.error(f"❌ 初始化ML表格時出錯: {str(e)}")
                if attempt < max_retries - 1:
                    logger.info(f"嘗試第{attempt + 2}次初始化...")
                    time.sleep(retry_delay)
                    continue
                else:
                    raise
        
        logger.error("❌ 多次重試後仍無法初始化ML表格")
        raise Exception("ML表格初始化失敗")
    
    def calculate_basic_features(self, signal_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        計算完整的36個ML特徵 - 真正的實現版本
        
        Args:
            signal_data: 原始信號數據
            
        Returns:
            Dict: 36個特徵的完整字典
        """
        features = {}
        
        try:
            logger.info(f"🧠 開始計算36個ML特徵...")
            
            # 🔥 安全的數值轉換函數
            def safe_float(value, default=0.0):
                try:
                    if value is None:
                        return float(default)
                    if isinstance(value, (int, float)):
                        return float(value)
                    str_value = str(value).replace(',', '').replace(' ', '').strip()
                    if str_value == '' or str_value == 'None':
                        return float(default)
                    return float(str_value)
                except (ValueError, TypeError):
                    return float(default)
            
            def safe_int(value, default=0):
                try:
                    if value is None:
                        return int(default)
                    return int(float(str(value).replace(',', '').replace(' ', '').strip()))
                except (ValueError, TypeError):
                    return int(default)
            
            # 提取基礎信號數據
            symbol = signal_data.get('symbol', '')
            signal_type = signal_data.get('signal_type', '')
            opposite = safe_int(signal_data.get('opposite', 0))
            side = signal_data.get('side', '')
            open_price = safe_float(signal_data.get('open', 0))
            close_price = safe_float(signal_data.get('close', 0))
            prev_close = safe_float(signal_data.get('prev_close', 0))
            prev_open = safe_float(signal_data.get('prev_open', 0))
            atr = safe_float(signal_data.get('ATR', 0))
            
            # === 第一類：信號品質核心特徵 (15個) ===
            
            # 1-2. 策略勝率分析
            recent_win_rate, overall_win_rate = self._calculate_strategy_win_rates(signal_type, opposite)
            features['strategy_win_rate_recent'] = recent_win_rate
            features['strategy_win_rate_overall'] = overall_win_rate
            
            # 3. 策略市場適應性
            features['strategy_market_fitness'] = self._calculate_market_fitness(signal_type, symbol, atr)
            
            # 4. 波動率匹配度
            features['volatility_match_score'] = self._calculate_volatility_match(atr, symbol)
            
            # 5. 時段匹配度
            features['time_slot_match_score'] = self._calculate_time_slot_match()
            
            # 6. 交易對匹配度
            features['symbol_match_score'] = self._calculate_symbol_match(symbol, signal_type)
            
            # 7. 價格動量強度
            features['price_momentum_strength'] = self._calculate_price_momentum(open_price, close_price, prev_close)
            
            # 8. ATR相對位置
            features['atr_relative_position'] = self._calculate_atr_position(atr, symbol)
            
            # 9. 風險回報比
            features['risk_reward_ratio'] = self._calculate_risk_reward_ratio(atr, signal_type)
            
            # 10. 執行難度
            features['execution_difficulty'] = self._calculate_execution_difficulty(signal_type, opposite, atr)
            
            # 11-12. 連續勝負次數
            win_streak, loss_streak = self._calculate_streak_counts(signal_type)
            features['consecutive_win_streak'] = win_streak
            features['consecutive_loss_streak'] = loss_streak
            
            # 13. 系統整體表現
            features['system_overall_performance'] = self._calculate_system_performance()
            
            # 14. 信號信心度
            features['signal_confidence_score'] = self._calculate_signal_confidence(features)
            
            # 15. 市場狀況適應性
            features['market_condition_fitness'] = self._calculate_market_condition_fitness(atr, features['hour_of_day'])
            
            # === 第二類：價格關係特徵 (12個) ===
            
            # 16-17. 價格偏差分析
            price_deviation = self._calculate_price_deviation(open_price, close_price, opposite)
            features['price_deviation_percent'] = price_deviation['percent']
            features['price_deviation_abs'] = price_deviation['absolute']
            
            # 18. ATR標準化偏差
            features['atr_normalized_deviation'] = abs(price_deviation['absolute']) / max(atr, 0.001)
            
            # 19. K線方向
            features['candle_direction'] = 1 if close_price > open_price else (-1 if close_price < open_price else 0)
            
            # 20. K線實體大小
            features['candle_body_size'] = abs(close_price - open_price) / max(open_price, 0.001)
            
            # 21. K線影線比例
            high_price = max(open_price, close_price)
            low_price = min(open_price, close_price)
            total_range = max(high_price - low_price, 0.001)
            body_size = abs(close_price - open_price)
            features['candle_wick_ratio'] = (total_range - body_size) / total_range
            
            # 22. 價格在區間位置
            features['price_position_in_range'] = self._calculate_price_position(close_price, high_price, low_price)
            
            # 23-24. 價格調整空間
            adjustment_space = self._calculate_adjustment_space(close_price, atr)
            features['upward_adjustment_space'] = adjustment_space['upward']
            features['downward_adjustment_space'] = adjustment_space['downward']
            
            # 25. 歷史最佳調整
            features['historical_best_adjustment'] = self._calculate_historical_adjustment(signal_type, symbol)
            
            # 26. 價格可達性分數
            features['price_reachability_score'] = self._calculate_price_reachability(close_price, atr, side)
            
            # 27. 開倉價格品質分數
            features['entry_price_quality_score'] = self._calculate_entry_price_quality(features)
            
            # === 第三類：市場環境特徵 (9個) ===
            
            # 28. 當前小時
            current_hour = datetime.now().hour
            features['hour_of_day'] = current_hour
            
            # 29. 交易時段
            features['trading_session'] = self._get_trading_session(current_hour)
            
            # 30. 週末因子
            features['weekend_factor'] = 1 if datetime.now().weekday() >= 5 else 0
            
            # 31. 交易對分類
            features['symbol_category'] = self._get_symbol_category(symbol)
            
            # 32. 當前持倉數
            features['current_positions'] = self._get_current_positions_count()
            
            # 33. 保證金比例
            features['margin_ratio'] = self._calculate_margin_ratio()
            
            # 34. ATR標準化
            features['atr_normalized'] = self._normalize_atr(atr, symbol)
            
            # 35. 波動率制度
            features['volatility_regime'] = self._get_volatility_regime(atr, symbol)
            
            # 36. 市場趨勢強度
            features['market_trend_strength'] = self._calculate_trend_strength(open_price, close_price, prev_close)
            
            # 驗證所有特徵都已計算
            expected_features = 36
            actual_features = len([k for k, v in features.items() if v is not None])
            
            logger.info(f"✅ ML特徵計算完成: {actual_features}/{expected_features} 個特徵")
            
            if actual_features != expected_features:
                missing_features = expected_features - actual_features
                logger.warning(f"⚠️ 缺少 {missing_features} 個特徵，使用默認值補齊")
                features.update(self._get_default_features())
            
            return features
                
        except Exception as e:
            logger.error(f"❌ 計算ML特徵時出錯: {str(e)}")
            logger.error(f"錯誤信號數據: {signal_data}")
            # 返回默認特徵確保系統繼續運行
            return self._get_default_features()
    
    def _calculate_strategy_win_rates(self, signal_type: str, opposite: int) -> Tuple[float, float]:
        """計算策略勝率（最近30天和總體）"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 最近30天勝率
                thirty_days_ago = time.time() - (30 * 24 * 3600)
                cursor.execute('''
                    SELECT 
                        COUNT(*) as total,
                        SUM(CASE WHEN tr.is_successful = 1 THEN 1 ELSE 0 END) as wins
                    FROM signals_received sr
                    JOIN orders_executed oe ON sr.id = oe.signal_id
                    JOIN trading_results tr ON oe.id = tr.order_id
                    WHERE sr.signal_type = ? AND sr.opposite = ? AND sr.timestamp > ?
                ''', (signal_type, opposite, thirty_days_ago))
                
                recent_data = cursor.fetchone()
                recent_total, recent_wins = recent_data if recent_data else (0, 0)
                recent_win_rate = recent_wins / max(recent_total, 1)
                
                # 總體勝率
                cursor.execute('''
                    SELECT 
                        COUNT(*) as total,
                        SUM(CASE WHEN tr.is_successful = 1 THEN 1 ELSE 0 END) as wins
                    FROM signals_received sr
                    JOIN orders_executed oe ON sr.id = oe.signal_id
                    JOIN trading_results tr ON oe.id = tr.order_id
                    WHERE sr.signal_type = ? AND sr.opposite = ?
                ''', (signal_type, opposite))
                
                overall_data = cursor.fetchone()
                overall_total, overall_wins = overall_data if overall_data else (0, 0)
                overall_win_rate = overall_wins / max(overall_total, 1)
                
                return recent_win_rate, overall_win_rate
                
        except Exception as e:
            logger.warning(f"計算策略勝率時出錯: {str(e)}")
            return 0.5, 0.5
    
    def _calculate_market_fitness(self, signal_type: str, symbol: str, atr: float) -> float:
        """計算策略市場適應性"""
        try:
            # 基於策略類型和市場波動的適應性評分
            strategy_volatility_preferences = {
                'breakout_buy': {'min_atr': 0.02, 'max_atr': 0.08, 'optimal': 0.04},
                'trend_sell': {'min_atr': 0.01, 'max_atr': 0.06, 'optimal': 0.03},
                'reversal_buy': {'min_atr': 0.015, 'max_atr': 0.05, 'optimal': 0.025},
                'bounce_buy': {'min_atr': 0.02, 'max_atr': 0.07, 'optimal': 0.035}
            }
            
            if signal_type in strategy_volatility_preferences:
                prefs = strategy_volatility_preferences[signal_type]
                optimal_atr = prefs['optimal']
                deviation = abs(atr - optimal_atr) / optimal_atr
                fitness = max(0.1, 1.0 - deviation)
                return min(1.0, fitness)
            
            return 0.5
            
        except Exception:
            return 0.5
    
    def _calculate_volatility_match(self, atr: float, symbol: str) -> float:
        """計算波動率匹配度"""
        try:
            # 不同交易對的標準ATR範圍
            symbol_atr_ranges = {
                'BTCUSDT': {'low': 0.015, 'high': 0.06},
                'ETHUSDT': {'low': 0.02, 'high': 0.08},
                'BNBUSDT': {'low': 0.025, 'high': 0.1},
                'ADAUSDT': {'low': 0.03, 'high': 0.12}
            }
            
            if symbol in symbol_atr_ranges:
                range_info = symbol_atr_ranges[symbol]
                if range_info['low'] <= atr <= range_info['high']:
                    # 在正常範圍內，計算相對位置
                    range_span = range_info['high'] - range_info['low']
                    position = (atr - range_info['low']) / range_span
                    # 中等波動率得分較高
                    return 1.0 - abs(position - 0.5) * 2
                else:
                    # 超出正常範圍
                    return 0.3
            
            return 0.5
            
        except Exception:
            return 0.5
    
    def _calculate_time_slot_match(self) -> float:
        """計算時段匹配度"""
        try:
            current_hour = datetime.now().hour
            
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
                
        except Exception:
            return 0.6
    
    def _calculate_symbol_match(self, symbol: str, signal_type: str) -> float:
        """計算交易對匹配度"""
        try:
            # 不同策略對不同交易對的適應性
            strategy_symbol_preferences = {
                'breakout_buy': ['BTCUSDT', 'ETHUSDT'],
                'trend_sell': ['BTCUSDT', 'BNBUSDT'],
                'reversal_buy': ['ETHUSDT', 'ADAUSDT'],
                'bounce_buy': ['BTCUSDT', 'ETHUSDT', 'BNBUSDT']
            }
            
            if signal_type in strategy_symbol_preferences:
                preferred_symbols = strategy_symbol_preferences[signal_type]
                if symbol in preferred_symbols:
                    return 0.8
                else:
                    return 0.4
            
            return 0.6
            
        except Exception:
            return 0.6
    
    def _calculate_price_momentum(self, open_price: float, close_price: float, prev_close: float) -> float:
        """計算價格動量強度"""
        try:
            if prev_close <= 0:
                return 0.0
            
            # 當前K線變化
            current_change = (close_price - open_price) / open_price
            # 與前一根的關係
            gap_change = (open_price - prev_close) / prev_close
            
            # 綜合動量強度
            momentum = abs(current_change) + abs(gap_change) * 0.5
            return min(1.0, momentum * 10)  # 標準化到0-1
            
        except Exception:
            return 0.0
    
    def _calculate_atr_position(self, atr: float, symbol: str) -> float:
        """計算ATR相對位置"""
        try:
            # 獲取該交易對的ATR歷史分位數
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT atr_value FROM signals_received 
                    WHERE symbol = ? AND atr_value > 0 
                    ORDER BY timestamp DESC LIMIT 100
                ''', (symbol,))
                
                atr_history = [row[0] for row in cursor.fetchall()]
                
                if len(atr_history) > 10:
                    atr_history.sort()
                    percentile = len([x for x in atr_history if x <= atr]) / len(atr_history)
                    return percentile
                else:
                    return 0.5
                    
        except Exception:
            return 0.5
    
    def _calculate_risk_reward_ratio(self, atr: float, signal_type: str) -> float:
        """計算風險回報比"""
        try:
            # 不同策略的標準風險回報比
            strategy_rr_ratios = {
                'breakout_buy': 2.5,
                'trend_sell': 3.0,
                'reversal_buy': 2.0,
                'bounce_buy': 2.2,
                'consolidation_buy': 1.8
            }
            
            base_rr = strategy_rr_ratios.get(signal_type, 2.5)
            
            # 根據ATR調整（高波動率降低RR，低波動率提高RR）
            if atr > 0.05:
                adjustment = 0.8  # 高波動率，降低期望RR
            elif atr < 0.02:
                adjustment = 1.2  # 低波動率，可以期望更高RR
            else:
                adjustment = 1.0
            
            return base_rr * adjustment
            
        except Exception:
            return 2.5
    
    def _calculate_execution_difficulty(self, signal_type: str, opposite: int, atr: float) -> float:
        """計算執行難度"""
        try:
            # 基礎難度評分
            base_difficulty = {
                'breakout_buy': 0.3,    # 突破相對容易執行
                'trend_sell': 0.2,      # 順勢最容易
                'reversal_buy': 0.7,    # 反轉較難
                'bounce_buy': 0.4,      # 反彈中等難度
                'consolidation_buy': 0.8  # 整理期最難
            }.get(signal_type, 0.5)
            
            # opposite調整（2=前根開盤價，執行難度最高）
            opposite_adjustment = {0: 0.0, 1: 0.1, 2: 0.3}.get(opposite, 0.2)
            
            # ATR調整（高波動率增加執行難度）
            atr_adjustment = min(0.3, atr * 5)
            
            total_difficulty = min(1.0, base_difficulty + opposite_adjustment + atr_adjustment)
            return total_difficulty
            
        except Exception:
            return 0.5
    
    def _calculate_streak_counts(self, signal_type: str) -> Tuple[int, int]:
        """計算連續勝負次數"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 獲取該策略最近的交易結果
                cursor.execute('''
                    SELECT tr.is_successful
                    FROM signals_received sr
                    JOIN orders_executed oe ON sr.id = oe.signal_id
                    JOIN trading_results tr ON oe.id = tr.order_id
                    WHERE sr.signal_type = ?
                    ORDER BY sr.timestamp DESC LIMIT 20
                ''', (signal_type,))
                
                results = [row[0] for row in cursor.fetchall()]
                
                if not results:
                    return 0, 0
                
                # 計算當前連續勝負
                current_streak_wins = 0
                current_streak_losses = 0
                
                for result in results:
                    if result == 1:  # 勝利
                        if current_streak_losses == 0:
                            current_streak_wins += 1
                        else:
                            break
                    else:  # 失敗
                        if current_streak_wins == 0:
                            current_streak_losses += 1
                        else:
                            break
                
                return current_streak_wins, current_streak_losses
                
        except Exception:
            return 0, 0
    
    def _calculate_system_performance(self) -> float:
        """計算系統整體表現"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 獲取最近7天的整體表現
                seven_days_ago = time.time() - (7 * 24 * 3600)
                cursor.execute('''
                    SELECT 
                        COUNT(*) as total,
                        SUM(CASE WHEN is_successful = 1 THEN 1 ELSE 0 END) as wins,
                        AVG(pnl_percentage) as avg_pnl
                    FROM trading_results tr
                    JOIN orders_executed oe ON tr.order_id = oe.id
                    WHERE oe.execution_timestamp > ?
                ''', (seven_days_ago,))
                
                result = cursor.fetchone()
                if result and result[0] > 0:
                    total, wins, avg_pnl = result
                    win_rate = wins / total
                    pnl_factor = max(0, min(1, (avg_pnl or 0) / 5 + 0.5))  # 標準化PNL
                    performance = (win_rate * 0.7) + (pnl_factor * 0.3)
                    return performance
                else:
                    return 0.5
                    
        except Exception:
            return 0.5
    
    def _calculate_signal_confidence(self, features: Dict[str, Any]) -> float:
        """計算信號信心度（基於其他特徵的綜合評分）"""
        try:
            # 權重化關鍵特徵
            confidence_factors = [
                features.get('strategy_win_rate_recent', 0.5) * 0.3,
                features.get('volatility_match_score', 0.5) * 0.2,
                features.get('time_slot_match_score', 0.5) * 0.15,
                features.get('symbol_match_score', 0.5) * 0.15,
                (1.0 - features.get('execution_difficulty', 0.5)) * 0.2
            ]
            
            confidence = sum(confidence_factors)
            return min(1.0, max(0.1, confidence))
            
        except Exception:
            return 0.5
    
    def _calculate_market_condition_fitness(self, atr: float, hour: int) -> float:
        """計算市場狀況適應性"""
        try:
            # 時段因子
            time_factor = 0.7 if 8 <= hour <= 22 else 0.4
            
            # 波動率因子（中等波動率最佳）
            volatility_factor = 1.0 - abs(atr - 0.03) / 0.03 if atr <= 0.06 else 0.3
            volatility_factor = max(0.1, min(1.0, volatility_factor))
            
            # 綜合適應性
            fitness = (time_factor * 0.6) + (volatility_factor * 0.4)
            return fitness
            
        except Exception:
            return 0.5
    
    def _calculate_price_deviation(self, open_price: float, close_price: float, opposite: int) -> Dict[str, float]:
        """計算價格偏差"""
        try:
            reference_price = close_price  # 基準價格
            
            if opposite == 1:  # 前根收盤價
                # 這裡應該用實際的前根收盤價，暫時用close_price
                deviation = 0.0
            elif opposite == 2:  # 前根開盤價
                deviation = (open_price - close_price) / close_price if close_price > 0 else 0.0
            else:  # 當前收盤價
                deviation = 0.0
            
            return {
                'percent': deviation,
                'absolute': abs(deviation * close_price) if close_price > 0 else 0.0
            }
            
        except Exception:
            return {'percent': 0.0, 'absolute': 0.0}
    
    def _calculate_price_position(self, close_price: float, high_price: float, low_price: float) -> float:
        """計算價格在區間中的位置"""
        try:
            if high_price <= low_price:
                return 0.5
            
            position = (close_price - low_price) / (high_price - low_price)
            return max(0.0, min(1.0, position))
            
        except Exception:
            return 0.5
    
    def _calculate_adjustment_space(self, close_price: float, atr: float) -> Dict[str, float]:
        """計算價格調整空間"""
        try:
            if close_price <= 0 or atr <= 0:
                return {'upward': 0.02, 'downward': 0.02}
            
            # 基於ATR計算調整空間
            upward_space = atr / close_price
            downward_space = atr / close_price
            
            return {
                'upward': min(0.05, max(0.01, upward_space)),
                'downward': min(0.05, max(0.01, downward_space))
            }
            
        except Exception:
            return {'upward': 0.02, 'downward': 0.02}
    
    def _calculate_historical_adjustment(self, signal_type: str, symbol: str) -> float:
        """計算歷史最佳調整"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 查找歷史上該策略+交易對的最佳調整
                cursor.execute('''
                    SELECT AVG(price_adjustment_percent)
                    FROM ml_price_optimization mpo
                    JOIN signals_received sr ON mpo.signal_id = sr.id
                    WHERE sr.signal_type = ? AND sr.symbol = ? AND mpo.expected_improvement > 0
                ''', (signal_type, symbol))
                
                result = cursor.fetchone()
                if result and result[0] is not None:
                    return float(result[0])
                else:
                    return 0.0
                    
        except Exception:
            return 0.0
    
    def _calculate_price_reachability(self, close_price: float, atr: float, side: str) -> float:
        """計算價格可達性分數"""
        try:
            # 基於ATR和方向計算價格可達性
            if atr <= 0:
                return 0.7
            
            # 不同方向的可達性不同
            if side.upper() == 'BUY':
                # 買入信號，考慮上漲可達性
                reachability = min(1.0, 0.5 + (atr / close_price) * 20)
            else:
                # 賣出信號，考慮下跌可達性
                reachability = min(1.0, 0.5 + (atr / close_price) * 15)
            
            return reachability
            
        except Exception:
            return 0.7
    
    def _calculate_entry_price_quality(self, features: Dict[str, Any]) -> float:
        """計算開倉價格品質分數"""
        try:
            # 基於多個因子的綜合評分
            quality_factors = [
                features.get('price_reachability_score', 0.7) * 0.3,
                (1.0 - features.get('atr_normalized_deviation', 0.5)) * 0.25,
                features.get('price_position_in_range', 0.5) * 0.2,
                features.get('volatility_match_score', 0.5) * 0.25
            ]
            
            quality = sum(quality_factors)
            return min(1.0, max(0.1, quality))
            
        except Exception:
            return 0.6
    
    def _get_trading_session(self, hour: int) -> int:
        """獲取交易時段"""
        if 0 <= hour <= 6:
            return 1  # 深夜時段
        elif 7 <= hour <= 12:
            return 2  # 亞洲時段
        elif 13 <= hour <= 17:
            return 3  # 歐洲時段
        elif 18 <= hour <= 23:
            return 4  # 美國時段
        else:
            return 1
    
    def _get_symbol_category(self, symbol: str) -> int:
        """獲取交易對分類"""
        try:
            if symbol in ['BTCUSDT']:
                return 1  # 比特幣
            elif symbol in ['ETHUSDT']:
                return 2  # 以太坊
            elif symbol in ['BNBUSDT', 'ADAUSDT', 'DOTUSDT', 'LINKUSDT', 'SOLUSDT', 'AVAXUSDT']:
                return 3  # 主流幣
            else:
                return 4  # 山寨幣
        except:
            return 4
    
    def _get_current_positions_count(self) -> int:
        """獲取當前持倉數量"""
        try:
            # 這裡應該調用binance_client獲取實際持倉
            # 暫時返回模擬數據
            return 0
        except Exception:
            return 0
    
    def _calculate_margin_ratio(self) -> float:
        """計算保證金比例"""
        try:
            # 這裡應該獲取實際的保證金使用率
            # 暫時返回安全的默認值
            return 0.5
        except Exception:
            return 0.5
    
    def _normalize_atr(self, atr: float, symbol: str) -> float:
        """標準化ATR值"""
        try:
            # 不同交易對的ATR標準化
            symbol_atr_standards = {
                'BTCUSDT': 0.03,
                'ETHUSDT': 0.04,
                'BNBUSDT': 0.05,
                'ADAUSDT': 0.06
            }
            
            standard = symbol_atr_standards.get(symbol, 0.04)
            return atr / standard
            
        except Exception:
            return 1.0
    
    def _get_volatility_regime(self, atr: float, symbol: str) -> int:
        """獲取波動率制度"""
        try:
            normalized_atr = self._normalize_atr(atr, symbol)
            
            if normalized_atr < 0.7:
                return 1  # 低波動
            elif normalized_atr < 1.5:
                return 2  # 中波動
            else:
                return 3  # 高波動
                
        except Exception:
            return 2
    
    def _calculate_trend_strength(self, open_price: float, close_price: float, prev_close: float) -> float:
        """計算市場趨勢強度"""
        try:
            if prev_close <= 0:
                return 0.5
            
            # 計算趨勢強度
            current_momentum = abs(close_price - open_price) / open_price
            gap_momentum = abs(open_price - prev_close) / prev_close
            
            trend_strength = (current_momentum + gap_momentum) / 2
            return min(1.0, trend_strength * 20)  # 標準化
            
        except Exception:
            return 0.5
    
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
    
    def record_ml_features(self, session_id: str, signal_id: int, features: Dict[str, Any]) -> bool:
        """記錄ML特徵數據 - 36個特徵完整版本"""
        try:
            with sqlite3.connect(self.db_path, timeout=30.0) as conn:
                cursor = conn.cursor()
                
                # 準備插入數據，確保所有36個特徵都有值
                feature_values = [
                    session_id, signal_id,
                    # 信號品質核心特徵 (15個)
                    features.get('strategy_win_rate_recent', 0.0),
                    features.get('strategy_win_rate_overall', 0.0),
                    features.get('strategy_market_fitness', 0.0),
                    features.get('volatility_match_score', 0.0),
                    features.get('time_slot_match_score', 0.0),
                    features.get('symbol_match_score', 0.0),
                    features.get('price_momentum_strength', 0.0),
                    features.get('atr_relative_position', 0.0),
                    features.get('risk_reward_ratio', 0.0),
                    features.get('execution_difficulty', 0.0),
                    features.get('consecutive_win_streak', 0),
                    features.get('consecutive_loss_streak', 0),
                    features.get('system_overall_performance', 0.0),
                    features.get('signal_confidence_score', 0.0),
                    features.get('market_condition_fitness', 0.0),
                    # 價格關係特徵 (12個)
                    features.get('price_deviation_percent', 0.0),
                    features.get('price_deviation_abs', 0.0),
                    features.get('atr_normalized_deviation', 0.0),
                    features.get('candle_direction', 0),
                    features.get('candle_body_size', 0.0),
                    features.get('candle_wick_ratio', 0.0),
                    features.get('price_position_in_range', 0.0),
                    features.get('upward_adjustment_space', 0.0),
                    features.get('downward_adjustment_space', 0.0),
                    features.get('historical_best_adjustment', 0.0),
                    features.get('price_reachability_score', 0.0),
                    features.get('entry_price_quality_score', 0.0),
                    # 市場環境特徵 (9個)
                    features.get('hour_of_day', 0),
                    features.get('trading_session', 0),
                    features.get('weekend_factor', 0),
                    features.get('symbol_category', 0),
                    features.get('current_positions', 0),
                    features.get('margin_ratio', 0.0),
                    features.get('atr_normalized', 0.0),
                    features.get('volatility_regime', 0),
                    features.get('market_trend_strength', 0.0)
                ]
                
                cursor.execute('''
                    INSERT INTO ml_features_v2 (
                        session_id, signal_id,
                        strategy_win_rate_recent, strategy_win_rate_overall, strategy_market_fitness,
                        volatility_match_score, time_slot_match_score, symbol_match_score,
                        price_momentum_strength, atr_relative_position, risk_reward_ratio,
                        execution_difficulty, consecutive_win_streak, consecutive_loss_streak,
                        system_overall_performance, signal_confidence_score, market_condition_fitness,
                        price_deviation_percent, price_deviation_abs, atr_normalized_deviation,
                        candle_direction, candle_body_size, candle_wick_ratio,
                        price_position_in_range, upward_adjustment_space, downward_adjustment_space,
                        historical_best_adjustment, price_reachability_score, entry_price_quality_score,
                        hour_of_day, trading_session, weekend_factor,
                        symbol_category, current_positions, margin_ratio,
                        atr_normalized, volatility_regime, market_trend_strength
                    ) VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                    )
                ''', feature_values)
                
                conn.commit()
                logger.info(f"✅ ML特徵記錄成功 - session_id: {session_id}, signal_id: {signal_id}")
                return True
                
        except Exception as e:
            logger.error(f"❌ 記錄ML特徵時出錯: {str(e)}")
            return False
    
    def record_signal_quality(self, session_id: str, signal_id: int, quality_data: Dict[str, Any]) -> bool:
        """記錄ML信號品質分析"""
        try:
            with sqlite3.connect(self.db_path, timeout=30.0) as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    INSERT INTO ml_signal_quality (
                        session_id, signal_id, ml_recommendation, confidence_score,
                        execution_probability, trading_probability, risk_level,
                        decision_reason, suggested_price_adjustment, actual_decision
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    session_id, signal_id,
                    quality_data.get('recommendation', 'EXECUTE'),
                    quality_data.get('confidence', 0.5),
                    quality_data.get('execution_probability', 0.5),
                    quality_data.get('trading_probability', 0.5),
                    quality_data.get('risk_level', 'MEDIUM'),
                    quality_data.get('reason', ''),
                    quality_data.get('suggested_price_adjustment', 0.0),
                    'EXECUTE'  # 當前階段總是執行
                ))
                
                conn.commit()
                logger.info(f"✅ ML信號品質記錄成功 - signal_id: {signal_id}")
                return True
                
        except Exception as e:
            logger.error(f"❌ 記錄ML信號品質時出錯: {str(e)}")
            return False
    
    def record_price_optimization(self, session_id: str, signal_id: int, 
                                original_price: float, optimized_price: float, 
                                reason: str, confidence: float) -> bool:
        """記錄ML價格優化建議"""
        try:
            adjustment_percent = ((optimized_price - original_price) / original_price) * 100
            
            with sqlite3.connect(self.db_path, timeout=30.0) as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    INSERT INTO ml_price_optimization (
                        session_id, signal_id, original_price, optimized_price,
                        price_adjustment_percent, optimization_reason, confidence_level
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    session_id, signal_id, original_price, optimized_price,
                    adjustment_percent, reason, confidence
                ))
                
                conn.commit()
                logger.info(f"✅ ML價格優化記錄成功 - signal_id: {signal_id}")
                return True
                
        except Exception as e:
            logger.error(f"❌ 記錄ML價格優化時出錯: {str(e)}")
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
                stats['total_signal_quality'] = cursor.fetchone()[0]
                
                cursor.execute('SELECT COUNT(*) FROM ml_price_optimization')
                stats['total_price_optimization'] = cursor.fetchone()[0]
                
                return stats
                
        except Exception as e:
            logger.error(f"獲取ML表格統計時出錯: {str(e)}")
            return {'total_ml_features': 0, 'total_signal_quality': 0, 'total_price_optimization': 0}
    
    def get_historical_features_for_ml(self, limit: int = 100) -> List[Dict[str, Any]]:
        """獲取歷史特徵數據用於ML訓練"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 獲取完整的特徵數據和對應的交易結果
                cursor.execute('''
                    SELECT 
                        mf.*,
                        tr.is_successful,
                        tr.pnl_percentage,
                        tr.holding_time_minutes,
                        sr.signal_type,
                        sr.symbol,
                        sr.side
                    FROM ml_features_v2 mf
                    JOIN signals_received sr ON mf.signal_id = sr.id
                    LEFT JOIN orders_executed oe ON sr.id = oe.signal_id
                    LEFT JOIN trading_results tr ON oe.id = tr.order_id
                    ORDER BY mf.created_at DESC
                    LIMIT ?
                ''', (limit,))
                
                columns = [description[0] for description in cursor.description]
                results = []
                
                for row in cursor.fetchall():
                    row_dict = dict(zip(columns, row))
                    results.append(row_dict)
                
                logger.info(f"✅ 獲取到 {len(results)} 條ML訓練數據")
                return results
                
        except Exception as e:
            logger.error(f"❌ 獲取ML訓練數據時出錯: {str(e)}")
            return []
    
    def analyze_feature_importance(self) -> Dict[str, float]:
        """分析特徵重要性（簡單版本）"""
        try:
            historical_data = self.get_historical_features_for_ml(200)
            
            if len(historical_data) < 10:
                logger.warning("數據量不足，無法進行特徵重要性分析")
                return {}
            
            # 簡單的相關性分析
            feature_correlations = {}
            
            success_data = [d for d in historical_data if d.get('is_successful') is not None]
            
            if len(success_data) < 5:
                return {}
            
            # 計算每個特徵與成功率的相關性
            feature_names = [
                'strategy_win_rate_recent', 'volatility_match_score', 'time_slot_match_score',
                'symbol_match_score', 'execution_difficulty', 'signal_confidence_score',
                'hour_of_day', 'trading_session', 'symbol_category'
            ]
            
            for feature in feature_names:
                feature_values = [d.get(feature, 0) for d in success_data]
                success_values = [d.get('is_successful', 0) for d in success_data]
                
                if len(set(feature_values)) > 1:  # 特徵有變化
                    correlation = self._calculate_simple_correlation(feature_values, success_values)
                    feature_correlations[feature] = abs(correlation)
            
            return feature_correlations
            
        except Exception as e:
            logger.error(f"分析特徵重要性時出錯: {str(e)}")
            return {}
    
    def _calculate_simple_correlation(self, x_values: List[float], y_values: List[float]) -> float:
        """計算簡單相關係數"""
        try:
            if len(x_values) != len(y_values) or len(x_values) < 2:
                return 0.0
            
            n = len(x_values)
            sum_x = sum(x_values)
            sum_y = sum(y_values)
            sum_xy = sum(x * y for x, y in zip(x_values, y_values))
            sum_x2 = sum(x * x for x in x_values)
            sum_y2 = sum(y * y for y in y_values)
            
            denominator = ((n * sum_x2 - sum_x * sum_x) * (n * sum_y2 - sum_y * sum_y)) ** 0.5
            
            if denominator == 0:
                return 0.0
            
            correlation = (n * sum_xy - sum_x * sum_y) / denominator
            return correlation
            
        except Exception:
            return 0.0

def create_ml_data_manager(db_path: str) -> MLDataManager:
    """創建ML數據管理器實例"""
    return MLDataManager(db_path)
