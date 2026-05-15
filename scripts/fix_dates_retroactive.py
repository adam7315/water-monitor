"""
fix_dates_retroactive.py
一次性補丁：重查資料庫內所有 pub_date=2026-05-15 的文章，
追蹤重導向 + 抓取文章頁面取得真實發布日，寫回 Google Sheets。
"""
import re, json, time, requests
from datetime import date
from concurrent.futures import ThreadPoolExecutor, as_completed

TARGET_DATE   = '2026-05-15'
SHEETS_API_URL = (
    "https://script.google.com/macros/s/"
    "AKfycbxTvnw8nXbSVc5fRim0nvX6gaLiR3yRVuT2e_faTUh_95hRFJfp5Ts4rC60LqZMrXb-/exec"
)
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
HEADERS = {"User-Agent": UA}


# ── 工具函式 ────────────────────────────────────────────────────

def extract_url_date(url: str):
    m = re.search(r'/(20\d{2})[/-]?(\d{2})[/-]?(\d{2})', url)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass
    return None


def resolve_redirect(url: str) -> str:
    try:
        r = requests.head(url, allow_redirects=True, timeout=6, headers=HEADERS)
        final = r.url
        if 'google.com' not in final and final.startswith('http'):
            return final
    except Exception:
        pass
    return url


def scrape_pub_date(url: str) -> str:
    try:
        r = requests.get(url, timeout=8, stream=True, headers=HEADERS)
        raw = b''
        for chunk in r.iter_content(4096):
            raw += chunk
            if len(raw) > 40960:
                break
        html = raw.decode('utf-8', errors='ignore')
        # article:published_time meta（最常見標準）
        for pat in [
            r'article:published_time[^>]+content=["\']([0-9T:Z+\-.]{10,})',
            r'content=["\']([0-9T:Z+\-.]{10,})["\'][^>]+article:published_time',
        ]:
            m = re.search(pat, html)
            if m:
                return m.group(1)[:10]
        # JSON-LD
        for pat in [
            r'"datePublished"\s*:\s*"(\d{4}-\d{2}-\d{2})',
            r'"publishDate"\s*:\s*"(\d{4}-\d{2}-\d{2})',
        ]:
            m = re.search(pat, html)
            if m:
                return m.group(1)
    except Exception:
        pass
    return ''


def get_real_date(url: str):
    """回傳 (real_date_str_or_None, real_url)"""
    if 'news.google.com' in url:
        real_url = resolve_redirect(url)
        if real_url != url:
            d = extract_url_date(real_url)
            if d:
                return d.isoformat(), real_url
            scraped = scrape_pub_date(real_url)
            if scraped:
                return scraped, real_url
        return None, url
    else:
        d = extract_url_date(url)
        if d:
            return d.isoformat(), url
        scraped = scrape_pub_date(url)
        if scraped:
            return scraped, url
        return None, url


def process_item(idx_item):
    idx, item = idx_item
    url = item.get('url', '')
    if not url:
        return idx, item, None
    real_date, _ = get_real_date(url)
    return idx, item, real_date


# ── 主程式 ────────────────────────────────────────────────────

def main():
    print(f"=== 補丁：修正 {TARGET_DATE} 文章的真實發布日 ===\n")

    # 1. 取得所有資料
    print("從 Google Sheets 讀取所有文章...")
    resp = requests.get(f"{SHEETS_API_URL}?action=getAll", timeout=60)
    data = resp.json()
    monitor_data = data.get('monitor_data', {})

    all_items = []
    for day_data in monitor_data.values():
        all_items.extend(day_data.get('items', []))
    print(f"總文章數: {len(all_items)}")

    targets = [x for x in all_items
               if (x.get('pub_date') or x.get('date') or '') == TARGET_DATE]
    print(f"需要驗證的文章（date={TARGET_DATE}）: {len(targets)}\n")

    if not targets:
        print("沒有需要修正的文章。")
        return

    # 2. 並行查詢真實發布日（5 個 worker，減少等待時間）
    print("並行追蹤重導向 + 抓取文章頁面取得真實發布日...")
    print("（每篇最多 6s HEAD + 8s GET，約需數分鐘）\n")

    results = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(process_item, (i, item)): i
                   for i, item in enumerate(targets)}
        for future in as_completed(futures):
            idx, item, real_date = future.result()
            results.append((idx, item, real_date))

    results.sort(key=lambda x: x[0])

    to_update = []
    kept = 0
    failed = 0

    for idx, item, real_date in results:
        url = item.get('url', '')
        prefix = f"[{idx+1:3d}/{len(targets)}]"
        if real_date and real_date != TARGET_DATE:
            item['pub_date']  = real_date
            item['date']      = real_date
            if item.get('published'):
                item['published'] = real_date
            to_update.append(item)
            print(f"{prefix} {TARGET_DATE} → {real_date}  {url[:55]}")
        elif real_date == TARGET_DATE:
            kept += 1
            print(f"{prefix} 保留 {TARGET_DATE}（確認正確）  {url[:50]}")
        else:
            failed += 1
            print(f"{prefix} 無法取得日期（保留）  {url[:50]}")

    print(f"\n── 統計 ────────────────────────")
    print(f"  修正: {len(to_update)} 篇")
    print(f"  保留: {kept} 篇（確認為 {TARGET_DATE}）")
    print(f"  失敗: {failed} 篇（無法解析，保留原日期）")

    if not to_update:
        print("\n沒有需要更新的項目。")
        return

    # 3. 分批寫回 Google Sheets
    print(f"\n將 {len(to_update)} 篇修正結果寫回 Google Sheets...")
    BATCH = 30
    total_updated = 0
    for i in range(0, len(to_update), BATCH):
        batch = to_update[i:i + BATCH]
        payload = json.dumps({'items': batch})
        r = requests.post(SHEETS_API_URL,
                         data=payload,
                         headers={'Content-Type': 'application/json'},
                         timeout=90)
        res = r.json()
        cnt = res.get('updated', 0) + res.get('added', 0)
        total_updated += cnt
        print(f"  批次 {i//BATCH+1}: {res}")
        time.sleep(2)

    print(f"\n✓ 已更新 {total_updated} 篇文章的日期")
    print("下一步：執行 build_dashboard.py 重建 data.js，再 git push")


if __name__ == '__main__':
    main()
