#!/usr/bin/env python3
"""
修復資料庫結構問題
新增缺失的 trading_probability 欄位
"""

import os
import sys
import sqlite3

# 添加專案根目錄到Python路徑
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

from database import get_database_path
from utils.logger_config import get_logger

logger = get_logger(__name__)

def fix_ml_signal_quality_table():
    """修復 ml_signal_quality 表結構"""
    db_path = get_database_path()
    
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            
            # 檢查表是否存在
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='ml_signal_quality'")
            if not cursor.fetchone():
                logger.info("ml_signal_quality 表不存在，跳過修復")
                return True
            
            # 檢查 trading_probability 欄位是否存在
            cursor.execute("PRAGMA table_info(ml_signal_quality)")
            columns = [column[1] for column in cursor.fetchall()]
            
            if 'trading_probability' not in columns:
                logger.info("添加缺失的 trading_probability 欄位...")
                cursor.execute('''
                    ALTER TABLE ml_signal_quality 
                    ADD COLUMN trading_probability REAL DEFAULT 0.5
                ''')
                conn.commit()
                logger.info("✅ 成功添加 trading_probability 欄位")
            else:
                logger.info("✅ trading_probability 欄位已存在")
            
            # 檢查其他可能缺失的欄位
            required_columns = [
                'execution_probability', 'risk_level', 'reason', 
                'suggested_price_adjustment', 'created_at'
            ]
            
            missing_columns = [col for col in required_columns if col not in columns]
            
            for column in missing_columns:
                if column == 'execution_probability':
                    cursor.execute('ALTER TABLE ml_signal_quality ADD COLUMN execution_probability REAL DEFAULT 0.5')
                elif column == 'risk_level':
                    cursor.execute('ALTER TABLE ml_signal_quality ADD COLUMN risk_level TEXT DEFAULT "MEDIUM"')
                elif column == 'reason':
                    cursor.execute('ALTER TABLE ml_signal_quality ADD COLUMN reason TEXT DEFAULT ""')
                elif column == 'suggested_price_adjustment':
                    cursor.execute('ALTER TABLE ml_signal_quality ADD COLUMN suggested_price_adjustment REAL DEFAULT 0.0')
                elif column == 'created_at':
                    cursor.execute('ALTER TABLE ml_signal_quality ADD COLUMN created_at DATETIME DEFAULT CURRENT_TIMESTAMP')
                
                logger.info(f"✅ 添加欄位: {column}")
            
            conn.commit()
            
            # 顯示最終表結構
            cursor.execute("PRAGMA table_info(ml_signal_quality)")
            final_columns = [f"{column[1]} ({column[2]})" for column in cursor.fetchall()]
            logger.info(f"✅ ml_signal_quality 表結構修復完成")
            logger.info(f"最終欄位: {', '.join(final_columns)}")
            
            return True
            
    except Exception as e:
        logger.error(f"❌ 修復資料庫結構時出錯: {e}")
        return False

def main():
    """主程式"""
    print("🔧 開始修復資料庫結構...")
    
    if fix_ml_signal_quality_table():
        print("✅ 資料庫結構修復完成")
    else:
        print("❌ 資料庫結構修復失敗")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())