"""
日誌配置模組
設置與原程式完全相同的日誌配置
=============================================================================
"""
import os
import logging
from config.settings import LOG_DIRECTORY

def setup_logging():
    """設置日誌配置，與原程式保持完全一致"""
    # 設定日誌目錄
    if not os.path.exists(LOG_DIRECTORY):
        os.makedirs(LOG_DIRECTORY)

    # 設定日誌 - 與原程式完全相同的配置
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(f"{LOG_DIRECTORY}/trading_bot.log"),
            logging.StreamHandler()
        ]
    )

def get_logger(name):
    """獲取logger實例"""
    return logging.getLogger(name)

def set_log_level(level):
    """
    設置日誌級別
    
    Args:
        level: 日誌級別 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    level_map = {
        'DEBUG': logging.DEBUG,
        'INFO': logging.INFO,
        'WARNING': logging.WARNING,
        'ERROR': logging.ERROR,
        'CRITICAL': logging.CRITICAL
    }
    
    log_level = level_map.get(level.upper(), logging.INFO)
    logging.getLogger().setLevel(log_level)

def add_file_handler(filename, level=logging.INFO):
    """
    添加額外的文件處理器
    
    Args:
        filename: 日誌文件名
        level: 日誌級別
    """
    # 確保日誌目錄存在
    if not os.path.exists(LOG_DIRECTORY):
        os.makedirs(LOG_DIRECTORY)
    
    # 創建文件處理器
    file_handler = logging.FileHandler(f"{LOG_DIRECTORY}/{filename}")
    file_handler.setLevel(level)
    
    # 設置格式
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    
    # 添加到根日誌器
    logging.getLogger().addHandler(file_handler)