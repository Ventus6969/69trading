"""
工具函數模組
包含通用的輔助函數，保持與原程式完全相同的邏輯
=============================================================================
"""
import time
import logging
from datetime import datetime, timezone
from config.settings import (
    SYMBOL_PRECISION, DEFAULT_PRECISION,
    MODE_TP_MULTIPLIER, SIGNAL_TP_MULTIPLIER, 
    DEFAULT_SIGNAL_TP_MULTIPLIER, DEFAULT_TP_MULTIPLIER,
    TW_TIMEZONE
)

# 設置logger
logger = logging.getLogger(__name__)

def get_symbol_precision(symbol):
    """獲取指定交易對的價格精度"""
    return SYMBOL_PRECISION.get(symbol, DEFAULT_PRECISION)

def get_tp_multiplier(symbol, opposite=0, signal_type=None):
    """
    根據策略信號、交易對和開倉模式獲取止盈ATR倍數
    
    Args:
        symbol: 交易對
        opposite: 開倉模式 0=當前收盤, 1=前根收盤, 2=前根開盤
        signal_type: 策略信號類型（新增）
        
    Returns:
        float: ATR倍數
    """
    # 1. 優先檢查策略信號專屬設定 (最高優先級)
    if signal_type and signal_type in SIGNAL_TP_MULTIPLIER:
        multiplier = SIGNAL_TP_MULTIPLIER[signal_type]
        logger.info(f"使用策略信號 {signal_type} 的ATR倍數: {multiplier}")
        return multiplier

    # 2. 使用開倉模式決定倍數（保持原有邏輯）
    multiplier = MODE_TP_MULTIPLIER.get(opposite, DEFAULT_TP_MULTIPLIER)
    logger.info(f"使用開倉模式 {opposite} 的ATR倍數: {multiplier}")
    return multiplier

def is_within_time_range(start_hour, start_minute, end_hour, end_minute):
    """
    檢查當前時間是否在指定的台灣時間範圍內
    
    Args:
        start_hour (int): 開始時間的小時
        start_minute (int): 開始時間的分鐘
        end_hour (int): 結束時間的小時
        end_minute (int): 結束時間的分鐘
        
    Returns:
        bool: 如果當前時間在指定範圍內，返回True；否則返回False
    """
    # 獲取當前UTC時間
    utc_now = datetime.now(timezone.utc)
    
    # 轉換為台灣時間
    tw_now = utc_now.astimezone(TW_TIMEZONE)
    
    # 創建今天的開始和結束時間點
    start_time = tw_now.replace(hour=start_hour, minute=start_minute, second=0, microsecond=0)
    end_time = tw_now.replace(hour=end_hour, minute=end_minute, second=0, microsecond=0)
    
    # 判斷當前時間是否在範圍內
    return start_time <= tw_now <= end_time

def generate_order_id(strategy_name, symbol, side, timestamp=None, counter=1):
    """
    生成符合長度限制的訂單ID
    
    Args:
        strategy_name: 策略名稱
        symbol: 交易對
        side: 交易方向
        timestamp: 時間戳（可選）
        counter: 計數器
        
    Returns:
        str: 生成的訂單ID
    """
    if timestamp is None:
        timestamp = int(time.time())
    
    # 縮短策略名稱和交易對
    short_strategy = strategy_name[:3] if len(strategy_name) > 3 else strategy_name
    short_symbol = symbol[:6]  # 大多數交易對的基本貨幣部分
    side_char = "B" if side == "BUY" else "S"  # 使用單字符表示方向
    
    # 只保留時間戳的後4位數字
    timestamp_short = timestamp % 10000
    
    client_order_id = f"{short_strategy}_{short_symbol}_{side_char}{timestamp_short}_{counter}"
    
    # 確保ID不超過30個字符(為止盈後綴預留空間)
    if len(client_order_id) > 30:
        # 進一步縮短ID
        short_strategy = short_strategy[:2]
        short_symbol = symbol[:4]
        client_order_id = f"{short_strategy}_{short_symbol}_{side_char}{timestamp_short}_{counter}"
    
    return client_order_id

def validate_signal_data(data):
    """
    驗證交易信號數據的完整性
    
    Args:
        data: 信號數據字典
        
    Returns:
        tuple: (是否有效, 錯誤訊息)
    """
    if not data:
        return False, "無效的數據"
    
    required_fields = ['symbol', 'side']
    for field in required_fields:
        if field not in data:
            return False, f"缺少必要字段: {field}"
    
    # 檢查交易方向
    side = data.get('side', '').upper()
    if side not in ['BUY', 'SELL']:
        return False, "無效的交易方向，必須是'BUY'或'SELL'"
    
    # 檢查價格數據
    open_price = data.get('open')
    close_price = data.get('close')
    if not open_price or not close_price:
        return False, "缺少開盤價或收盤價"
    
    return True, "數據有效"

def format_order_summary(order_info):
    """
    格式化訂單摘要信息用於日誌輸出
    
    Args:
        order_info: 訂單信息字典
        
    Returns:
        str: 格式化的訂單摘要
    """
    symbol = order_info.get('symbol', 'Unknown')
    side = order_info.get('side', 'Unknown')
    quantity = order_info.get('quantity', 'Unknown')
    price = order_info.get('price', 'Unknown')
    status = order_info.get('status', 'Unknown')
    
    return f"{symbol} {side} {quantity}@{price} [{status}]"

def calculate_price_with_precision(price, symbol):
    """
    根據交易對精度計算價格
    
    Args:
        price: 原始價格
        symbol: 交易對
        
    Returns:
        float: 調整精度後的價格
    """
    precision = get_symbol_precision(symbol)
    return round(float(price), precision)

def get_entry_mode_name(opposite):
    """
    獲取開倉模式的中文名稱
    
    Args:
        opposite: 開倉模式代碼
        
    Returns:
        str: 開倉模式名稱
    """
    entry_mode_names = {
        0: "當前收盤價",
        1: "前根收盤價", 
        2: "前根開盤價"
    }
    return entry_mode_names.get(opposite, f"未知模式{opposite}")

def safe_float_conversion(value, default=0.0):
    """
    安全的浮點數轉換
    
    Args:
        value: 要轉換的值
        default: 轉換失敗時的默認值
        
    Returns:
        float: 轉換後的浮點數
    """
    try:
        return float(value) if value is not None else default
    except (ValueError, TypeError):
        return default

def safe_int_conversion(value, default=0):
    """
    安全的整數轉換
    
    Args:
        value: 要轉換的值
        default: 轉換失敗時的默認值
        
    Returns:
        int: 轉換後的整數
    """
    try:
        return int(value) if value is not None else default
    except (ValueError, TypeError):
        return default

def format_time_for_log():
    """
    格式化當前台灣時間用於日誌
    
    Returns:
        str: 格式化的時間字符串
    """
    tw_now = datetime.now(TW_TIMEZONE)
    return tw_now.strftime('%Y-%m-%d %H:%M:%S')

def truncate_string_for_log(text, max_length=100):
    """
    截斷字符串用於日誌輸出
    
    Args:
        text: 要截斷的字符串
        max_length: 最大長度
        
    Returns:
        str: 截斷後的字符串
    """
    if len(str(text)) <= max_length:
        return str(text)
    return str(text)[:max_length] + "..."

def calculate_percentage_change(old_value, new_value):
    """
    計算百分比變化
    
    Args:
        old_value: 舊值
        new_value: 新值
        
    Returns:
        float: 百分比變化
    """
    try:
        old_val = float(old_value)
        new_val = float(new_value)
        if old_val == 0:
            return 0.0
        return ((new_val - old_val) / old_val) * 100
    except (ValueError, TypeError, ZeroDivisionError):
        return 0.0

def format_currency(amount, precision=4):
    """
    格式化貨幣數字
    
    Args:
        amount: 金額
        precision: 小數位數
        
    Returns:
        str: 格式化的金額字符串
    """
    try:
        return f"{float(amount):.{precision}f}"
    except (ValueError, TypeError):
        return "0.0000"

def validate_order_params(symbol, side, quantity, price=None):
    """
    驗證訂單參數
    
    Args:
        symbol: 交易對
        side: 方向
        quantity: 數量
        price: 價格（可選）
        
    Returns:
        tuple: (是否有效, 錯誤訊息)
    """
    # 檢查必要參數
    if not symbol or not side or not quantity:
        return False, "缺少必要的訂單參數"
    
    # 檢查交易方向
    if side.upper() not in ['BUY', 'SELL']:
        return False, "無效的交易方向"
    
    # 檢查數量
    try:
        qty = float(quantity)
        if qty <= 0:
            return False, "訂單數量必須大於0"
    except (ValueError, TypeError):
        return False, "無效的訂單數量"
    
    # 檢查價格（如果提供）
    if price is not None:
        try:
            p = float(price)
            if p <= 0:
                return False, "訂單價格必須大於0"
        except (ValueError, TypeError):
            return False, "無效的訂單價格"
    
    return True, "訂單參數有效"

def calculate_order_value(quantity, price):
    """
    計算訂單價值
    
    Args:
        quantity: 數量
        price: 價格
        
    Returns:
        float: 訂單價值
    """
    try:
        return float(quantity) * float(price)
    except (ValueError, TypeError):
        return 0.0

def get_current_timestamp():
    """
    獲取當前時間戳（毫秒）
    
    Returns:
        int: 當前時間戳
    """
    return int(time.time() * 1000)

def parse_timeframe(timeframe_str):
    """
    解析時間框架字符串
    
    Args:
        timeframe_str: 時間框架字符串 (如 "1m", "5m", "1h")
        
    Returns:
        int: 時間框架的秒數
    """
    timeframe_map = {
        '1m': 60,
        '3m': 180,
        '5m': 300,
        '15m': 900,
        '30m': 1800,
        '1h': 3600,
        '2h': 7200,
        '4h': 14400,
        '6h': 21600,
        '8h': 28800,
        '12h': 43200,
        '1d': 86400
    }
    
    return timeframe_map.get(timeframe_str.lower(), 300)  # 默認5分鐘

def format_large_number(number):
    """
    格式化大數字（添加千分位分隔符）
    
    Args:
        number: 要格式化的數字
        
    Returns:
        str: 格式化後的數字字符串
    """
    try:
        return f"{float(number):,.2f}"
    except (ValueError, TypeError):
        return "0.00"

def is_valid_symbol(symbol):
    """
    檢查是否為有效的交易對符號
    
    Args:
        symbol: 交易對符號
        
    Returns:
        bool: 是否有效
    """
    if not symbol or not isinstance(symbol, str):
        return False
    
    # 基本檢查：長度和字符
    symbol = symbol.upper()
    if len(symbol) < 6 or len(symbol) > 12:
        return False
    
    # 檢查是否只包含字母和數字
    if not symbol.replace('USDT', '').replace('USDC', '').replace('BTC', '').replace('ETH', '').isalpha():
        return False
    
    return True
