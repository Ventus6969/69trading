#!/usr/bin/env python3
"""
ML狀態監控程式
用於查看69交易機器人的ML系統當前狀態並檢測異常情況
"""

import os
import sys
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List, Any, Tuple
import json
from tabulate import tabulate

# 添加專案根目錄到Python路徑
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

from database.ml_data_manager import MLDataManager, create_ml_data_manager
from database import get_database_path
from shadow_decision_engine import shadow_decision_engine, ML_AVAILABLE
from utils.logger_config import get_logger

logger = get_logger(__name__)

class MLStatusMonitor:
    """ML狀態監控器"""
    
    def __init__(self):
        db_path = get_database_path()
        self.ml_manager = create_ml_data_manager(db_path)
        
    def display_ml_overview(self):
        """顯示ML系統總覽"""
        print("=" * 60)
        print("🤖 69交易機器人 ML系統狀態監控")
        print("=" * 60)
        
        # ML可用性狀態
        ml_status = "✅ 啟用" if ML_AVAILABLE else "❌ 未啟用"
        print(f"ML系統狀態: {ml_status}")
        
        # 獲取基本統計
        stats = self.ml_manager.get_ml_table_stats()
        
        print(f"\n📊 數據統計:")
        print(f"  • ML特徵記錄: {stats.get('total_ml_features', 0):,} 筆")
        print(f"  • ML決策記錄: {stats.get('total_ml_decisions', 0):,} 筆") 
        print(f"  • 價格優化記錄: {stats.get('total_price_optimizations', 0):,} 筆")
        
    def display_feature_statistics(self):
        """顯示特徵統計"""
        print("\n" + "=" * 60)
        print("📈 ML特徵統計")
        print("=" * 60)
        
        feature_stats = self.ml_manager.get_feature_statistics()
        
        if feature_stats:
            print(f"總特徵數量: {feature_stats.get('total_features', 0):,}")
            print(f"平均勝率: {feature_stats.get('avg_win_rate', 0):.2%}")
            print(f"平均風險回報比: {feature_stats.get('avg_risk_reward', 0):.2f}")
            print(f"平均信心分數: {feature_stats.get('avg_confidence', 0):.2f}")
        else:
            print("暫無特徵統計數據")
    
    def display_recent_decisions(self, limit: int = 10):
        """顯示最近的ML決策"""
        print("\n" + "=" * 60)
        print(f"🎯 最近 {limit} 筆ML決策")
        print("=" * 60)
        
        decisions = self.ml_manager.get_recent_ml_decisions(limit)
        
        if not decisions:
            print("暫無ML決策記錄")
            return
            
        # 準備表格數據
        table_data = []
        headers = ["時間", "交易對", "策略", "方向", "專家信心", "ML信心", "最終決策"]
        
        for decision in decisions:
            created_at = decision.get('created_at', '')
            if created_at:
                # 轉換時間格式
                try:
                    dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                    time_str = dt.strftime('%m-%d %H:%M')
                except:
                    time_str = created_at[:16]
            else:
                time_str = "N/A"
                
            symbol = decision.get('symbol', 'N/A')
            signal_type = decision.get('signal_type', 'N/A')
            side = decision.get('side', 'N/A')
            expert_confidence = f"{decision.get('expert_confidence', 0):.2f}"
            ml_confidence = f"{decision.get('ml_confidence', 0):.2f}"
            final_decision = "執行" if decision.get('final_decision') else "跳過"
            
            table_data.append([
                time_str, symbol, signal_type, side, 
                expert_confidence, ml_confidence, final_decision
            ])
        
        print(tabulate(table_data, headers=headers, tablefmt="grid"))
    
    def check_data_integrity(self) -> List[Dict[str, Any]]:
        """檢查數據完整性"""
        issues = []
        
        try:
            with sqlite3.connect(self.ml_manager.db_path) as conn:
                cursor = conn.cursor()
                
                # 1. 檢查NULL值數量
                cursor.execute('''
                    SELECT 
                        COUNT(*) as total_records,
                        SUM(CASE WHEN strategy_win_rate_recent IS NULL THEN 1 ELSE 0 END) as null_win_rate,
                        SUM(CASE WHEN signal_confidence_score IS NULL THEN 1 ELSE 0 END) as null_confidence,
                        SUM(CASE WHEN risk_reward_ratio IS NULL THEN 1 ELSE 0 END) as null_risk_reward,
                        SUM(CASE WHEN session_id IS NULL OR session_id = '' THEN 1 ELSE 0 END) as null_session_id
                    FROM ml_features_v2
                ''')
                
                result = cursor.fetchone()
                if result and result[0] > 0:
                    total, null_win_rate, null_confidence, null_risk_reward, null_session = result
                    
                    if null_win_rate > 0:
                        issues.append({
                            'type': 'NULL_VALUES',
                            'table': 'ml_features_v2',
                            'field': 'strategy_win_rate_recent',
                            'count': null_win_rate,
                            'severity': 'MEDIUM',
                            'description': f'{null_win_rate}/{total} 記錄的勝率為空值'
                        })
                    
                    if null_confidence > 0:
                        issues.append({
                            'type': 'NULL_VALUES',
                            'table': 'ml_features_v2', 
                            'field': 'signal_confidence_score',
                            'count': null_confidence,
                            'severity': 'HIGH',
                            'description': f'{null_confidence}/{total} 記錄的信心分數為空值'
                        })
                    
                    if null_session > 0:
                        issues.append({
                            'type': 'NULL_VALUES',
                            'table': 'ml_features_v2',
                            'field': 'session_id', 
                            'count': null_session,
                            'severity': 'HIGH',
                            'description': f'{null_session}/{total} 記錄的session_id為空值'
                        })
                
                # 2. 檢查異常數值範圍
                cursor.execute('''
                    SELECT COUNT(*) FROM ml_features_v2 
                    WHERE strategy_win_rate_recent < 0 OR strategy_win_rate_recent > 1
                ''')
                invalid_win_rate = cursor.fetchone()[0]
                if invalid_win_rate > 0:
                    issues.append({
                        'type': 'INVALID_RANGE',
                        'table': 'ml_features_v2',
                        'field': 'strategy_win_rate_recent',
                        'count': invalid_win_rate,
                        'severity': 'HIGH',
                        'description': f'{invalid_win_rate} 記錄的勝率超出有效範圍 [0,1]'
                    })
                
                # 3. 檢查孤立記錄 (有特徵但無決策)
                cursor.execute('''
                    SELECT COUNT(*) FROM ml_features_v2 f
                    LEFT JOIN ml_signal_quality q ON f.signal_id = q.signal_id
                    WHERE q.id IS NULL AND f.signal_id IS NOT NULL
                ''')
                orphaned_features = cursor.fetchone()[0]
                if orphaned_features > 0:
                    issues.append({
                        'type': 'ORPHANED_RECORD',
                        'table': 'ml_features_v2',
                        'field': 'signal_id',
                        'count': orphaned_features,
                        'severity': 'MEDIUM',
                        'description': f'{orphaned_features} 特徵記錄沒有對應的決策記錄'
                    })
                
                # 4. 檢查最近記錄時間
                cursor.execute('SELECT MAX(created_at) FROM ml_features_v2')
                last_feature_time = cursor.fetchone()[0]
                if last_feature_time:
                    try:
                        last_dt = datetime.fromisoformat(last_feature_time.replace('Z', '+00:00'))
                        time_diff = datetime.now() - last_dt
                        if time_diff.total_seconds() > 86400:  # 24小時
                            issues.append({
                                'type': 'STALE_DATA',
                                'table': 'ml_features_v2',
                                'field': 'created_at',
                                'count': 1,
                                'severity': 'MEDIUM',
                                'description': f'最後特徵記錄時間: {last_feature_time} (超過24小時)'
                            })
                    except:
                        pass
                
        except Exception as e:
            issues.append({
                'type': 'DATABASE_ERROR',
                'table': 'unknown',
                'field': 'unknown',
                'count': 0,
                'severity': 'HIGH',
                'description': f'檢查數據完整性時出錯: {str(e)}'
            })
        
        return issues
    
    def check_ml_training_data_quality(self) -> Dict[str, Any]:
        """檢查ML訓練數據品質"""
        result = {
            'total_features': 0,
            'total_decisions': 0,
            'complete_training_pairs': 0,
            'training_ready_records': 0,
            'issues': []
        }
        
        try:
            with sqlite3.connect(self.ml_manager.db_path) as conn:
                cursor = conn.cursor()
                
                # 1. 檢查完整的訓練數據對 (特徵+決策+交易結果)
                cursor.execute('''
                    SELECT 
                        COUNT(*) as complete_pairs
                    FROM ml_features_v2 f
                    INNER JOIN ml_signal_quality q ON f.signal_id = q.signal_id
                    INNER JOIN orders_executed oe ON f.signal_id = oe.signal_id
                    INNER JOIN trading_results tr ON oe.id = tr.order_id
                    WHERE f.signal_id IS NOT NULL
                ''')
                
                complete_pairs = cursor.fetchone()[0]
                result['complete_training_pairs'] = complete_pairs
                
                # 2. 檢查特徵+決策對 (即使沒有交易結果)
                cursor.execute('''
                    SELECT COUNT(*) 
                    FROM ml_features_v2 f
                    INNER JOIN ml_signal_quality q ON f.signal_id = q.signal_id
                    WHERE f.signal_id IS NOT NULL
                ''')
                
                feature_decision_pairs = cursor.fetchone()[0]
                result['feature_decision_pairs'] = feature_decision_pairs
                
                # 3. 檢查缺失交易結果的記錄
                cursor.execute('''
                    SELECT COUNT(*) 
                    FROM ml_features_v2 f
                    INNER JOIN ml_signal_quality q ON f.signal_id = q.signal_id
                    INNER JOIN orders_executed oe ON f.signal_id = oe.signal_id
                    LEFT JOIN trading_results tr ON oe.id = tr.order_id
                    WHERE f.signal_id IS NOT NULL AND tr.id IS NULL
                ''')
                
                missing_results = cursor.fetchone()[0]
                result['missing_trading_results'] = missing_results
                
                # 4. 統計各策略的可用訓練數據
                cursor.execute('''
                    SELECT 
                        sr.signal_type,
                        COUNT(*) as count
                    FROM ml_features_v2 f
                    INNER JOIN ml_signal_quality q ON f.signal_id = q.signal_id
                    INNER JOIN signals_received sr ON f.signal_id = sr.id
                    INNER JOIN orders_executed oe ON f.signal_id = oe.signal_id
                    INNER JOIN trading_results tr ON oe.id = tr.order_id
                    GROUP BY sr.signal_type
                    ORDER BY count DESC
                ''')
                
                strategy_stats = {}
                for row in cursor.fetchall():
                    strategy_stats[row[0]] = row[1]
                result['strategy_training_data'] = strategy_stats
                
                # 5. 分析數據品質問題
                if complete_pairs < 10:
                    result['issues'].append({
                        'type': 'INSUFFICIENT_TRAINING_DATA',
                        'severity': 'HIGH',
                        'description': f'完整訓練數據不足: {complete_pairs}/50 (需要至少50筆)'
                    })
                
                if missing_results > 0:
                    result['issues'].append({
                        'type': 'MISSING_TRADING_RESULTS', 
                        'severity': 'MEDIUM',
                        'description': f'{missing_results} 筆交易缺少最終結果記錄 (可能是手動操作)'
                    })
                
                # 6. 檢查特徵完整性
                cursor.execute('''
                    SELECT COUNT(*) FROM ml_features_v2
                    WHERE strategy_win_rate_recent = 0 
                    AND signal_confidence_score = 0
                    AND risk_reward_ratio = 0
                ''')
                
                zero_features = cursor.fetchone()[0]
                if zero_features > 0:
                    result['issues'].append({
                        'type': 'ZERO_VALUE_FEATURES',
                        'severity': 'MEDIUM', 
                        'description': f'{zero_features} 筆記錄的關鍵特徵值為0 (可能是計算失敗)'
                    })
                
                result['training_ready_records'] = complete_pairs
                
        except Exception as e:
            result['issues'].append({
                'type': 'ANALYSIS_ERROR',
                'severity': 'HIGH',
                'description': f'ML訓練數據檢查出錯: {str(e)}'
            })
        
        return result
    
    def check_ml_anomalies(self) -> List[Dict[str, Any]]:
        """檢查ML系統異常"""
        anomalies = []
        
        try:
            with sqlite3.connect(self.ml_manager.db_path) as conn:
                cursor = conn.cursor()
                
                # 1. 檢查決策一致性 (使用現有欄位)
                cursor.execute('''
                    SELECT 
                        COUNT(*) as total,
                        AVG(confidence_score) as avg_confidence
                    FROM ml_signal_quality 
                    WHERE confidence_score IS NOT NULL
                    AND created_at > datetime('now', '-7 days')
                ''')
                
                result = cursor.fetchone()
                if result and result[0] > 0:
                    avg_confidence = result[1] or 0
                    if avg_confidence < 0.2:  # 平均信心分數過低
                        anomalies.append({
                            'type': 'LOW_CONFIDENCE',
                            'severity': 'MEDIUM', 
                            'value': avg_confidence,
                            'description': f'最近7天平均信心分數過低: {avg_confidence:.3f}'
                        })
                
                # 2. 檢查勝率異常
                cursor.execute('''
                    SELECT AVG(strategy_win_rate_recent) 
                    FROM ml_features_v2 
                    WHERE created_at > datetime('now', '-7 days')
                    AND strategy_win_rate_recent IS NOT NULL
                ''')
                
                result = cursor.fetchone()
                if result and result[0] is not None:
                    avg_win_rate = result[0]
                    if avg_win_rate < 0.3:  # 勝率低於30%
                        anomalies.append({
                            'type': 'LOW_WIN_RATE',
                            'severity': 'HIGH',
                            'value': avg_win_rate,
                            'description': f'最近7天平均勝率過低: {avg_win_rate:.2%}'
                        })
                
                # 3. 檢查決策頻率異常
                cursor.execute('''
                    SELECT COUNT(*) FROM ml_signal_quality
                    WHERE created_at > datetime('now', '-24 hours')
                ''')
                
                decisions_24h = cursor.fetchone()[0]
                if decisions_24h == 0:
                    anomalies.append({
                        'type': 'NO_RECENT_DECISIONS',
                        'severity': 'HIGH',
                        'value': 0,
                        'description': '過去24小時內沒有ML決策記錄'
                    })
                elif decisions_24h > 100:  # 異常高頻
                    anomalies.append({
                        'type': 'HIGH_FREQUENCY_DECISIONS',
                        'severity': 'MEDIUM',
                        'value': decisions_24h,
                        'description': f'過去24小時決策頻率異常高: {decisions_24h} 次'
                    })
                
                # 4. 檢查特徵值分佈異常
                cursor.execute('''
                    SELECT 
                        AVG(signal_confidence_score) as avg_confidence,
                        MIN(signal_confidence_score) as min_confidence,
                        MAX(signal_confidence_score) as max_confidence
                    FROM ml_features_v2 
                    WHERE created_at > datetime('now', '-7 days')
                    AND signal_confidence_score IS NOT NULL
                ''')
                
                result = cursor.fetchone()
                if result:
                    avg_conf, min_conf, max_conf = result
                    if avg_conf and min_conf and max_conf:
                        if max_conf - min_conf < 0.1:  # 變異性太小
                            anomalies.append({
                                'type': 'LOW_FEATURE_VARIANCE',
                                'severity': 'MEDIUM', 
                                'value': max_conf - min_conf,
                                'description': f'信心分數變異性過低: 範圍 {min_conf:.3f} - {max_conf:.3f}'
                            })
                
        except Exception as e:
            anomalies.append({
                'type': 'ANALYSIS_ERROR',
                'severity': 'HIGH',
                'value': 0,
                'description': f'ML異常檢查時出錯: {str(e)}'
            })
        
        return anomalies
    
    def display_ml_training_data_analysis(self):
        """顯示ML訓練數據分析"""
        print("\n" + "=" * 60)
        print("🎯 ML訓練數據品質分析")
        print("=" * 60)
        
        analysis = self.check_ml_training_data_quality()
        
        print(f"📊 訓練數據統計:")
        print(f"  • 完整訓練數據對: {analysis['complete_training_pairs']} 筆")
        print(f"  • 特徵+決策配對: {analysis['feature_decision_pairs']} 筆") 
        print(f"  • 缺失交易結果: {analysis['missing_trading_results']} 筆")
        
        # 顯示各策略的訓練數據
        if analysis.get('strategy_training_data'):
            print(f"\n📈 各策略完整訓練數據:")
            for strategy, count in analysis['strategy_training_data'].items():
                print(f"  • {strategy}: {count} 筆")
        else:
            print(f"\n📈 各策略完整訓練數據: 暫無")
        
        # 顯示進度
        progress = analysis['complete_training_pairs']
        target = 50
        progress_pct = (progress / target * 100) if target > 0 else 0
        print(f"\n🎯 ML啟用進度: {progress}/{target} 筆 ({progress_pct:.1f}%)")
        
        # 顯示問題
        if analysis['issues']:
            print(f"\n⚠️ 訓練數據問題:")
            for issue in analysis['issues']:
                severity_icon = "🚨" if issue['severity'] == 'HIGH' else "🟡"
                print(f"  {severity_icon} {issue['description']}")
        else:
            print(f"\n✅ 訓練數據品質良好")
    
    def display_missing_trading_results_details(self):
        """顯示缺失交易結果的詳細信息"""
        print("\n" + "=" * 60)
        print("🔍 缺失交易結果詳細分析")
        print("=" * 60)
        
        try:
            with sqlite3.connect(self.ml_manager.db_path) as conn:
                cursor = conn.cursor()
                
                # 查找有決策但缺失交易結果的記錄
                cursor.execute('''
                    SELECT 
                        sr.id as signal_id,
                        sr.symbol,
                        sr.signal_type,
                        sr.side,
                        sr.timestamp,
                        oe.client_order_id,
                        oe.binance_order_id,
                        oe.price as entry_price,
                        oe.quantity,
                        oe.tp_price,
                        oe.sl_price,
                        oe.status,
                        datetime(sr.timestamp, 'unixepoch') as signal_time,
                        datetime(oe.execution_timestamp, 'unixepoch') as execution_time
                    FROM ml_features_v2 f
                    INNER JOIN ml_signal_quality q ON f.signal_id = q.signal_id
                    INNER JOIN signals_received sr ON f.signal_id = sr.id
                    INNER JOIN orders_executed oe ON f.signal_id = oe.signal_id
                    LEFT JOIN trading_results tr ON oe.id = tr.order_id
                    WHERE f.signal_id IS NOT NULL AND tr.id IS NULL
                    ORDER BY sr.timestamp DESC
                ''')
                
                missing_orders = cursor.fetchall()
                
                if not missing_orders:
                    print("✅ 沒有發現缺失交易結果的訂單")
                    return
                
                print(f"發現 {len(missing_orders)} 筆缺失交易結果的訂單：\n")
                
                headers = ["信號時間", "交易對", "策略", "方向", "客戶訂單ID", "幣安訂單ID", "開倉價", "數量", "止盈價", "狀態"]
                table_data = []
                
                for order in missing_orders:
                    signal_id, symbol, signal_type, side, timestamp, client_order_id, binance_order_id, entry_price, quantity, tp_price, sl_price, status, signal_time, execution_time = order
                    
                    table_data.append([
                        signal_time[:16] if signal_time else "N/A",
                        symbol or "N/A",
                        signal_type or "N/A", 
                        side or "N/A",
                        client_order_id or "N/A",
                        str(binance_order_id) if binance_order_id else "N/A",
                        f"{entry_price:.6f}" if entry_price else "N/A",
                        f"{quantity:.4f}" if quantity else "N/A",
                        f"{tp_price:.6f}" if tp_price else "N/A",
                        status or "N/A"
                    ])
                
                print(tabulate(table_data, headers=headers, tablefmt="grid"))
                
                # 提供恢復建議
                print(f"\n💡 數據恢復建議:")
                print(f"1. 檢查以下客戶訂單ID的交易記錄:")
                for order in missing_orders:
                    client_order_id = order[5]
                    binance_order_id = order[6]
                    if client_order_id:
                        print(f"   • 客戶訂單ID: {client_order_id}")
                    if binance_order_id:
                        print(f"     幣安訂單ID: {binance_order_id}")
                
                print(f"\n2. 可以使用以下方法恢復數據:")
                print(f"   • 從交易所API查詢訂單最終狀態")
                print(f"   • 檢查系統日誌文件")
                print(f"   • 手動調用 record_trading_result_by_client_id() 補充結果")
                
                # 顯示SQL恢復模板
                print(f"\n3. 手動恢復SQL模板:")
                print(f"   如果知道交易結果，可以直接插入 trading_results 表")
                
        except Exception as e:
            print(f"❌ 查詢缺失交易結果時出錯: {e}")

    def display_data_health_check(self):
        """顯示數據健康檢查結果"""
        print("\n" + "=" * 60)
        print("🔍 ML數據健康檢查")
        print("=" * 60)
        
        # 檢查數據完整性
        integrity_issues = self.check_data_integrity()
        
        # 檢查ML異常
        ml_anomalies = self.check_ml_anomalies()
        
        # 合併所有問題
        all_issues = integrity_issues + ml_anomalies
        
        if not all_issues:
            print("✅ 數據健康狀況良好，未發現異常")
            return
        
        # 按嚴重程度分類
        high_issues = [i for i in all_issues if i.get('severity') == 'HIGH']
        medium_issues = [i for i in all_issues if i.get('severity') == 'MEDIUM']
        
        if high_issues:
            print("🚨 高嚴重度問題:")
            for issue in high_issues:
                print(f"  ❌ {issue['description']}")
        
        if medium_issues:
            print("\n⚠️  中等嚴重度問題:")
            for issue in medium_issues:
                print(f"  🟡 {issue['description']}")
        
        # 顯示統計
        print(f"\n📋 問題統計: 高嚴重度 {len(high_issues)} 個，中嚴重度 {len(medium_issues)} 個")
    
    def display_database_info(self):
        """顯示資料庫信息"""
        print("\n" + "=" * 60)
        print("💾 資料庫信息")
        print("=" * 60)
        
        db_path = self.ml_manager.db_path
        print(f"資料庫路徑: {db_path}")
        
        if os.path.exists(db_path):
            # 獲取文件大小
            size_mb = os.path.getsize(db_path) / (1024 * 1024)
            print(f"資料庫大小: {size_mb:.2f} MB")
            
            # 獲取修改時間
            mtime = os.path.getmtime(db_path)
            mtime_str = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')
            print(f"最後修改: {mtime_str}")
            
            # 檢查表格結構
            try:
                with sqlite3.connect(db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                    tables = [row[0] for row in cursor.fetchall()]
                    print(f"資料表數量: {len(tables)}")
                    print(f"主要表格: {', '.join(tables[:5])}")
            except Exception as e:
                print(f"無法讀取表格信息: {e}")
        else:
            print("❌ 資料庫文件不存在")
    
    def display_shadow_engine_status(self):
        """顯示影子決策引擎狀態"""
        print("\n" + "=" * 60)
        print("👤 影子決策引擎狀態")
        print("=" * 60)
        
        try:
            # 檢查引擎是否可用
            if shadow_decision_engine:
                print("✅ 影子決策引擎已初始化")
                
                # 獲取策略配置
                if hasattr(shadow_decision_engine, 'strategy_configs'):
                    configs = shadow_decision_engine.strategy_configs
                    print(f"已配置策略: {len(configs)} 個")
                    
                    # 顯示部分策略配置
                    for strategy, config in list(configs.items())[:3]:
                        confidence = config.get('default_confidence', 0)
                        note = config.get('note', '')
                        print(f"  • {strategy}: 信心度 {confidence:.2f} - {note}")
                        
                    if len(configs) > 3:
                        print(f"  ... 還有 {len(configs) - 3} 個策略")
                        
            else:
                print("❌ 影子決策引擎未初始化")
                
        except Exception as e:
            print(f"❌ 檢查影子決策引擎時出錯: {e}")
    
    def run_full_status_check(self):
        """執行完整狀態檢查"""
        try:
            self.display_ml_overview()
            self.display_feature_statistics() 
            self.display_recent_decisions()
            self.display_ml_training_data_analysis()  # 新增ML訓練數據分析
            self.display_data_health_check()  # 新增健康檢查
            self.display_shadow_engine_status()
            self.display_database_info()
            
            print("\n" + "=" * 60)
            print("✅ ML狀態檢查完成")
            print("=" * 60)
            
        except Exception as e:
            logger.error(f"執行狀態檢查時出錯: {e}")
            print(f"❌ 狀態檢查出錯: {e}")

def main():
    """主程式"""
    import argparse
    
    parser = argparse.ArgumentParser(description='69交易機器人 ML狀態監控')
    parser.add_argument('--recent', '-r', type=int, default=10, 
                       help='顯示最近N筆ML決策 (預設: 10)')
    parser.add_argument('--overview', '-o', action='store_true', 
                       help='只顯示總覽')
    parser.add_argument('--stats', '-s', action='store_true',
                       help='只顯示統計')
    parser.add_argument('--health', '--check', action='store_true',
                       help='只執行健康檢查')
    parser.add_argument('--training', '-t', action='store_true',
                       help='只顯示ML訓練數據分析')
    parser.add_argument('--missing', '-m', action='store_true',
                       help='顯示缺失交易結果的詳細信息')
    
    args = parser.parse_args()
    
    monitor = MLStatusMonitor()
    
    try:
        if args.overview:
            monitor.display_ml_overview()
        elif args.stats:
            monitor.display_feature_statistics()
        elif args.health:
            monitor.display_data_health_check()
        elif args.training:
            monitor.display_ml_training_data_analysis()
        elif args.missing:
            monitor.display_missing_trading_results_details()
        else:
            # 預設執行完整檢查
            monitor.run_full_status_check()
            
    except KeyboardInterrupt:
        print("\n👋 程式已中斷")
    except Exception as e:
        print(f"❌ 程式執行出錯: {e}")
        logger.error(f"ML狀態監控程式出錯: {e}")

if __name__ == "__main__":
    main()