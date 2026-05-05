"""
台股成交量前十大公司爬蟲 - 使用 STOCK_DAY_ALL API (穩定版本)
這個 API 回傳全市場當日成交資料，直接解析取得成交量前十名
支援：ETF、受益憑證、特別股等所有交易標的
"""

import requests
import json
import os
import sys
from datetime import datetime, timedelta
from typing import List, Dict, Tuple
import logging

# ========== 設定區 ==========
DATA_DIR = "data"
HISTORY_DIR = os.path.join(DATA_DIR, "history")
LATEST_FILE = os.path.join(DATA_DIR, "latest.json")

# 證交所穩定 API：每日收盤行情 (全市場)
# 回傳所有股票的當日成交資料
STOCK_DAY_ALL_API = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"

# 設定 log
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_all_stocks_volume() -> Tuple[List[Dict], str]:
    """
    從 STOCK_DAY_ALL API 取得全市場股票當日成交量
    回傳: (成交量排序後的前10大列表, 日期字串)
    """
    try:
        # 發送請求
        logger.info(f"正在呼叫 API: {STOCK_DAY_ALL_API}")
        response = requests.get(STOCK_DAY_ALL_API, timeout=30)
        
        # 檢查 HTTP 狀態碼
        if response.status_code != 200:
            logger.error(f"API 回應錯誤: HTTP {response.status_code}")
            return [], ""
        
        # 檢查內容是否為空
        if not response.text or response.text.strip() == "":
            logger.warning("API 回傳空內容")
            return [], ""
        
        # 解析 JSON
        try:
            data = response.json()
        except Exception as e:
            logger.error(f"JSON 解析失敗: {e}")
            logger.error(f"回傳內容前200字: {response.text[:200]}")
            return [], ""
        
        # 檢查資料格式
        if not isinstance(data, list):
            logger.error(f"API 回傳格式錯誤，型別為: {type(data)}")
            return [], ""
        
        if len(data) == 0:
            logger.warning("API 回傳空陣列，今日可能無交易資料")
            return [], ""
        
        logger.info(f"成功取得 {len(data)} 檔股票資料")
        
        # 解析每檔股票的成交量
        volume_list = []
        for item in data:
            # 取得股票代碼和名稱
            code = item.get("Code", "")
            name = item.get("Name", "")
            
            # 過濾條件：放寬規則，包含所有股票、ETF、受益憑證
            if not code or not code.strip():
                continue
            
            # 代碼長度為 4-6 位字元（允許字母，如 00981A）
            code_clean = code.strip()
            if len(code_clean) < 4 or len(code_clean) > 6:
                continue
            
            # 排除空白名稱
            if not name or name.strip() == "":
                continue
            
            # 取得成交量 (TradeVolume 欄位)
            volume_str = item.get("TradeVolume", "0")
            if isinstance(volume_str, str):
                volume_str = volume_str.replace(",", "").strip()
            
            try:
                volume = int(volume_str) if volume_str else 0
            except ValueError:
                volume = 0
            
            # 只保留成交量 > 0 的標的
            if volume > 0:
                volume_list.append({
                    "code": code_clean,
                    "name": name.strip(),
                    "volume": volume
                })
        
        logger.info(f"過濾後有效資料: {len(volume_list)} 筆 (成交量 > 0)")
        
        # 依成交量降冪排序
        volume_list.sort(key=lambda x: x["volume"], reverse=True)
        
        # 取前 10 名
        top10 = []
        for idx, item in enumerate(volume_list[:10]):
            top10.append({
                "rank": idx + 1,
                "code": item["code"],
                "name": item["name"],
                "volume": item["volume"]
            })
        
        # 取得資料日期
        date_str = datetime.now().strftime("%Y%m%d")
        
        # 顯示前10名
        logger.info("=" * 40)
        logger.info("📊 成交量前十大公司:")
        for item in top10:
            vol_display = f"{item['volume']:,}"
            logger.info(f"  {item['rank']}. {item['code']} {item['name']} - {vol_display} 股")
        logger.info("=" * 40)
        
        return top10, date_str
        
    except requests.exceptions.Timeout:
        logger.error("API 請求超時")
        return [], ""
    except requests.exceptions.ConnectionError:
        logger.error("網路連線錯誤")
        return [], ""
    except Exception as e:
        logger.error(f"取得資料失敗: {e}")
        return [], ""


def save_top10_to_file(top10_data: List[Dict], date_str: str):
    """儲存資料到 JSON 檔案"""
    # 確保目錄存在
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(HISTORY_DIR, exist_ok=True)
    
    output = {
        "date": date_str,
        "update_time": datetime.now().isoformat(),
        "top10": top10_data,
        "total_stocks": len(top10_data)
    }
    
    # 儲存最新檔案
    with open(LATEST_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    # 儲存歷史備份
    history_file = os.path.join(HISTORY_DIR, f"{date_str}.json")
    with open(history_file, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    logger.info(f"✅ 資料已儲存: {LATEST_FILE}")
    logger.info(f"✅ 歷史備份: {history_file}")
    
    return True


def get_last_trading_day() -> str:
    """取得最近一個交易日 (排除週六、週日)"""
    today = datetime.now()
    offset = 0
    while True:
        target_date = today - timedelta(days=offset)
        # weekday(): 0=週一, 6=週日
        if target_date.weekday() < 5:
            return target_date.strftime("%Y%m%d")
        offset += 1


def daily_job():
    """每日執行任務"""
    logger.info("=" * 50)
    logger.info("開始執行台股成交量爬蟲 (STOCK_DAY_ALL API)")
    
    target_date = get_last_trading_day()
    logger.info(f"目標日期: {target_date}")
    
    # 檢查今天是否已經抓過 (避免重複)
    history_file = os.path.join(HISTORY_DIR, f"{target_date}.json")
    if os.path.exists(history_file):
        logger.info(f"⚠️ {target_date} 資料已存在，跳過")
        return True
    
    try:
        top10, date_str = get_all_stocks_volume()
        
        if top10 and len(top10) == 10:
            save_top10_to_file(top10, date_str)
            logger.info(f"✅ {date_str} 資料處理完成")
            return True
        else:
            logger.warning(f"⚠️ 取得資料不足，僅 {len(top10) if top10 else 0} 筆")
            logger.warning("可能原因：非交易時段 或 API 尚無資料")
            return True  # 不讓 workflow 失敗
            
    except Exception as e:
        logger.error(f"❌ 任務執行失敗: {e}")
        return True  # 不讓 workflow 失敗


def run_once():
    """手動執行一次"""
    success = daily_job()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    run_once()