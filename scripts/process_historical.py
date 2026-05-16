"""
process_historical.py
合併所有 hist_*.json → keyword 情感分類 → 同步到 Google Sheets
"""
import json, os, glob, re, time, requests
from datetime import datetime, date
from zoneinfo import ZoneInfo
from urllib.parse import urlparse

_TW = ZoneInfo('Asia/Taipei')
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
SHEETS_API_URL = os.environ.get("SHEETS_API_URL") or \
    "https://script.google.com/macros/s/AKfycbxTvnw8nXbSVc5fRim0nvX6gaLiR3yRVuT2e_faTUh_95hRFJfp5Ts4rC60LqZMrXb-/exec"

DOMAIN_BLACKLIST = {
    "fathomjournal.org", "lineshoppingtw.line.me", "tripadvisor.com",
    "tripadvisor.com.tw", "agoda.com", "booking.com", "pixnet.net",
    "upskilltw.com", "ia.gov.tw",
}

NEGATIVE_KEYWORDS = [
    "抗議", "陳情", "抗爭", "示威", "連署", "反對", "怒", "憤",
    "抱怨", "不滿", "民怨", "居民抗議", "漁民抗議",
    "批評", "質疑", "投訴", "爭議", "糾紛", "失職", "延誤", "失敗",
    "缺水", "乾旱", "限水", "停水", "水荒", "污染", "水質",
    "漏水", "供水不足", "蓄水不足",
    "淹水", "危機", "警戒", "警告", "風險", "威脅",
    "water crisis", "water shortage", "contamination", "protest",
]
POSITIVE_KEYWORDS = [
    "完工", "啟用", "通水", "竣工", "提升", "改善", "增加",
    "節水", "豐水", "蓄水充足", "水情穩定", "供水穩定",
    "榮獲", "獲獎", "成功", "突破",
]

def keyword_classify(text):
    t = text.lower()
    neg = sum(1 for kw in NEGATIVE_KEYWORDS if kw in t)
    pos = sum(1 for kw in POSITIVE_KEYWORDS if kw in t)
    if neg > pos:
        return "負面"
    elif pos > 0:
        return "正面"
    return "中立"

def is_junk(url, title=""):
    if not url:
        return True
    domain = urlparse(url).netloc.lower()
    if any(b in domain for b in DOMAIN_BLACKLIST):
        return True
    junk_words = ["美食", "旅遊", "一日遊", "餐廳", "住宿", "秘境"]
    return any(w in (title or "") for w in junk_words)

def sync_batch(items_batch, batch_num):
    try:
        r = requests.post(SHEETS_API_URL, json={"items": items_batch}, timeout=90)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.Timeout:
        print(f"  第 {batch_num} 批 timeout，略過")
        return {}
    except Exception as e:
        print(f"  第 {batch_num} 批失敗：{e}")
        return {}

def main():
    # 1. 載入所有 hist_*.json
    hist_files = sorted(glob.glob(os.path.join(DATA_DIR, "hist_*.json")))
    if not hist_files:
        print("找不到 hist_*.json 檔案，請先執行 collect_historical.py"); return

    print(f"找到 {len(hist_files)} 個歷史檔案：")
    for f in hist_files:
        print(f"  {os.path.basename(f)}")

    # 2. 合併 + URL 去重
    all_items = []
    seen_urls = set()
    total_raw = 0
    for fpath in hist_files:
        with open(fpath, encoding="utf-8") as f:
            items = json.load(f)
        total_raw += len(items)
        for item in items:
            url = item.get("url", "")
            if not url or url in seen_urls:
                continue
            if is_junk(url, item.get("title", "")):
                continue
            seen_urls.add(url)
            all_items.append(item)

    print(f"\n原始：{total_raw} 則 → 去重後：{len(all_items)} 則")

    # 3. keyword 情感分類（不過濾舊文，歷史資料全部保留）
    analyzed = []
    for item in all_items:
        text      = (item.get("title", "") + " " + item.get("content", ""))
        sentiment = keyword_classify(text)
        category  = item.get("category", "全台水資源")
        priority_label = "高" if (sentiment == "負面" and category in ("海淡廠", "南部水資源", "社群輿情")) else \
                         "中" if sentiment == "負面" else "低"
        pub_date  = item.get("pub_date") or item.get("published") or item.get("date") or ""
        if pub_date and len(pub_date) > 10:
            pub_date = pub_date[:10]
        analyzed.append({
            **item,
            "sentiment":          sentiment,
            "priority_label":     priority_label,
            "pub_date":           pub_date,
            "date":               pub_date,
            "track_status":       item.get("track_status", ""),
            "clarification_draft": item.get("clarification_draft", ""),
        })

    # 依 pub_date 由新到舊排序
    analyzed.sort(key=lambda x: x.get("pub_date", ""), reverse=True)

    neg_count = sum(1 for x in analyzed if x["sentiment"] == "負面")
    pos_count = sum(1 for x in analyzed if x["sentiment"] == "正面")
    print(f"情感分類：負面 {neg_count}、正面 {pos_count}、中立 {len(analyzed)-neg_count-pos_count}")

    # 4. 批次同步到 Sheets
    BATCH_SIZE = 50
    total_added   = 0
    total_updated = 0
    total_batches = (len(analyzed) + BATCH_SIZE - 1) // BATCH_SIZE

    print(f"\n同步 {len(analyzed)} 則到 Google Sheets（{total_batches} 批）...")
    for i in range(0, len(analyzed), BATCH_SIZE):
        batch     = analyzed[i:i + BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1
        print(f"  第 {batch_num}/{total_batches} 批（{len(batch)} 筆）...", end=" ", flush=True)
        result = sync_batch(batch, batch_num)
        added   = result.get("added", 0)
        updated = result.get("updated", 0)
        total_added   += added
        total_updated += updated
        print(f"新增 {added} 更新 {updated}")
        time.sleep(0.5)

    print(f"\n同步完成：新增 {total_added}、更新 {total_updated}")

    # 5. 排序
    try:
        r = requests.get(f"{SHEETS_API_URL}?action=sortByDate", timeout=60)
        res = r.json()
        print(f"排序完成：{res.get('sorted', '?')} 列")
    except Exception as e:
        print(f"排序失敗（不影響資料）：{e}")

if __name__ == "__main__":
    main()
