# 任務完成檢查清單

## 程式碼修改後必須執行

### 1. 語法檢查
```bash
# 檢查修改的Python檔案語法
python -m py_compile [修改的檔案.py]

# 或檢查所有Python檔案
find . -name "*.py" -exec python -m py_compile {} \;
```

### 2. 功能測試
由於系統沒有自動化測試，需要手動驗證：
- 確認main.py能正常啟動
- 檢查Flask服務是否在5000埠正常運行
- 驗證WebSocket連線功能
- 測試TradingView webhook接收

### 3. 配置檢查
- 確認.env檔案配置正確
- 檢查config/settings.py中的參數設定
- 驗證資料庫路徑和表格結構

### 4. 日誌輸出
- 啟動系統檢查日誌輸出是否正常
- 確認無錯誤或警告訊息
- 驗證關鍵功能的日誌記錄

## 重要提醒
- 此專案沒有配置pytest、flake8、black等標準開發工具
- 建議在修改核心交易邏輯後進行紙上交易測試
- 修改API相關程式碼時要特別小心，避免影響實際交易