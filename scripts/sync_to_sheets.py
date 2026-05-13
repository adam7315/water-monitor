"""
每日新聞同步至 Google Sheets
讀取 analyzed_{TODAY}.json，批次 POST 到 Apps Script Web App
"""
import json, os, requests
from datetime import date

SHEETS_API_URL = os.environ.get(
    "SHEETS_API_URL",
    "https://script.google.com/macros/s/AKfycbxTvnw8nXbSVc5fRim0nvX6gaLiR3yRVuT2e_faTUh_95hRFJfp5Ts4rC60LqZMrXb-/exec"
)
TODAY    = date.today().isoformat()
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")

def main():
    raw_path = os.path.join(DATA_DIR, f"analyzed_{TODAY}.json")
    if not os.path.exists(raw_path):
        print(f"找不到分析資料：{raw_path}"); return

    with open(raw_path, encoding="utf-8") as f:
        data = json.load(f)

    items = data.get("items", [])
    if not items:
        print("無資料可同步"); return

    payload = {"type": "daily", "items": items}
    try:
        r = requests.post(SHEETS_API_URL, json=payload, timeout=30)
        result = r.json()
        print(f"同步完成：{result.get('count', '?')} 則 → Google Sheets")
    except Exception as e:
        print(f"同步失敗：{e}")

if __name__ == "__main__":
    main()
