"""
輿情分析：關鍵字預分類 → 情感判斷 + 優先度
AI 澄清文稿不在此生成，由前端使用者手動點「AI文稿」按鈕觸發。
"""
import json, os
from datetime import datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

_TW = ZoneInfo('Asia/Taipei')
TODAY    = datetime.now(_TW).date().isoformat()
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
MAX_ITEMS = 300  # 由 200 提升至 300，確保國際類有足夠空間

# ── 封鎖垃圾/非新聞網域（與 collect_news.py 保持一致）──────
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
    "ia.gov.tw",
}

# 封鎖特定 source（Google News 重導向 URL 看不出原始域名，需靠 source 欄）
SOURCE_BLACKLIST = {
    "ia.gov.tw",   # 政府活動頁，非新聞
    "Fathom Journal",
    "fathomjournal.org",
}

def is_junk_url(url: str) -> bool:
    if not url:
        return True
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower().lstrip("www.")
        if domain in DOMAIN_BLACKLIST:
            return True
        if "today.line.me" in domain and "/discuss/" in parsed.path:
            return True
    except Exception:
        pass
    return False

def is_junk_title(title: str) -> bool:
    """過濾明顯非新聞的標題"""
    junk_markers = ["美食", "旅遊", "一日遊", "餐廳", "住宿", "❁", "🍽", "秘境"]
    return any(m in title for m in junk_markers)

def extract_pub_date(item: dict) -> str:
    """從 item 的 published/pub_date 欄位解析出 YYYY-MM-DD"""
    # 優先使用已有的 pub_date
    if item.get("pub_date") and len(item["pub_date"]) >= 10:
        return item["pub_date"][:10]
    published = item.get("published", "")
    if not published:
        return TODAY
    # RFC 2822 格式（RSS 標準）
    try:
        dt = parsedate_to_datetime(published)
        return dt.astimezone(_TW).date().isoformat()
    except Exception:
        pass
    # ISO 8601 格式
    try:
        dt = datetime.fromisoformat(published.replace("Z", "+00:00"))
        return dt.astimezone(_TW).date().isoformat()
    except Exception:
        pass
    # 直接取前 10 字元
    if len(published) >= 10 and published[4:5] in ("-", "/"):
        return published[:10].replace("/", "-")
    return TODAY

# ── 關鍵字分類規則 ──────────────────────────────────────────
NEGATIVE_KEYWORDS = [
    # 直接抗議/不滿
    "抗議", "陳情", "抗爭", "示威", "連署", "反對", "怒", "憤",
    "抱怨", "不滿", "生氣", "憤怒", "民怨", "居民反彈", "居民抗議",
    "漁民抗議", "養殖業者反對", "環團抗議",
    # 批評/負面評價
    "批評", "質疑", "投訴", "申訴", "檢舉", "爭議", "糾紛",
    "弊端", "失職", "延誤", "失敗", "停擺", "敷衍",
    # 缺水/水質問題
    "缺水", "乾旱", "限水", "停水", "水荒", "汙染", "污染", "水質",
    "漏水", "管線破裂", "供水不足", "水庫低", "蓄水不足",
    # 洪水/警示/風險
    "淹水", "危機", "警戒", "警告", "風險", "威脅", "衝擊", "損害",
    # 英文
    "water crisis", "water shortage", "contamination", "protest", "oppose"
]
POSITIVE_KEYWORDS = [
    "完工", "啟用", "通水", "竣工", "提升", "改善", "增加", "擴充",
    "節水", "豐水", "蓄水充足", "水情穩定", "供水穩定",
    "榮獲", "獲獎", "表揚", "肯定", "成功", "突破"
]

def keyword_classify(text: str) -> str:
    t = text.lower()
    neg_score = sum(1 for kw in NEGATIVE_KEYWORDS if kw in t)
    pos_score = sum(1 for kw in POSITIVE_KEYWORDS if kw in t)
    if neg_score > pos_score:
        return "負面"
    elif pos_score > 0:
        return "正面"
    return "中立"

def keyword_priority(sentiment: str, category: str) -> str:
    if sentiment == "負面":
        if category in ("海淡廠", "南部水資源"):
            return "高"
        return "中"
    return "低"

def main():
    raw_path = os.path.join(DATA_DIR, f"raw_{TODAY}.json")
    if not os.path.exists(raw_path):
        print(f"找不到原始資料：{raw_path}"); return

    with open(raw_path, encoding="utf-8") as f:
        items = json.load(f)

    print(f"原始資料：{len(items)} 則")

    # ── 品質過濾 ────────────────────────────────────────────
    # 1. 過濾垃圾 URL / 標題 / 來源
    items = [x for x in items
             if not is_junk_url(x.get("url", ""))
             and not is_junk_title(x.get("title", ""))
             and x.get("source", "") not in SOURCE_BLACKLIST]
    print(f"過濾垃圾後：{len(items)} 則")

    # 2. URL 去重（analyze 層再做一道保險）
    seen_urls: set = set()
    deduped = []
    for item in items:
        url = item.get("url", "")
        if url and url not in seen_urls:
            seen_urls.add(url)
            deduped.append(item)
        elif not url:
            deduped.append(item)
    items = deduped
    print(f"去重後：{len(items)} 則")

    # 3. 舊文過濾：pub_date 超過 14 天且非負面 → 移除
    # （Google News 有時翻出舊文配上近期日期，這類非負面舊文不具監控價值）
    from datetime import date as _date, timedelta
    _cutoff = _date.fromisoformat(TODAY) - timedelta(days=14)

    def _is_old_nonneg(item: dict) -> bool:
        pd = item.get("pub_date", "") or item.get("date", "")
        if not pd or len(pd) < 10:
            return False
        try:
            pub = _date.fromisoformat(pd[:10])
            return pub < _cutoff
        except Exception:
            return False

    before_old = len(items)
    # 先做情感分類，以便用來決定是否保留
    def _quick_sentiment(item: dict) -> str:
        text = (item.get("title", "") + " " + item.get("content", "")).lower()
        neg_score = sum(1 for kw in NEGATIVE_KEYWORDS if kw in text)
        pos_score = sum(1 for kw in POSITIVE_KEYWORDS if kw in text)
        if neg_score > pos_score:
            return "負面"
        elif pos_score > 0:
            return "正面"
        return "中立"

    items = [x for x in items
             if not _is_old_nonneg(x) or _quick_sentiment(x) == "負面"]
    print(f"舊文非負面過濾後：{len(items)} 則（移除 {before_old - len(items)} 篇）")

    # 3. 每類別保留配額，再合併排序（確保國際類不被截掉）
    CATEGORY_QUOTA = {"海淡廠": 50, "社群輿情": 30, "南部水資源": 100, "全台水資源": 80, "國際": 80}
    by_cat: dict = {}
    for item in items:
        c = item.get("category", "全台水資源")
        by_cat.setdefault(c, []).append(item)

    selected = []
    for cat, quota in CATEGORY_QUOTA.items():
        cat_items = by_cat.get(cat, [])
        selected.extend(cat_items[:quota])
    # 其他未分類
    for cat, cat_items in by_cat.items():
        if cat not in CATEGORY_QUOTA:
            selected.extend(cat_items[:20])

    # 依優先級排序後取 MAX_ITEMS
    priority_map = {"海淡廠": 1, "社群輿情": 2, "南部水資源": 2, "全台水資源": 3, "國際": 4}
    selected.sort(key=lambda x: priority_map.get(x.get("category", ""), 5))
    items = selected[:MAX_ITEMS]

    print(f"=== 分析 {len(items)} 則新聞（最多 {MAX_ITEMS}）===")

    analyzed = []
    for i, item in enumerate(items):
        title    = item.get("title", "")
        text     = title + " " + item.get("content", "")
        sentiment = keyword_classify(text)
        category  = item.get("category", "全台水資源")
        priority  = keyword_priority(sentiment, category)
        pub_date  = extract_pub_date(item)

        print(f"  [{i+1}/{len(items)}] {sentiment} {title[:40]}...")

        merged = {
            **item,
            "sentiment":          sentiment,
            "category":           category,
            "summary":            title[:30],
            "priority":           priority,
            "is_credible_threat": sentiment == "負面" and priority == "高",
            "line_message":       "",
            "pub_date":           pub_date,
            "date":               TODAY,
        }
        analyzed.append(merged)

    stats = {
        "total":         len(analyzed),
        "positive":      sum(1 for x in analyzed if x.get("sentiment") == "正面"),
        "negative":      sum(1 for x in analyzed if x.get("sentiment") == "負面"),
        "neutral":       sum(1 for x in analyzed if x.get("sentiment") == "中立"),
        "high_priority": sum(1 for x in analyzed if x.get("priority") == "高"),
        "date": TODAY
    }

    out_path = os.path.join(DATA_DIR, f"analyzed_{TODAY}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"stats": stats, "items": analyzed}, f, ensure_ascii=False, indent=2)

    print(f"\n正面:{stats['positive']} 負面:{stats['negative']} 中立:{stats['neutral']} 高優先:{stats['high_priority']}")
    print(f"完成 → {out_path}")

if __name__ == "__main__":
    main()
