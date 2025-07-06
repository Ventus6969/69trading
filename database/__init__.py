"""
Database模組初始化
統一管理所有數據管理器實例
=============================================================================
"""
import os
from .trading_data_manager import TradingDataManager, trading_data_manager
from .ml_data_manager import create_ml_data_manager
from .analytics_manager import create_analytics_manager

# 獲取資料庫路徑
def get_database_path():
    """獲取資料庫檔案路徑"""
    data_dir = os.path.join(os.getcwd(), 'data')
    return os.path.join(data_dir, 'trading_signals.db')

# 創建統一的管理器實例
DB_PATH = get_database_path()

# 核心交易數據管理器（已在trading_data_manager中創建）
# trading_data_manager 已可用

# ML數據管理器
ml_data_manager = create_ml_data_manager(DB_PATH)

# 統計分析管理器  
analytics_manager = create_analytics_manager(DB_PATH)

# 統一導出接口
__all__ = [
    'trading_data_manager',
    'ml_data_manager', 
    'analytics_manager',
    'TradingDataManager'
]