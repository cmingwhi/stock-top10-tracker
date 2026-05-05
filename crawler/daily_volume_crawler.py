"""
台股成交量前十大公司爬蟲 - 使用 STOCK_DAY_ALL API (穩定版本)
修正：明確指定查詢日期，確保取得正確日期的資料
"""

import requests
import json
import os
import sys
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional
import logging

# ========== 設定區 ==========
DATA_DIR = "data"
HISTORY_DIR = os.path.join(DATA_DIR, "history")
LATEST_FILE = os.path.join(DATA_DIR, "latest.json")

# 證交所 API：每日收盤行情 (支援指定日期)
# 格式：https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL?date=YYYYMMDD
STOCK_DAY_ALL_API = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"

# 設定 log
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_stocks_volume_by_date(date_str: str) -> Tuple[List[Dict], Optional[str]]:
    """
    從 STOCK_DAY_ALL API 取得指定日期的全市場成交量
    參數: date_str - 格式 YYYYMMDD (例如 20260505)
    回傳: (成交量排序後的前10大列表, 實際資料日期)
    """
    try:
        # 加入日期參數
        url = f"{STOCK_DAY_ALL_API}?date={date_str}"
        logger.info(f"正在呼叫 API: {url}")
        
        response = requests.get(url, timeout=30)
        
        # 檢查 HTTP 狀態碼
        if response.status_code != 200:
            logger.error(f"API 回應錯誤: HTTP {response.status_code}")
            return [], None
        
        # 檢查內容是否為空
        if not response.text or response.text.strip() == "":
            logger.warning(f"API 回傳空內容 (日期 {date_str})")
            return [], None
        
        # 解析 JSON
        try:
            data = response.json()
        except Exception as e:
            logger.error(f"JSON 解析失敗: {e}")
            logger.error(f"回傳內容前200字: {response.text[:200]}")
            return [], None
        
        # 檢查資料格式
        if not isinstance(data, list):
            logger.error(f"API 回傳格式錯誤，型別為: {type(data)}")
            return [], None
        
        if len(data) == 0:
            logger.warning(f"API 回傳空陣列 (日期 {date_str})，可能無交易資料或日期無效")
            return [], None
        
        logger.info(f"成功取得 {len(data)} 檔股票資料 (日期 {date_str})")
        
        # 解析每檔股票的成交量
        volume_list = []
        for item in data:
            code = item.get("Code", "")
            name = item.get("Name", "")
            
            if not code or not code.strip():
                continue
            
            code_clean = code.strip()
            if len(code_clean) < 4 or len(code_clean) > 6:
                continue
            
            if not name or name.strip() == "":
                continue
            
            volume_str = item.get("TradeVolume", "0")
            if isinstance(volume_str, str):
                volume_str = volume_str.replace(",", "").strip()
            
            try:
                volume = int(volume_str) if volume_str else 0
            except ValueError:
                volume = 0
            
            if volume > 0:
                volume_list.append({
                    "code": code_clean,
                    "name": name.strip(),
                    "volume": volume
                })
        
        logger.info(f"過濾後有效資料: {len(volume_list)} 筆 (成交量 > 0)")
        
        if len(volume_list) == 0:
            logger.warning("無任何成交量 > 0 的資料")
            return [], None
        
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
        
        # 顯示前10名
        logger.info("=" * 40)
        logger.info(f"📊 {date_str} 成交量前十大公司:")
        for item in top10:
            vol_display = f"{item['volume']:,}"
            logger.info(f"  {item['rank']}. {item['code']} {item['name']} - {vol_display} 股")
        logger.info("=" * 40)
        
        return top10, date_str
        
    except requests.exceptions.Timeout:
        logger.error("API 請求超時")
        return [], None
    except requests.exceptions.ConnectionError:
        logger.error("網路連線錯誤")
        return [], None
    except Exception as e:
        logger.error(f"取得資料失敗: {e}")
        return [], None


def get_last_trading_day(target_date: Optional[datetime] = None) -> str:
    """取得最近一個交易日 (排除週六、週日)"""
    if target_date is None:
        target_date = datetime.now()
    
    offset = 0
    while True:
        check_date = target_date - timedelta(days=offset)
        if check_date.weekday() < 5:  # 0=週一, 6=週日
            return check_date.strftime("%Y%m%d")
        offset += 1


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


def daily_job():
    """每日執行任務 - 抓取最近一個交易日的資料"""
    logger.info("=" * 50)
    logger.info("開始執行台股成交量爬蟲 (STOCK_DAY_ALL API)")
    
    # 取得今天日期
    today = datetime.now()
    today_str = today.strftime("%Y%m%d")
    logger.info(f"今天日期: {today_str}")
    
    # 取得最近一個交易日（排除週末）
    target_date = get_last_trading_day(today)
    logger.info(f"目標日期 (最近交易日): {target_date}")
    
    # 檢查今天是否已經抓過
    history_file = os.path.join(HISTORY_DIR, f"{target_date}.json")
    if os.path.exists(history_file):
        logger.info(f"⚠️ {target_date} 資料已存在，跳過")
        # 即使跳過，也確認一下 latest.json 是否存在
        if not os.path.exists(LATEST_FILE):
            logger.info("但 latest.json 不存在，重新讀取並建立")
        else:
            return True
    
    try:
        # 嘗試取得目標日期的資料
        top10, actual_date = get_stocks_volume_by_date(target_date)
        
        if top10 and len(top10) == 10:
            save_top10_to_file(top10, actual_date)
            logger.info(f"✅ {actual_date} 資料處理完成")
            return True
        else:
            # 如果失敗，嘗試往前推一天
            logger.warning(f"⚠️ 無法取得 {target_date} 資料，嘗試前一個交易日...")
            
            prev_date = get_last_trading_day(today - timedelta(days=1))
            if prev_date != target_date:
                logger.info(f"嘗試日期: {prev_date}")
                top10, actual_date = get_stocks_volume_by_date(prev_date)
                
                if top10 and len(top10) == 10:
                    save_top10_to_file(top10, actual_date)
                    logger.info(f"✅ 使用備用日期 {actual_date} 資料完成")
                    return True
            
            logger.warning(f"⚠️ 無法取得資料，僅 {len(top10) if top10 else 0} 筆")
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