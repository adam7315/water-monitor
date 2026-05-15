"""
fix_dates_playwright.py
用 Playwright 瀏覽器追蹤 Google News 重導向，取得真實文章 URL 與發布日期。
適用於補丁修正資料庫內 pub_date=2026-05-15 的文章。
"""
import sys, re, json, time, requests
from datetime import date
from playwright.sync_api import sync_playwright, TimeoutError as PwTimeout

# Fix Windows console encoding
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

TARGET_DATE = '2026-05-15'
SHEETS_API_URL = (
    "https://script.google.com/macros/s/"
    "AKfycbxTvnw8nXbSVc5fRim0nvX6gaLiR3yRVuT2e_faTUh_95hRFJfp5Ts4rC60LqZMrXb-/exec"
)

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")


# ── 工具函式 ────────────────────────────────────────────────────

def extract_url_date(url: str):
    m = re.search(r'/(20\d{2})[/-]?(\d{2})[/-]?(\d{2})', url)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass
    return None


def get_page_date(page) -> str:
    """從當前頁面取得發布日期（article:published_time 或 JSON-LD datePublished）"""
    try:
        return page.evaluate("""() => {
            // article:published_time meta
            const m = document.querySelector('meta[property="article:published_time"]');
            if (m) return m.getAttribute('content') || '';
            // JSON-LD
            const lds = document.querySelectorAll('script[type="application/ld+json"]');
            for (const ld of lds) {
                try {
                    const d = JSON.parse(ld.textContent);
                    if (d.datePublished) return d.datePublished;
                    if (d.publishDate)   return d.publishDate;
                    if (Array.isArray(d['@graph'])) {
                        for (const g of d['@graph']) {
                            if (g.datePublished) return g.datePublished;
                        }
                    }
                } catch(e) {}
            }
            // og:article:published_time
            const og = document.querySelector('meta[property="og:article:published_time"]');
            if (og) return og.getAttribute('content') || '';
            return '';
        }""")
    except Exception:
        return ''


# ── 主程式 ────────────────────────────────────────────────────

def main():
    print(f"=== Playwright 補丁：修正 {TARGET_DATE} 文章的真實發布日 ===\n")

    # 1. 讀取資料庫
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
    print(f"需要驗證的文章: {len(targets)}\n")

    if not targets:
        print("沒有需要修正的文章。")
        return

    # 2. 用 Playwright 逐一取得真實日期
    to_update = []
    kept = 0
    failed = 0

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(user_agent=UA)
        page = context.new_page()

        for i, item in enumerate(targets):
            url = item.get('url', '')
            title = item.get('title', '')[:40]
            prefix = f"[{i+1:3d}/{len(targets)}]"
            if not url:
                failed += 1
                continue

            real_date = None
            try:
                # 導航到文章 URL（Google News 會經由 JS 重導到真實文章）
                page.goto(url, timeout=12000, wait_until='domcontentloaded')
                # 等一下讓 JS redirect 完成
                page.wait_for_timeout(800)
                final_url = page.url

                # 步驟1：從 final URL 萃取日期
                d = extract_url_date(final_url)
                if d:
                    real_date = d.isoformat()
                else:
                    # 步驟2：從頁面 meta 取得日期
                    raw = get_page_date(page)
                    if raw and len(raw) >= 10:
                        candidate = raw[:10]
                        # 只接受 YYYY-MM-DD 格式（不接受 Unix timestamp 或其他格式）
                        if re.match(r'^20\d{2}-\d{2}-\d{2}$', candidate):
                            real_date = candidate

            except PwTimeout:
                print(f"{prefix} TIMEOUT  {url[:55]}")
                failed += 1
                continue
            except Exception as e:
                print(f"{prefix} ERR {str(e)[:30]}  {url[:45]}")
                failed += 1
                continue

            if real_date and real_date != TARGET_DATE:
                item['pub_date']  = real_date
                item['date']      = real_date
                if item.get('published'):
                    item['published'] = real_date
                to_update.append(item)
                print(f"{prefix} {TARGET_DATE} -> {real_date}  {title}")
            elif real_date == TARGET_DATE:
                kept += 1
                print(f"{prefix} keep {TARGET_DATE}  {title}")
            else:
                failed += 1
                print(f"{prefix} FAIL (no date)  {title}")

        page.close()
        context.close()
        browser.close()

    print(f"\n-- 統計 ---------------------------")
    print(f"  修正: {len(to_update)} 篇")
    print(f"  保留: {kept} 篇（確認為 {TARGET_DATE}）")
    print(f"  失敗: {failed} 篇")

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
        print(f"  Batch {i//BATCH+1}: {res}")
        time.sleep(2)

    print(f"\nDone: {total_updated} 篇已更新")
    print("下一步: python scripts/build_dashboard.py && git add docs/data.js && git commit && git push")


if __name__ == '__main__':
    main()
