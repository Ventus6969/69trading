"""
Flask路由模組
包含所有API端點的路由處理
=============================================================================
"""
import logging
from datetime import datetime
from flask import request, jsonify
from api.binance_client import binance_client
from trading.order_manager import order_manager
from trading.position_manager import position_manager
from web.signal_processor import signal_processor
from config.settings import (
    DEFAULT_LEVERAGE, TP_PERCENTAGE, ORDER_TIMEOUT_MINUTES,
    TW_TIMEZONE, SYMBOL_PRECISION, MODE_TP_MULTIPLIER,
    MIN_TP_PROFIT_PERCENTAGE, STOP_LOSS_PERCENTAGE, ENABLE_STOP_LOSS,
    SIGNAL_TP_MULTIPLIER
)

# 設置logger
logger = logging.getLogger(__name__)

def register_routes(app):
    """註冊所有路由到Flask應用"""
    
    @app.route('/webhook', methods=['POST'])
    def webhook():
        """接收TradingView信號的API端點"""
        try:
            # === 1. 接收和驗證數據 ===
            data = request.json
            
            if not data:
                return jsonify({"status": "error", "message": "無效的數據"}), 400
            
            # === 2. 處理信號 ===
            result = signal_processor.process_signal(data)
            
            # === 3. 返回處理結果 ===
            if result.get('status') == 'error':
                return jsonify(result), 500
            elif result.get('status') == 'ignored':
                return jsonify(result)
            else:
                return jsonify(result)
                
        except Exception as e:
            logger.error(f"處理webhook時出錯: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return jsonify({"status": "error", "message": str(e)}), 500
    
    @app.route('/health', methods=['GET'])
    def health_check():
        """健康檢查端點 - 用於監控系統運行狀態（優化版本）"""
        try:
            # 檢查基本系統狀態
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # 檢查WebSocket連接狀態（通過檢查最近的數據更新）
            last_webhook_data = signal_processor.get_last_webhook_data()
            last_webhook_time = None
            if last_webhook_data:
                last_webhook_time = last_webhook_data.get('timestamp')
            
            # 統計當前訂單狀態
            all_orders = order_manager.get_orders()
            total_orders = len(all_orders)
            active_orders = len([o for o in all_orders.values() if o.get('status') in ['NEW', 'PARTIALLY_FILLED']])
            filled_orders = len([o for o in all_orders.values() if o.get('status') == 'FILLED'])
            tp_filled_orders = len([o for o in all_orders.values() if o.get('status') == 'TP_FILLED'])
            
            # 檢查當前持倉（不輸出詳細log）
            try:
                current_positions = position_manager.get_current_positions()
                position_count = len(current_positions)
                
                # 計算總未實現盈虧
                total_pnl = sum(p['unRealizedProfit'] for p in current_positions.values()) if current_positions else 0
                
            except Exception as e:
                current_positions = {}
                position_count = 0
                total_pnl = 0
                logger.warning(f"健康檢查時獲取持倉信息失敗: {str(e)}")
            
            # 構造健康檢查響應
            health_status = {
                "status": "ok",
                "message": "服務正常運行中",
                "timestamp": current_time,
                "system_info": {
                    "total_orders": total_orders,
                    "active_orders": active_orders,
                    "filled_orders": filled_orders,
                    "tp_filled_orders": tp_filled_orders,
                    "current_positions": position_count,
                    "total_unrealized_pnl": round(total_pnl, 4),
                    "last_webhook_time": datetime.fromtimestamp(last_webhook_time).strftime('%Y-%m-%d %H:%M:%S') if last_webhook_time else "無",
                    "leverage": f"{DEFAULT_LEVERAGE}x",
                    "timezone": "Asia/Taipei"
                },
                "active_positions": {symbol: {"side": pos["side"], "amount": pos["positionAmt"], "pnl": pos["unRealizedProfit"]} 
                                   for symbol, pos in current_positions.items()} if current_positions else {}
            }
            
            return jsonify(health_status)
            
        except Exception as e:
            logger.error(f"健康檢查時出錯: {str(e)}")
            return jsonify({
                "status": "error",
                "message": f"健康檢查失敗: {str(e)}",
                "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }), 500
    
    @app.route('/orders', methods=['GET'])
    def get_orders():
        """訂單狀態查詢端點 - 查看所有訂單記錄"""
        try:
            # 獲取查詢參數
            symbol = request.args.get('symbol')  # 可選：按交易對過濾
            status = request.args.get('status')  # 可選：按狀態過濾
            limit = request.args.get('limit', type=int)  # 可選：限制返回數量
            
            # 獲取所有訂單
            all_orders = order_manager.get_orders()
            filtered_orders = {}
            
            for order_id, order_info in all_orders.items():
                # 按交易對過濾
                if symbol and order_info.get('symbol') != symbol.upper():
                    continue
                    
                # 按狀態過濾
                if status and order_info.get('status') != status.upper():
                    continue
                    
                filtered_orders[order_id] = order_info
            
            # 按時間排序（最新的在前）
            sorted_orders = dict(sorted(
                filtered_orders.items(), 
                key=lambda x: x[1].get('entry_time', ''), 
                reverse=True
            ))
            
            # 限制返回數量
            if limit:
                sorted_orders = dict(list(sorted_orders.items())[:limit])
            
            # 統計信息
            stats = {
                "total_filtered": len(sorted_orders),
                "total_all": len(all_orders),
                "filter_applied": {
                    "symbol": symbol,
                    "status": status,
                    "limit": limit
                }
            }
            
            return jsonify({
                "status": "success",
                "statistics": stats,
                "orders": sorted_orders
            })
            
        except Exception as e:
            logger.error(f"查詢訂單時出錯: {str(e)}")
            return jsonify({
                "status": "error",
                "message": f"查詢訂單失敗: {str(e)}"
            }), 500
    
    @app.route('/positions', methods=['GET'])
    def get_positions():
        """當前持倉查詢端點"""
        try:
            # 獲取持倉摘要
            summary = position_manager.calculate_position_summary()
            
            return jsonify({
                "status": "success",
                "summary": {
                    "total_positions": summary['total_positions'],
                    "long_positions": summary['long_positions'],
                    "short_positions": summary['short_positions'],
                    "total_unrealized_pnl": summary['total_unrealized_pnl']
                },
                "positions": summary['positions_detail'],
                "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            })
            
        except Exception as e:
            logger.error(f"查詢持倉時出錯: {str(e)}")
            return jsonify({
                "status": "error",
                "message": f"查詢持倉失敗: {str(e)}"
            }), 500
    
    @app.route('/cancel/<symbol>', methods=['POST'])
    def cancel_symbol_orders(symbol):
        """取消指定交易對的所有訂單"""
        try:
            symbol = symbol.upper()
            cancelled_count = 0
            cancelled_orders = []
            
            # 取消該交易對的所有未完成訂單
            all_orders = order_manager.get_orders()
            for order_id, order_info in all_orders.items():
                if (order_info.get('symbol') == symbol and 
                    order_info.get('status') in ['NEW', 'PARTIALLY_FILLED']):
                    
                    # 取消主訂單
                    cancel_result = binance_client.cancel_order(symbol, order_id)
                    if cancel_result:
                        cancelled_count += 1
                        cancelled_orders.append(order_id)
                        
                    # 取消對應的止盈單
                    tp_client_id = order_info.get('tp_client_id')
                    if tp_client_id:
                        binance_client.cancel_order(symbol, tp_client_id)
            
            # 額外取消所有止盈單和止損單
            tp_cancelled = order_manager.cancel_existing_tp_orders_for_symbol(symbol)
            sl_cancelled = order_manager.cancel_existing_sl_orders_for_symbol(symbol)
            
            return jsonify({
                "status": "success",
                "message": f"已取消 {symbol} 的訂單",
                "cancelled_orders": cancelled_count,
                "cancelled_tp_orders": tp_cancelled,
                "cancelled_sl_orders": sl_cancelled,
                "cancelled_order_ids": cancelled_orders
            })
            
        except Exception as e:
            logger.error(f"取消訂單時出錯: {str(e)}")
            return jsonify({
                "status": "error",
                "message": f"取消訂單失敗: {str(e)}"
            }), 500
    
    @app.route('/config', methods=['GET'])
    def get_config():
        """獲取當前系統配置"""
        try:
            config_info = {
                "trading_config": {
                    "default_leverage": DEFAULT_LEVERAGE,
                    "default_tp_percentage": f"{TP_PERCENTAGE:.1%}",
                    "min_tp_profit_percentage": f"{MIN_TP_PROFIT_PERCENTAGE:.1%}",
                    "stop_loss_percentage": f"{STOP_LOSS_PERCENTAGE:.1%}",
                    "stop_loss_enabled": ENABLE_STOP_LOSS,
                    "order_timeout_minutes": ORDER_TIMEOUT_MINUTES,
                    "timezone": str(TW_TIMEZONE)
                },
                "symbol_precision": SYMBOL_PRECISION,
                "mode_tp_multiplier": MODE_TP_MULTIPLIER,
                "signal_tp_multiplier": SIGNAL_TP_MULTIPLIER,
                "api_endpoints": {
                    "webhook": "/webhook",
                    "health": "/health", 
                    "orders": "/orders",
                    "positions": "/positions",
                    "cancel": "/cancel/<symbol>",
                    "config": "/config",
                    "stats": "/stats"
                },
                "trading_time_restriction": {
                    "blocked_time": "20:00-23:50 (台灣時間)",
                    "description": "此時間段內不執行交易操作"
                }
            }
            
            return jsonify({
                "status": "success",
                "config": config_info,
                "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            })
            
        except Exception as e:
            logger.error(f"獲取配置時出錯: {str(e)}")
            return jsonify({
                "status": "error",
                "message": f"獲取配置失敗: {str(e)}"
            }), 500
    
    @app.route('/stats', methods=['GET'])
    def get_statistics():
        """獲取交易統計信息"""
        try:
            # 計算各種統計數據
            all_orders = order_manager.get_orders()
            total_orders = len(all_orders)
            
            # 按狀態統計
            status_stats = {}
            for order_info in all_orders.values():
                status = order_info.get('status', 'UNKNOWN')
                status_stats[status] = status_stats.get(status, 0) + 1
            
            # 按交易對統計
            symbol_stats = {}
            for order_info in all_orders.values():
                symbol = order_info.get('symbol', 'UNKNOWN')
                symbol_stats[symbol] = symbol_stats.get(symbol, 0) + 1
            
            # 按方向統計
            side_stats = {}
            for order_info in all_orders.values():
                side = order_info.get('side', 'UNKNOWN')
                side_stats[side] = side_stats.get(side, 0) + 1
            
            # 按策略信號統計
            signal_stats = {}
            for order_info in all_orders.values():
                signal_type = order_info.get('signal_type', 'UNKNOWN')
                signal_stats[signal_type] = signal_stats.get(signal_type, 0) + 1
            
            # 計算成功率（如果有足夠數據）
            filled_orders = status_stats.get('FILLED', 0)
            tp_filled_orders = status_stats.get('TP_FILLED', 0)
            sl_filled_orders = status_stats.get('SL_FILLED', 0)
            success_rate = None
            if filled_orders > 0:
                success_rate = f"{(tp_filled_orders / filled_orders * 100):.1f}%"
            
            # 當前持倉統計
            current_positions = position_manager.get_current_positions()
            
            return jsonify({
                "status": "success",
                "statistics": {
                    "total_orders": total_orders,
                    "status_breakdown": status_stats,
                    "symbol_breakdown": symbol_stats,
                    "side_breakdown": side_stats,
                    "signal_breakdown": signal_stats,
                    "success_rate": success_rate,
                    "current_positions_count": len(current_positions),
                    "performance": {
                        "filled_orders": filled_orders,
                        "tp_filled_orders": tp_filled_orders,
                        "sl_filled_orders": sl_filled_orders,
                        "win_rate": success_rate
                    }
                },
                "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            })
            
        except Exception as e:
            logger.error(f"獲取統計信息時出錯: {str(e)}")
            return jsonify({
                "status": "error",
                "message": f"獲取統計失敗: {str(e)}"
            }), 500
