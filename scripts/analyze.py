"""
使用 Google Gemini API 進行情感分析與澄清文字產生
"""
import json, os, time
from datetime import date
import google.generativeai as genai

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
TODAY    = date.today().isoformat()
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")

SYSTEM_PROMPT = """你是政府水利機關（水利署南水資源分署）的公關幕僚。
請分析以下新聞或社群貼文的情感傾向，並在負面時提供澄清建議。

判斷規則：
- 正面：民眾或媒體對水利設施、政策表示支持、感謝、讚賞
- 負面：批評、抱怨、質疑、反對、散布恐慌、不實指控
- 中立：純資訊報導、無明顯立場

澄清文字要求（僅負面時產生）：
- 繁體中文、政府公文口吻
- 200字以內
- 格式：「感謝關心～，實際情況為～，歡迎民眾～」
- 不要承認錯誤，聚焦說明實際情況"""

def analyze_batch(items: list, model) -> list:
    """一次分析最多 5 則新聞"""
    batch_text = ""
    for i, item in enumerate(items):
        batch_text += f"""
---文章{i+1}---
標題：{item.get('title','')}
內容：{item.get('content','')[:300]}
來源：{item.get('source','')} ({item.get('platform','')})
"""

    prompt = f"""{SYSTEM_PROMPT}

請分析以下 {len(items)} 則文章，回傳 JSON 陣列（每則對應一個物件）：

{batch_text}

回傳格式（嚴格 JSON，不要有其他文字）：
[
  {{
    "sentiment": "正面|負面|中立",
    "category": "海淡廠|南部水資源|全台水資源|社群輿情|國際",
    "summary": "50字以內摘要",
    "is_credible_threat": false,
    "line_message": "澄清建議（負面才寫，其他留空字串）",
    "priority": "高|中|低",
    "reason": "判斷理由（20字）"
  }}
]

priority 判斷：高=負面且可能屬實且易擴散、中=負面但影響有限、低=正面或中立"""

    try:
        response = model.generate_content(prompt)
        text = response.text.strip()
        # 清除 markdown code block
        text = text.replace("```json", "").replace("```", "").strip()
        results = json.loads(text)
        if len(results) != len(items):
            raise ValueError(f"回傳數量不符：期待 {len(items)}，實得 {len(results)}")
        return results
    except Exception as e:
        print(f"  Gemini 分析失敗：{e}")
        return [{"sentiment": "中立", "category": items[i].get("category","全台水資源"),
                 "summary": items[i].get("title","")[:50], "is_credible_threat": False,
                 "line_message": "", "priority": "低", "reason": "分析失敗"} for i in range(len(items))]

def main():
    if not GEMINI_API_KEY:
        print("ERROR: GEMINI_API_KEY 未設定")
        return

    raw_path = os.path.join(DATA_DIR, f"raw_{TODAY}.json")
    if not os.path.exists(raw_path):
        print(f"找不到原始資料：{raw_path}")
        return

    with open(raw_path, encoding="utf-8") as f:
        items = json.load(f)

    print(f"=== 開始分析 {len(items)} 則新聞 ===")
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel("gemini-1.5-flash")

    analyzed = []
    batch_size = 5

    for i in range(0, len(items), batch_size):
        batch = items[i:i+batch_size]
        print(f"  分析第 {i+1}~{i+len(batch)} 則...")
        results = analyze_batch(batch, model)
        for item, result in zip(batch, results):
            merged = {**item, **result}
            merged["date"] = TODAY
            analyzed.append(merged)
        time.sleep(2)  # 避免超過 rate limit

    # 依優先級排序：高>中>低，同級依 priority 排
    priority_order = {"高": 0, "中": 1, "低": 2}
    analyzed.sort(key=lambda x: (
        priority_order.get(x.get("priority","低"), 2),
        x.get("priority_num", 9)
    ))

    # 統計
    stats = {
        "total": len(analyzed),
        "positive": sum(1 for x in analyzed if x.get("sentiment") == "正面"),
        "negative": sum(1 for x in analyzed if x.get("sentiment") == "負面"),
        "neutral":  sum(1 for x in analyzed if x.get("sentiment") == "中立"),
        "high_priority": sum(1 for x in analyzed if x.get("priority") == "高"),
        "date": TODAY
    }

    out = {"stats": stats, "items": analyzed}
    out_path = os.path.join(DATA_DIR, f"analyzed_{TODAY}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"\n=== 分析完成 ===")
    print(f"  正面：{stats['positive']} | 負面：{stats['negative']} | 中立：{stats['neutral']}")
    print(f"  高優先：{stats['high_priority']} 則需立即處理")
    print(f"  儲存至 {out_path}")

if __name__ == "__main__":
    main()
