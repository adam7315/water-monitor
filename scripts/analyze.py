"""
輿情分析：關鍵字預分類 + Gemini REST API（僅負面項目呼叫）
使用 requests 直接呼叫 REST API，支援真正的 HTTP 超時
"""
import json, os, time, requests
from datetime import date

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
TODAY    = date.today().isoformat()
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
MAX_ITEMS = 30
API_TIMEOUT = 20  # 秒，requests HTTP 超時

GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-1.5-flash:generateContent?key={key}"
)

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

def gemini_clarify(item: dict) -> str:
    title   = item.get("title", "")[:100]
    content = item.get("content", "")[:200]
    source  = item.get("source", "")
    prompt = (
        f"這則新聞被判斷為負面輿情，請用繁體中文撰寫一段約200字的澄清說明，"
        f"適合直接傳送到 LINE 群組使用。\n"
        f"標題：{title}\n內容：{content}\n來源：{source}\n\n"
        f"只回傳澄清文字，不要任何標題或前言。"
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"maxOutputTokens": 400, "temperature": 0.3}
    }
    try:
        r = requests.post(
            GEMINI_URL.format(key=GEMINI_API_KEY),
            json=payload,
            timeout=API_TIMEOUT
        )
        r.raise_for_status()
        data = r.json()
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception as e:
        print(f"    Gemini 失敗：{e}")
        return ""

def main():
    if not GEMINI_API_KEY:
        print("ERROR: GEMINI_API_KEY 未設定"); return

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
    neg_count = 0
    for i, item in enumerate(items):
        title = item.get("title", "")
        text  = title + " " + item.get("content", "")

        sentiment = keyword_classify(text)
        category  = item.get("category", "全台水資源")
        priority  = keyword_priority(sentiment, category)
        summary   = title[:30]
        line_msg  = ""

        print(f"  [{i+1}/{len(items)}] {sentiment} {title[:40]}...")

        if sentiment == "負面":
            neg_count += 1
            print(f"    → 呼叫 Gemini 產生澄清文字（第 {neg_count} 則負面）")
            line_msg = gemini_clarify(item)
            time.sleep(2)  # 避免 rate limit

        merged = {
            **item,
            "sentiment": sentiment,
            "category": category,
            "summary": summary,
            "priority": priority,
            "is_credible_threat": sentiment == "負面" and priority == "高",
            "line_message": line_msg,
            "date": TODAY
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
    print(f"Gemini 呼叫次數：{neg_count}（僅負面項目）")
    print(f"完成 → {out_path}")

if __name__ == "__main__":
    main()
