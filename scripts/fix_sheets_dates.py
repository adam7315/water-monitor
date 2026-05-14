"""
批次將 Google Sheets「日期」欄位更新為實際發布日（pub_date）
讀取所有 analyzed_*.json → 建立 URL→pub_date 對照 → 呼叫 Apps Script batchUpdateDates
"""
import json, os, glob, requests
from datetime import datetime
from zoneinfo import ZoneInfo

SHEETS_API_URL = os.environ.get(
    "SHEETS_API_URL",
    "https://script.google.com/macros/s/AKfycbxTvnw8nXbSVc5fRim0nvX6gaLiR3yRVuT2e_faTUh_95hRFJfp5Ts4rC60LqZMrXb-/exec"
)
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")

def main():
    # 建立 URL → pub_date 對照表（全部 analyzed JSON）
    url_to_pubdate = {}
    pattern = os.path.join(DATA_DIR, "analyzed_*.json")
    files = sorted(glob.glob(pattern))
    print(f"讀取 {len(files)} 個 analyzed JSON 檔案...")

    for f in files:
        try:
            with open(f, encoding="utf-8") as fp:
                data = json.load(fp)
            items = data.get("items", [])
            for item in items:
                url     = item.get("url", "")
                pub_date = item.get("pub_date", "") or item.get("date", "")
                if url and pub_date:
                    url_to_pubdate[url] = pub_date[:10]  # 只取 YYYY-MM-DD
        except Exception as ex:
            print(f"  跳過 {os.path.basename(f)}: {ex}")

    print(f"共建立 {len(url_to_pubdate)} 筆 URL→pub_date 對照")

    # 分批傳送（每批 200 筆，避免請求過大）
    updates = [{"url": u, "pub_date": d} for u, d in url_to_pubdate.items()]
    batch_size = 200
    total_updated = 0

    for i in range(0, len(updates), batch_size):
        batch = updates[i:i+batch_size]
        print(f"  傳送第 {i//batch_size+1} 批（{len(batch)} 筆）...", end=" ", flush=True)
        try:
            r = requests.post(
                SHEETS_API_URL,
                json={"action": "batchUpdateDates", "updates": batch},
                timeout=60
            )
            result = r.json()
            updated = result.get("updated", 0)
            total_updated += updated
            print(f"更新 {updated} 筆")
            if result.get("status") == "error":
                print(f"  錯誤：{result.get('message')}")
                break
        except Exception as ex:
            print(f"失敗：{ex}")

    print(f"\n完成！共更新 {total_updated} 筆日期")

if __name__ == "__main__":
    main()
