"""
每日新聞與社群媒體蒐集腳本
來源：
  1. Google News RSS（關鍵字逐一查詢）
  2. 直接台灣新聞源 RSS（中央社、聯合、自由、ETtoday、公視、東森、TVBS、三立）
  3. 國際新聞源 RSS（BBC / Global Times / Xinhua / Japan Times / 香港電台 / 香港01 / 聯合早報）
  4. PTT RSS
  5. Dcard API（實驗性）
  6. Google Custom Search（FB/IG/Dcard）
  7. NewsData.io API（若設定 API key）
"""
import json, os, hashlib, time
from datetime import date, timedelta, datetime
from zoneinfo import ZoneInfo
from urllib.parse import quote, urlparse
import feedparser
import requests

_TW = ZoneInfo('Asia/Taipei')

# 只收 7 天內發布的文章（避免 Google News 翻出舊文）
MAX_AGE_DAYS = 7
CUTOFF_DATE  = datetime.now(_TW).date() - timedelta(days=MAX_AGE_DAYS)

# ── 封鎖垃圾/非新聞網域 ─────────────────────────────────────
DOMAIN_BLACKLIST = {
    "fathomjournal.org",
    "lineshoppingtw.line.me",
    "tripadvisor.com",
    "tripadvisor.com.tw",
    "agoda.com",
    "booking.com",
    "pixnet.net",
    "upskilltw.com",
    "matters.town",
    "ia.gov.tw",          # 政府活動頁（非新聞）
}

def is_junk_url(url: str) -> bool:
    """回傳 True 表示該 URL 應被過濾"""
    if not url:
        return True
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower().lstrip("www.")
        if domain in DOMAIN_BLACKLIST:
            return True
        # LINE TODAY 討論牆（無實際新聞內容）
        if "today.line.me" in domain and "/discuss/" in parsed.path:
            return True
        # 標題含美食/旅遊關鍵字的 Google News 結果
    except Exception:
        pass
    return False

def is_recent(entry) -> bool:
    pp = entry.get("published_parsed")
    if pp:
        try:
            pub = date(pp[0], pp[1], pp[2])
            return pub >= CUTOFF_DATE
        except Exception:
            pass
    return True  # 無日期則放行

def get_pub_date(entry) -> str:
    """從 feedparser entry 取出 YYYY-MM-DD 格式的發布日期（台灣時區）"""
    pp = entry.get("published_parsed")
    if pp:
        try:
            return date(pp[0], pp[1], pp[2]).isoformat()
        except Exception:
            pass
    published = entry.get("published", "")
    if published and len(published) >= 10:
        return published[:10]
    return datetime.now(_TW).date().isoformat()

# ── 關鍵字分組 ─────────────────────────────────────────────
KEYWORDS = {
    # 台南海水淡化廠 + 將軍區（最高優先）
    "海淡廠": [
        "海水淡化廠", "海淡廠", "台南海淡", "臺南海水淡化",
        "南水資源分署", "海水淡化 台南", "海水淡化 將軍",
        "將軍海水淡化", "將軍區 水資源", "將軍漁港",
        "養殖漁業 將軍", "將軍區 養殖", "七股海水淡化",
        "臺南市 海水淡化", "海淡廠 施工", "海淡廠 工程",
        "麥寮海淡", "基隆海淡", "澳底海淡",
    ],
    # 南水資源分署轄區
    "南部水資源": [
        "曾文水庫", "烏山頭水庫", "南化水庫", "白河水庫", "嘉南大圳",
        "仁義潭", "蘭潭水庫",
        "阿公店水庫", "高屏溪攔河堰",
        "牡丹水庫",
        "台東用水", "台東水資源", "台東缺水", "台東水情",
        "卑南大圳", "台東供水",
        "嘉南供水", "台南用水", "嘉義用水", "高雄用水",
        "屏東用水", "南部水情", "南部缺水", "南區水資源",
    ],
    # 全台水資源通用
    "全台水資源": [
        "水情警戒", "限水措施", "水庫蓄水率", "乾旱缺水",
        "水患淹水", "淹水", "水利署", "自來水漲價", "供水問題", "水質污染",
        "水庫水位", "豐水期", "枯水期", "缺水危機",
        "曾文蓄水", "南化蓄水", "高雄缺水", "嘉義缺水",
        "再生水", "水循環", "廢水回收", "水資源回收",
        "自來水公司", "水費調漲", "節水措施",
    ],
    # 國際海水淡化
    "國際": [
        "desalination plant", "seawater desalination",
        "water desalination technology", "reverse osmosis plant",
        "desalination water crisis", "global desalination",
        "desalination Taiwan",
        "海水淡化 國際", "全球海水淡化", "海水淡化 技術",
        "再造水", "中水回用", "海水淡化 香港", "海水淡化 中國",
    ],
}

# 所有關鍵字扁平化（用於掃描直接 RSS）
ALL_KW_FLAT = [(kw, cat) for cat, kws in KEYWORDS.items() for kw in kws]

PRIORITY = {"海淡廠": 1, "南部水資源": 2, "全台水資源": 3, "國際": 4}

# ── 直接新聞源 RSS ──────────────────────────────────────────
DIRECT_RSS_FEEDS = [
    # 中央社
    {"url": "https://feeds.feedburner.com/rsscna/social",     "source": "中央社", "platform": "新聞"},
    {"url": "https://feeds.feedburner.com/rsscna/lifehealth", "source": "中央社", "platform": "新聞"},
    {"url": "https://feeds.feedburner.com/rsscna/finance",    "source": "中央社", "platform": "新聞"},
    {"url": "https://feeds.feedburner.com/rsscna/local",      "source": "中央社", "platform": "新聞"},
    # 聯合新聞網
    {"url": "https://udn.com/rssfeed/news/2/6638?ch=news",         "source": "聯合新聞網", "platform": "新聞"},
    {"url": "https://udn.com/rssfeed/news/2/BREAKINGNEWS?ch=news", "source": "聯合新聞網", "platform": "新聞"},
    # 自由時報
    {"url": "https://news.ltn.com.tw/rss/all.xml",      "source": "自由時報", "platform": "新聞"},
    {"url": "https://news.ltn.com.tw/rss/society.xml",  "source": "自由時報", "platform": "新聞"},
    {"url": "https://news.ltn.com.tw/rss/local.xml",    "source": "自由時報", "platform": "新聞"},
    {"url": "https://news.ltn.com.tw/rss/politics.xml", "source": "自由時報", "platform": "新聞"},
    # ETtoday
    {"url": "https://feeds.feedburner.com/ettoday/realtime", "source": "ETtoday", "platform": "新聞"},
    {"url": "https://feeds.feedburner.com/ettoday/society",  "source": "ETtoday", "platform": "新聞"},
    {"url": "https://feeds.feedburner.com/ettoday/local",    "source": "ETtoday", "platform": "新聞"},
    # 公視新聞
    {"url": "https://news.pts.org.tw/xml/newsfeed.xml", "source": "公視新聞", "platform": "新聞"},
    # 東森新聞（新增）
    {"url": "https://news.ebc.net.tw/rss.xml", "source": "東森新聞", "platform": "新聞"},
    # TVBS（新增）
    {"url": "https://news.tvbs.com.tw/rss/news", "source": "TVBS", "platform": "新聞"},
    # 三立新聞（新增）
    {"url": "https://www.setn.com/rss.aspx", "source": "三立新聞", "platform": "新聞"},
    # 民視新聞（新增）
    {"url": "https://www.ftvnews.com.tw/rss/politics_rss.xml", "source": "民視新聞", "platform": "新聞"},
    # ── 國際新聞源 ──
    # BBC
    {"url": "https://feeds.bbci.co.uk/news/world/rss.xml",                   "source": "BBC News",    "platform": "國際新聞"},
    {"url": "https://feeds.bbci.co.uk/news/world/asia/rss.xml",              "source": "BBC News",    "platform": "國際新聞"},
    {"url": "https://feeds.bbci.co.uk/news/science_and_environment/rss.xml", "source": "BBC News",    "platform": "國際新聞"},
    # 中國
    {"url": "https://www.globaltimes.cn/rssfeeds/outbrain.xml", "source": "Global Times", "platform": "國際新聞"},
    {"url": "http://www.xinhuanet.com/english/rss/worldrss.xml","source": "Xinhua",       "platform": "國際新聞"},
    # 日本
    {"url": "https://www.japantimes.co.jp/feed/", "source": "Japan Times", "platform": "國際新聞"},
    # 香港（新增）
    {"url": "https://rthk.hk/rss/chinese-news.xml",       "source": "香港電台",  "platform": "國際新聞"},
    {"url": "https://www.hk01.com/rss/latest-news",        "source": "香港01",    "platform": "國際新聞"},
    # 新加坡
    {"url": "https://www.zaobao.com.sg/rss/singapore.xml", "source": "聯合早報",  "platform": "國際新聞"},
]

CSE_API_KEY      = os.environ.get("GOOGLE_CSE_API_KEY", "")
CSE_ID           = os.environ.get("GOOGLE_CSE_ID", "964c6016fea3947d5")
NEWSDATA_API_KEY = os.environ.get("NEWSDATA_API_KEY", "")
TODAY            = datetime.now(_TW).date().isoformat()
DATA_DIR         = os.path.join(os.path.dirname(__file__), "..", "data")
os.makedirs(DATA_DIR, exist_ok=True)

seen_hashes: set = set()

def dedup_id(title: str, url: str) -> str:
    return hashlib.md5(f"{title}{url}".encode()).hexdigest()

def match_keywords(text: str) -> tuple:
    """回傳 (category, keyword) 或 (None, None)"""
    text_lower = text.lower()
    for cat in ["海淡廠", "南部水資源", "全台水資源", "國際"]:
        for kw in KEYWORDS[cat]:
            if kw.lower() in text_lower:
                return cat, kw
    return None, None

# ── 1. Google News RSS ────────────────────────────────────────
def fetch_google_news_rss(keyword: str, category: str, priority: int) -> list:
    q = quote(keyword)
    is_en = all(ord(c) < 128 for c in keyword.replace(' ', ''))
    if is_en:
        url = f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
    else:
        url = f"https://news.google.com/rss/search?q={q}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    items = []
    try:
        feed = feedparser.parse(url)
        for entry in feed.entries[:20]:  # 多取再過濾
            if not is_recent(entry):
                continue
            link = entry.get("link", "")
            if is_junk_url(link):
                continue
            # 過濾標題含美食/旅遊符號的文章
            title = entry.get("title", "")
            if any(kw in title for kw in ["美食", "旅遊", "一日遊", "餐廳", "住宿", "❁", "🍽"]):
                continue
            uid = dedup_id(title, link)
            if uid in seen_hashes:
                continue
            seen_hashes.add(uid)
            items.append({
                "id": uid,
                "title": title,
                "url": link,
                "source": entry.get("source", {}).get("title", "Google News"),
                "published": entry.get("published", ""),
                "pub_date": get_pub_date(entry),
                "content": entry.get("summary", "")[:500],
                "keyword": keyword,
                "category": category,
                "priority": priority,
                "platform": "新聞",
                "feed_source": "Google News RSS"
            })
            if len(items) >= 10:
                break
    except Exception as e:
        print(f"  Google RSS 失敗 [{keyword}]: {e}")
    return items

# ── 2. 直接新聞源 RSS ─────────────────────────────────────────
def fetch_direct_rss() -> list:
    items = []
    for feed_cfg in DIRECT_RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_cfg["url"])
            matched = 0
            for entry in feed.entries:
                if not is_recent(entry):
                    continue
                link = entry.get("link", "")
                if is_junk_url(link):
                    continue
                title = entry.get("title", "")
                if any(kw in title for kw in ["美食", "旅遊", "一日遊", "餐廳", "住宿", "❁"]):
                    continue
                text = title + " " + entry.get("summary", "")
                cat, kw = match_keywords(text)
                if not cat:
                    continue
                uid = dedup_id(title, link)
                if uid in seen_hashes:
                    continue
                seen_hashes.add(uid)
                items.append({
                    "id": uid,
                    "title": title,
                    "url": link,
                    "source": feed_cfg["source"],
                    "published": entry.get("published", ""),
                    "pub_date": get_pub_date(entry),
                    "content": entry.get("summary", "")[:500],
                    "keyword": kw,
                    "category": cat,
                    "priority": PRIORITY.get(cat, 3),
                    "platform": feed_cfg["platform"],
                    "feed_source": feed_cfg["source"]
                })
                matched += 1
            print(f"  {feed_cfg['source']} ({feed_cfg['url'].split('/')[-1][:20]}): {len(feed.entries)} 則 → {matched} 則相關")
        except Exception as e:
            print(f"  直接 RSS 失敗 [{feed_cfg['source']}]: {e}")
    return items

# ── 3. PTT RSS ────────────────────────────────────────────────
def fetch_ptt_rss(board: str) -> list:
    url = f"https://www.ptt.cc/bbs/{board}/index.rss"
    items = []
    try:
        feed = feedparser.parse(url)
        for entry in feed.entries[:10]:
            if not is_recent(entry):
                continue
            text = entry.get("title", "") + " " + entry.get("summary", "")
            cat, kw = match_keywords(text)
            if not cat:
                continue
            link = entry.get("link", "")
            uid = dedup_id(entry.get("title", ""), link)
            if uid in seen_hashes:
                continue
            seen_hashes.add(uid)
            items.append({
                "id": uid,
                "title": entry.get("title", ""),
                "url": link,
                "source": f"PTT/{board}",
                "published": entry.get("published", ""),
                "pub_date": get_pub_date(entry),
                "content": entry.get("summary", "")[:500],
                "keyword": kw,
                "category": cat,
                "priority": PRIORITY.get(cat, 3),
                "platform": "PTT",
                "feed_source": "PTT"
            })
    except Exception as e:
        print(f"  PTT RSS 失敗 [{board}]: {e}")
    return items

# ── 4. Dcard API（實驗性）─────────────────────────────────────
def fetch_dcard() -> list:
    """Dcard API 抓水資源相關討論"""
    items = []
    forums = ["water", "environment", "tainan", "kaohsiung", "taiwanpolitics"]
    for forum in forums:
        try:
            r = requests.get(
                "https://www.dcard.tw/service/api/v2/posts",
                params={"forumAlias": forum, "limit": 30},
                headers={"User-Agent": "Mozilla/5.0 (compatible; water-monitor/1.0)"},
                timeout=10
            )
            if r.status_code != 200:
                continue
            posts = r.json()
            if not isinstance(posts, list):
                continue
            for post in posts:
                title   = post.get("title", "")
                excerpt = post.get("excerpt", "")
                text    = title + " " + excerpt
                cat, kw = match_keywords(text)
                if not cat:
                    continue
                post_id = str(post.get("id", ""))
                uid = dedup_id(title, post_id)
                if uid in seen_hashes:
                    continue
                seen_hashes.add(uid)
                created_at = post.get("createdAt", "")
                items.append({
                    "id": uid,
                    "title": title,
                    "url": f"https://www.dcard.tw/f/{forum}/p/{post_id}",
                    "source": f"Dcard/{forum}",
                    "published": created_at,
                    "pub_date": created_at[:10] if created_at else TODAY,
                    "content": excerpt[:500],
                    "keyword": kw,
                    "category": cat,
                    "priority": PRIORITY.get(cat, 3),
                    "platform": "Dcard",
                    "feed_source": "Dcard"
                })
        except Exception as e:
            print(f"  Dcard 失敗 [{forum}]: {e}")
    return items

# ── 5. Google CSE（FB / IG / Dcard）──────────────────────────
def fetch_cse(keyword: str, category: str, priority: int, sites: list) -> list:
    if not CSE_API_KEY:
        return []
    site_filter = " OR ".join([f"site:{s}" for s in sites])
    params = {
        "key": CSE_API_KEY,
        "cx": CSE_ID,
        "q": f"{keyword} ({site_filter})",
        "num": 5,
        "dateRestrict": "d1",
        "lr": "lang_zh-TW"
    }
    items = []
    try:
        r = requests.get("https://www.googleapis.com/customsearch/v1", params=params, timeout=10)
        for item in r.json().get("items", []):
            link = item.get("link", "")
            if is_junk_url(link):
                continue
            uid = dedup_id(item.get("title", ""), link)
            if uid in seen_hashes:
                continue
            seen_hashes.add(uid)
            platform = "FB"
            if "instagram" in link:  platform = "Instagram"
            elif "ptt.cc" in link:   platform = "PTT"
            elif "dcard" in link:    platform = "Dcard"
            items.append({
                "id": uid,
                "title": item.get("title", ""),
                "url": link,
                "source": item.get("displayLink", ""),
                "published": TODAY,
                "pub_date": TODAY,
                "content": item.get("snippet", "")[:500],
                "keyword": keyword,
                "category": category,
                "priority": priority,
                "platform": platform,
                "feed_source": "Google CSE"
            })
    except Exception as e:
        print(f"  CSE 失敗 [{keyword}]: {e}")
    return items

# ── 6. NewsData.io API ────────────────────────────────────────
def fetch_newsdata(keyword: str, category: str, priority: int) -> list:
    if not NEWSDATA_API_KEY:
        return []
    items = []
    try:
        r = requests.get(
            "https://newsdata.io/api/1/news",
            params={
                "apikey": NEWSDATA_API_KEY,
                "q": keyword,
                "country": "tw",
                "language": "zh",
                "size": 5
            },
            timeout=15
        )
        for article in r.json().get("results", []):
            link = article.get("link", "")
            if is_junk_url(link):
                continue
            uid = dedup_id(article.get("title", ""), link)
            if uid in seen_hashes:
                continue
            seen_hashes.add(uid)
            pub = article.get("pubDate", "")
            items.append({
                "id": uid,
                "title": article.get("title", ""),
                "url": link,
                "source": article.get("source_id", "NewsData"),
                "published": pub,
                "pub_date": pub[:10] if pub else TODAY,
                "content": (article.get("description", "") or "")[:500],
                "keyword": keyword,
                "category": category,
                "priority": priority,
                "platform": "新聞",
                "feed_source": "NewsData.io"
            })
    except Exception as e:
        print(f"  NewsData.io 失敗 [{keyword}]: {e}")
    return items

# ── 主程式 ────────────────────────────────────────────────────
def main():
    all_items = []
    print(f"=== 開始蒐集 {TODAY}（收錄 {MAX_AGE_DAYS} 天內新聞）===")

    # 1. Google News RSS（關鍵字查詢）
    for category, keywords in KEYWORDS.items():
        pri = PRIORITY[category]
        print(f"\n[{category}] Google News RSS...")
        for kw in keywords:
            items = fetch_google_news_rss(kw, category, pri)
            if items:
                print(f"  {kw}: {len(items)} 則")
            all_items.extend(items)

    # 2. 直接新聞源（台灣 + 國際，全量掃描）
    print(f"\n[直接新聞源] 台灣：中央社/聯合/自由/ETtoday/公視/東森/TVBS/三立/民視")
    print(f"             國際：BBC/Global Times/Xinhua/Japan Times/香港電台/香港01/聯合早報...")
    direct_items = fetch_direct_rss()
    all_items.extend(direct_items)
    print(f"  直接新聞源合計：{len(direct_items)} 則相關")

    # 3. PTT
    print(f"\n[社群] PTT...")
    for board in ["WaterEngr", "Gossiping", "TW-News", "Environment", "Tainan",
                  "kaohsiung", "Taichung", "publicissue"]:
        items = fetch_ptt_rss(board)
        print(f"  {board}: {len(items)} 則相關")
        all_items.extend(items)

    # 4. Dcard（實驗性）
    print(f"\n[社群] Dcard...")
    dcard_items = fetch_dcard()
    print(f"  Dcard 合計：{len(dcard_items)} 則相關")
    all_items.extend(dcard_items)

    # 5. Google CSE（FB/IG/Dcard）
    if CSE_API_KEY:
        print(f"\n[社群] Google CSE (FB/IG/Dcard)...")
        social_sites = ["facebook.com", "instagram.com", "dcard.tw"]
        for kw in ["海水淡化廠", "南水資源", "台南缺水", "水庫蓄水"]:
            items = fetch_cse(kw, "社群輿情", 1, social_sites)
            print(f"  {kw}: {len(items)} 則")
            all_items.extend(items)
    else:
        print("\n[社群] 跳過 CSE（未設 API key）")

    # 6. NewsData.io（若設定 key）
    if NEWSDATA_API_KEY:
        print(f"\n[NewsData.io] 關鍵字查詢...")
        nd_keywords = [
            ("海水淡化", "海淡廠", 1),
            ("南水資源分署", "海淡廠", 1),
            ("曾文水庫", "南部水資源", 2),
            ("台南缺水", "全台水資源", 3),
        ]
        for kw, cat, pri in nd_keywords:
            items = fetch_newsdata(kw, cat, pri)
            print(f"  {kw}: {len(items)} 則")
            all_items.extend(items)
            time.sleep(0.5)
    else:
        print("\n[NewsData.io] 跳過（未設 NEWSDATA_API_KEY）")

    # 儲存
    out_path = os.path.join(DATA_DIR, f"raw_{TODAY}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(all_items, f, ensure_ascii=False, indent=2)

    from collections import Counter
    by_source = Counter(x.get("feed_source", "?") for x in all_items)
    print(f"\n=== 共蒐集 {len(all_items)} 則 ===")
    for src, cnt in by_source.most_common():
        print(f"  {src}: {cnt} 則")
    print(f"儲存至 {out_path}")

if __name__ == "__main__":
    main()
