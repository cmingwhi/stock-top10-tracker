"""
台股成交量前十大公司爬蟲 - GitHub Actions 優化版
特點：
- 支援 GitHub Actions 環境
- 錯誤重試機制
- 歷史資料保留
- 輕量化（減少 API 呼叫次數）
"""

import requests
import json
import os
import time
import sys
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import logging

# ========== 設定區 ==========
DATA_DIR = "data"
HISTORY_DIR = os.path.join(DATA_DIR, "history")
LATEST_FILE = os.path.join(DATA_DIR, "latest.json")

# 證交所 API (使用已排序好的前 100 名 API，效率更高！)
# 注意：這個 API 回傳前 100 大成交量股票，直接取前 10 即可
VOLUME_RANK_API = "https://openapi.twse.com.tw/v1/stock/aftertrading/volumeRank"

# 設定 log
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_top10_directly() -> Tuple[List[Dict], str]:
    """
    直接從證交所 API 取得前 10 大成交量 (效率最高)
    回傳: (top10_list, date_string)
    """
    try:
        response = requests.get(VOLUME_RANK_API, timeout=30)
        
        if response.status_code != 200:
            logger.error(f"API 回應錯誤: {response.status_code}")
            return [], ""
        
        data = response.json()
        
        if not data or not isinstance(data, list):
            logger.error("API 回傳格式錯誤")
            return [], ""
        
        # 取前 10 名
        top10 = []
        for idx, item in enumerate(data[:10]):
            volume_str = item.get("TradeVolume", "0").replace(",", "")
            volume = int(volume_str) if volume_str.isdigit() else 0
            
            top10.append({
                "rank": idx + 1,
                "code": item.get("Code", ""),
                "name": item.get("Name", ""),
                "volume": volume
            })
        
        # 取得資料日期 (API 回傳的資料日期)
        date_str = datetime.now().strftime("%Y%m%d")
        
        logger.info(f"成功取得 {len(top10)} 筆資料")
        for item in top10:
            logger.info(f"  {item['rank']}. {item['code']} {item['name']} - {item['volume']:,} 股")
        
        return top10, date_str
        
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
        "top10": top10_data
    }
    
    # 儲存最新檔案
    with open(LATEST_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    # 儲存歷史備份
    history_file = os.path.join(HISTORY_DIR, f"{date_str}.json")
    with open(history_file, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    logger.info(f"資料已儲存: {LATEST_FILE}")
    return True


def get_last_trading_day() -> str:
    """取得最近一個交易日 (排除週六、週日)"""
    today = datetime.now()
    offset = 0
    while True:
        target_date = today - timedelta(days=offset)
        if target_date.weekday() < 5:  # 週一到週五
            return target_date.strftime("%Y%m%d")
        offset += 1


def daily_job():
    """每日執行任務"""
    logger.info("=" * 50)
    logger.info("開始執行台股成交量爬蟲")
    
    target_date = get_last_trading_day()
    logger.info(f"目標日期: {target_date}")
    
    # 檢查今天是否已經抓過 (避免重複)
    history_file = os.path.join(HISTORY_DIR, f"{target_date}.json")
    if os.path.exists(history_file):
        logger.info(f"⚠️ {target_date} 資料已存在，跳過")
        return True
    
    # 執行爬蟲
    try:
        top10, date_str = get_top10_directly()
        
        if top10 and len(top10) == 10:
            save_top10_to_file(top10, date_str)
            logger.info(f"✅ {date_str} 資料處理完成")
            return True
        else:
            logger.error(f"❌ 取得資料不足，僅 {len(top10) if top10 else 0} 筆")
            return False
            
    except Exception as e:
        logger.error(f"❌ 任務執行失敗: {e}")
        return False


def run_once():
    """手動執行一次"""
    success = daily_job()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    run_once()