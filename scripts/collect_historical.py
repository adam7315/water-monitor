"""
collect_historical.py
歷史新聞回填腳本：搜尋指定日期範圍內的新聞與社群媒體貼文
用法: python scripts/collect_historical.py --start 2025-06-17 --end 2025-08-31
"""
import argparse, json, os, re, time, hashlib
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from urllib.parse import quote, urlparse
import feedparser
import requests

_TW = ZoneInfo('Asia/Taipei')
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
os.makedirs(DATA_DIR, exist_ok=True)

CSE_API_KEY      = os.getenv("GOOGLE_CSE_API_KEY", "")
CSE_ID           = os.getenv("GOOGLE_CSE_ID", "")
NEWSDATA_API_KEY = os.getenv("NEWSDATA_API_KEY", "")

DOMAIN_BLACKLIST = {
    "fathomjournal.org", "lineshoppingtw.line.me", "tripadvisor.com",
    "tripadvisor.com.tw", "agoda.com", "booking.com", "pixnet.net",
    "upskilltw.com", "matters.town", "ia.gov.tw", "shopee.tw",
    "pchome.com.tw", "amazon.com", "ebay.com",
}

# ── 關鍵字（依重要性排序，歷史回填只取核心關鍵字避免配額耗盡）──
KEYWORDS = {
    "海淡廠": [
        "海水淡化廠", "海淡廠", "台南海淡", "臺南海水淡化",
        "南水資源分署", "海水淡化 台南", "海水淡化 將軍",
        "將軍海水淡化", "海淡廠 施工", "海淡廠 工程",
        "desalination plant Taiwan", "台南海水淡化",
    ],
    "南部水資源": [
        "曾文水庫", "烏山頭水庫", "南化水庫",
        "台南缺水", "南部缺水", "南部水情",
        "嘉南供水", "高屏溪攔河堰",
    ],
    "全台水資源": [
        "水情警戒", "限水措施", "水庫蓄水率", "乾旱缺水",
        "水利署", "缺水危機", "供水問題", "水質污染",
    ],
    "國際": [
        "seawater desalination", "desalination plant",
        "water desalination technology", "reverse osmosis plant",
    ],
}
PRIORITY = {"海淡廠": 1, "南部水資源": 2, "全台水資源": 3, "國際": 4}

# 社群媒體關鍵字（CSE 用）
SOCIAL_KEYWORDS = [
    "海水淡化廠", "南水資源分署", "台南缺水", "海淡廠",
    "曾文水庫 水情", "水情警戒", "限水",
]
SOCIAL_SITES = [
    "site:facebook.com", "site:dcard.tw",
    "site:ptt.cc", "site:instagram.com",
]

# ── 工具函式 ─────────────────────────────────────────────────

def dedup_id(title, url):
    key = (url or title or "").strip()
    return hashlib.md5(key.encode()).hexdigest()

def is_junk(url, title=""):
    if not url:
        return True
    domain = urlparse(url).netloc.lower()
    if any(b in domain for b in DOMAIN_BLACKLIST):
        return True
    junk_words = ["美食", "旅遊", "一日遊", "餐廳", "住宿", "秘境"]
    if any(w in (title or "") for w in junk_words):
        return True
    return False

def extract_url_date(url):
    m = re.search(r'/(\d{4})[/_-](\d{1,2})[/_-](\d{1,2})', url or "")
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass
    return None

def parse_entry_date(entry, link=""):
    """從 feedparser entry 取出台灣時區日期字串"""
    for key in ("published_parsed", "updated_parsed"):
        pp = entry.get(key)
        if pp:
            try:
                dt_utc = datetime(pp[0], pp[1], pp[2], pp[3], pp[4], pp[5], tzinfo=timezone.utc)
                return dt_utc.astimezone(_TW).date().isoformat()
            except Exception:
                pass
    published = entry.get("published", "")
    if published:
        try:
            from email.utils import parsedate_to_datetime
            return parsedate_to_datetime(published).astimezone(_TW).date().isoformat()
        except Exception:
            if len(published) >= 10:
                return published[:10]
    if link:
        d = extract_url_date(link)
        if d:
            return d.isoformat()
    return ""

def in_range(pub_date_str, start_dt, end_dt):
    """檢查日期字串是否在 [start_dt, end_dt] 區間內"""
    if not pub_date_str:
        return False
    try:
        d = date.fromisoformat(pub_date_str[:10])
        return start_dt <= d <= end_dt
    except Exception:
        return False

# ── 蒐集函式 ─────────────────────────────────────────────────

def fetch_gnews_range(keyword, category, priority, start_dt, end_dt):
    """Google News RSS：after: before: 日期區間查詢"""
    after_str  = start_dt.strftime('%Y-%m-%d')
    before_str = (end_dt + timedelta(days=1)).strftime('%Y-%m-%d')
    q   = f"{keyword} after:{after_str} before:{before_str}"
    url = f"https://news.google.com/rss/search?q={quote(q)}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"

    items = []
    try:
        feed = feedparser.parse(url)
        for entry in feed.entries:
            link  = entry.get("link", "")
            title = entry.get("title", "")
            if is_junk(link, title):
                continue
            pub_date = parse_entry_date(entry, link)
            # 嚴格日期過濾
            if pub_date and not in_range(pub_date, start_dt, end_dt):
                continue
            if not pub_date:
                continue  # 無日期資訊的歷史文章跳過
            source = ""
            if isinstance(entry.get("source"), dict):
                source = entry["source"].get("title", "")
            items.append({
                "id":         dedup_id(title, link),
                "title":      title,
                "url":        link,
                "source":     source,
                "published":  pub_date,
                "pub_date":   pub_date,
                "date":       pub_date,
                "content":    entry.get("summary", "")[:500],
                "keyword":    keyword,
                "category":   category,
                "priority":   priority,
                "platform":   "新聞",
                "feed_source":"Google News RSS",
            })
    except Exception as e:
        print(f"    [RSS 失敗] {keyword}: {e}")
    return items

def fetch_cse_news_range(keyword, category, priority, start_dt, end_dt, pages=2):
    """Google CSE：新聞關鍵字 + 日期範圍（sort=date:r）"""
    if not CSE_API_KEY or not CSE_ID:
        return []
    start_s = start_dt.strftime('%Y%m%d')
    end_s   = end_dt.strftime('%Y%m%d')
    items   = []
    for start_idx in range(1, pages * 10, 10):
        try:
            params = {
                "key": CSE_API_KEY, "cx": CSE_ID,
                "q":   keyword,
                "num": 10,
                "start": start_idx,
                "sort": f"date:r:{start_s}:{end_s}",
            }
            r = requests.get("https://www.googleapis.com/customsearch/v1",
                             params=params, timeout=15)
            r.raise_for_status()
            data = r.json()
            results = data.get("items", [])
            if not results:
                break
            for res in results:
                link  = res.get("link", "")
                title = res.get("title", "")
                if is_junk(link, title):
                    continue
                # 從 URL 或 snippet 取日期
                pub_date = ""
                d = extract_url_date(link)
                if d:
                    pub_date = d.isoformat()
                else:
                    snippet = res.get("snippet", "")
                    m = re.search(r'(\d{4})[年/-](\d{1,2})[月/-](\d{1,2})', snippet)
                    if m:
                        try:
                            pub_date = date(int(m.group(1)), int(m.group(2)),
                                            int(m.group(3))).isoformat()
                        except ValueError:
                            pass
                if pub_date and not in_range(pub_date, start_dt, end_dt):
                    continue
                if not pub_date:
                    pub_date = start_dt.isoformat()  # 無日期時以範圍起始日記錄
                domain = urlparse(link).netloc.lower()
                items.append({
                    "id":         dedup_id(title, link),
                    "title":      title,
                    "url":        link,
                    "source":     domain,
                    "published":  pub_date,
                    "pub_date":   pub_date,
                    "date":       pub_date,
                    "content":    res.get("snippet", "")[:500],
                    "keyword":    keyword,
                    "category":   category,
                    "priority":   priority,
                    "platform":   "新聞",
                    "feed_source":"Google CSE",
                })
            time.sleep(0.3)
        except Exception as e:
            print(f"    [CSE 失敗] {keyword} start={start_idx}: {e}")
            break
    return items

def fetch_cse_social_range(keyword, start_dt, end_dt):
    """Google CSE：社群媒體（FB/Dcard/PTT/IG）+ 日期範圍"""
    if not CSE_API_KEY or not CSE_ID:
        return []
    start_s = start_dt.strftime('%Y%m%d')
    end_s   = end_dt.strftime('%Y%m%d')
    site_q  = " OR ".join(SOCIAL_SITES)
    q       = f"{keyword} ({site_q})"
    items   = []
    try:
        params = {
            "key": CSE_API_KEY, "cx": CSE_ID,
            "q":   q, "num": 10,
            "sort": f"date:r:{start_s}:{end_s}",
        }
        r = requests.get("https://www.googleapis.com/customsearch/v1",
                         params=params, timeout=15)
        r.raise_for_status()
        for res in r.json().get("items", []):
            link  = res.get("link", "")
            title = res.get("title", "")
            if is_junk(link, title):
                continue
            domain = urlparse(link).netloc.lower()
            platform = "社群"
            if "facebook" in domain:   platform = "Facebook"
            elif "dcard" in domain:    platform = "Dcard"
            elif "ptt.cc" in domain:   platform = "PTT"
            elif "instagram" in domain: platform = "Instagram"

            pub_date = ""
            d = extract_url_date(link)
            if d:
                pub_date = d.isoformat()
            else:
                snippet = res.get("snippet", "")
                m = re.search(r'(\d{4})[年/-](\d{1,2})[月/-](\d{1,2})', snippet)
                if m:
                    try:
                        pub_date = date(int(m.group(1)), int(m.group(2)),
                                        int(m.group(3))).isoformat()
                    except ValueError:
                        pass
            if pub_date and not in_range(pub_date, start_dt, end_dt):
                continue
            if not pub_date:
                pub_date = start_dt.isoformat()
            items.append({
                "id":         dedup_id(title, link),
                "title":      title,
                "url":        link,
                "source":     domain,
                "published":  pub_date,
                "pub_date":   pub_date,
                "date":       pub_date,
                "content":    res.get("snippet", "")[:500],
                "keyword":    keyword,
                "category":   "社群輿情",
                "priority":   1,
                "platform":   platform,
                "feed_source":"Google CSE",
            })
    except Exception as e:
        print(f"    [CSE Social 失敗] {keyword}: {e}")
    return items

def fetch_newsdata_range(keyword, category, priority, start_dt, end_dt):
    """NewsData.io 歷史查詢（需 paid plan 的 from_date/to_date 參數）"""
    if not NEWSDATA_API_KEY:
        return []
    items = []
    try:
        params = {
            "apikey":     NEWSDATA_API_KEY,
            "q":          keyword,
            "country":    "tw",
            "language":   "zh",
            "from_date":  start_dt.isoformat(),
            "to_date":    end_dt.isoformat(),
            "size":       10,
        }
        r = requests.get("https://newsdata.io/api/1/news", params=params, timeout=15)
        r.raise_for_status()
        for art in r.json().get("results", []):
            link = art.get("link", "")
            if is_junk(link):
                continue
            pub = art.get("pubDate", "")
            pub_date = pub[:10] if pub else start_dt.isoformat()
            if pub_date and not in_range(pub_date, start_dt, end_dt):
                continue
            items.append({
                "id":         dedup_id(art.get("title", ""), link),
                "title":      art.get("title", ""),
                "url":        link,
                "source":     art.get("source_id", "NewsData"),
                "published":  pub_date,
                "pub_date":   pub_date,
                "date":       pub_date,
                "content":    (art.get("description", "") or "")[:500],
                "keyword":    keyword,
                "category":   category,
                "priority":   priority,
                "platform":   "新聞",
                "feed_source":"NewsData.io",
            })
    except Exception as e:
        print(f"    [NewsData 失敗] {keyword}: {e}")
    return items

def fetch_ptt_historical(board, start_dt, end_dt, max_pages=20):
    """PTT 看板：向前翻頁取歷史文章（從最新頁往前找到 start_dt）"""
    items = []
    headers = {"Cookie": "over18=1", "User-Agent": "Mozilla/5.0"}
    KEYWORDS_FLAT = [kw for kws in KEYWORDS.values() for kw in kws]

    try:
        # 取最新頁面的頁碼
        r = requests.get(f"https://www.ptt.cc/bbs/{board}/index.html",
                         headers=headers, timeout=10)
        m = re.search(r'href="/bbs/' + board + r'/index(\d+)\.html"[^>]*>‹', r.text)
        if not m:
            return []
        latest_idx = int(m.group(1)) + 1

        for page_offset in range(max_pages):
            page_num = latest_idx - page_offset
            if page_num < 1:
                break
            url = f"https://www.ptt.cc/bbs/{board}/index{page_num}.html"
            try:
                pr = requests.get(url, headers=headers, timeout=10)
                # 找出所有文章
                entries = re.findall(
                    r'<div class="title">\s*(?:<[^>]+>)?\s*<a href="(/bbs/'
                    + board + r'/[^"]+\.html)"[^>]*>([^<]+)</a>',
                    pr.text
                )
                page_oldest = None
                found_in_range = False
                for path, title in entries:
                    title = title.strip()
                    # 日期從下方 meta 區塊取（簡化：從文章路徑取年月）
                    d = extract_url_date(path)
                    if not d:
                        m2 = re.search(r'M\.(\d{10})\.', path)
                        if m2:
                            ts = int(m2.group(1))
                            d = datetime.fromtimestamp(ts, tz=_TW).date()
                    if not d:
                        continue
                    if page_oldest is None or d < page_oldest:
                        page_oldest = d
                    if not in_range(d.isoformat(), start_dt, end_dt):
                        continue
                    found_in_range = True
                    # 關鍵字過濾
                    if not any(kw in title for kw in KEYWORDS_FLAT
                               if len(kw) >= 2):
                        continue
                    link = f"https://www.ptt.cc{path}"
                    items.append({
                        "id":         dedup_id(title, link),
                        "title":      title,
                        "url":        link,
                        "source":     f"PTT/{board}",
                        "published":  d.isoformat(),
                        "pub_date":   d.isoformat(),
                        "date":       d.isoformat(),
                        "content":    title,
                        "keyword":    board,
                        "category":   "社群輿情",
                        "priority":   1,
                        "platform":   "PTT",
                        "feed_source":"PTT",
                    })
                # 如果這頁最舊的文章已早於 start_dt，停止往前翻
                if page_oldest and page_oldest < start_dt:
                    break
                time.sleep(0.3)
            except Exception:
                time.sleep(0.5)
    except Exception as e:
        print(f"    [PTT 失敗] {board}: {e}")
    return items

def fetch_dcard_historical(forum, start_dt, end_dt, max_requests=10):
    """Dcard：往前翻頁取歷史討論（靠 before 參數）"""
    items = []
    KEYWORDS_FLAT = [kw for kws in KEYWORDS.values() for kw in kws]
    before_id = None
    try:
        for _ in range(max_requests):
            params = {"popular": "false", "limit": 30}
            if before_id:
                params["before"] = before_id
            r = requests.get(
                f"https://www.dcard.tw/service/api/v2/forums/{forum}/posts",
                params=params, timeout=10,
                headers={"User-Agent": "Mozilla/5.0"}
            )
            r.raise_for_status()
            posts = r.json()
            if not posts:
                break
            oldest_date = None
            for post in posts:
                created = post.get("createdAt", "")
                if created:
                    try:
                        d = datetime.fromisoformat(created.replace("Z", "+00:00")).astimezone(_TW).date()
                    except Exception:
                        continue
                    if oldest_date is None or d < oldest_date:
                        oldest_date = d
                    if not in_range(d.isoformat(), start_dt, end_dt):
                        continue
                    title = post.get("title", "")
                    if not any(kw in title for kw in KEYWORDS_FLAT if len(kw) >= 2):
                        if not any(kw in post.get("excerpt", "") for kw in KEYWORDS_FLAT if len(kw) >= 2):
                            continue
                    pid  = post.get("id", "")
                    link = f"https://www.dcard.tw/f/{forum}/p/{pid}"
                    items.append({
                        "id":         dedup_id(title, link),
                        "title":      title,
                        "url":        link,
                        "source":     f"Dcard/{forum}",
                        "published":  d.isoformat(),
                        "pub_date":   d.isoformat(),
                        "date":       d.isoformat(),
                        "content":    post.get("excerpt", "")[:500],
                        "keyword":    forum,
                        "category":   "社群輿情",
                        "priority":   1,
                        "platform":   "Dcard",
                        "feed_source":"Dcard",
                    })
                before_id = post.get("id")
            if oldest_date and oldest_date < start_dt:
                break
            time.sleep(0.5)
    except Exception as e:
        print(f"    [Dcard 失敗] {forum}: {e}")
    return items

# ── 主程式 ────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="歷史新聞回填")
    parser.add_argument("--start", required=True, help="開始日期 YYYY-MM-DD")
    parser.add_argument("--end",   required=True, help="結束日期 YYYY-MM-DD")
    args = parser.parse_args()

    start_dt = date.fromisoformat(args.start)
    end_dt   = date.fromisoformat(args.end)
    span     = (end_dt - start_dt).days + 1

    print(f"=== 歷史蒐集：{start_dt} → {end_dt}（{span} 天）===")
    print(f"    CSE: {'有' if CSE_API_KEY else '無'} | NewsData: {'有' if NEWSDATA_API_KEY else '無'}")

    all_items  = []
    seen_urls  = set()

    def add_items(new_items):
        added = 0
        for it in new_items:
            u = it.get("url", "")
            if u and u not in seen_urls:
                seen_urls.add(u)
                all_items.append(it)
                added += 1
        return added

    # 1. Google News RSS（主力：免費，歷史覆蓋依 Google 快取）
    print("\n[1] Google News RSS...")
    for category, keywords in KEYWORDS.items():
        pri = PRIORITY[category]
        for kw in keywords:
            items = fetch_gnews_range(kw, category, pri, start_dt, end_dt)
            n = add_items(items)
            if n:
                print(f"    {kw}: +{n}")
            time.sleep(0.4)

    # 2. Google CSE（新聞補強 + 社群媒體）
    if CSE_API_KEY:
        print("\n[2] Google CSE 新聞補強...")
        cse_kws = ["海水淡化廠 台南", "南水資源分署", "台南缺水", "曾文水庫 缺水"]
        for kw in cse_kws:
            items = fetch_cse_news_range(kw, "全台水資源", 3, start_dt, end_dt, pages=1)
            n = add_items(items)
            if n:
                print(f"    {kw}: +{n}")
            time.sleep(1.0)

        print("\n[2b] Google CSE 社群媒體...")
        for kw in SOCIAL_KEYWORDS:
            items = fetch_cse_social_range(kw, start_dt, end_dt)
            n = add_items(items)
            if n:
                print(f"    {kw}: +{n} (社群)")
            time.sleep(1.0)
    else:
        print("\n[2] 跳過 Google CSE（未設 GOOGLE_CSE_API_KEY）")

    # 3. NewsData.io
    if NEWSDATA_API_KEY:
        print("\n[3] NewsData.io...")
        nd_kws = [
            ("海水淡化", "海淡廠", 1),
            ("南水資源分署", "海淡廠", 1),
            ("曾文水庫", "南部水資源", 2),
        ]
        for kw, cat, pri in nd_kws:
            items = fetch_newsdata_range(kw, cat, pri, start_dt, end_dt)
            n = add_items(items)
            if n:
                print(f"    {kw}: +{n}")
            time.sleep(0.5)
    else:
        print("\n[3] 跳過 NewsData.io（未設 NEWSDATA_API_KEY）")

    # 4. PTT 歷史翻頁
    print("\n[4] PTT 歷史翻頁...")
    ptt_boards = ["WaterEngr", "Gossiping", "TW-News", "Tainan", "Environment"]
    for board in ptt_boards:
        items = fetch_ptt_historical(board, start_dt, end_dt, max_pages=30)
        n = add_items(items)
        if n:
            print(f"    {board}: +{n}")
        time.sleep(0.5)

    # 5. Dcard 歷史翻頁
    print("\n[5] Dcard 歷史翻頁...")
    dcard_forums = ["trending", "girl", "marriage", "tainan"]
    for forum in dcard_forums:
        items = fetch_dcard_historical(forum, start_dt, end_dt, max_requests=15)
        n = add_items(items)
        if n:
            print(f"    {forum}: +{n}")
        time.sleep(0.5)

    # 儲存
    out_name = f"hist_{start_dt.isoformat()}_{end_dt.isoformat()}.json"
    out_path = os.path.join(DATA_DIR, out_name)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(all_items, f, ensure_ascii=False, indent=2)

    print(f"\n=== 完成：{len(all_items)} 則 → {out_name} ===")

if __name__ == "__main__":
    main()
