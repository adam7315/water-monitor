"""
歷史資料回填至 Google Sheets（每日新聞歸檔）
讀取所有 analyzed_*.json，分批 POST 到 Apps Script Web App
"""
import json, os, glob, time, requests
from datetime import date

SHEETS_API_URL = (
    "https://script.google.com/macros/s/"
    "AKfycbxTvnw8nXbSVc5fRim0nvX6gaLiR3yRVuT2e_faTUh_95hRFJfp5Ts4rC60LqZMrXb-/exec"
)
DATA_DIR   = os.path.join(os.path.dirname(__file__), "..", "data")
START_DATE = "2025-04-01"  # 只送這個日期之後的資料
BATCH_SIZE = 50            # Apps Script 每次最多處理筆數

def main():
    files = sorted(glob.glob(os.path.join(DATA_DIR, "analyzed_*.json")))
    files = [f for f in files if os.path.basename(f).replace("analyzed_","").replace(".json","") >= START_DATE]

    all_items = []
    for fpath in files:
        d = os.path.basename(fpath).replace("analyzed_","").replace(".json","")
        with open(fpath, encoding="utf-8") as f:
            data = json.load(f)
        items = data.get("items", [])
        # 補齊 date 欄位
        for item in items:
            if not item.get("date"):
                item["date"] = d
        all_items.extend(items)

    print(f"共 {len(all_items)} 則資料，日期範圍 {files[0][-15:-5]} ~ {files[-1][-15:-5]}")
    print(f"分批傳送（每批 {BATCH_SIZE} 則）...")

    total_sent = 0
    for i in range(0, len(all_items), BATCH_SIZE):
        batch = all_items[i:i+BATCH_SIZE]
        try:
            r = requests.post(
                SHEETS_API_URL,
                json={"type": "daily", "items": batch},
                timeout=60
            )
            result = r.json()
            total_sent += result.get("count", len(batch))
            print(f"  批次 {i//BATCH_SIZE+1}：{result}")
        except Exception as e:
            print(f"  批次 {i//BATCH_SIZE+1} 失敗：{e}")
        time.sleep(2)  # 避免 Apps Script rate limit

    print(f"\n完成！共寫入 {total_sent} 則至 Google Sheets")

if __name__ == "__main__":
    main()
