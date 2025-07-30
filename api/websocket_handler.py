"""
WebSocket連接管理模組
處理幣安WebSocket連接和訂單狀態更新
🔥 Phase 1修復版：新增止盈/止損單關聯自動取消機制 + 價格獲取修復
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
        """WebSocket消息處理函數 - 🔥 Phase 1修復版 + 價格獲取修復"""
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
                quantity = order_data["q"]
                executed_qty = order_data["z"]  # 累計成交量
                
                # 🔥 核心修復：正確獲取成交價格
                avg_price = order_data.get("ap", "0")      # 平均成交價
                limit_price = order_data.get("p", "0")     # 限價
                last_price = order_data.get("L", "0")      # 最後成交價
                
                # 智能價格選擇邏輯
                if avg_price and float(avg_price) > 0:
                    price = avg_price
                    price_source = "平均成交價(ap)"
                elif last_price and float(last_price) > 0:
                    price = last_price
                    price_source = "最後成交價(L)"
                else:
                    price = limit_price
                    price_source = "限價(p)"
                
                logger.info(f"訂單更新: {client_order_id} - {symbol} - {side} - {order_status} - 成交量: {executed_qty}/{quantity}")
                logger.info(f"🔍 WebSocket價格修復:")
                logger.info(f"  平均成交價(ap): {avg_price}")
                logger.info(f"  限價(p): {limit_price}")
                logger.info(f"  最後成交價(L): {last_price}")
                logger.info(f"  最終選擇: {price} (來源: {price_source})")
                
                # 🔥 Phase 1修復：新增止盈/止損單關聯處理
                self._handle_tp_sl_completion(client_order_id, order_status)
                
                # 檢查是否是止盈單（ID以T結尾）或止損單（ID以S結尾）
                is_tp_order = client_order_id.endswith("T")
                is_sl_order = client_order_id.endswith("S")
                
                # === 處理入場訂單完全成交 ===
                if (order_status == "FILLED" and not is_tp_order and not is_sl_order):
                    
                    # 過濾邏輯：只處理系統訂單
                    if not client_order_id.startswith('V69_'):
                        logger.info(f"檢測到非系統訂單ID: {client_order_id}，跳過自動止盈設置")
                        return
                    
                    # 🔥 新增：價格有效性驗證
                    try:
                        price_float = float(price)
                        if price_float <= 0:
                            logger.error(f"🚨 獲取到無效價格: {price}，跳過處理")
                            return
                    except (ValueError, TypeError):
                        logger.error(f"🚨 價格格式錯誤: {price}，跳過處理")
                        return
                        
                    # 優化本地記錄檢查，增加等待機制
                    if client_order_id not in order_manager.orders:
                        logger.warning(f"WebSocket收到訂單 {client_order_id} 成交通知，但本地記錄中未找到")
                        
                        # 🔥 方案2：增強重試機制（指數退避策略）
                        logger.info(f"🔄 開始重試尋找訂單: {client_order_id}")
                        found_order = False
                        
                        for attempt in range(6):  # 增加到6次嘗試
                            wait_time = 0.2 * (2 ** attempt)  # 指數退避: 0.2s, 0.4s, 0.8s, 1.6s, 3.2s, 6.4s
                            max_wait = min(wait_time, 2.0)  # 最大等待時間限制為2秒
                            
                            logger.info(f"🔍 嘗試 {attempt + 1}/6 尋找訂單 {client_order_id}, 等待 {max_wait:.1f}s")
                            time.sleep(max_wait)
                            
                            if client_order_id in order_manager.orders:
                                logger.info(f"✅ 第 {attempt + 1} 次嘗試成功找到訂單: {client_order_id}")
                                found_order = True
                                break
                        
                        if not found_order:
                            logger.error(f"❌ 6次重試後仍未找到訂單 {client_order_id} 的本地記錄，可能是併發問題")
                            
                            # 🔥 最後嘗試：使用WebSocket數據創建臨時記錄
                            logger.warning(f"🚨 嘗試使用WebSocket數據創建臨時訂單記錄: {client_order_id}")
                            try:
                                order_manager.orders[client_order_id] = {
                                    'symbol': symbol,
                                    'side': side,
                                    'quantity': executed_qty,
                                    'price': price,
                                    'type': 'UNKNOWN',
                                    'status': 'FILLED',
                                    'entry_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                                    'tp_placed': False,
                                    'sl_placed': False,
                                    'position_side': 'BOTH',
                                    'created_from_websocket': True,  # 標記來源
                                    'created_at': time.time()
                                }
                                logger.info(f"✅ 成功創建臨時訂單記錄: {client_order_id}")
                            except Exception as e:
                                logger.error(f"❌ 創建臨時訂單記錄失敗: {str(e)}")
                                return
                    
                    # 更寬鬆的訂單記錄驗證
                    order_record = order_manager.orders[client_order_id]
                    if not self._validate_order_record_relaxed(order_record, client_order_id):
                        logger.warning(f"訂單 {client_order_id} 記錄驗證失敗，跳過WebSocket處理")
                        return
                    
                    # 從本地記錄獲取加倉資訊，不再重新查詢
                    is_add_position = order_record.get('is_add_position', False)
                    logger.info(f"從訂單記錄獲取加倉資訊 - {symbol}: {'加倉' if is_add_position else '新開倉'}")
                    
                    # 檢查是否已經處理過，避免重複處理
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
                        
                    # 核心改進：統一調用訂單管理器處理成交
                    logger.info(f"🚀 即將調用 handle_order_filled，傳遞參數:")
                    logger.info(f"  price: {price} (修復後的正確價格)")
                    logger.info(f"  quantity: {quantity}")
                    order_manager.handle_order_filled(
                        client_order_id=client_order_id,
                        symbol=symbol,
                        side=side,
                        order_type=order_type,
                        price=price,  # 🔥 現在傳遞正確的價格
                        quantity=quantity,
                        executed_qty=executed_qty,
                        position_side=order_data.get('ps', 'BOTH'),
                        is_add_position=is_add_position
                    )
                
                # === 統一訂單狀態更新（包含資料庫同步） ===
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
    
    # ================================================================
    # 🔥 Phase 1 核心修復：止盈/止損單關聯處理
    # ================================================================
    
    def _handle_tp_sl_completion(self, order_id: str, order_status: str):
        """
        🔥 Phase 1 修復：處理止盈/止損單完成時的關聯取消
        
        Args:
            order_id: 訂單ID
            order_status: 訂單狀態
        """
        try:
            # 只處理完全成交的止盈/止損單
            if order_status != 'FILLED':
                return
            
            if order_id.endswith('T'):  # 止盈單成交
                logger.info(f"🎯 止盈單成交: {order_id}")
                self._cancel_partner_order(order_id, 'S')  # 取消對應止損單
                
            elif order_id.endswith('S'):  # 止損單成交
                logger.info(f"🛡️ 止損單成交: {order_id}")
                self._cancel_partner_order(order_id, 'T')  # 取消對應止盈單
                
        except Exception as e:
            logger.error(f"❌ 處理止盈止損完成時出錯: {str(e)}")
    
    def _cancel_partner_order(self, completed_order_id: str, partner_suffix: str):
        """
        🔥 Phase 1 修復：取消配對訂單
        
        Args:
            completed_order_id: 已完成的訂單ID
            partner_suffix: 配對訂單後綴 ('T' 或 'S')
        """
        try:
            # 提取主訂單前綴邏輯
            if completed_order_id.endswith('T') or completed_order_id.endswith('S'):
                # 處理格式：V69_BTCUSD_S7207_1852T 或 V69_BTCUSD_S7207_1896S
                parts = completed_order_id.split('_')
                if len(parts) >= 4:  
                    # 重建前綴：V69_BTCUSD_S7207
                    prefix = '_'.join(parts[:-1])
                    
                    # 獲取所有開放訂單
                    open_orders = binance_client.get_all_open_orders()
                    
                    for order in open_orders:
                        order_client_id = order.get('clientOrderId', '')
                        
                        # 找到同組的配對訂單
                        if (order_client_id.startswith(prefix) and 
                            order_client_id.endswith(partner_suffix)):
                            
                            # 🔥 關鍵修復：取消配對訂單
                            cancel_result = self._cancel_order_safe(order_client_id)
                            if cancel_result:
                                logger.info(f"✅ 已取消配對訂單: {order_client_id}")
                            else:
                                logger.warning(f"⚠️ 取消配對訂單失敗: {order_client_id}")
                            break
                    else:
                        logger.info(f"ℹ️ 未找到配對訂單: {prefix}*{partner_suffix}")
                        
        except Exception as e:
            logger.error(f"❌ 取消配對訂單失敗: {completed_order_id} - {str(e)}")
    
    def _cancel_order_safe(self, order_id: str) -> bool:
        """
        🔥 Phase 1 修復：安全取消訂單
        
        Args:
            order_id: 要取消的訂單ID
            
        Returns:
            bool: 是否取消成功
        """
        try:
            # 先檢查訂單是否還存在
            try:
                order_info = binance_client.get_order_by_client_id(order_id)
                if order_info and order_info.get('status') in ['NEW', 'PARTIALLY_FILLED']:
                    # 訂單存在且可取消
                    cancel_result = binance_client.cancel_order_by_client_id(order_id)
                    logger.info(f"✅ 訂單取消成功: {order_id}")
                    return True
                else:
                    logger.info(f"ℹ️ 訂單已不存在或已完成: {order_id}")
                    return True  # 視為成功，因為目標已達成
                    
            except Exception as e:
                if "Unknown order sent" in str(e):
                    logger.info(f"ℹ️ 訂單不存在: {order_id}")
                    return True  # 訂單已不存在，視為成功
                else:
                    raise e
                    
        except Exception as e:
            logger.error(f"❌ 取消訂單失敗: {order_id} - {str(e)}")
            return False
    
    # ================================================================
    # 原有邏輯保持不變
    # ================================================================
    
    def _validate_order_record_relaxed(self, order_record, client_order_id):
        """
        更寬鬆的訂單記錄驗證
        
        Args:
            order_record: 訂單記錄
            client_order_id: 訂單ID
            
        Returns:
            bool: 是否有效
        """
        try:
            # 基本字段檢查
            required_fields = ['symbol', 'side', 'quantity', 'price']
            
            for field in required_fields:
                if field not in order_record:
                    logger.warning(f"訂單記錄缺少字段 {field}: {client_order_id}")
                    return False
            
            # 數據類型檢查（更寬鬆）
            try:
                float(order_record['price'])
                float(order_record['quantity'])
            except (ValueError, TypeError):
                logger.warning(f"訂單記錄數據類型無效: {client_order_id}")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"驗證訂單記錄時出錯: {str(e)}")
            return False
    
    def _update_order_status_with_db_sync(self, client_order_id, order_status, executed_qty):
        """
        訂單狀態更新並同步到資料庫
        
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
                
                # 同步更新資料庫狀態
                self._sync_order_status_to_database(client_order_id, order_status, executed_qty)
                
                # 特別處理取消狀態
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
        同步訂單狀態到資料庫
        
        Args:
            client_order_id: 訂單ID
            status: 訂單狀態
            executed_qty: 成交數量（可選）
        """
        try:
            from database import trading_data_manager
            
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