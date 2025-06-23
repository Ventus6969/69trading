"""
Flask應用創建模組
創建和配置Flask應用實例
=============================================================================
"""
import logging
from flask import Flask
from web.routes import register_routes
from utils.logger_config import get_logger
from config.settings import DEFAULT_LEVERAGE, TP_PERCENTAGE, MIN_TP_PROFIT_PERCENTAGE, STOP_LOSS_PERCENTAGE, ENABLE_STOP_LOSS, ORDER_TIMEOUT_MINUTES, TW_TIMEZONE, SYMBOL_PRECISION, SIGNAL_TP_MULTIPLIER

# 設置logger
logger = get_logger(__name__)

def create_flask_app():
    """創建並配置Flask應用"""
    
    # 創建Flask應用
    app = Flask(__name__)
    
    # 註冊路由
    register_routes(app)
    
    # 顯示系統配置信息
    _display_system_info()
    
    return app

def _display_system_info():
    """顯示系統配置信息"""
    logger.info("="*60)
    
    # 顯示API端點信息
    logger.info("可用API端點:")
    logger.info("  POST /webhook        - 接收TradingView信號")
    logger.info("  GET  /health         - 健康檢查")
    logger.info("  GET  /orders         - 查詢訂單")
    logger.info("  GET  /positions      - 查詢持倉")
    logger.info("  POST /cancel/<symbol> - 取消指定交易對訂單")
    logger.info("  GET  /config         - 獲取系統配置")
    logger.info("  GET  /stats          - 獲取統計信息")
    logger.info("="*60)
    logger.info("69大師背離交易機器人 - 系統啟動")
    logger.info("="*60)
    logger.info(f"槓桿設定: {DEFAULT_LEVERAGE}x")
    logger.info(f"默認止盈: {TP_PERCENTAGE:.1%}")
    logger.info(f"最小止盈獲利: {MIN_TP_PROFIT_PERCENTAGE:.1%}")
    logger.info(f"止損功能: {'啟用' if ENABLE_STOP_LOSS else '停用'}")
    logger.info(f"止損百分比: {STOP_LOSS_PERCENTAGE:.1%}")
    logger.info(f"訂單超時: {ORDER_TIMEOUT_MINUTES}分鐘")
    logger.info(f"時區設定: {TW_TIMEZONE}")
    logger.info(f"禁止交易時間: 20:00-23:50 (台灣時間)")
    logger.info(f"支援交易對數量: {len(SYMBOL_PRECISION)}")
    logger.info(f"策略信號ATR倍數: {len(SIGNAL_TP_MULTIPLIER)}個")
    logger.info("="*60)