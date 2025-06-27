"""
交易機器人配置文件
集中管理所有配置參數，保持與原程式完全相同的設定
=============================================================================
"""
import os
import pytz
from dotenv import load_dotenv

# =============================================================================
# 環境變量載入
# =============================================================================

# 載入環境變量
load_dotenv()

# 如果存在.env.follow文件，優先使用它的API密鑰
if os.path.exists('.env.follow'):
    load_dotenv('.env.follow', override=True)

# =============================================================================
# API配置
# =============================================================================

# 幣安API配置
API_KEY = os.getenv("BINANCE_TRADING_API_KEY") or os.getenv("BINANCE_API_KEY")
API_SECRET = os.getenv("BINANCE_TRADING_API_SECRET") or os.getenv("BINANCE_API_SECRET")

BASE_URL = "https://fapi.binance.com"
WS_BASE_URL = "wss://fstream.binance.com/ws"

# =============================================================================
# 交易對配置
# =============================================================================

# 交易對價格精度設定
SYMBOL_PRECISION = {
    'SOLUSDT': 2,       # SOLUSDT 精度為小數點後2位
    'BTCUSDT': 1,       # BTCUSDT 精度為小數點後1位
    'ETHUSDT': 2,       # ETHUSDT 精度為小數點後2位
    'WLDUSDC': 5,       # WLDUSDC 精度為小數點後5位
    'SOLUSDC': 2,       # SOLUSDC 精度為小數點後2位
    'BTCUSDC': 1,       # BTCUSDC 精度為小數點後1位
    'ETHUSDC': 2,       # ETHUSDC 精度為小數點後2位
    'BNBUSDC': 2,       # BNBUSDC 精度為小數點後2位	
    # 可以根據需要添加更多交易對
}

# 默認精度，當找不到指定交易對時使用
DEFAULT_PRECISION = 2

# =============================================================================
# 止盈止損配置
# =============================================================================

# 根據開倉模式的止盈ATR倍數設定
MODE_TP_MULTIPLIER = {
    0: 1.2,  # 當前收盤價模式
    1: 1.5,  # 前根收盤價模式  
    2: 1.5   # 前根開盤價模式
}

# 策略信號專屬ATR倍數設定
SIGNAL_TP_MULTIPLIER = {
    # === 看多策略 ===
    'pullback_buy': 1.2,        # 回調買進 - 相對保守，回調進場風險較小
    'breakout_buy': 1.5,        # 突破買進 - 較積極，突破後有續航力
    'consolidation_buy': 1.0,   # 整理買進 - 保守，盤整階段小幅獲利
    'reversal_buy': 1.5,        # 反轉買進 - 積極，反轉信號強烈
    'bounce_buy': 1.5,          # 反彈買進 - 中等，反彈力度適中
    'negative_div_bounce': 1.2, # 負背離反彈 - 新增
    
    # === 看空策略 ===
    'trend_sell': 1.2,          # 趨勢做空 - 中等，跟隨趨勢
    'bounce_sell': 1,           # 反彈做空 - 較積極，反彈做空機會珍貴
    'breakdown_sell': 1.5,      # 破底做空 - 很積極，破底後加速下跌
    'high_sell': 1.5,           # 高位做空 - 保守，高位風險大
    'reversal_sell': 1.5        # 轉勢做空 - 積極，轉勢信號強烈
}

# 默認策略倍數，當找不到指定策略時使用
DEFAULT_SIGNAL_TP_MULTIPLIER = 1.3

# 默認倍數，當找不到指定交易對時使用
DEFAULT_TP_MULTIPLIER = 1.0

# 最小止盈獲利百分比（如果ATR計算的獲利小於此值，則使用此值）
MIN_TP_PROFIT_PERCENTAGE = 0.0045  # 0.45%

# 止損設定
STOP_LOSS_PERCENTAGE = 0.02  # 2% 止損
ENABLE_STOP_LOSS = True  # 是否啟用止損功能

# =============================================================================
# 交易參數設定
# =============================================================================

# 新的交易參數設定
DEFAULT_LEVERAGE = 30  # 30倍槓桿
TP_PERCENTAGE = 0.05  # 5% 默認止盈（作為備案）

# 訂單超時設置 (分鐘)
ORDER_TIMEOUT_MINUTES = 45

# =============================================================================
# 時間設定
# =============================================================================

# 設置台灣時區
TW_TIMEZONE = pytz.timezone('Asia/Taipei')

# 交易時間限制 (台灣時間)
TRADING_BLOCK_START_HOUR = 20
TRADING_BLOCK_START_MINUTE = 0
TRADING_BLOCK_END_HOUR = 23
TRADING_BLOCK_END_MINUTE = 50

# =============================================================================
# 系統配置
# =============================================================================

# 日誌目錄
LOG_DIRECTORY = 'logs'

# 訂單相關
MAX_ARRAY_SIZE = 20
MAX_ORDER_ID_LENGTH = 28  # 預留2字符給T/S後綴

# WebSocket相關
WEBSOCKET_RECONNECT_DELAY = 5
LISTENKEY_RENEWAL_INTERVAL = 30 * 60  # 30分鐘
LISTENKEY_MAX_AGE = 23 * 60 * 60      # 23小時

# Flask相關
FLASK_HOST = '0.0.0.0'
FLASK_PORT = 5000
FLASK_DEBUG = False
FLASK_THREADED = True

# =============================================================================
# API端點配置
# =============================================================================

API_ENDPOINTS = {
    "webhook": "/webhook",
    "health": "/health", 
    "orders": "/orders",
    "positions": "/positions",
    "cancel": "/cancel/<symbol>",
    "config": "/config",
    "stats": "/stats"
}

# =============================================================================
# 系統版本信息
# =============================================================================

# 版本信息
VERSION = "2.0.0"
VERSION_NAME = "69大師背離交易機器人 - 模組化版本"

# 更新歷史
VERSION_HISTORY = [
    "2025/06/05 修正手動單衝突",
    "2025/06/06 調整止盈邏輯", 
    "2025/06/10 增加止損邏輯2%",
    "2025/01/XX 完整模組化重構"
]

# =============================================================================
# 策略配置
# =============================================================================

# 支持的策略類型
SUPPORTED_STRATEGIES = [
    'pullback_buy', 'breakout_buy', 'consolidation_buy', 
    'reversal_buy', 'bounce_buy', 'negative_div_bounce',
    'trend_sell', 'bounce_sell', 'breakdown_sell', 
    'high_sell', 'reversal_sell'
]

# 支持的開倉模式
ENTRY_MODES = {
    0: "當前收盤價",
    1: "前根收盤價", 
    2: "前根開盤價"
}

# 支持的訂單類型
SUPPORTED_ORDER_TYPES = ['MARKET', 'LIMIT', 'STOP_MARKET', 'TAKE_PROFIT_MARKET']

# =============================================================================
# 風險控制配置
# =============================================================================

# 最大持倉數量限制
MAX_POSITIONS = 10

# 單個交易對最大倉位（USDT）
MAX_POSITION_SIZE_USDT = 10000

# 每日最大交易次數
MAX_DAILY_TRADES = 50

# 最大連續虧損次數
MAX_CONSECUTIVE_LOSSES = 5

# =============================================================================
# 驗證配置
# =============================================================================

def validate_config():
    """驗證配置完整性"""
    errors = []
    
    # 驗證API密鑰
    if not API_KEY or not API_SECRET:
        errors.append("無法載入API密鑰，請檢查環境變量配置")
    
    # 驗證基本參數
    if DEFAULT_LEVERAGE <= 0 or DEFAULT_LEVERAGE > 125:
        errors.append(f"槓桿設定無效: {DEFAULT_LEVERAGE}，應該在1-125之間")
    
    if TP_PERCENTAGE <= 0 or TP_PERCENTAGE > 1:
        errors.append(f"止盈百分比無效: {TP_PERCENTAGE}，應該在0-1之間")
    
    if STOP_LOSS_PERCENTAGE <= 0 or STOP_LOSS_PERCENTAGE > 1:
        errors.append(f"止損百分比無效: {STOP_LOSS_PERCENTAGE}，應該在0-1之間")
    
    # 驗證時間設定
    if not (0 <= TRADING_BLOCK_START_HOUR <= 23):
        errors.append(f"交易時間開始小時無效: {TRADING_BLOCK_START_HOUR}")
    
    if not (0 <= TRADING_BLOCK_END_HOUR <= 23):
        errors.append(f"交易時間結束小時無效: {TRADING_BLOCK_END_HOUR}")
    
    # 如果有錯誤，拋出異常
    if errors:
        raise ValueError("配置驗證失敗:\n" + "\n".join(f"- {error}" for error in errors))
    
    return True

def get_config_summary():
    """獲取配置摘要信息"""
    return {
        "version": VERSION,
        "version_name": VERSION_NAME,
        "api_configured": bool(API_KEY and API_SECRET),
        "leverage": DEFAULT_LEVERAGE,
        "tp_percentage": f"{TP_PERCENTAGE:.1%}",
        "sl_percentage": f"{STOP_LOSS_PERCENTAGE:.1%}",
        "sl_enabled": ENABLE_STOP_LOSS,
        "supported_symbols": len(SYMBOL_PRECISION),
        "supported_strategies": len(SUPPORTED_STRATEGIES),
        "trading_time_block": f"{TRADING_BLOCK_START_HOUR:02d}:{TRADING_BLOCK_START_MINUTE:02d}-{TRADING_BLOCK_END_HOUR:02d}:{TRADING_BLOCK_END_MINUTE:02d}",
        "timezone": str(TW_TIMEZONE)
    }

# =============================================================================
# 配置初始化
# =============================================================================

# 在導入時驗證配置
try:
    validate_config()
except ValueError as e:
    import logging
    logging.error(f"配置驗證失敗: {e}")
    raise
