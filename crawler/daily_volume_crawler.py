"""
台股成交量前十大公司爬蟲 - 使用 STOCK_DAY API (支援指定日期)
這個版本可以準確取得指定日期的成交量資料
"""

import requests
import json
import os
import sys
import time
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional
import logging

# ========== 設定區 ==========
DATA_DIR = "data"
HISTORY_DIR = os.path.join(DATA_DIR, "history")
LATEST_FILE = os.path.join(DATA_DIR, "latest.json")

# 證交所 API
STOCK_LIST_API = "https://openapi.twse.com.tw/v1/stock/list"  # 股票清單
STOCK_DAY_API = "https://www.twse.com.tw/exchangeReport/STOCK_DAY"  # 個股日成交資訊

# 設定 log
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_all_stock_codes() -> List[Dict[str, str]]:
    """取得全市場股票清單（上市）"""
    try:
        response = requests.get(STOCK_LIST_API, timeout=30)
        if response.status_code == 200:
            stocks = response.json()
            stock_list = []
            for s in stocks:
                code = s.get("code", "")
                name = s.get("name", "")
                # 只保留純數字代碼（上市股票）
                if code.isdigit() and 4 <= len(code) <= 6:
                    stock_list.append({
                        "code": code,
                        "name": name
                    })
            logger.info(f"取得 {len(stock_list)} 檔上市股票")
            return stock_list
        else:
            logger.error(f"取得股票清單失敗: HTTP {response.status_code}")
            return []
    except Exception as e:
        logger.error(f"取得股票清單錯誤: {e}")
        return []


def get_stock_volume_on_date(stock_code: str, date_str: str) -> Optional[int]:
    """
    取得特定股票在特定日期的成交量
    date_str: YYYYMMDD (例: 20260505)
    """
    try:
        # 轉換日期格式為民國年 (113/05/05)
        year = int(date_str[:4])
        month = int(date_str[4:6])
        day = int(date_str[6:8])
        roc_year = year - 1911
        date_roc = f"{roc_year}/{month:02d}/{day:02d}"
        
        params = {
            "response": "json",
            "date": date_roc,
            "stockNo": stock_code
        }
        
        response = requests.get(STOCK_DAY_API, params=params, timeout=10)
        
        if response.status_code != 200:
            return None
        
        data = response.json()
        
        if data.get("stat") != "OK":
            return None
        
        if not data.get("data"):
            return None
        
        # 找到該日期的資料
        for row in data["data"]:
            # row[0] 格式為 "113/05/05"
            if row[0] == date_roc:
                volume_str = row[1].replace(",", "")
                return int(volume_str)
        
        return None
        
    except Exception as e:
        logger.debug(f"股票 {stock_code} 查詢失敗: {e}")
        return None


def get_top10_by_date(target_date: str, max_stocks: int = 500) -> Tuple[List[Dict], str]:
    """
    取得指定日期的成交量前十大公司
    target_date: YYYYMMDD 格式
    """
    logger.info(f"開始抓取 {target_date} 成交量排行...")
    
    # 1. 取得所有股票清單
    stocks = get_all_stock_codes()
    if not stocks:
        logger.error("無法取得股票清單")
        return [], target_date
    
    # 2. 逐一抓取成交量（限制筆數避免超時）
    volume_data = []
    total = min(len(stocks), max_stocks)
    
    for idx, stock in enumerate(stocks[:max_stocks]):
        code = stock["code"]
        name = stock["name"]
        
        volume = get_stock_volume_on_date(code, target_date)
        
        if volume is not None and volume > 0:
            volume_data.append({
                "code": code,
                "name": name,
                "volume": volume
            })
        
        # 進度顯示
        if (idx + 1) % 100 == 0:
            logger.info(f"進度: {idx+1}/{total}, 已取得 {len(volume_data)} 筆有效資料")
        
        # 避免請求過於密集
        time.sleep(0.05)
    
    logger.info(f"掃描完成，共取得 {len(volume_data)} 筆有成交量的股票")
    
    # 3. 依成交量排序，取前十名
    volume_data.sort(key=lambda x: x["volume"], reverse=True)
    top10 = volume_data[:10]
    
    for i, item in enumerate(top10):
        item["rank"] = i + 1
    
    logger.info("=" * 40)
    logger.info(f"📊 {target_date} 成交量前十大公司:")
    for item in top10:
        vol_display = f"{item['volume']:,}"
        logger.info(f"  {item['rank']}. {item['code']} {item['name']} - {vol_display} 股")
    logger.info("=" * 40)
    
    return top10, target_date


def save_top10_to_file(top10_data: List[Dict], date_str: str):
    """儲存資料到 JSON 檔案"""
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(HISTORY_DIR, exist_ok=True)
    
    output = {
        "date": date_str,
        "update_time": datetime.now().isoformat(),
        "top10": top10_data,
        "total_stocks": len(top10_data)
    }
    
    with open(LATEST_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    history_file = os.path.join(HISTORY_DIR, f"{date_str}.json")
    with open(history_file, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    logger.info(f"✅ 資料已儲存: {LATEST_FILE}")
    return True


def get_last_trading_day() -> str:
    """取得最近一個交易日 (排除週六、週日)"""
    today = datetime.now()
    offset = 0
    while True:
        target_date = today - timedelta(days=offset)
        if target_date.weekday() < 5:
            return target_date.strftime("%Y%m%d")
        offset += 1


def daily_job():
    """每日執行任務"""
    logger.info("=" * 50)
    logger.info("開始執行台股成交量爬蟲 (STOCK_DAY API)")
    
    target_date = get_last_trading_day()
    logger.info(f"目標日期: {target_date}")
    
    history_file = os.path.join(HISTORY_DIR, f"{target_date}.json")
    if os.path.exists(history_file):
        logger.info(f"⚠️ {target_date} 資料已存在，跳過")
        return True
    
    try:
        top10, actual_date = get_top10_by_date(target_date)
        
        if top10 and len(top10) >= 5:
            save_top10_to_file(top10, actual_date)
            logger.info(f"✅ {actual_date} 資料處理完成")
            return True
        else:
            logger.warning(f"⚠️ 取得資料不足，僅 {len(top10) if top10 else 0} 筆")
            return True
            
    except Exception as e:
        logger.error(f"❌ 任務執行失敗: {e}")
        return True


def run_once():
    """手動執行一次"""
    success = daily_job()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    run_once()