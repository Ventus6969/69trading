"""
WebSocket連接管理模組
處理幣安WebSocket連接和訂單狀態更新
=============================================================================
"""
import json
import time
import logging
import threading
import traceback
import websocket
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
        """WebSocket消息處理函數 - 監控訂單狀態變化"""
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
                
                # === 處理入場訂單完全成交 ===
                if (order_status == "FILLED" and not is_tp_order and not is_sl_order):
                    
                    # 🚨 過濾邏輯：只處理系統訂單
                    if not client_order_id.startswith('V69_'):
                        logger.info(f"檢測到非系統訂單ID: {client_order_id}，跳過自動止盈設置")
                        return
                        
                    # 🔥 檢查是否為加倉操作
                    current_positions_for_check = binance_client.get_current_positions()
                    is_add_position = symbol in current_positions_for_check
        
                    if is_add_position:
                        logger.info(f"檢測到加倉操作 - {symbol}")
                        # 取消現有的止盈單和止損單
                        order_manager.cancel_existing_tp_orders_for_symbol(symbol)
                        order_manager.cancel_existing_sl_orders_for_symbol(symbol)
                    else:
                        logger.info(f"檢測到新開倉操作 - {symbol}")
                        
                    # 處理訂單成交
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
                
                # === 更新訂單信息 ===
                order_manager.update_order_status(client_order_id, order_status, executed_qty)
                
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

# 創建全局WebSocket管理器實例
websocket_manager = WebSocketManager()
