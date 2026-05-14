"""
輿情分析：關鍵字預分類 → 情感判斷 + 優先度
AI 澄清文稿不在此生成，由前端使用者手動點「澄清文稿」按鈕觸發。

v1：修正 date 欄位 — 改用文章實際發布日期（published），而非收集當天
"""
import json, os, re
from datetime import datetime
from zoneinfo import ZoneInfo

TODAY    = datetime.now(ZoneInfo('Asia/Taipei')).date().isoformat()
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
MAX_ITEMS = 30

# ── 關鍵字分類規則 ──────────────────────────────────────────
NEGATIVE_KEYWORDS = [
    # 直接抗議/不滿（最高權重）
    "抗議", "陳情", "抗爭", "示威", "連署", "反對", "怒", "憤",
    "抱怨", "不滿", "生氣", "憤怒", "民怨", "居民反彈", "居民抗議",
    "漁民抗議", "養殖業者反對", "環團抗議",
    # 批評/負面評價
    "批評", "質疑", "投訴", "申訴", "檢舉", "爭議", "糾紛",
    "弊端", "失職", "延誤", "失敗", "停擺", "敷衍",
    # 缺水/水質問題
    "缺水", "乾旱", "限水", "停水", "水荒", "汙染", "污染", "水質",
    "漏水", "管線破裂", "供水不足", "水庫低", "蓄水不足",
    # 警示/風險
    "危機", "警戒", "警告", "風險", "威脅", "衝擊", "損害",
    # 英文
    "water crisis", "water shortage", "contamination", "protest", "oppose"
]
POSITIVE_KEYWORDS = [
    "完工", "啟用", "通水", "竣工", "提升", "改善", "增加", "擴充",
    "節水", "豐水", "蓄水充足", "水情穩定", "供水穩定",
    "榮獲", "獲獎", "表揚", "肯定", "成功", "突破"
]

def normalize_pub_date(pub_str: str, fallback: str = TODAY) -> str:
    """將任意格式的日期字串轉為 YYYY-MM-DD，解析失敗則回傳 fallback。"""
    if not pub_str:
        return fallback
    s = str(pub_str).strip()
    # 已是 YYYY-MM-DD 開頭
    if re.match(r'^\d{4}-\d{2}-\d{2}', s):
        return s[:10]
    # RFC 2822：Wed, 14 May 2026 02:32:00 GMT / +0800 / +0000
    for fmt in [
        "%a, %d %b %Y %H:%M:%S %Z",
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S",
    ]:
        try:
            return datetime.strptime(s[:31].strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    # ISO 8601：2026-05-14T10:32:00
    try:
        return datetime.strptime(s[:19], "%Y-%m-%dT%H:%M:%S").strftime("%Y-%m-%d")
    except ValueError:
        pass
    # 其他常見格式
    for fmt in ["%Y/%m/%d", "%d/%m/%Y", "%B %d, %Y"]:
        try:
            return datetime.strptime(s[:20].strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return fallback

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

    # 依類別優先排序，只取前 MAX_ITEMS
    priority_map = {"海淡廠": 1, "社群輿情": 2, "南部水資源": 2, "全台水資源": 3, "國際": 4}
    items.sort(key=lambda x: priority_map.get(x.get("category", ""), 5))
    items = items[:MAX_ITEMS]

    print(f"=== 分析 {len(items)} 則新聞（最多 {MAX_ITEMS}）===")

    analyzed = []
    for i, item in enumerate(items):
        title = item.get("title", "")
        text  = title + " " + item.get("content", "")

        sentiment = keyword_classify(text)
        category  = item.get("category", "全台水資源")
        priority  = keyword_priority(sentiment, category)

        # 用文章實際發布日期，而非收集當天
        article_date = normalize_pub_date(item.get("published", ""), fallback=TODAY)

        print(f"  [{i+1}/{len(items)}] {sentiment} [{article_date}] {title[:40]}...")

        merged = {
            **item,
            "sentiment": sentiment,
            "category": category,
            "summary": title[:30],
            "priority": priority,
            "is_credible_threat": sentiment == "負面" and priority == "高",
            "line_message": "",
            "date": article_date,          # 文章實際發布日期
            "collected_date": TODAY        # 收集日期（保留備查）
        }
        analyzed.append(merged)

    stats = {
        "total":        len(analyzed),
        "positive":     sum(1 for x in analyzed if x.get("sentiment") == "正面"),
        "negative":     sum(1 for x in analyzed if x.get("sentiment") == "負面"),
        "neutral":      sum(1 for x in analyzed if x.get("sentiment") == "中立"),
        "high_priority":sum(1 for x in analyzed if x.get("priority") == "高"),
        "date": TODAY
    }

    out_path = os.path.join(DATA_DIR, f"analyzed_{TODAY}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"stats": stats, "items": analyzed}, f, ensure_ascii=False, indent=2)

    print(f"\n正面:{stats['positive']} 負面:{stats['negative']} 中立:{stats['neutral']} 高優先:{stats['high_priority']}")
    print(f"完成 → {out_path}")

if __name__ == "__main__":
    main()
