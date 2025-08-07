"""
訂單超時管理器
=============================================================================
負責監控和取消超時的訂單，支援策略專屬超時設定

功能：
- 每60秒檢查一次所有未成交訂單
- 根據策略類型使用不同的超時時間
- 自動取消超時訂單，不影響現有交易流程

設計：
- 獨立運行的背景線程
- 最小侵入性，不修改現有程式碼
- 通過現有API進行訂單取消
=============================================================================
"""
import threading
import time
from datetime import datetime, timedelta
from utils.logger_config import get_logger
from config.settings import get_strategy_timeout, ORDER_TIMEOUT_MINUTES

logger = get_logger(__name__)

class OrderTimeoutManager:
    """訂單超時管理器"""
    
    def __init__(self, check_interval=60):
        """
        初始化超時管理器
        
        Args:
            check_interval (int): 檢查間隔（秒），預設60秒
        """
        self.check_interval = check_interval
        self.running = False
        self._lock = threading.Lock()
        
    def start(self):
        """啟動超時檢查器"""
        self.running = True
        logger.info(f"訂單超時管理器已啟動，檢查間隔：{self.check_interval}秒")
        
        while self.running:
            try:
                self._check_timeout_orders()
                time.sleep(self.check_interval)
            except Exception as e:
                logger.error(f"超時檢查器運行錯誤：{str(e)}")
                import traceback
                logger.error(traceback.format_exc())
                # 發生錯誤時等待更長時間再重試
                time.sleep(self.check_interval * 2)
    
    def stop(self):
        """停止超時檢查器"""
        self.running = False
        logger.info("訂單超時管理器已停止")
    
    def _check_timeout_orders(self):
        """檢查並取消超時訂單"""
        try:
            # 動態導入，避免循環導入
            from trading.order_manager import order_manager
            from api.binance_client import binance_client
            
            with self._lock:
                current_time = datetime.now()
                timeout_orders = []
                
                # 獲取所有活躍訂單
                all_orders = order_manager.get_orders()
                
                for order_id, order_info in all_orders.items():
                    # 只處理系統訂單且狀態為未成交的訂單
                    if not self._should_check_order(order_id, order_info):
                        continue
                    
                    # 檢查是否超時
                    if self._is_order_timeout(order_info, current_time):
                        timeout_orders.append((order_id, order_info))
                
                # 處理超時訂單
                if timeout_orders:
                    logger.info(f"發現 {len(timeout_orders)} 個超時訂單，準備取消...")
                    
                for order_id, order_info in timeout_orders:
                    self._cancel_timeout_order(order_id, order_info, binance_client)
                    
        except Exception as e:
            logger.error(f"檢查超時訂單時發生錯誤：{str(e)}")
            import traceback
            logger.error(traceback.format_exc())
    
    def _should_check_order(self, order_id: str, order_info: dict) -> bool:
        """
        判斷訂單是否需要檢查超時
        
        Args:
            order_id: 訂單ID
            order_info: 訂單資訊
            
        Returns:
            bool: 是否需要檢查
        """
        try:
            # 只處理系統訂單
            if not order_id.startswith('V69_'):
                return False
            
            # 只處理未完成的主訂單（不包括止盈止損單）
            status = order_info.get('status', '').upper()
            if status not in ['NEW', 'PARTIALLY_FILLED']:
                return False
            
            # 不處理止盈止損單（以T或S結尾）
            if order_id.endswith('T') or order_id.endswith('S'):
                return False
            
            # 必須有入場時間
            entry_time = order_info.get('entry_time')
            if not entry_time:
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"判斷訂單檢查條件時出錯：{order_id} - {str(e)}")
            return False
    
    def _is_order_timeout(self, order_info: dict, current_time: datetime) -> bool:
        """
        判斷訂單是否超時
        
        Args:
            order_info: 訂單資訊
            current_time: 當前時間
            
        Returns:
            bool: 是否超時
        """
        try:
            entry_time_str = order_info.get('entry_time')
            if not entry_time_str:
                return False
            
            # 解析入場時間
            entry_time = datetime.strptime(entry_time_str, '%Y-%m-%d %H:%M:%S')
            
            # 獲取策略專屬超時時間
            signal_type = order_info.get('signal_type')
            timeout_minutes = get_strategy_timeout(signal_type)
            
            # 計算超時時間點
            timeout_threshold = entry_time + timedelta(minutes=timeout_minutes)
            
            # 判斷是否超時（增加30秒緩衝避免邊界問題）
            is_timeout = current_time > (timeout_threshold + timedelta(seconds=30))
            
            if is_timeout:
                elapsed_minutes = (current_time - entry_time).total_seconds() / 60
                logger.info(f"訂單超時：{order_info.get('symbol')} - 策略：{signal_type} - "
                          f"已過時間：{elapsed_minutes:.1f}分鐘 - 超時設定：{timeout_minutes}分鐘")
            
            return is_timeout
            
        except Exception as e:
            logger.error(f"判斷訂單超時時出錯：{str(e)}")
            return False
    
    def _cancel_timeout_order(self, order_id: str, order_info: dict, binance_client):
        """
        取消超時訂單
        
        Args:
            order_id: 訂單ID
            order_info: 訂單資訊
            binance_client: 幣安客戶端
        """
        try:
            symbol = order_info.get('symbol')
            signal_type = order_info.get('signal_type', 'unknown')
            
            logger.info(f"⏰ 準備取消超時訂單：{order_id} - {symbol} - 策略：{signal_type}")
            
            # 取消前再次確認訂單狀態（避免競爭條件）
            try:
                current_order = binance_client.get_order_by_client_id(order_id)
                if not current_order:
                    logger.info(f"訂單已不存在，跳過取消：{order_id}")
                    return
                
                current_status = current_order.get('status', '').upper()
                if current_status not in ['NEW', 'PARTIALLY_FILLED']:
                    logger.info(f"訂單狀態已變更（{current_status}），跳過取消：{order_id}")
                    return
                    
            except Exception as e:
                logger.warning(f"無法確認訂單狀態，繼續嘗試取消：{order_id} - {str(e)}")
            
            # 執行取消操作
            cancel_result = binance_client.cancel_order_by_client_id(order_id)
            
            if cancel_result:
                logger.info(f"✅ 超時訂單取消成功：{order_id}")
                
                # 同步取消相關的止盈止損單
                self._cancel_related_tp_sl_orders(order_id, order_info, binance_client)
                
            else:
                logger.warning(f"❌ 超時訂單取消失敗：{order_id}")
                
        except Exception as e:
            # 常見的取消失敗原因，記錄但不影響系統運行
            if "Unknown order sent" in str(e):
                logger.info(f"訂單已不存在：{order_id}")
            elif "Order does not exist" in str(e):
                logger.info(f"訂單不存在：{order_id}")
            else:
                logger.error(f"取消超時訂單時出錯：{order_id} - {str(e)}")
    
    def _cancel_related_tp_sl_orders(self, main_order_id: str, order_info: dict, binance_client):
        """
        取消主訂單相關的止盈止損單
        
        Args:
            main_order_id: 主訂單ID
            order_info: 主訂單資訊
            binance_client: 幣安客戶端
        """
        try:
            symbol = order_info.get('symbol')
            
            # 取消止盈單
            tp_client_id = order_info.get('tp_client_id')
            if tp_client_id:
                try:
                    binance_client.cancel_order_by_client_id(tp_client_id)
                    logger.info(f"🎯 已取消相關止盈單：{tp_client_id}")
                except Exception as e:
                    logger.warning(f"取消止盈單失敗：{tp_client_id} - {str(e)}")
            
            # 取消止損單
            sl_client_id = order_info.get('sl_client_id')
            if sl_client_id:
                try:
                    binance_client.cancel_order_by_client_id(sl_client_id)
                    logger.info(f"🛡️ 已取消相關止損單：{sl_client_id}")
                except Exception as e:
                    logger.warning(f"取消止損單失敗：{sl_client_id} - {str(e)}")
                    
        except Exception as e:
            logger.error(f"取消相關止盈止損單時出錯：{main_order_id} - {str(e)}")
    
    def get_status(self) -> dict:
        """
        獲取超時管理器狀態
        
        Returns:
            dict: 狀態資訊
        """
        return {
            "running": self.running,
            "check_interval": self.check_interval,
            "status": "active" if self.running else "stopped"
        }

# 創建全域實例（但不啟動）
timeout_manager = OrderTimeoutManager()