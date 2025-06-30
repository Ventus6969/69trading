"""
交易數據管理模組
負責建立資料庫、記錄交易數據、提供基礎統計功能
=============================================================================
"""
import sqlite3
import os
import json
import time
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List  # 🔥 修復：添加 typing import
from config.settings import LOG_DIRECTORY

# 設置logger
logger = logging.getLogger(__name__)

class TradingDataManager:
    """交易數據管理類"""
    
    def __init__(self, db_path: str = None):
        # 設定資料庫路徑
        if db_path is None:
            # 在專案根目錄建立data資料夾
            data_dir = os.path.join(os.getcwd(), 'data')
            if not os.path.exists(data_dir):
                os.makedirs(data_dir)
            self.db_path = os.path.join(data_dir, 'trading_signals.db')
        else:
            self.db_path = db_path
            
        # 初始化資料庫
        self._init_database()
        logger.info(f"交易數據管理器已初始化，資料庫路徑: {self.db_path}")
    
    def _init_database(self):
        """初始化資料庫表格"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 1. 信號接收記錄表
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS signals_received (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp REAL NOT NULL,
                        signal_type TEXT NOT NULL,
                        symbol TEXT NOT NULL,
                        side TEXT NOT NULL,
                        open_price REAL,
                        close_price REAL,
                        prev_close REAL,
                        prev_open REAL,
                        atr_value REAL,
                        opposite INTEGER,
                        strategy_name TEXT,
                        quantity TEXT,
                        order_type TEXT,
                        margin_type TEXT,
                        precision INTEGER,
                        tp_multiplier REAL,
                        signal_data_json TEXT,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # 2. 訂單執行記錄表
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS orders_executed (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        signal_id INTEGER,
                        client_order_id TEXT UNIQUE NOT NULL,
                        symbol TEXT NOT NULL,
                        side TEXT NOT NULL,
                        order_type TEXT,
                        quantity REAL,
                        price REAL,
                        leverage INTEGER,
                        execution_timestamp REAL,
                        execution_delay_ms INTEGER,
                        binance_order_id TEXT,
                        status TEXT DEFAULT 'NEW',
                        is_add_position BOOLEAN DEFAULT 0,
                        tp_client_id TEXT,
                        sl_client_id TEXT,
                        tp_price REAL,
                        sl_price REAL,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (signal_id) REFERENCES signals_received (id)
                    )
                ''')
                
                # 3. 交易結果記錄表
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS trading_results (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        order_id INTEGER,
                        client_order_id TEXT NOT NULL,
                        symbol TEXT NOT NULL,
                        final_pnl REAL,
                        pnl_percentage REAL,
                        holding_time_minutes INTEGER,
                        exit_method TEXT,
                        max_drawdown REAL,
                        max_profit REAL,
                        entry_price REAL,
                        exit_price REAL,
                        total_quantity REAL,
                        result_timestamp REAL,
                        is_successful BOOLEAN,
                        trade_quality_score REAL,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (order_id) REFERENCES orders_executed (id)
                    )
                ''')
                
                # 4. 每日統計摘要表
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS daily_stats (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        date TEXT UNIQUE NOT NULL,
                        total_signals INTEGER DEFAULT 0,
                        total_orders INTEGER DEFAULT 0,
                        successful_trades INTEGER DEFAULT 0,
                        failed_trades INTEGER DEFAULT 0,
                        win_rate REAL DEFAULT 0,
                        total_pnl REAL DEFAULT 0,
                        best_trade REAL DEFAULT 0,
                        worst_trade REAL DEFAULT 0,
                        avg_holding_time REAL DEFAULT 0,
                        signal_type_stats TEXT,
                        symbol_stats TEXT,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # 建立索引提升查詢效能
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_signals_timestamp ON signals_received(timestamp)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_signals_type_symbol ON signals_received(signal_type, symbol)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_orders_client_id ON orders_executed(client_order_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_orders_symbol ON orders_executed(symbol)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_results_timestamp ON trading_results(result_timestamp)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_daily_stats_date ON daily_stats(date)')
                
                conn.commit()
                logger.info("資料庫表格初始化完成")
                
        except Exception as e:
            logger.error(f"初始化資料庫時出錯: {str(e)}")
            raise
    
    def record_signal_received(self, signal_data: Dict[str, Any]) -> int:
        """
        記錄接收到的交易信號
        
        Args:
            signal_data: 信號數據字典
            
        Returns:
            int: 插入記錄的ID
        """
        try:
            timestamp = time.time()
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    INSERT INTO signals_received (
                        timestamp, signal_type, symbol, side, open_price, close_price,
                        prev_close, prev_open, atr_value, opposite, strategy_name,
                        quantity, order_type, margin_type, precision, tp_multiplier,
                        signal_data_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    timestamp,
                    signal_data.get('signal_type'),
                    signal_data.get('symbol'),
                    signal_data.get('side'),
                    float(signal_data.get('open', 0)) if signal_data.get('open') else None,
                    float(signal_data.get('close', 0)) if signal_data.get('close') else None,
                    float(signal_data.get('prev_close', 0)) if signal_data.get('prev_close') else None,
                    float(signal_data.get('prev_open', 0)) if signal_data.get('prev_open') else None,
                    float(signal_data.get('ATR', 0)) if signal_data.get('ATR') else None,
                    int(signal_data.get('opposite', 0)),
                    signal_data.get('strategy_name'),
                    signal_data.get('quantity'),
                    signal_data.get('order_type'),
                    signal_data.get('margin_type'),
                    signal_data.get('precision'),
                    signal_data.get('tp_multiplier'),
                    json.dumps(signal_data)  # 保存完整的原始數據
                ))
                
                signal_id = cursor.lastrowid
                conn.commit()
                
                logger.info(f"已記錄信號: ID={signal_id}, {signal_data.get('symbol')} {signal_data.get('side')} {signal_data.get('signal_type')}")
                return signal_id
                
        except Exception as e:
            logger.error(f"記錄信號時出錯: {str(e)}")
            return -1
    
    def record_order_executed(self, signal_id: int, order_data: Dict[str, Any]) -> bool:
        """
        記錄訂單執行信息
        
        Args:
            signal_id: 對應的信號ID
            order_data: 訂單數據字典
            
        Returns:
            bool: 是否記錄成功
        """
        try:
            execution_timestamp = time.time()
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    INSERT INTO orders_executed (
                        signal_id, client_order_id, symbol, side, order_type,
                        quantity, price, leverage, execution_timestamp, execution_delay_ms,
                        binance_order_id, status, is_add_position, tp_client_id, sl_client_id,
                        tp_price, sl_price
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    signal_id,
                    order_data.get('client_order_id'),
                    order_data.get('symbol'),
                    order_data.get('side'),
                    order_data.get('order_type'),
                    float(order_data.get('quantity', 0)),
                    float(order_data.get('price', 0)) if order_data.get('price') else None,
                    int(order_data.get('leverage', 30)),
                    execution_timestamp,
                    order_data.get('execution_delay_ms'),
                    order_data.get('binance_order_id'),
                    order_data.get('status', 'NEW'),
                    bool(order_data.get('is_add_position', False)),
                    order_data.get('tp_client_id'),
                    order_data.get('sl_client_id'),
                    float(order_data.get('tp_price', 0)) if order_data.get('tp_price') else None,
                    float(order_data.get('sl_price', 0)) if order_data.get('sl_price') else None
                ))
                
                conn.commit()
                logger.info(f"已記錄訂單執行: {order_data.get('client_order_id')}")
                return True
                
        except Exception as e:
            logger.error(f"記錄訂單執行時出錯: {str(e)}")
            return False
    
    # 🔥 新增：關鍵修復方法
    def record_trading_result_by_client_id(self, client_order_id: str, result_data: Dict[str, Any]) -> bool:
        """
        根據客戶訂單ID記錄交易結果
        
        Args:
            client_order_id: 客戶訂單ID
            result_data: 交易結果數據
            
        Returns:
            bool: 是否記錄成功
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 查找對應的訂單記錄
                cursor.execute("""
                    SELECT id FROM orders_executed 
                    WHERE client_order_id = ?
                """, (client_order_id,))
                
                order_record = cursor.fetchone()
                if not order_record:
                    logger.error(f"未找到訂單記錄: {client_order_id}")
                    return False
                
                order_id = order_record[0]
                
                # 檢查是否已存在交易結果
                cursor.execute("SELECT id FROM trading_results WHERE order_id = ?", (order_id,))
                if cursor.fetchone():
                    logger.info(f"訂單 {client_order_id} 交易結果已存在，跳過重複記錄")
                    return True
                
                # 插入交易結果記錄
                cursor.execute("""
                    INSERT INTO trading_results (
                        order_id, client_order_id, symbol, final_pnl, pnl_percentage,
                        exit_method, entry_price, exit_price, total_quantity,
                        result_timestamp, is_successful, holding_time_minutes
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    order_id,
                    result_data['client_order_id'],
                    result_data['symbol'],
                    result_data['final_pnl'],
                    result_data.get('pnl_percentage', 0),
                    result_data['exit_method'],
                    result_data['entry_price'],
                    result_data['exit_price'],
                    result_data['total_quantity'],
                    result_data['result_timestamp'],
                    result_data['is_successful'],
                    result_data['holding_time_minutes']
                ))
                
                conn.commit()
                logger.info(f"✅ 交易結果已記錄: {client_order_id}, 盈虧: {result_data['final_pnl']}")
                return True
                
        except Exception as e:
            logger.error(f"記錄交易結果失敗: {str(e)}")
            return False
    
    def get_recent_signals(self, limit: int = 10) -> List[Dict]:
        """獲取最近的信號記錄"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT * FROM signals_received 
                    ORDER BY timestamp DESC 
                    LIMIT ?
                ''', (limit,))
                
                return [dict(row) for row in cursor.fetchall()]
                
        except Exception as e:
            logger.error(f"獲取最近信號時出錯: {str(e)}")
            return []
    
    def get_recent_trading_results(self, limit: int = 10) -> List[Dict]:
        """獲取最近的交易結果"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT 
                        r.*,
                        s.signal_type,
                        s.symbol as signal_symbol,
                        o.side
                    FROM trading_results r
                    JOIN orders_executed o ON r.order_id = o.id
                    JOIN signals_received s ON o.signal_id = s.id
                    ORDER BY r.result_timestamp DESC
                    LIMIT ?
                """, (limit,))
                
                return [dict(row) for row in cursor.fetchall()]
                
        except Exception as e:
            logger.error(f"獲取交易結果時出錯: {str(e)}")
            return []
    
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
    
    def get_database_stats(self) -> Dict[str, Any]:
        """獲取資料庫統計信息"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 統計各表的記錄數量
                stats = {}
                
                cursor.execute('SELECT COUNT(*) FROM signals_received')
                stats['total_signals'] = cursor.fetchone()[0]
                
                cursor.execute('SELECT COUNT(*) FROM orders_executed')
                stats['total_orders'] = cursor.fetchone()[0]
                
                cursor.execute('SELECT COUNT(*) FROM trading_results')
                stats['total_results'] = cursor.fetchone()[0]
                
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
                
                return stats
                
        except Exception as e:
            logger.error(f"獲取資料庫統計時出錯: {str(e)}")
            return {}
    
    def _update_daily_stats(self):
        """更新每日統計數據"""
        try:
            today = datetime.now().strftime('%Y-%m-%d')
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 計算今日統計
                cursor.execute("""
                    SELECT 
                        COUNT(*) as total_signals
                    FROM signals_received 
                    WHERE DATE(datetime(timestamp, 'unixepoch')) = ?
                """, (today,))
                total_signals = cursor.fetchone()[0]
                
                cursor.execute("""
                    SELECT 
                        COUNT(*) as total_orders
                    FROM orders_executed 
                    WHERE DATE(datetime(execution_timestamp, 'unixepoch')) = ?
                """, (today,))
                total_orders = cursor.fetchone()[0]
                
                cursor.execute("""
                    SELECT 
                        COUNT(*) as total_trades,
                        SUM(CASE WHEN is_successful = 1 THEN 1 ELSE 0 END) as successful_trades,
                        SUM(final_pnl) as total_pnl,
                        MAX(final_pnl) as best_trade,
                        MIN(final_pnl) as worst_trade,
                        AVG(holding_time_minutes) as avg_holding_time
                    FROM trading_results 
                    WHERE DATE(datetime(result_timestamp, 'unixepoch')) = ?
                """, (today,))
                
                trade_stats = cursor.fetchone()
                total_trades, successful_trades, total_pnl, best_trade, worst_trade, avg_holding_time = trade_stats
                
                # 計算勝率
                win_rate = (successful_trades / total_trades * 100) if total_trades > 0 else 0
                
                # 計算信號類型統計
                cursor.execute("""
                    SELECT s.signal_type, COUNT(*) 
                    FROM signals_received s
                    JOIN orders_executed o ON s.id = o.signal_id
                    JOIN trading_results r ON o.id = r.order_id
                    WHERE DATE(datetime(r.result_timestamp, 'unixepoch')) = ?
                    GROUP BY s.signal_type
                """, (today,))
                
                signal_type_stats = dict(cursor.fetchall())
                
                # 更新或插入每日統計
                cursor.execute("""
                    INSERT OR REPLACE INTO daily_stats (
                        date, total_signals, total_orders, successful_trades, failed_trades,
                        win_rate, total_pnl, best_trade, worst_trade, avg_holding_time,
                        signal_type_stats, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, (
                    today, total_signals, total_orders, successful_trades or 0, 
                    (total_trades - successful_trades) if total_trades and successful_trades else 0,
                    round(win_rate, 2), total_pnl or 0, best_trade or 0, worst_trade or 0,
                    avg_holding_time or 0, json.dumps(signal_type_stats)
                ))
                
                conn.commit()
                logger.info(f"已更新每日統計: {today}, 勝率: {win_rate:.1f}%")
                
        except Exception as e:
            logger.error(f"更新每日統計時出錯: {str(e)}")

# 創建全局數據管理器實例
trading_data_manager = TradingDataManager()
