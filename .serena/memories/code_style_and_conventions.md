# 程式碼風格與慣例

## 命名慣例
- **類別**: 使用PascalCase (如: `OrderManager`, `WebSocketManager`)
- **函數和變數**: 使用snake_case (如: `create_order`, `signal_processor`)
- **常數**: 使用UPPER_SNAKE_CASE (如: `API_KEY`, `DEFAULT_LEVERAGE`)
- **私有方法**: 以底線開頭 (如: `_calculate_tp_offset`)

## 檔案結構慣例
- **管理器類別**: 以`_manager.py`結尾 (如: `order_manager.py`)
- **處理器類別**: 以`_handler.py`或`_processor.py`結尾
- **配置檔案**: 放在`config/`目錄
- **工具函數**: 放在`utils/`目錄

## 日誌規範
- 使用統一的logger配置 (`utils/logger_config.py`)
- 各模組從logger_config匯入logger: `from utils.logger_config import get_logger`
- 日誌格式: `'%(asctime)s - %(levelname)s - %(message)s'`

## 例外處理
- 使用try-except包裹關鍵操作
- 記錄完整堆疊追蹤: `logger.error(traceback.format_exc())`

## 文檔字串
- 函數和類別使用三引號文檔字串
- 中文註解說明業務邏輯

## 模組導入
- 標準庫導入放最前面
- 第三方庫導入在中間  
- 本地模組導入放最後
- 相對導入使用明確路徑