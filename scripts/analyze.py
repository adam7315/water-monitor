"""
使用 Google Gemini API 進行情感分析與澄清文字產生（優化版）
每次分析一則，加入 20 秒執行緒超時，最多分析 30 則
"""
import json, os, time
from datetime import date
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
import google.generativeai as genai

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
TODAY    = date.today().isoformat()
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
MAX_ITEMS = 30
CALL_TIMEOUT = 25  # 秒

def analyze_one(model, item: dict) -> dict:
    title   = item.get("title", "")[:100]
    content = item.get("content", "")[:200]
    source  = item.get("source", "")
    platform= item.get("platform", "")

    prompt = f"""分析這則新聞（繁體中文回答）：
標題：{title}
內容：{content}
來源：{source}（{platform}）

回傳 JSON（不要任何其他文字）：
{{"sentiment":"正面|負面|中立","category":"海淡廠|南部水資源|全台水資源|社群輿情|國際","summary":"30字摘要","priority":"高|中|低","is_credible_threat":false,"line_message":"（負面時填200字澄清，其他留空）"}}

priority規則：高=負面且影響大、中=負面輕微、低=正面或中立"""

    try:
        resp = model.generate_content(prompt)
        text = resp.text.strip().replace("```json","").replace("```","").strip()
        return json.loads(text)
    except Exception as e:
        return {
            "sentiment": "中立",
            "category": item.get("category", "全台水資源"),
            "summary": title[:30],
            "priority": "低",
            "is_credible_threat": False,
            "line_message": ""
        }

def analyze_with_timeout(model, item):
    with ThreadPoolExecutor(max_workers=1) as ex:
        future = ex.submit(analyze_one, model, item)
        try:
            return future.result(timeout=CALL_TIMEOUT)
        except FuturesTimeout:
            print(f"  超時略過：{item.get('title','')[:30]}")
            return {
                "sentiment": "中立", "category": item.get("category","全台水資源"),
                "summary": item.get("title","")[:30], "priority": "低",
                "is_credible_threat": False, "line_message": ""
            }

def main():
    if not GEMINI_API_KEY:
        print("ERROR: GEMINI_API_KEY 未設定"); return

    raw_path = os.path.join(DATA_DIR, f"raw_{TODAY}.json")
    if not os.path.exists(raw_path):
        print(f"找不到原始資料：{raw_path}"); return

    with open(raw_path, encoding="utf-8") as f:
        items = json.load(f)

    # 依優先排序，只取前 MAX_ITEMS 則
    priority_map = {"海淡廠": 1, "社群輿情": 2, "南部水資源": 2, "全台水資源": 3, "國際": 4}
    items.sort(key=lambda x: priority_map.get(x.get("category",""), 5))
    items = items[:MAX_ITEMS]

    print(f"=== 分析 {len(items)} 則新聞（最多 {MAX_ITEMS}）===")
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel("gemini-1.5-flash")

    analyzed = []
    for i, item in enumerate(items):
        print(f"  [{i+1}/{len(items)}] {item.get('title','')[:40]}...")
        result = analyze_with_timeout(model, item)
        merged = {**item, **result, "date": TODAY}
        analyzed.append(merged)
        time.sleep(1)  # 避免 rate limit

    stats = {
        "total": len(analyzed),
        "positive": sum(1 for x in analyzed if x.get("sentiment") == "正面"),
        "negative": sum(1 for x in analyzed if x.get("sentiment") == "負面"),
        "neutral":  sum(1 for x in analyzed if x.get("sentiment") == "中立"),
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
