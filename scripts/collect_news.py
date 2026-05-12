"""
每日新聞與社群媒體蒐集腳本
來源：Google News RSS、PTT、Google Custom Search (FB/IG/Dcard)
"""
import json, os, hashlib, re
from datetime import datetime, date, timedelta
from urllib.parse import quote
import feedparser
import requests

# ── 關鍵字分組 ─────────────────────────────────────────────
KEYWORDS = {
    "海淡廠": [
        "海水淡化廠", "海淡廠", "台南海淡", "臺南海水淡化",
        "南水資源分署", "海水淡化"
    ],
    "南部水資源": [
        "曾文水庫", "烏山頭水庫", "南化水庫", "白河水庫",
        "嘉南供水", "台南用水", "嘉義用水", "南部水情", "南部缺水"
    ],
    "全台水資源": [
        "水情警戒", "限水措施", "水庫蓄水率", "乾旱缺水",
        "水患淹水", "自來水漲價", "供水問題", "水質污染"
    ],
    "國際": [
        "desalination plant", "water crisis", "water shortage desalination"
    ]
}

PRIORITY = {
    "海淡廠": 1,
    "南部水資源": 2,
    "全台水資源": 3,
    "國際": 4
}

CSE_API_KEY = os.environ.get("GOOGLE_CSE_API_KEY", "")
CSE_ID      = os.environ.get("GOOGLE_CSE_ID", "964c6016fea3947d5")
TODAY       = date.today().isoformat()
DATA_DIR    = os.path.join(os.path.dirname(__file__), "..", "data")
os.makedirs(DATA_DIR, exist_ok=True)

seen_hashes = set()

def dedup_id(title: str, url: str) -> str:
    return hashlib.md5(f"{title}{url}".encode()).hexdigest()

def fetch_google_news_rss(keyword: str, category: str, priority: int) -> list:
    q = quote(keyword)
    url = f"https://news.google.com/rss/search?q={q}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    items = []
    try:
        feed = feedparser.parse(url)
        for entry in feed.entries[:8]:
            uid = dedup_id(entry.get("title",""), entry.get("link",""))
            if uid in seen_hashes:
                continue
            seen_hashes.add(uid)
            items.append({
                "id": uid,
                "title": entry.get("title", ""),
                "url": entry.get("link", ""),
                "source": entry.get("source", {}).get("title", "Google News"),
                "published": entry.get("published", ""),
                "content": entry.get("summary", "")[:500],
                "keyword": keyword,
                "category": category,
                "priority": priority,
                "platform": "新聞"
            })
    except Exception as e:
        print(f"  RSS 抓取失敗 [{keyword}]: {e}")
    return items

def fetch_ptt_rss(board: str, category: str) -> list:
    url = f"https://www.ptt.cc/bbs/{board}/index.rss"
    items = []
    try:
        feed = feedparser.parse(url)
        for entry in feed.entries[:5]:
            uid = dedup_id(entry.get("title",""), entry.get("link",""))
            if uid in seen_hashes:
                continue
            seen_hashes.add(uid)
            items.append({
                "id": uid,
                "title": entry.get("title", ""),
                "url": entry.get("link", ""),
                "source": f"PTT {board}",
                "published": entry.get("published", ""),
                "content": entry.get("summary", "")[:500],
                "keyword": board,
                "category": category,
                "priority": 2,
                "platform": "PTT"
            })
    except Exception as e:
        print(f"  PTT RSS 失敗 [{board}]: {e}")
    return items

def fetch_cse(keyword: str, category: str, priority: int, sites: list) -> list:
    if not CSE_API_KEY:
        return []
    items = []
    site_filter = " OR ".join([f"site:{s}" for s in sites])
    q = f"{keyword} ({site_filter})"
    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        "key": CSE_API_KEY,
        "cx": CSE_ID,
        "q": q,
        "num": 5,
        "dateRestrict": "d1",
        "lr": "lang_zh-TW"
    }
    try:
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
        for item in data.get("items", []):
            uid = dedup_id(item.get("title",""), item.get("link",""))
            if uid in seen_hashes:
                continue
            seen_hashes.add(uid)
            platform = "FB"
            link = item.get("link","")
            if "instagram" in link: platform = "Instagram"
            elif "ptt.cc" in link:  platform = "PTT"
            elif "dcard" in link:   platform = "Dcard"
            items.append({
                "id": uid,
                "title": item.get("title",""),
                "url": link,
                "source": item.get("displayLink",""),
                "published": TODAY,
                "content": item.get("snippet","")[:500],
                "keyword": keyword,
                "category": category,
                "priority": priority,
                "platform": platform
            })
    except Exception as e:
        print(f"  CSE 搜尋失敗 [{keyword}]: {e}")
    return items

def main():
    all_items = []
    print(f"=== 開始蒐集 {TODAY} ===")

    # Google News RSS
    for category, keywords in KEYWORDS.items():
        pri = PRIORITY[category]
        print(f"\n[{category}] 抓取 RSS...")
        for kw in keywords:
            items = fetch_google_news_rss(kw, category, pri)
            print(f"  {kw}: {len(items)} 則")
            all_items.extend(items)

    # PTT
    print("\n[社群] 抓取 PTT...")
    for board in ["WaterEngr", "Gossiping", "TW-News"]:
        items = fetch_ptt_rss(board, "社群輿情")
        # 過濾相關文章
        filtered = [i for i in items if any(
            kw in i["title"] for kws in KEYWORDS.values() for kw in kws
        )]
        print(f"  {board}: {len(filtered)} 則相關")
        all_items.extend(filtered)

    # Google CSE (FB / IG / Dcard)
    if CSE_API_KEY:
        print("\n[社群] 搜尋 FB/IG/Dcard...")
        social_sites = ["facebook.com", "instagram.com", "dcard.tw"]
        cse_keywords = ["海水淡化廠", "南水資源", "台南缺水", "水庫蓄水"]
        for kw in cse_keywords:
            items = fetch_cse(kw, "社群輿情", 1, social_sites)
            print(f"  {kw}: {len(items)} 則")
            all_items.extend(items)
    else:
        print("\n[社群] 跳過 CSE（未設 API key）")

    # 儲存
    out_path = os.path.join(DATA_DIR, f"raw_{TODAY}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(all_items, f, ensure_ascii=False, indent=2)

    print(f"\n=== 共蒐集 {len(all_items)} 則，儲存至 {out_path} ===")

if __name__ == "__main__":
    main()
