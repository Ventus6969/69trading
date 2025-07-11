"""
Database模組初始化
統一管理所有數據管理器實例
=============================================================================
"""
import os
import logging
from .trading_data_manager import TradingDataManager, trading_data_manager
from .analytics_manager import create_analytics_manager

# 設置logger
logger = logging.getLogger(__name__)

# 獲取資料庫路徑
def get_database_path():
    """獲取資料庫檔案路徑"""
    data_dir = os.path.join(os.getcwd(), 'data')
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)
    return os.path.join(data_dir, 'trading_signals.db')

# 創建統一的管理器實例
DB_PATH = get_database_path()

# ML數據管理器 - 添加錯誤處理
ml_data_manager = None
try:
    from .ml_data_manager import MLDataManager
    ml_data_manager = MLDataManager(DB_PATH)
    logger.info("✅ ML數據管理器初始化成功")
except Exception as e:
    logger.error(f"❌ ML數據管理器初始化失敗: {str(e)}")
    logger.error("將在首次使用時重新嘗試初始化")

# 統計分析管理器  
analytics_manager = create_analytics_manager(DB_PATH)

# 統一導出接口
__all__ = [
    'trading_data_manager',
    'ml_data_manager', 
    'analytics_manager',
    'TradingDataManager'
]
