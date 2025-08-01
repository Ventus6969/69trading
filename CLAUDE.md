# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 專案概覽

69交易機器人是一個專業的AI驅動自動化加密貨幣交易系統，具備36維機器學習特徵分析和智能決策能力。系統接收TradingView信號，透過影子決策引擎分析，自動執行交易並管理風險。

## 核心架構

```
TradingView信號 → Flask Webhook → 信號處理器 → 影子決策引擎 → 訂單管理器 → 幣安API
                                              ↓
                               WebSocket監控 → 訂單狀態更新 → 止盈止損處理
```

主要模組：
- **main.py**: 系統入口，啟動WebSocket和Flask服務
- **shadow_decision_engine.py**: AI影子決策引擎，36維特徵分析
- **web/**: Flask應用和信號處理（webhook接收在port 5000）
- **trading/**: 訂單管理和倉位管理
- **api/**: 幣安API客戶端和WebSocket處理
- **database/**: 數據管理（交易、ML、分析數據）

## 開發指令

### 系統啟動
```bash
# 安裝依賴
pip install -r requirements.txt

# 設定環境變數（需要幣安API密鑰）
cp .env.example .env
# 編輯.env檔案填入API密鑰

# 啟動系統
python main.py
```

### 程式碼檢查
此專案未配置標準的testing/linting工具，請手動執行：
```bash
# 語法檢查
python -m py_compile [檔案名.py]

# 檢查所有Python檔案
find . -name "*.py" -exec python -m py_compile {} \;
```

## 程式碼慣例

### 命名規範
- 類別: PascalCase (`OrderManager`, `WebSocketManager`)
- 函數/變數: snake_case (`create_order`, `signal_processor`)
- 常數: UPPER_SNAKE_CASE (`API_KEY`, `DEFAULT_LEVERAGE`)
- 私有方法: 底線開頭 (`_calculate_tp_offset`)

### 模組結構
- 管理器類別: `*_manager.py`
- 處理器類別: `*_handler.py` 或 `*_processor.py`
- 統一日誌: `from utils.logger_config import get_logger`
- 例外處理: 記錄完整堆疊 `logger.error(traceback.format_exc())`

### 重要設計模式
- 單例模式: 各管理器使用模組級實例（如`order_manager`, `websocket_manager`）
- 工廠模式: `create_flask_app()`, `create_ml_data_manager()`
- 觀察者模式: WebSocket事件處理和回調機制

## 關鍵配置

**技術棧**: Python 3.9+, Flask, SQLite, requests, websocket-client, scikit-learn
**API**: 幣安期貨API，需要API_KEY和API_SECRET
**資料庫**: SQLite，位於database/目錄
**WebSocket**: 監控訂單狀態變化和自動觸發止盈止損

## 特殊注意事項

1. **交易安全**: 修改交易邏輯時需特別小心，建議先紙上交易測試
2. **API限制**: 注意幣安API速率限制，避免過頻繁請求
3. **資料完整性**: 所有交易都有完整記錄，包括36維ML特徵數據
4. **中文註解**: 業務邏輯使用中文註解，符合專案慣例
5. **WebSocket穩定性**: 系統依賴WebSocket監控，需確保連線穩定性

## AI決策系統

核心特色是36維特徵分析的影子決策引擎：
- 15個信號品質特徵（策略勝率、市場適應性等）
- 12個價格關係特徵（K線形態、ATR偏差等）
- 9個市場環境特徵（交易時段、波動率制度等）

目前處於數據收集階段，專家規則決策為主，ML模型訓練為輔。