# Changelog

All notable changes to the 69交易機器人系統 will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [v2.5.0] - 2025-07-08 🔥 

### 🚨 **CRITICAL SECURITY FIX**

#### **🛡️ 解決止盈/止損單關聯管理風險**
- **🔥 修復核心風險**: 止盈單成交後，對應止損單未自動取消的嚴重風險
- **💡 智能解決方案**: 新增WebSocket訂單關聯自動處理機制
- **⚡ 零停機修復**: 僅修改WebSocket處理邏輯，不影響現有功能
- **🎯 精準識別**: 基於訂單ID命名規律的智能配對取消系統

```python
# 修復邏輯
止盈單成交 → 自動取消對應止損單
止損單成交 → 自動取消對應止盈單  
防止遺留訂單 → 消除意外開倉風險
```

#### **🔧 實施細節**
- **檔案修改**: `api/websocket_handler.py` (Phase 1精準修復)
- **新增功能**: `_handle_tp_sl_completion()` - 智能關聯處理
- **安全機制**: `_cancel_order_safe()` - 防錯容錯取消邏輯
- **向後相容**: 100%保持現有功能，零破壞性變更

### 📊 **系統狀態優化**

#### **🧹 數據庫清理與優化**  
- **精準清理**: 保留6筆真實交易記錄，清除55筆測試數據
- **數據質量**: 確保ML學習基於真實多樣化的交易樣本
- **策略覆蓋**: 保留consolidation_buy、breakdown_sell、reversal_sell等策略記錄

```sql
-- 保留的真實數據分布
├── consolidation_buy (3筆, opposite=2