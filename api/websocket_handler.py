"""
WebSocket連接管理模組
處理幣安WebSocket連接和訂單狀態更新
修正版本：解決PARTIALLY_FILLED狀態處理問題 + 修正狀態同步到資料庫
=============================================================================
"""
import json
import time
import logging
import threading
import traceback
import websocket
import sqlite3
from datetime import datetime
from api.binance_client import binance_client
from config.settings import WS_BASE_URL
from trading.order_manager import order_manager

# 設置logger
logger = logging.getLogger(__name__)

class WebSocketManager:
    """WebSocket連接管理器"""
    
    def __init__(self):
        self.listen_key = None
        self.ws = None
        self.connection_time = None
        
    def start(self):
        """啟動WebSocket連接"""
        self.connection_time = time.time()
        
        while True:
            try:
                # === 檢查連接時間，24小時重新獲取listenKey ===
                current_time = time.time()
                if current_time - self.connection_time > 23 * 60 * 60:  # 23小時
                    logger.info("WebSocket連接時間接近24小時，將重新獲取listenKey")
                    self.connection_time = current_time
                    
                # === 獲取listenKey ===
                self.listen_key = binance_client.get_listen_key()
                if not self.listen_key:
                    logger.error("無法獲取listenKey，重試中...")
                    time.sleep(5)
                    continue
                
                # === 啟動listenKey續期線程 ===
                keep_alive_thread = threading.Thread(
                    target=binance_client.keep_listen_key_alive,
                    args=(self.listen_key,),
                    daemon=True
                )
                keep_alive_thread.start()
                
                # === 建立WebSocket連接 ===
                socket_url = f"{WS_BASE_URL}/{self.listen_key}"
                
                websocket.enableTrace(False)
                self.ws = websocket.WebSocketApp(
                    socket_url,
                    on_open=self.on_open,
                    on_message=self.on_message,
                    on_error=self.on_error,
                    on_close=self.on_close
                )
                
                logger.info("開始連接WebSocket...")
                
                # === 運行WebSocket連接 ===
                # ping_interval=30: 每30秒發送一次ping
                # ping_timeout=10: ping超時時間10秒
                self.ws.run_forever(ping_interval=30, ping_timeout=10)
                
                logger.warning("WebSocket連接已斷開，正在重新連接...")
                time.sleep(5)
                
            except Exception as e:
                logger.error(f"WebSocket連接過程中發生錯誤: {str(e)}")
                logger.error(traceback.format_exc())
                time.sleep(5)
    
    def on_open(self, ws):
        """WebSocket連接建立處理"""
        logger.info("WebSocket連接已建立")
    
    def on_error(self, ws, error):
        """WebSocket錯誤處理"""
        logger.error(f"WebSocket錯誤: {str(error)}")
    
    def on_close(self, ws, close_status_code, close_msg):
        """WebSocket連接關閉處理"""
        logger.warning(f"WebSocket連接關閉: {close_status_code} - {close_msg}")
    
    def on_message(self, ws, message):
        """WebSocket消息處理函數 - 修正狀態同步版本"""
        try:
            data = json.loads(message)
            
            # 處理訂單更新事件
            if "e" in data and data["e"] == "ORDER_TRADE_UPDATE":
                order_data = data["o"]
                client_order_id = order_data["c"]
                order_status = order_data["X"]
                symbol = order_data["s"]
                side = order_data["S"]
                order_type = order_data["o"]
                price = order_data["p"]
                quantity = order_data["q"]
                executed_qty = order_data["z"]  # 累計成交量
                
                logger.info(f"訂單更新: {client_order_id} - {symbol} - {side} - {order_status} - 成交量: {executed_qty}/{quantity}")
                
                # 檢查是否是止盈單（ID以T結尾）或止損單（ID以S結尾）
                is_tp_order = client_order_id.endswith("T")
                is_sl_order = client_order_id.endswith("S")
                
                # === 🔥 修正：處理入場訂單完全成交 ===
                if (order_status == "FILLED" and not is_tp_order and not is_sl_order):
                    
                    # 🚨 過濾邏輯：只處理系統訂單
                    if not client_order_id.startswith('V69_'):
                        logger.info(f"檢測到非系統訂單ID: {client_order_id}，跳過自動止盈設置")
                        return
                        
                    # 🔥 修正：優化本地記錄檢查，增加等待機制
                    if client_order_id not in order_manager.orders:
                        logger.warning(f"WebSocket收到訂單 {client_order_id} 成交通知，但本地記錄中未找到")
                        
                        # 🔥 新增：等待API響應（最多等待2秒）
                        for wait_count in range(4):  # 4次 x 0.5秒 = 2秒
                            time.sleep(0.5)
                            if client_order_id in order_manager.orders:
                                logger.info(f"等待 {(wait_count + 1) * 0.5}秒後找到訂單記錄: {client_order_id}")
                                break
                        else:
                            logger.error(f"等待2秒後仍未找到訂單 {client_order_id} 的本地記錄，跳過處理")
                            return
                    
                    # 🔥 修正：更寬鬆的訂單記錄驗證
                    order_record = order_manager.orders[client_order_id]
                    if not self._validate_order_record_relaxed(order_record, client_order_id):
                        logger.warning(f"訂單 {client_order_id} 記錄驗證失敗，跳過WebSocket處理")
                        return
                    
                    # 🔥 核心改進：從本地記錄獲取加倉資訊，不再重新查詢
                    is_add_position = order_record.get('is_add_position', False)
                    logger.info(f"從訂單記錄獲取加倉資訊 - {symbol}: {'加倉' if is_add_position else '新開倉'}")
                    
                    # 🔥 修正：檢查是否已經處理過，避免重複處理
                    current_status = order_record.get('status')
                    tp_placed = order_record.get('tp_placed', False)
                    
                    if current_status == 'FILLED' and tp_placed:
                        logger.info(f"訂單 {client_order_id} 已經處理過成交和止盈設置，跳過WebSocket重複處理")
                        return
                    
                    # 確認處理類型
                    if is_add_position:
                        logger.info(f"確認加倉操作 - {symbol}")
                        # 取消現有的止盈單和止損單
                        order_manager.cancel_existing_tp_orders_for_symbol(symbol)
                        order_manager.cancel_existing_sl_orders_for_symbol(symbol)
                    else:
                        logger.info(f"確認新開倉操作 - {symbol}")
                        
                    # 🔥 核心改進：統一調用訂單管理器處理成交
                    order_manager.handle_order_filled(
                        client_order_id=client_order_id,
                        symbol=symbol,
                        side=side,
                        order_type=order_type,
                        price=price,
                        quantity=quantity,
                        executed_qty=executed_qty,
                        position_side=order_data.get('ps', 'BOTH'),
                        is_add_position=is_add_position
                    )
                
                # === 🔥 修正：統一訂單狀態更新（包含資料庫同步） ===
                self._update_order_status_with_db_sync(client_order_id, order_status, executed_qty)
                
                # === 處理止盈單成交 ===
                if order_status == "FILLED" and is_tp_order:
                    logger.info(f"止盈單 {client_order_id} 已成交，倉位已關閉")
                    order_manager.handle_tp_filled(client_order_id)
                
                # === 處理止損單成交 ===
                if order_status == "FILLED" and is_sl_order:
                    logger.info(f"止損單 {client_order_id} 已成交，倉位已關閉")
                    order_manager.handle_sl_filled(client_order_id)
        
        except Exception as e:
            logger.error(f"處理WebSocket消息時出錯: {str(e)}")
            logger.error(traceback.format_exc())
    
    def _validate_order_record_relaxed(self, order_record, client_order_id):
        """
        🔥 修正：更寬鬆的訂單記錄驗證（允許PARTIALLY_FILLED狀態）
        
        Args:
            order_record: 訂單記錄字典
            client_order_id: 客戶訂單ID
            
        Returns:
            bool: 記錄是否完整有效
        """
        try:
            # 檢查必要欄位
            required_fields = ['symbol', 'side', 'quantity', 'price']
            for field in required_fields:
                if field not in order_record:
                    logger.warning(f"訂單 {client_order_id} 缺少必要欄位: {field}")
                    return False
            
            # 🔥 修正：允許更多狀態，包括PARTIALLY_FILLED
            status = order_record.get('status')
            valid_statuses = ['PENDING', 'NEW', 'FILLED', 'PARTIALLY_FILLED']
            if status not in valid_statuses:
                logger.warning(f"訂單 {client_order_id} 狀態不在允許範圍: {status} (允許: {valid_statuses})")
                return False
            
            # 檢查價格和數量的有效性
            try:
                price = float(order_record.get('price', 0))
                quantity = float(order_record.get('quantity', 0))
                if price <= 0 or quantity <= 0:
                    logger.warning(f"訂單 {client_order_id} 價格或數量無效: price={price}, quantity={quantity}")
                    return False
            except (ValueError, TypeError):
                logger.warning(f"訂單 {client_order_id} 價格或數量格式錯誤")
                return False
            
            # 🔥 修正：is_add_position是可選欄位，提供默認值
            if 'is_add_position' not in order_record:
                logger.info(f"訂單 {client_order_id} 缺少is_add_position欄位，設為False")
                order_record['is_add_position'] = False
            
            # 檢查信號相關欄位（非必須）
            signal_id = order_record.get('signal_id')
            if not signal_id:
                logger.info(f"訂單 {client_order_id} 缺少信號ID關聯（非致命錯誤）")
            
            return True
            
        except Exception as e:
            logger.error(f"驗證訂單記錄時出錯: {str(e)}")
            return False
    
    def _update_order_status_with_db_sync(self, client_order_id, order_status, executed_qty):
        """
        🔥 修正：訂單狀態更新並同步到資料庫
        
        Args:
            client_order_id: 訂單ID
            order_status: 新狀態
            executed_qty: 成交數量
        """
        try:
            # 對所有系統訂單都更新狀態
            if client_order_id.startswith('V69_'):
                # 更新記憶體狀態
                order_manager.update_order_status(client_order_id, order_status, executed_qty)
                
                # 🔥 關鍵修正：同步更新資料庫狀態
                self._sync_order_status_to_database(client_order_id, order_status, executed_qty)
                
                # 🔥 新增：特別處理取消狀態
                if order_status in ['CANCELED', 'CANCELLED', 'EXPIRED']:
                    logger.info(f"🚫 訂單已取消/過期: {client_order_id} - {order_status}")
                elif order_status == 'FILLED':
                    logger.info(f"✅ 訂單已完全成交: {client_order_id}")
                elif order_status == 'PARTIALLY_FILLED':
                    logger.info(f"⏳ 訂單部分成交: {client_order_id} - {executed_qty}")
                    
            else:
                # 非系統訂單，簡化log
                if order_status == "FILLED":
                    logger.info(f"非系統訂單完成: {client_order_id}")
                
        except Exception as e:
            logger.error(f"更新訂單狀態時出錯: {str(e)}")
    
    def _sync_order_status_to_database(self, client_order_id, status, executed_qty=None):
        """
        🔥 新增：同步訂單狀態到資料庫
        
        Args:
            client_order_id: 訂單ID
            status: 訂單狀態
            executed_qty: 成交數量（可選）
        """
        try:
<<<<<<< HEAD
            from database import trading_data_manager
=======
            from trading_data_manager import trading_data_manager
>>>>>>> 36e2ad4b1d6e4e77ba5ccb0190b9c66b01d574f8
            
            with sqlite3.connect(trading_data_manager.db_path) as conn:
                cursor = conn.cursor()
                
                # 檢查訂單是否存在於資料庫中
                cursor.execute("SELECT id FROM orders_executed WHERE client_order_id = ?", (client_order_id,))
                order_exists = cursor.fetchone()
                
                if not order_exists:
                    logger.warning(f"⚠️  資料庫中未找到訂單: {client_order_id}，跳過狀態更新")
                    return
                
                # 更新訂單狀態
                if executed_qty is not None:
                    cursor.execute("""
                        UPDATE orders_executed 
                        SET status = ?, executed_qty = ?
                        WHERE client_order_id = ?
                    """, (status, executed_qty, client_order_id))
                else:
                    cursor.execute("""
                        UPDATE orders_executed 
                        SET status = ?
                        WHERE client_order_id = ?
                    """, (status, client_order_id))
                
                rows_affected = cursor.rowcount
                conn.commit()
                
                if rows_affected > 0:
                    logger.info(f"📊 資料庫狀態已同步: {client_order_id} → {status}")
                else:
                    logger.warning(f"⚠️  資料庫狀態同步失敗: {client_order_id}")
                    
        except Exception as e:
            logger.error(f"同步資料庫狀態時出錯: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
    
    def _get_order_processing_info(self, client_order_id):
        """
        獲取訂單處理信息（用於調試）
        
        Args:
            client_order_id: 客戶訂單ID
            
        Returns:
            dict: 處理信息
        """
        try:
            if client_order_id not in order_manager.orders:
                return {"found": False, "reason": "not_in_records"}
            
            order_record = order_manager.orders[client_order_id]
            
            return {
                "found": True,
                "status": order_record.get('status'),
                "tp_placed": order_record.get('tp_placed', False),
                "sl_placed": order_record.get('sl_placed', False),
                "is_add_position": order_record.get('is_add_position', False),
                "signal_id": order_record.get('signal_id'),
                "entry_time": order_record.get('entry_time'),
                "symbol": order_record.get('symbol'),
                "side": order_record.get('side')
            }
            
        except Exception as e:
            logger.error(f"獲取訂單處理信息時出錯: {str(e)}")
            return {"found": False, "reason": "error", "error": str(e)}
    
    def get_connection_status(self):
        """
        獲取WebSocket連接狀態
        
        Returns:
            dict: 連接狀態信息
        """
        try:
            return {
                "connected": self.ws is not None and self.ws.sock and self.ws.sock.connected,
                "listen_key": self.listen_key is not None,
                "connection_time": self.connection_time,
                "uptime_hours": (time.time() - self.connection_time) / 3600 if self.connection_time else 0
            }
        except Exception:
            return {
                "connected": False,
                "listen_key": False,
                "connection_time": None,
                "uptime_hours": 0
            }

# 創建全局WebSocket管理器實例
websocket_manager = WebSocketManager()
