# 69交易機器人系統概覽

## 專案目的
69交易機器人是一個專業的AI驅動自動化加密貨幣交易系統，主要功能包括：
- 接收TradingView交易信號並自動執行交易
- 配備36維機器學習特徵分析的影子決策系統
- 智能風險管理與止盈止損機制
- 完整的交易記錄與分析功能

## 技術棧
- **語言**: Python 3.9+
- **Web框架**: Flask 2.3.3
- **數據庫**: SQLite（通過內建sqlite3模組）
- **HTTP客戶端**: requests 2.31.0
- **WebSocket**: websocket-client 1.6.4
- **機器學習**: scikit-learn（可選，用於ML決策引擎）
- **其他**: python-dotenv, pytz

## 主要組件
- **main.py**: 主程式入口，啟動WebSocket監控和Flask服務
- **shadow_decision_engine.py**: AI影子決策引擎，36維特徵分析
- **web/**: Flask應用和信號處理模組
- **api/**: 幣安API客戶端和WebSocket處理器
- **trading/**: 交易訂單管理和倉位管理
- **database/**: 數據管理模組（交易數據、ML數據、分析數據）
- **config/**: 系統配置和參數設定
- **utils/**: 工具函數和日誌配置