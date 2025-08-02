# 開發常用指令

## 安裝與設定
```bash
# 安裝依賴
pip install -r requirements.txt

# 設定環境變數（複製.env.example並修改）
cp .env.example .env
# 編輯.env檔案，填入幣安API密鑰
```

## 運行系統
```bash
# 啟動主程式
python main.py

# 系統會在localhost:5000啟動Flask服務接收TradingView webhook
```

## 開發工具指令
**注意**: 此專案目前沒有配置標準的測試、linting或格式化工具。開發者需要手動執行基本檢查：

```bash
# 檢查Python語法
python -m py_compile main.py

# 檢查所有Python檔案語法
find . -name "*.py" -exec python -m py_compile {} \;
```

## 資料庫操作
系統使用SQLite資料庫，位於`database/`目錄。主要表格：
- 交易記錄表
- ML特徵數據表  
- 影子決策記錄表

## 日誌檢查
系統日誌配置在`utils/logger_config.py`，運行時會輸出到控制台。