"""
從競爭對手公開的 Google Sheets 匯入歷史資料
轉換為系統格式，生成 data/analyzed_YYYY-MM-DD.json
"""
import json, os, csv, io, hashlib, requests
from datetime import date, timedelta
from collections import defaultdict

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
os.makedirs(DATA_DIR, exist_ok=True)

SHEETS_CSV = (
    "https://docs.google.com/spreadsheets/d/"
    "1c2qO-a1GMXu6QBb1578C713wEp83C_w_CO59jwm_5xY/export?format=csv"
)

# ── 情感關鍵字（與 analyze.py 一致）──────────────────────────
NEGATIVE_KEYWORDS = [
    "缺水","乾旱","限水","停水","水荒","汙染","污染","水質",
    "抗議","反對","爭議","危機","警戒","警告","風險","問題",
    "漏水","管線破裂","供水不足","蓄水不足","水庫低",
    "民怨","投訴","批評","質疑","延誤","失敗","弊端",
    "water crisis","water shortage","contamination",
    "嚴峻","告急","吃緊","不足","跌破","剩","偏低"
]
POSITIVE_KEYWORDS = [
    "完工","啟用","通水","竣工","提升","改善","增加","擴充",
    "節水","豐水","蓄水充足","水情穩定","供水穩定","可控",
    "榮獲","獲獎","表揚","肯定","成功","突破","穩定供水","無虞"
]

# ── 分類關鍵字 ───────────────────────────────────────────────
HAIDAN_KEYWORDS = ["海淡廠","海水淡化","desalination","將軍","南水","鹵水"]
SOUTH_KEYWORDS  = ["曾文","烏山頭","南化","白河","嘉南","台南","臺南","南部","南區"]

def kw_classify_sentiment(text):
    t = text.lower()
    neg = sum(1 for k in NEGATIVE_KEYWORDS if k in t)
    pos = sum(1 for k in POSITIVE_KEYWORDS if k in t)
    if neg > pos:   return "負面"
    elif pos > 0:   return "正面"
    return "中立"

def kw_classify_category(title, src_cat):
    # 先用 source category 判斷
    if "海淡廠" in src_cat:  return "海淡廠"
    if "正向" in src_cat:    return "南部水資源"
    # 再用標題關鍵字
    t = title
    if any(k in t for k in HAIDAN_KEYWORDS): return "海淡廠"
    if any(k in t for k in SOUTH_KEYWORDS):  return "南部水資源"
    return "全台水資源"

def kw_priority(sentiment, category):
    if sentiment == "負面":
        return "高" if category in ("海淡廠","南部水資源") else "中"
    return "低"

def uid(title, url):
    return hashlib.md5(f"{title}{url}".encode()).hexdigest()

def main():
    print("=== 下載競爭對手公開資料 ===")
    r = requests.get(SHEETS_CSV, timeout=20)
    r.encoding = "utf-8"
    reader = csv.DictReader(io.StringIO(r.text))
    rows = list(reader)
    print(f"取得 {len(rows)} 筆原始資料")

    # 依日期分組
    by_date = defaultdict(list)
    for row in rows:
        d = row.get("日期","").strip()
        if d and len(d) >= 10:
            by_date[d[:10]].append(row)

    # 只處理有資料的日期（或依需求指定範圍）
    today      = date.today()
    cutoff     = (today - timedelta(days=90)).isoformat()  # 近3個月
    target_dates = sorted([d for d in by_date if d >= cutoff])

    print(f"近3個月有資料的天數：{len(target_dates)}")

    created = 0
    for day in target_dates:
        out_path = os.path.join(DATA_DIR, f"analyzed_{day}.json")
        # 不覆蓋已有的 AI 分析資料
        if os.path.exists(out_path):
            print(f"  跳過 {day}（已有 AI 分析資料）")
            continue

        items = []
        for row in by_date[day]:
            title  = row.get("標題","").strip()
            url    = row.get("網址","").strip()
            source = row.get("來源","").strip()
            cat_s  = row.get("分類","").strip()

            category  = kw_classify_category(title, cat_s)
            sentiment = kw_classify_sentiment(title)
            priority  = kw_priority(sentiment, category)

            items.append({
                "id":        uid(title, url),
                "title":     title,
                "url":       url,
                "source":    source,
                "published": day,
                "content":   "",
                "keyword":   cat_s,
                "category":  category,
                "priority":  priority,
                "platform":  "新聞",
                "sentiment": sentiment,
                "summary":   title[:30],
                "is_credible_threat": sentiment == "負面" and priority == "高",
                "line_message": "",
                "date":      day,
            })

        stats = {
            "total":         len(items),
            "positive":      sum(1 for x in items if x["sentiment"] == "正面"),
            "negative":      sum(1 for x in items if x["sentiment"] == "負面"),
            "neutral":       sum(1 for x in items if x["sentiment"] == "中立"),
            "high_priority": sum(1 for x in items if x["priority"] == "高"),
            "date": day,
        }

        with open(out_path, "w", encoding="utf-8") as f:
            json.dump({"stats": stats, "items": items}, f, ensure_ascii=False, indent=2)

        print(f"  {day}: {len(items)}則 (負面{stats['negative']} 正面{stats['positive']})")
        created += 1

    print(f"\n完成：建立 {created} 天歷史資料")

if __name__ == "__main__":
    main()
