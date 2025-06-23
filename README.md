# 69大師背離交易機器人 - 模組化版本 v2.0

[![Python](https://img.shields.io/badge/Python-3.8%2B-blue.svg)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-2.3%2B-green.svg)](https://flask.palletsprojects.com/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## 🎯 專案描述

這是一個基於TradingView信號的全自動化期貨交易機器人，經過完整的模組化重構。支援幣安期貨交易，具備完善的風險控制和監控功能。

## ✨ 主要特色

### 🏗️ **模組化架構**
- **主程式**：從800行重構為僅30行
- **8個功能模組**：職責分離，易於維護
- **13個檔案**：清晰的程式碼結構

### 🎯 **交易功能**
- **自動下單**：接收TradingView信號自動執行交易
- **智能止盈**：基於ATR動態計算止盈價格
- **風險控制**：2%止損保護，最小獲利保證
- **加倉邏輯**：同向加倉，平均成本計算

### 🛡️ **風險管理**
- **時間控制**：台灣時間20:00-23:50禁止交易
- **倉位管理**：支援多個交易對同時運行
- **錯誤處理**：完善的異常處理機制

### 📊 **監控系統**
- **實時監控**：WebSocket監控訂單狀態
- **完整API**：7個API端點，全面監控
- **詳細日誌**：完整的交易記錄

## 📁 專案結構

```
trading_bot/
├── main.py                      # 🎯 主程式 (30行)
├── config/
│   ├── __init__.py
│   └── settings.py              # 配置管理
├── api/
│   ├── __init__.py
│   ├── binance_client.py        # 幣安API客戶端
│   └── websocket_handler.py     # WebSocket管理
├── trading/
│   ├── __init__.py
│   ├── order_manager.py         # 訂單管理
│   └── position_manager.py      # 倉位管理
├── web/
│   ├── __init__.py
│   ├── app.py                   # Flask應用
│   ├── routes.py                # API路由
│   └── signal_processor.py      # 信號處理
└── utils/
    ├── __init__.py
    ├── helpers.py               # 工具函數
    └── logger_config.py         # 日誌配置
```

## 🚀 快速開始

### 1. 環境需求
- Python 3.8+
- 幣安期貨帳戶
- TradingView Pro帳戶（用於發送信號）

### 2. 安裝步驟

```bash
# 克隆專案
git clone https://github.com/您的用戶名/trading-bot-refactored.git
cd trading-bot-refactored

# 創建虛擬環境
python -m venv trading_env
source trading_env/bin/activate  # Linux/Mac
# 或
trading_env\Scripts\activate     # Windows

# 安裝依賴
pip install -r requirements.txt
```

### 3. 配置設定

```bash
# 複製環境變量範例
cp .env.example .env

# 編輯.env檔案，填入您的API密鑰
nano .env
```

在 `.env` 檔案中填入：
```bash
BINANCE_API_KEY=your_api_key_here
BINANCE_API_SECRET=your_api_secret_here
```

### 4. 啟動系統

```bash
python main.py
```

啟動成功後，您將看到：
```
============================================================
69大師背離交易機器人 - 模組化版本 - 系統啟動
============================================================
槓桿設定: 30x
默認止盈: 5.0%
止損功能: 啟用
止損百分比: 2.0%
============================================================
```

## 🎛️ API端點

| 端點 | 方法 | 描述 |
|------|------|------|
| `/webhook` | POST | 接收TradingView信號 |
| `/health` | GET | 健康檢查和系統狀態 |
| `/orders` | GET | 查詢訂單狀態 |
| `/positions` | GET | 查詢當前持倉 |
| `/cancel/<symbol>` | POST | 取消指定交易對訂單 |
| `/config` | GET | 獲取系統配置 |
| `/stats` | GET | 獲取交易統計 |

### 使用範例

```bash
# 健康檢查
curl http://localhost:5000/health

# 查詢訂單
curl http://localhost:5000/orders?symbol=BTCUSDT&limit=10

# 查詢持倉
curl http://localhost:5000/positions
```

## 📋 TradingView設定

### Webhook設定
在TradingView的Alert中設定：
- **Webhook URL**: `http://your-server:5000/webhook`
- **Message**: 
```json
{
  "strategy_name": "V69",
  "symbol": "{{ticker}}",
  "side": "BUY",
  "quantity": "100",
  "open": "{{open}}",
  "close": "{{close}}",
  "prev_close": "{{plot("PREV_CLOSE")}}",
  "prev_open": "{{plot("PREV_OPEN")}}",
  "order_type": "LIMIT",
  "position_side": "BOTH",
  "ATR": "{{plot("ATR")}}",
  "signal_type": "breakout_buy",
  "opposite": "0"
}
```

### 支援的策略類型
- **看多策略**: `pullback_buy`, `breakout_buy`, `consolidation_buy`, `reversal_buy`, `bounce_buy`
- **看空策略**: `trend_sell`, `bounce_sell`, `breakdown_sell`, `high_sell`, `reversal_sell`

## ⚙️ 配置說明

### 主要參數
- **槓桿**: 30倍（可在`config/settings.py`調整）
- **止盈方式**: ATR動態計算 + 最小0.5%保護
- **止損**: 2%固定止損
- **交易對精度**: 支援多種交易對的價格精度

### 止盈倍數設定
```python
SIGNAL_TP_MULTIPLIER = {
    'pullback_buy': 1.2,     # 回調買進
    'breakout_buy': 1.5,     # 突破買進
    'consolidation_buy': 1.0, # 整理買進
    # ... 更多策略
}
```

## 📊 監控和日誌

### 日誌檔案
- 位置: `logs/trading_bot.log`
- 格式: `時間 - 級別 - 訊息`
- 包含: 交易信號、訂單狀態、錯誤信息

### 監控介面
```bash
# 即時查看日誌
tail -f logs/trading_bot.log

# 監控系統狀態
curl http://localhost:5000/health | jq
```

## 🛡️ 安全建議

### API密鑰安全
- ✅ 使用期貨交易專用API密鑰
- ✅ 設定IP白名單
- ✅ 限制API權限（只需期貨交易權限）
- ❌ 絕不在程式碼中硬編碼密鑰

### 風險控制
- 建議初期使用小額測試
- 設定合理的槓桿倍數
- 定期檢查交易記錄
- 監控帳戶餘額變化

## 🔧 故障排除

### 常見問題

**1. 無法連接幣安API**
```bash
# 檢查API密鑰配置
curl -H "X-MBX-APIKEY: your_api_key" https://fapi.binance.com/fapi/v1/time
```

**2. TradingView信號未觸發**
```bash
# 檢查webhook端點
curl -X POST http://localhost:5000/webhook \
  -H "Content-Type: application/json" \
  -d '{"test": "data"}'
```

**3. 程式無法啟動**
```bash
# 檢查依賴
pip list | grep flask

# 檢查Python版本
python --version
```

## 📈 效能指標

### 重構效果
- **主程式行數**: 800行 → 30行 (-96%)
- **檔案數量**: 1個 → 13個 (+1200%)
- **可維護性**: 大幅提升
- **功能完整性**: 100%保留

### 系統效能
- **延遲**: <100ms處理TradingView信號
- **記憶體**: 約50MB運行時記憶體
- **併發**: 支援多個交易對同時運行

## 🤝 貢獻指南

1. Fork本專案
2. 創建功能分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 開啟Pull Request

## 📜 更新日誌

### v2.0.0 (2025-01-XX)
- 🎉 完整模組化重構
- 🏗️ 8個功能模組分離
- 📝 主程式縮減至30行
- 🔧 新增完整API端點

### v1.x (2025-06-XX)
- 修正手動單衝突
- 調整止盈邏輯
- 增加止損邏輯2%

## ⚠️ 免責聲明

本軟體僅供教育和研究目的使用。加密貨幣交易存在高風險，可能導致部分或全部資金損失。使用者應：

- 充分理解交易風險
- 僅使用可承受損失的資金
- 在實盤使用前充分測試
- 自行承擔所有交易決策的責任

開發者不對任何直接或間接的損失承擔責任。

## 📞 支援

如有問題或建議，請：
- 開啟 [GitHub Issue](https://github.com/您的用戶名/trading-bot-refactored/issues)
- 查看 [Wiki文檔](https://github.com/您的用戶名/trading-bot-refactored/wiki)

## 📄 授權

本專案採用 [MIT License](LICENSE) 授權 - 查看LICENSE檔案了解詳情。

---

**⭐ 如果這個專案對您有幫助，請給個Star支持！**