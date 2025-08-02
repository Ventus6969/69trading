# 系統架構與模組說明

## 整體架構
```
TradingView信號 → Flask Webhook → 信號處理器 → 影子決策引擎 → 訂單管理器 → 幣安API
                                              ↓
                               WebSocket監控 → 訂單狀態更新 → 止盈止損處理
```

## 核心模組

### 1. 主程式 (main.py)
- 系統啟動入口
- 啟動WebSocket監控線程
- 啟動Flask服務 (port 5000)

### 2. Web模組 (web/)
- **app.py**: Flask應用建立和配置
- **routes.py**: API路由定義，處理TradingView webhook
- **signal_processor.py**: 信號處理核心邏輯

### 3. 影子決策引擎 (shadow_decision_engine.py)
- 36維特徵計算和分析
- AI決策建議 (專家規則 + 機器學習)
- 決策記錄和學習數據收集

### 4. 交易模組 (trading/)
- **order_manager.py**: 訂單管理 (建立、執行、止盈止損)
- **position_manager.py**: 倉位管理和追蹤

### 5. API模組 (api/)
- **binance_client.py**: 幣安API客戶端封裝
- **websocket_handler.py**: WebSocket連線和訂單狀態監控

### 6. 資料庫模組 (database/)
- **trading_data_manager.py**: 交易數據管理
- **ml_data_manager.py**: ML特徵和決策數據管理  
- **analytics_manager.py**: 分析數據管理

### 7. 配置模組 (config/)
- **settings.py**: 系統參數配置 (槓桿、止損、API設定等)

### 8. 工具模組 (utils/)
- **logger_config.py**: 統一日誌配置
- **helpers.py**: 工具函數 (價格計算、格式化、驗證等)

## 資料流向
1. TradingView發送webhook到Flask `/webhook`端點
2. SignalProcessor驗證和處理信號數據
3. ShadowDecisionEngine分析信號品質並提供AI建議
4. OrderManager根據決策執行交易訂單
5. WebSocketManager監控訂單狀態變化
6. 觸發止盈止損時自動處理並記錄結果