"""
每日新聞同步至 Google Sheets
讀取 analyzed_{TODAY}.json，批次 upsert（以 URL 為主鍵）到 Apps Script Web App
"""
import json, os, requests
from datetime import datetime
from zoneinfo import ZoneInfo

SHEETS_API_URL = os.environ.get(
    "SHEETS_API_URL",
    "https://script.google.com/macros/s/AKfycbxTvnw8nXbSVc5fRim0nvX6gaLiR3yRVuT2e_faTUh_95hRFJfp5Ts4rC60LqZMrXb-/exec"
)
TODAY    = datetime.now(ZoneInfo('Asia/Taipei')).date().isoformat()
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
BATCH_SIZE = 50  # 每批最多 50 筆，避免 Apps Script timeout

def sync_batch(items_batch: list, batch_num: int) -> dict:
    """傳送一批資料，回傳 Apps Script 結果"""
    try:
        r = requests.post(
            SHEETS_API_URL,
            json={"items": items_batch},
            timeout=90
        )
        r.raise_for_status()
        return r.json()
    except requests.exceptions.Timeout:
        print(f"  第 {batch_num} 批 timeout（{len(items_batch)} 筆），略過")
        return {}
    except Exception as e:
        print(f"  第 {batch_num} 批失敗：{e}")
        return {}

def main():
    raw_path = os.path.join(DATA_DIR, f"analyzed_{TODAY}.json")
    if not os.path.exists(raw_path):
        print(f"找不到分析資料：{raw_path}"); return

    with open(raw_path, encoding="utf-8") as f:
        data = json.load(f)

    items = data.get("items", [])
    if not items:
        print("無資料可同步"); return

    # 確保 pub_date 是純 YYYY-MM-DD 字串（非 UTC datetime）
    for item in items:
        pd = item.get("pub_date", "")
        if pd and len(pd) >= 10:
            item["pub_date"] = pd[:10]

    # 最新發布日的新聞排在最前面
    items = sorted(
        items,
        key=lambda x: x.get("pub_date") or x.get("date") or x.get("published", ""),
        reverse=True
    )

    total = len(items)
    total_added = 0
    total_updated = 0

    print(f"開始同步 {total} 則新聞（批次大小 {BATCH_SIZE}）...")
    for i in range(0, total, BATCH_SIZE):
        batch = items[i:i+BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1
        total_batches = (total + BATCH_SIZE - 1) // BATCH_SIZE
        print(f"  第 {batch_num}/{total_batches} 批（{len(batch)} 筆）...", end=" ", flush=True)
        result = sync_batch(batch, batch_num)
        added   = result.get("added", 0)
        updated = result.get("updated", 0)
        count   = result.get("count", added + updated)
        total_added   += added
        total_updated += updated
        print(f"新增 {added} 更新 {updated}")

    print(f"\n同步完成：共新增 {total_added} 筆，更新 {total_updated} 筆 → Google Sheets")

if __name__ == "__main__":
    main()
