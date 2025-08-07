"""
69大師背離交易機器人 - 主程式
=============================================================================
2025/06/05 修正手動單衝突
2025/06/06 調整止盈邏輯
2025/06/10 增加止損邏輯2%

完整重構版本 - 模組化架構
=============================================================================
"""
import threading
import time
from utils.logger_config import setup_logging, get_logger
from api.websocket_handler import WebSocketManager
from web.app import create_flask_app
from trading import timeout_manager

def main():
    """主程式入口點"""
    try:
        # =============================================================================
        # 初始化系統
        # =============================================================================
        setup_logging()
        logger = get_logger(__name__)
        
        # =============================================================================
        # 啟動WebSocket監控
        # =============================================================================
        logger.info("正在啟動WebSocket監控線程...")
        ws_manager = WebSocketManager()
        ws_thread = threading.Thread(target=ws_manager.start, daemon=True)
        ws_thread.start()
        logger.info("WebSocket監控線程已啟動")
        
        # 等待WebSocket線程初始化
        time.sleep(2)
        
        # =============================================================================
        # 啟動訂單超時管理器
        # =============================================================================
        logger.info("正在啟動訂單超時管理器...")
        timeout_thread = threading.Thread(target=timeout_manager.start, daemon=True)
        timeout_thread.start()
        logger.info("訂單超時管理器已啟動")
        
        # =============================================================================
        # 啟動Flask服務
        # =============================================================================
        logger.info("正在啟動Flask服務...")
        app = create_flask_app()
        logger.info("準備接收TradingView信號...")
        
        # 啟動Flask應用
        app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
        
    except KeyboardInterrupt:
        logger.info("收到中斷信號，正在關閉系統...")
        timeout_manager.stop()
    except Exception as e:
        logger.error(f"系統啟動失敗: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
    finally:
        timeout_manager.stop()
        logger.info("交易機器人已停止運行")

if __name__ == "__main__":
    main()
