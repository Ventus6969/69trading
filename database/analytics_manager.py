"""
統計分析數據管理模組
負責勝率統計、策略分析和資料庫統計功能
=============================================================================
"""
import sqlite3
import os
import logging
from datetime import datetime
from typing import Dict, Any, List

# 設置logger
logger = logging.getLogger(__name__)

class AnalyticsManager:
    """統計分析管理類"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        logger.info(f"統計分析管理器已初始化，資料庫路徑: {self.db_path}")
    
    def get_win_rate_stats(self) -> Dict[str, Any]:
        """獲取勝率統計"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 總體勝率
                cursor.execute("""
                    SELECT 
                        COUNT(*) as total,
                        SUM(CASE WHEN is_successful = 1 THEN 1 ELSE 0 END) as wins,
                        SUM(final_pnl) as total_pnl
                    FROM trading_results
                """)
                
                overall = cursor.fetchone()
                total, wins, total_pnl = overall
                
                overall_win_rate = (wins / total * 100) if total > 0 else 0
                
                # 按信號類型統計
                cursor.execute("""
                    SELECT 
                        s.signal_type,
                        COUNT(*) as total,
                        SUM(CASE WHEN r.is_successful = 1 THEN 1 ELSE 0 END) as wins,
                        SUM(r.final_pnl) as pnl,
                        AVG(r.final_pnl) as avg_pnl
                    FROM trading_results r
                    JOIN orders_executed o ON r.order_id = o.id  
                    JOIN signals_received s ON o.signal_id = s.id
                    GROUP BY s.signal_type
                    ORDER BY wins DESC
                """)
                
                signal_stats = []
                for row in cursor.fetchall():
                    signal_type, total, wins, pnl, avg_pnl = row
                    win_rate = (wins / total * 100) if total > 0 else 0
                    signal_stats.append({
                        'signal_type': signal_type,
                        'total': total,
                        'wins': wins,
                        'win_rate': round(win_rate, 1),
                        'total_pnl': round(pnl or 0, 4),
                        'avg_pnl': round(avg_pnl or 0, 4)
                    })
                
                return {
                    'overall_win_rate': round(overall_win_rate, 1),
                    'total_trades': total,
                    'successful_trades': wins,
                    'total_pnl': round(total_pnl or 0, 4),
                    'by_signal_type': signal_stats
                }
                
        except Exception as e:
            logger.error(f"獲取勝率統計時出錯: {str(e)}")
            return {
                'overall_win_rate': 0,
                'total_trades': 0, 
                'successful_trades': 0,
                'total_pnl': 0,
                'by_signal_type': []
            }
    
    def get_execution_analysis(self) -> Dict[str, Any]:
        """獲取執行成功率分析"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 總體執行分析
                cursor.execute("""
                    SELECT 
                        COUNT(*) as total_orders,
                        SUM(CASE WHEN status IN ('FILLED', 'TP_FILLED', 'SL_FILLED') THEN 1 ELSE 0 END) as executed_orders,
                        SUM(CASE WHEN status IN ('CANCELED', 'CANCELLED', 'EXPIRED') THEN 1 ELSE 0 END) as failed_orders
                    FROM orders_executed
                """)
                
                result = cursor.fetchone()
                total_orders, executed_orders, failed_orders = result
                
                execution_rate = (executed_orders / total_orders * 100) if total_orders > 0 else 0
                
                # 按策略組合分析執行率
                cursor.execute("""
                    SELECT 
                        s.signal_type,
                        s.opposite,
                        COUNT(*) as total,
                        SUM(CASE WHEN o.status IN ('FILLED', 'TP_FILLED', 'SL_FILLED') THEN 1 ELSE 0 END) as executed,
                        AVG(ABS(s.close_price - o.price) / s.close_price) as avg_price_gap
                    FROM signals_received s
                    JOIN orders_executed o ON s.id = o.signal_id
                    GROUP BY s.signal_type, s.opposite
                    ORDER BY executed DESC
                """)
                
                strategy_execution = []
                for row in cursor.fetchall():
                    signal_type, opposite, total, executed, avg_price_gap = row
                    exec_rate = (executed / total * 100) if total > 0 else 0
                    strategy_execution.append({
                        'strategy_combo': f"{signal_type}_opposite_{opposite}",
                        'signal_type': signal_type,
                        'opposite': opposite,
                        'total_orders': total,
                        'executed_orders': executed,
                        'execution_rate': round(exec_rate, 1),
                        'avg_price_gap': round(avg_price_gap or 0, 6)
                    })
                
                return {
                    'overall_execution_rate': round(execution_rate, 1),
                    'total_orders': total_orders,
                    'executed_orders': executed_orders,
                    'failed_orders': failed_orders,
                    'by_strategy_combo': strategy_execution
                }
                
        except Exception as e:
            logger.error(f"獲取執行分析時出錯: {str(e)}")
            return {
                'overall_execution_rate': 0,
                'total_orders': 0,
                'executed_orders': 0,
                'failed_orders': 0,
                'by_strategy_combo': []
            }
    
    def get_symbol_performance(self) -> Dict[str, Any]:
        """獲取交易對表現分析"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT 
                        r.symbol,
                        COUNT(*) as total_trades,
                        SUM(CASE WHEN r.is_successful = 1 THEN 1 ELSE 0 END) as successful_trades,
                        SUM(r.final_pnl) as total_pnl,
                        AVG(r.final_pnl) as avg_pnl,
                        AVG(r.holding_time_minutes) as avg_holding_time
                    FROM trading_results r
                    GROUP BY r.symbol
                    ORDER BY total_pnl DESC
                """)
                
                symbol_performance = []
                for row in cursor.fetchall():
                    symbol, total, successful, total_pnl, avg_pnl, avg_holding = row
                    win_rate = (successful / total * 100) if total > 0 else 0
                    symbol_performance.append({
                        'symbol': symbol,
                        'total_trades': total,
                        'successful_trades': successful,
                        'win_rate': round(win_rate, 1),
                        'total_pnl': round(total_pnl or 0, 4),
                        'avg_pnl': round(avg_pnl or 0, 4),
                        'avg_holding_time': round(avg_holding or 0, 1)
                    })
                
                return {'by_symbol': symbol_performance}
                
        except Exception as e:
            logger.error(f"獲取交易對表現時出錯: {str(e)}")
            return {'by_symbol': []}
    
    def get_time_analysis(self) -> Dict[str, Any]:
        """獲取時間分析統計"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 按小時統計
                cursor.execute("""
                    SELECT 
                        strftime('%H', datetime(s.timestamp, 'unixepoch')) as hour,
                        COUNT(*) as total_signals,
                        COUNT(r.id) as completed_trades,
                        SUM(CASE WHEN r.is_successful = 1 THEN 1 ELSE 0 END) as successful_trades,
                        AVG(r.final_pnl) as avg_pnl
                    FROM signals_received s
                    LEFT JOIN orders_executed o ON s.id = o.signal_id
                    LEFT JOIN trading_results r ON o.id = r.order_id
                    GROUP BY hour
                    ORDER BY hour
                """)
                
                hourly_stats = []
                for row in cursor.fetchall():
                    hour, total_signals, completed_trades, successful_trades, avg_pnl = row
                    win_rate = (successful_trades / completed_trades * 100) if completed_trades > 0 else 0
                    hourly_stats.append({
                        'hour': int(hour),
                        'total_signals': total_signals,
                        'completed_trades': completed_trades or 0,
                        'successful_trades': successful_trades or 0,
                        'win_rate': round(win_rate, 1),
                        'avg_pnl': round(avg_pnl or 0, 4)
                    })
                
                # 按星期統計
                cursor.execute("""
                    SELECT 
                        strftime('%w', datetime(s.timestamp, 'unixepoch')) as weekday,
                        COUNT(*) as total_signals,
                        COUNT(r.id) as completed_trades,
                        SUM(CASE WHEN r.is_successful = 1 THEN 1 ELSE 0 END) as successful_trades
                    FROM signals_received s
                    LEFT JOIN orders_executed o ON s.id = o.signal_id
                    LEFT JOIN trading_results r ON o.id = r.order_id
                    GROUP BY weekday
                    ORDER BY weekday
                """)
                
                weekday_names = ['週日', '週一', '週二', '週三', '週四', '週五', '週六']
                weekly_stats = []
                for row in cursor.fetchall():
                    weekday, total_signals, completed_trades, successful_trades = row
                    win_rate = (successful_trades / completed_trades * 100) if completed_trades > 0 else 0
                    weekly_stats.append({
                        'weekday': weekday_names[int(weekday)],
                        'total_signals': total_signals,
                        'completed_trades': completed_trades or 0,
                        'win_rate': round(win_rate, 1)
                    })
                
                return {
                    'hourly_stats': hourly_stats,
                    'weekly_stats': weekly_stats
                }
                
        except Exception as e:
            logger.error(f"獲取時間分析時出錯: {str(e)}")
            return {'hourly_stats': [], 'weekly_stats': []}
    
    def get_database_stats(self) -> Dict[str, Any]:
        """獲取完整資料庫統計信息"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 基礎表格統計
                stats = {}
                
                cursor.execute('SELECT COUNT(*) FROM signals_received')
                stats['total_signals'] = cursor.fetchone()[0]
                
                cursor.execute('SELECT COUNT(*) FROM orders_executed')
                stats['total_orders'] = cursor.fetchone()[0]
                
                cursor.execute('SELECT COUNT(*) FROM trading_results')
                stats['total_results'] = cursor.fetchone()[0]
                
                # ML表格統計（如果存在）
                try:
                    cursor.execute('SELECT COUNT(*) FROM ml_features_v2')
                    stats['total_ml_features'] = cursor.fetchone()[0]
                    
                    cursor.execute('SELECT COUNT(*) FROM ml_predictions_v2')
                    stats['total_ml_predictions'] = cursor.fetchone()[0]
                    
                    cursor.execute('SELECT COUNT(*) FROM feature_importance')
                    stats['total_feature_importance'] = cursor.fetchone()[0]
                except sqlite3.OperationalError:
                    # ML表格尚未創建
                    stats['total_ml_features'] = 0
                    stats['total_ml_predictions'] = 0
                    stats['total_feature_importance'] = 0
                
                # 最近的信號時間
                cursor.execute('SELECT MAX(timestamp) FROM signals_received')
                last_signal_time = cursor.fetchone()[0]
                if last_signal_time:
                    stats['last_signal_time'] = datetime.fromtimestamp(last_signal_time).strftime('%Y-%m-%d %H:%M:%S')
                else:
                    stats['last_signal_time'] = "無"
                
                # 資料庫檔案大小
                if os.path.exists(self.db_path):
                    file_size = os.path.getsize(self.db_path)
                    stats['database_size_kb'] = round(file_size / 1024, 2)
                else:
                    stats['database_size_kb'] = 0
                
                # 數據完整性檢查
                cursor.execute("""
                    SELECT 
                        COUNT(DISTINCT s.id) as signals_with_orders,
                        COUNT(DISTINCT r.order_id) as orders_with_results
                    FROM signals_received s
                    LEFT JOIN orders_executed o ON s.id = o.signal_id
                    LEFT JOIN trading_results r ON o.id = r.order_id
                """)
                
                integrity = cursor.fetchone()
                stats['signals_with_orders'] = integrity[0]
                stats['orders_with_results'] = integrity[1]
                
                # 計算數據完整性百分比
                if stats['total_signals'] > 0:
                    stats['order_completion_rate'] = round((stats['signals_with_orders'] / stats['total_signals']) * 100, 1)
                else:
                    stats['order_completion_rate'] = 0
                
                if stats['total_orders'] > 0:
                    stats['result_completion_rate'] = round((stats['orders_with_results'] / stats['total_orders']) * 100, 1)
                else:
                    stats['result_completion_rate'] = 0
                
                return stats
                
        except Exception as e:
            logger.error(f"獲取資料庫統計時出錯: {str(e)}")
            return {}
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """獲取綜合表現摘要"""
        try:
            # 整合各種統計
            win_rate_stats = self.get_win_rate_stats()
            execution_analysis = self.get_execution_analysis()
            symbol_performance = self.get_symbol_performance()
            database_stats = self.get_database_stats()
            
            # 計算關鍵指標
            summary = {
                'overview': {
                    'total_signals': database_stats.get('total_signals', 0),
                    'total_orders': database_stats.get('total_orders', 0),
                    'total_trades': win_rate_stats.get('total_trades', 0),
                    'execution_rate': execution_analysis.get('overall_execution_rate', 0),
                    'win_rate': win_rate_stats.get('overall_win_rate', 0),
                    'total_pnl': win_rate_stats.get('total_pnl', 0)
                },
                'data_quality': {
                    'order_completion_rate': database_stats.get('order_completion_rate', 0),
                    'result_completion_rate': database_stats.get('result_completion_rate', 0),
                    'last_signal_time': database_stats.get('last_signal_time', '無'),
                    'database_size_kb': database_stats.get('database_size_kb', 0)
                },
                'best_performers': {
                    'best_signal_type': self._get_best_signal_type(win_rate_stats),
                    'best_symbol': self._get_best_symbol(symbol_performance),
                    'best_strategy_combo': self._get_best_strategy_combo(execution_analysis)
                }
            }
            
            return summary
            
        except Exception as e:
            logger.error(f"獲取表現摘要時出錯: {str(e)}")
            return {}
    
    def _get_best_signal_type(self, win_rate_stats: Dict) -> Dict[str, Any]:
        """獲取最佳信號類型"""
        signal_stats = win_rate_stats.get('by_signal_type', [])
        if not signal_stats:
            return {'signal_type': 'N/A', 'win_rate': 0, 'total_pnl': 0}
        
        # 按勝率和盈利綜合排序
        best = max(signal_stats, key=lambda x: (x['win_rate'], x['total_pnl']))
        return {
            'signal_type': best['signal_type'],
            'win_rate': best['win_rate'],
            'total_pnl': best['total_pnl'],
            'total_trades': best['total']
        }
    
    def _get_best_symbol(self, symbol_performance: Dict) -> Dict[str, Any]:
        """獲取最佳交易對"""
        symbol_stats = symbol_performance.get('by_symbol', [])
        if not symbol_stats:
            return {'symbol': 'N/A', 'win_rate': 0, 'total_pnl': 0}
        
        best = max(symbol_stats, key=lambda x: (x['win_rate'], x['total_pnl']))
        return {
            'symbol': best['symbol'],
            'win_rate': best['win_rate'],
            'total_pnl': best['total_pnl'],
            'total_trades': best['total_trades']
        }
    
    def _get_best_strategy_combo(self, execution_analysis: Dict) -> Dict[str, Any]:
        """獲取最佳策略組合"""
        strategy_stats = execution_analysis.get('by_strategy_combo', [])
        if not strategy_stats:
            return {'strategy_combo': 'N/A', 'execution_rate': 0}
        
        best = max(strategy_stats, key=lambda x: x['execution_rate'])
        return {
            'strategy_combo': best['strategy_combo'],
            'execution_rate': best['execution_rate'],
            'total_orders': best['total_orders'],
            'executed_orders': best['executed_orders']
        }

# 創建統計分析管理器實例（需要傳入資料庫路徑）
def create_analytics_manager(db_path: str) -> AnalyticsManager:
    """創建統計分析管理器實例"""
    return AnalyticsManager(db_path)