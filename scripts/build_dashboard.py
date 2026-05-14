"""
產生 GitHub Pages 靜態儀表板（v6）
"""
import json, os, glob
from datetime import datetime
from zoneinfo import ZoneInfo
from collections import Counter, defaultdict

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
DOCS_DIR = os.path.join(os.path.dirname(__file__), "..", "docs")
os.makedirs(DOCS_DIR, exist_ok=True)
TODAY = datetime.now(ZoneInfo('Asia/Taipei')).date().isoformat()

# 歸檔用 Apps Script Web App URL（寫入 Google Sheets）
SHEETS_API_URL = "https://script.google.com/macros/s/AKfycbxTvnw8nXbSVc5fRim0nvX6gaLiR3yRVuT2e_faTUh_95hRFJfp5Ts4rC60LqZMrXb-/exec"

def load_recent_data(days=90):
    all_data = {}
    pattern = os.path.join(DATA_DIR, "analyzed_*.json")
    files = sorted(glob.glob(pattern), reverse=True)[:days]
    for f in files:
        try:
            with open(f, encoding="utf-8") as fp:
                d = json.load(fp)
                day = os.path.basename(f).replace("analyzed_","").replace(".json","")
                all_data[day] = d
        except Exception as e:
            print(f"  讀取失敗 {f}: {e}")
    return all_data

def calc_topic_heat(all_data):
    heat = defaultdict(lambda: {"total": 0, "negative": 0, "positive": 0})
    for day_data in all_data.values():
        for item in day_data.get("items", []):
            cat = item.get("category", "其他")
            heat[cat]["total"] += 1
            if item.get("sentiment") == "負面":  heat[cat]["negative"] += 1
            elif item.get("sentiment") == "正面": heat[cat]["positive"] += 1
    return {k: dict(v) for k, v in heat.items()}

def calc_keyword_ranking(all_data, top_n=20):
    counter = Counter()
    for day_data in all_data.values():
        for item in day_data.get("items", []):
            kw = item.get("keyword", "")
            if kw and len(kw) > 1:
                counter[kw] += 1
    return counter.most_common(top_n)

def main():
    all_data = load_recent_data()
    if not all_data:
        print("無資料，建立空白頁面")

    topic_heat      = calc_topic_heat(all_data)
    keyword_ranking = calc_keyword_ranking(all_data)
    total_all       = sum(d.get("stats", {}).get("total", 0) for d in all_data.values())
    total_neg_all   = sum(d.get("stats", {}).get("negative", 0) for d in all_data.values())

    data_js = (
        f"const MONITOR_DATA = {json.dumps(all_data, ensure_ascii=False)};\n"
        f"const TODAY = '{TODAY}';\n"
        f"const TOPIC_HEAT = {json.dumps(topic_heat, ensure_ascii=False)};\n"
        f"const KEYWORD_RANKING = {json.dumps(keyword_ranking, ensure_ascii=False)};\n"
        f"const TOTAL_ALL = {total_all};\n"
        f"const TOTAL_NEG_ALL = {total_neg_all};\n"
        f"const SHEETS_API_URL = '{SHEETS_API_URL}';\n"
    )
    with open(os.path.join(DOCS_DIR, "data.js"), "w", encoding="utf-8") as f:
        f.write(data_js)

    print(f"data.js 已產生（{len(all_data)} 天、共 {total_all} 則、負面 {total_neg_all} 則）")
    build_html()
    print("index.html 已產生")

def build_html():
    html = r"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>南水資源分署 輿情監控系統</title>
<script src="https://cdn.tailwindcss.com"></script>
<style>
body { font-family:-apple-system,"Noto Sans TC",sans-serif; background:#eef2f7; }
.sidebar { background:#0a1628; }
.sb-sec  { border-bottom:1px solid #1a2e4a; padding:.875rem 1rem; }
.sb-sec:last-child { border-bottom:none; }
.sb-title { color:#7eb4d8; font-size:.72rem; font-weight:700; letter-spacing:.06em; text-transform:uppercase; margin-bottom:.625rem; display:block; }
.kpi  { background:white; border-radius:.875rem; padding:.875rem 1.125rem; box-shadow:0 2px 10px rgba(0,0,0,.08); cursor:pointer; transition:box-shadow .15s, transform .1s; }
.kpi:hover { box-shadow:0 4px 18px rgba(0,0,0,.14); transform:translateY(-1px); }
.knum { font-size:2.4rem; font-weight:800; line-height:1; letter-spacing:-.03em; }
.card-neg { border-left:4px solid #ef4444; }
.card-pos { border-left:4px solid #22c55e; }
.card-neu { border-left:4px solid #cbd5e1; }
.news-card { background:white; border-radius:.75rem; box-shadow:0 1px 4px rgba(0,0,0,.06); transition:box-shadow .15s; }
.news-card:hover { box-shadow:0 4px 16px rgba(0,0,0,.12); }
.link-title { color:#1d4ed8; text-decoration:underline; text-underline-offset:2px; cursor:pointer; }
.link-title:hover { color:#1e40af; }
.line-box  { background:linear-gradient(135deg,#f0fdf4,#dcfce7); border:1px solid #86efac; border-radius:.75rem; }
.urg-card  { background:white; border-radius:.75rem; overflow:hidden; box-shadow:0 2px 8px rgba(0,0,0,.10); }
.don-wrap { display:flex; flex-direction:column; align-items:center; gap:.15rem; cursor:pointer; }
.don-lbl  { font-size:.62rem; color:#5a85a8; }
/* Category circles - 固定尺寸 */
.cat-circle { display:flex; flex-direction:column; align-items:center; cursor:pointer; transition:transform .2s; }
.cat-circle:hover { transform:translateY(-3px); }
.cat-circle.active .cat-ring { box-shadow:0 0 0 3px white, 0 0 0 5px #ef4444; }
.cat-ring { border-radius:50%; width:96px; height:96px; display:flex; flex-direction:column; align-items:center; justify-content:center; color:white; font-weight:700; transition:box-shadow .2s; }
.cat-name { font-size:.72rem; font-weight:600; margin-top:.5rem; text-align:center; max-width:90px; line-height:1.3; }
.chip { font-size:.72rem; padding:.25rem .75rem; border-radius:9999px; cursor:pointer; border:1px solid #cbd5e1; color:#64748b; background:white; transition:all .15s; }
.chip.on { background:#1e5799; border-color:#1e5799; color:white; }
.spl-btn { font-size:.68rem; padding:.2rem .6rem; border-radius:9999px; cursor:pointer; border:1px solid #243c57; color:#7eb4d8; background:transparent; transition:all .15s; }
.spl-btn.on { background:#1e5799; border-color:#1e5799; color:white; }
.corr-btn { font-size:.65rem; padding:.15rem .5rem; border-radius:9999px; cursor:pointer; border:1px solid; transition:all .15s; }
.corr-neg { border-color:#fca5a5; color:#dc2626; }
.corr-neg.on { background:#ef4444; color:white; border-color:#ef4444; }
.corr-pos { border-color:#86efac; color:#16a34a; }
.corr-pos.on { background:#22c55e; color:white; border-color:#22c55e; }
.corr-neu { border-color:#cbd5e1; color:#64748b; }
.corr-neu.on { background:#94a3b8; color:white; border-color:#94a3b8; }
.track-btn { font-size:.65rem; padding:.15rem .6rem; border-radius:9999px; cursor:pointer; border:1px solid #93c5fd; color:#2563eb; transition:all .15s; }
.track-btn.on { background:#2563eb; color:white; border-color:#2563eb; }
.wf-stage { font-size:.65rem; padding:.2rem .5rem; border-radius:.375rem; cursor:pointer; border:1px solid #e2e8f0; background:white; color:#475569; transition:all .15s; white-space:nowrap; }
.wf-stage.done { background:#1e5799; color:white; border-color:#1e5799; }
.wf-stage.current { background:#fef3c7; color:#92400e; border-color:#fcd34d; }
.bdg-done { background:#dcfce7; color:#15803d; font-size:.65rem; padding:.15rem .5rem; border-radius:9999px; white-space:nowrap; }
.pg-btn { padding:.3rem .7rem; border-radius:.5rem; font-size:.8rem; border:1px solid #e2e8f0; background:white; cursor:pointer; transition:all .15s; color:#475569; }
.pg-btn:hover:not(:disabled) { background:#1e5799; color:white; border-color:#1e5799; }
.pg-btn.on { background:#1e5799; color:white; border-color:#1e5799; }
.pg-btn:disabled { opacity:.4; cursor:not-allowed; }
.search-btn { background:#1e5799; color:white; border:none; border-radius:.5rem; padding:.4rem 1.25rem; font-size:.8rem; cursor:pointer; transition:background .15s; font-weight:600; }
.search-btn:hover { background:#1a4a8a; }
.home-btn { background:#475569; color:white; border:none; border-radius:.5rem; padding:.4rem 1.25rem; font-size:.8rem; cursor:pointer; transition:background .15s; font-weight:600; }
.home-btn:hover { background:#334155; }
.ai-badge { background:linear-gradient(135deg,#667eea,#764ba2); }
.pulse    { animation:pulse 2s infinite; }
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}
.sidebar-scroll { max-height:calc(100vh - 80px); overflow-y:auto; overflow-x:hidden; scrollbar-width:thin; scrollbar-color:#1e3a60 #0a1628; }
.sidebar-scroll::-webkit-scrollbar { width:4px; }
.sidebar-scroll::-webkit-scrollbar-track { background:#0a1628; }
.sidebar-scroll::-webkit-scrollbar-thumb { background:#1e3a60; border-radius:2px; }
.sb-clickable { cursor:pointer; transition:opacity .15s; }
.sb-clickable:hover { opacity:.8; }
@media(max-width:1023px){ .layout-sidebar{ display:none !important; } .layout-main{ grid-template-columns:1fr !important; } }
</style>
</head>
<body>

<!-- ── Header ── -->
<header style="background:linear-gradient(160deg,#0a1628 0%,#0e2d5e 60%,#1a4a8a 100%)" class="text-white shadow-xl">
  <div class="max-w-7xl mx-auto px-5 py-4">
    <div class="flex justify-between items-center gap-4 flex-wrap">
      <div class="flex items-center gap-4">
        <div style="background:rgba(255,255,255,.1);border:1px solid rgba(255,255,255,.2)"
             class="w-12 h-12 rounded-xl flex items-center justify-center text-2xl shrink-0">💧</div>
        <div>
          <div class="text-blue-300 text-xs tracking-widest mb-0.5">114–115年度 臺南海水淡化廠暨南區水資源推廣計畫</div>
          <h1 class="text-xl font-extrabold tracking-tight">輿情監控系統</h1>
          <div class="text-blue-400 text-xs mt-0.5">🕐 每日 07:00 &amp; 14:00 自動蒐集分析（台灣時間）</div>
        </div>
      </div>
      <div class="flex items-center gap-4 shrink-0 flex-wrap">
        <div class="text-center">
          <div class="text-blue-300 text-xs mb-0.5">最新資料</div>
          <div class="text-white font-bold text-base" id="latestDateDisplay">-</div>
        </div>
        <div class="text-center sb-clickable" onclick="filterToday('正面')">
          <div class="text-xs text-blue-300 mb-0.5">今日正面</div>
          <div class="text-2xl font-bold text-green-300" id="hdrPos">-</div>
          <div class="text-xs text-blue-300">則 ↗</div>
        </div>
        <div class="text-center sb-clickable" onclick="filterToday('負面')">
          <div class="text-xs text-blue-300 mb-0.5">今日負面</div>
          <div class="text-2xl font-bold text-red-300" id="hdrNeg">-</div>
          <div class="text-xs text-blue-300">則 ↗</div>
        </div>
        <div class="flex flex-col gap-1.5">
          <div class="ai-badge text-white text-xs px-3 py-1.5 rounded-full flex items-center gap-1.5 shadow"
               title="每則新聞由 Google Gemini AI 自動分析情感傾向（正面／負面／中立）並產生澄清建議文稿，不代表官方立場">
            <span class="pulse w-1.5 h-1.5 bg-white rounded-full"></span>🤖 AI 自動分析
          </div>
          <div class="text-xs text-blue-300 text-center">每日自動更新</div>
        </div>
      </div>
    </div>
  </div>
</header>

<!-- ── Stats Row ── -->
<div class="max-w-7xl mx-auto px-5 pt-4 pb-3">
  <div class="flex items-center gap-2 mb-2.5">
    <span class="text-xs text-slate-400">最新資料：</span>
    <span class="text-sm font-semibold text-slate-600" id="statsDateLabel">-</span>
    <span class="text-xs text-slate-300 ml-1">（點擊卡片可篩選今日新聞）</span>
  </div>
  <div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
    <div class="kpi border-t-4 border-blue-400" onclick="filterToday('')" title="點擊查看今日所有新聞">
      <div class="text-xs text-slate-400 mb-1.5">今日蒐集</div>
      <div class="knum text-slate-700" id="statTotal">-</div>
      <div class="text-xs text-slate-400 mt-1">則新聞 ↗</div>
    </div>
    <div class="kpi border-t-4 border-red-500" onclick="filterToday('負面')" title="點擊查看今日負面新聞">
      <div class="text-xs text-slate-400 mb-1.5">今日負面</div>
      <div class="knum text-red-600" id="statNeg">-</div>
      <div class="text-xs text-red-300 mt-1">則（今日蒐集）↗</div>
    </div>
    <div class="kpi border-t-4 border-green-500" onclick="filterToday('正面')" title="點擊查看今日正面新聞">
      <div class="text-xs text-slate-400 mb-1.5">今日正面</div>
      <div class="knum text-green-600" id="statPos">-</div>
      <div class="text-xs text-slate-400 mt-1">則正向報導 ↗</div>
    </div>
    <div class="kpi border-t-4 border-orange-500" onclick="filterHighPriority()" title="點擊查看高優先負面新聞">
      <div class="text-xs text-slate-400 mb-1.5">高優先</div>
      <div class="knum text-orange-500" id="statHigh">-</div>
      <div class="text-xs text-orange-300 mt-1">則待立即處理 ↗</div>
    </div>
  </div>
</div>

<!-- ── Today Negative + Clarify ── -->
<div class="max-w-7xl mx-auto px-5 pb-3">
  <div class="grid grid-cols-1 lg:grid-cols-5 gap-3">

    <!-- 今日負面輿情 -->
    <div class="lg:col-span-2 bg-gradient-to-br from-red-50 to-orange-50 border border-red-200 rounded-xl p-3.5">
      <div class="flex items-center justify-between mb-3">
        <div class="flex items-center gap-2">
          <span class="text-lg">📢</span>
          <span class="font-bold text-red-700 text-sm">今日負面輿情</span>
          <span class="text-xs text-red-400 bg-red-100 px-1.5 py-0.5 rounded-full" id="todayNegCount"></span>
        </div>
        <span class="text-xs text-slate-400">點「關注」加入追蹤</span>
      </div>
      <div id="todayNegList" class="space-y-2"></div>
      <div id="todayNegEmpty" class="hidden text-center py-6">
        <div class="text-3xl mb-2">✅</div>
        <div class="text-green-600 text-xs font-medium">今日無負面輿情</div>
      </div>
    </div>

    <!-- 澄清追蹤工作流 -->
    <div class="lg:col-span-3 bg-white border border-slate-100 rounded-xl shadow-sm">
      <div class="flex items-center justify-between p-3.5 border-b border-slate-100">
        <div class="flex items-center gap-2">
          <span>📋</span>
          <span class="font-bold text-slate-600 text-sm">負面輿情 · 澄清追蹤</span>
          <span class="text-xs text-slate-400 ml-1" id="trackCount"></span>
        </div>
        <button onclick="exportCSV()"
          class="text-xs bg-green-600 hover:bg-green-700 text-white px-3 py-1 rounded-lg font-medium transition flex items-center gap-1">
          📊 匯出 Excel
        </button>
      </div>
      <div id="clarifyList" class="p-2 space-y-2 max-h-64 overflow-y-auto"></div>
      <div id="clarifyEmpty" class="hidden text-center py-6 text-slate-400">
        <div class="text-2xl mb-1">📭</div>
        <div class="text-xs">尚無追蹤中的輿情<br>在今日負面輿情或新聞列表點「關注」即可加入</div>
      </div>
    </div>

  </div>
</div>

<!-- ── Main Layout ── -->
<div class="max-w-7xl mx-auto px-5 pb-10">
  <div class="layout-main" style="display:grid;grid-template-columns:248px 1fr;gap:16px;align-items:start">

    <!-- ── Sidebar ── -->
    <aside class="layout-sidebar sidebar rounded-xl shadow-xl" style="position:sticky;top:12px">
      <div class="sidebar-scroll">

        <!-- 輿情分析（對應日期範圍） -->
        <div class="sb-sec">
          <span class="sb-title">📊 輿情分析（依搜尋範圍）</span>
          <div class="text-xs text-blue-400 mb-2 text-center" id="donutCatLabel">全部分類</div>
          <div class="flex justify-around items-center py-1.5" id="sentimentDonuts"></div>
          <div class="mt-3 grid grid-cols-2 gap-1.5 text-xs">
            <div class="text-center py-1 rounded sb-clickable" style="background:#1a2e4a;color:#7eb4d8"
                 onclick="filterBySentiment('正面')">
              正面 <span class="font-bold text-green-400" id="donutPos">-</span> 則
            </div>
            <div class="text-center py-1 rounded sb-clickable" style="background:#1a2e4a;color:#7eb4d8"
                 onclick="filterBySentiment('負面')">
              負面 <span class="font-bold text-red-400" id="donutNeg">-</span> 則
            </div>
          </div>
        </div>

        <!-- 關鍵字頻率排行 -->
        <div class="sb-sec">
          <span class="sb-title">🔑 關鍵字頻率（點擊查看全部）</span>
          <div id="kwRanking" class="space-y-2"></div>
        </div>

      </div>
    </aside>

    <!-- ── Main Content ── -->
    <main class="space-y-3">

      <!-- 4 Category Circles -->
      <div class="bg-white rounded-xl shadow-sm p-5 border border-slate-100">
        <div class="mb-4">
          <h3 class="font-bold text-slate-700 text-sm">📂 分類總覽（點擊篩選）</h3>
        </div>
        <div class="flex justify-around items-start gap-2 flex-wrap" id="catCircles"></div>
      </div>

      <!-- Filters -->
      <div class="bg-white rounded-xl shadow-sm p-4 border border-slate-100">
        <div class="flex flex-wrap gap-4 items-end">
          <!-- 日期範圍 -->
          <div>
            <div class="text-xs text-slate-400 mb-1.5">日期範圍</div>
            <div class="flex items-center gap-1.5">
              <input type="date" id="dateFrom"
                class="border border-slate-200 rounded-lg px-2 py-1 text-xs focus:outline-none focus:ring-2 focus:ring-blue-300">
              <span class="text-slate-400 text-xs">至</span>
              <input type="date" id="dateTo"
                class="border border-slate-200 rounded-lg px-2 py-1 text-xs focus:outline-none focus:ring-2 focus:ring-blue-300">
            </div>
          </div>
          <!-- 情感 -->
          <div>
            <div class="text-xs text-slate-400 mb-1.5">情感</div>
            <select id="sentFilter"
              class="border border-slate-200 rounded-lg px-2 py-1.5 text-xs focus:outline-none">
              <option value="">全部</option>
              <option value="負面">🔴 負面</option>
              <option value="正面">🟢 正面</option>
              <option value="中立">⚪ 中立</option>
            </select>
          </div>
          <!-- 排序 -->
          <div>
            <div class="text-xs text-slate-400 mb-1.5">排序</div>
            <select id="sortBy"
              class="border border-slate-200 rounded-lg px-2 py-1.5 text-xs focus:outline-none">
              <option value="date-desc">日期新→舊</option>
              <option value="neg-first">負面優先</option>
              <option value="date-asc">日期舊→新</option>
              <option value="tracked">澄清追蹤</option>
            </select>
          </div>
          <!-- 關鍵字 -->
          <div class="flex-1 min-w-32">
            <div class="text-xs text-slate-400 mb-1.5">關鍵字</div>
            <input type="text" id="searchBox" placeholder="輸入關鍵字…"
              class="w-full border border-slate-200 rounded-lg px-3 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-blue-300">
          </div>
          <!-- Buttons -->
          <button class="search-btn" onclick="applyFilters()">🔍 搜尋</button>
          <button class="home-btn" onclick="resetHome()">🏠 首頁</button>
        </div>
      </div>

      <!-- Count + page info -->
      <div class="flex justify-between items-center px-1">
        <div class="text-sm text-slate-500">
          共 <strong id="showCount">0</strong> 則
          <span class="ml-2 text-red-500 sb-clickable" onclick="filterBySentiment('負面')">負面 <strong id="showNeg">0</strong> ↗</span>
          <span class="ml-1.5 text-green-500 sb-clickable" onclick="filterBySentiment('正面')">正面 <strong id="showPos">0</strong> ↗</span>
          <span class="ml-1.5 text-slate-400">中立 <strong id="showNeu">0</strong></span>
        </div>
        <span class="text-xs text-slate-400" id="pageInfo"></span>
      </div>

      <!-- News List -->
      <div id="newsList" class="space-y-2.5"></div>
      <div id="emptyState" class="hidden text-center py-12 text-slate-400">
        <div class="text-5xl mb-3">🔍</div>
        <div class="text-sm">目前無符合條件的資料</div>
      </div>

      <!-- Pagination -->
      <div id="pagination" class="flex justify-center gap-1.5 pt-2 flex-wrap"></div>

    </main>
  </div>
</div>

<!-- Footer -->
<footer class="border-t border-slate-200 bg-white py-3 mt-2">
  <div class="max-w-7xl mx-auto px-5 text-center text-xs text-slate-400 space-x-2">
    <span>114-115年度 臺南海水淡化廠暨南區水資源推廣計畫</span>
    <span>·</span><span>每日 07:00 &amp; 14:00（台灣時間）自動蒐集分析</span>
    <span>·</span><span>Powered by Google Gemini AI &amp; GitHub Actions</span>
  </div>
</footer>

<!-- Keyword Articles Modal -->
<div id="kwModal" class="hidden fixed inset-0 z-50 flex items-center justify-center" style="background:rgba(0,0,0,.5)">
  <div class="bg-white rounded-2xl shadow-2xl w-full max-w-2xl mx-4 flex flex-col" style="max-height:80vh">
    <div class="p-5 border-b border-slate-100 flex items-center justify-between shrink-0">
      <h3 class="font-bold text-slate-700" id="kwModalTitle">關鍵字文章</h3>
      <button onclick="closeKwModal()" class="text-slate-400 hover:text-slate-600 text-xl leading-none">✕</button>
    </div>
    <div id="kwModalContent" class="p-4 space-y-2 overflow-y-auto"></div>
  </div>
</div>

<!-- Workflow Modal -->
<div id="wfModal" class="hidden fixed inset-0 z-50 flex items-center justify-center" style="background:rgba(0,0,0,.5)">
  <div class="bg-white rounded-2xl shadow-2xl w-full max-w-lg mx-4 max-h-screen overflow-y-auto">
    <div class="p-5 border-b border-slate-100 flex items-center justify-between">
      <h3 class="font-bold text-slate-700">澄清稿件工作流</h3>
      <button onclick="closeModal()" class="text-slate-400 hover:text-slate-600 text-xl leading-none">✕</button>
    </div>
    <div id="wfModalContent" class="p-5"></div>
  </div>
</div>

<script src="data.js"></script>
<script>
/* ══════════════════════════════════════════
   狀態
══════════════════════════════════════════ */
let allItemsFlat = [];
let filteredItems = [];
let currentPage = 1;
const PAGE_SIZE = 30;

const CAT_GROUPS = {
  '台南海水淡化廠': {cats:['海淡廠'],                icon:'🏭', color:'#065f46', grad:'linear-gradient(135deg,#064e3b,#059669)'},
  '南水資源分署':   {cats:['南部水資源','社群輿情'], icon:'💧', color:'#1e5799', grad:'linear-gradient(135deg,#1a3a6c,#2d6a9f)'},
  '水庫相關新聞':   {cats:['全台水資源'],             icon:'🏔', color:'#92400e', grad:'linear-gradient(135deg,#78350f,#d97706)'},
  '國際水資源新聞': {cats:['國際'],                   icon:'🌍', color:'#4c1d95', grad:'linear-gradient(135deg,#3b0764,#7c3aed)'}
};
let activeCatGroup = null;
let highPriorityOnly = false;

const LS_CORRECTIONS = 'wm_v6_corrections';
const LS_TRACKED     = 'wm_v6_tracked';
const LS_WORKFLOWS   = 'wm_v6_workflows';

function getCorrections(){ return JSON.parse(localStorage.getItem(LS_CORRECTIONS)||'{}'); }
function getTracked()    { return JSON.parse(localStorage.getItem(LS_TRACKED)||'{}'); }
function getWorkflows()  { return JSON.parse(localStorage.getItem(LS_WORKFLOWS)||'{}'); }
function saveCorrections(v){ localStorage.setItem(LS_CORRECTIONS, JSON.stringify(v)); }
function saveTracked(v)    { localStorage.setItem(LS_TRACKED, JSON.stringify(v)); }
function saveWorkflows(v)  { localStorage.setItem(LS_WORKFLOWS, JSON.stringify(v)); }

function showToast(msg) {
  const d = document.createElement('div');
  d.textContent = msg;
  d.style.cssText = 'position:fixed;bottom:24px;right:24px;background:#1e293b;color:#fff;padding:10px 18px;border-radius:8px;font-size:14px;z-index:9999;box-shadow:0 4px 12px rgba(0,0,0,.3);';
  document.body.appendChild(d);
  setTimeout(()=>d.remove(), 3000);
}

/* ══════════════════════════════════════════
   日期工具
══════════════════════════════════════════ */
function normalizeDate(s) {
  if (!s) return '';
  if (/^\d{4}-\d{2}-\d{2}/.test(s)) return s.slice(0,10);
  try { const d = new Date(s); if (!isNaN(d)) return d.toISOString().slice(0,10); } catch(e) {}
  return '';
}

function toROC(s) {
  if (!s) return '';
  const iso = normalizeDate(s);
  if (iso) {
    const d = new Date(iso+'T00:00:00');
    return `民國${d.getFullYear()-1911}年${d.getMonth()+1}月${d.getDate()}日`;
  }
  return s.slice(0,10);
}

function getItemId(item){ return item.id || (item.title||'')+(item.published||''); }
function getSentiment(item){ const c=getCorrections(); return c[getItemId(item)]||item.sentiment||'中立'; }

/* ══════════════════════════════════════════
   初始化
══════════════════════════════════════════ */
function init() {
  const dates = Object.keys(MONITOR_DATA).sort();
  const latest = dates[dates.length-1] || '';
  document.getElementById('latestDateDisplay').textContent = latest;
  document.getElementById('statsDateLabel').textContent   = latest;

  if (latest && MONITOR_DATA[latest]) {
    const todayPub = (MONITOR_DATA[latest].items||[]).filter(x=>normalizeDate(x.pub_date||x.published||x.date||'')===latest);
    const todayNegC  = todayPub.filter(x=>getSentiment(x)==='負面').length;
    const todayPosC  = todayPub.filter(x=>getSentiment(x)==='正面').length;
    const todayHighC = todayPub.filter(x=>x.priority==='高').length;
    document.getElementById('statTotal').textContent = todayPub.length;
    document.getElementById('statNeg').textContent   = todayNegC;
    document.getElementById('statPos').textContent   = todayPosC;
    document.getElementById('statHigh').textContent  = todayHighC;
    document.getElementById('hdrPos').textContent    = todayPosC;
    document.getElementById('hdrNeg').textContent    = todayNegC;
  }

  allItemsFlat = [];
  const _seenIds = new Set();
  Object.values(MONITOR_DATA).forEach(d=>{
    (d.items||[]).forEach(item=>{
      const _id = item.id || (item.title||'')+(item.published||'');
      if (!_seenIds.has(_id)) { _seenIds.add(_id); allItemsFlat.push(item); }
    });
  });

  // 預設日期範圍：近30天
  if (dates.length) {
    const thirtyBack = new Date(Date.now()-30*86400000).toISOString().slice(0,10);
    document.getElementById('dateFrom').value = thirtyBack < dates[0] ? dates[0] : thirtyBack;
    document.getElementById('dateTo').value   = latest;
  }
  // 預設排序：日期新→舊
  document.getElementById('sortBy').value = 'date-desc';

  renderCatCircles();
  renderKwRanking();
  renderTodayNeg(latest);
  renderClarifyList();
  applyFilters();
}

/* ══════════════════════════════════════════
   快速篩選捷徑
══════════════════════════════════════════ */
function filterToday(sent) {
  highPriorityOnly = false;
  const dates = Object.keys(MONITOR_DATA).sort();
  const latest = dates[dates.length-1]||'';
  document.getElementById('dateFrom').value   = latest;
  document.getElementById('dateTo').value     = latest;
  document.getElementById('sentFilter').value = sent;
  document.getElementById('sortBy').value     = 'date-desc';
  document.getElementById('searchBox').value  = '';
  activeCatGroup = null;
  document.querySelectorAll('.cat-circle').forEach(c=>c.classList.remove('active'));
  applyFilters();
  document.getElementById('newsList').scrollIntoView({behavior:'smooth', block:'start'});
}



function fpCorr(id, newSent, idx) {
  const c = getCorrections();
  if (c[id]===newSent) { delete c[id]; } else { c[id]=newSent; }
  saveCorrections(c);
  renderDonut(activeCatGroup);
  const cur = c[id] || allItemsFlat.find(x=>getItemId(x)===id)?.sentiment || '中立';
  const el = document.getElementById('fp-'+idx);
  if (el) el.querySelectorAll('.corr-btn').forEach(b=>{
    if (b.classList.contains('corr-neg')) b.classList.toggle('on', cur==='負面');
    else if (b.classList.contains('corr-pos')) b.classList.toggle('on', cur==='正面');
    else b.classList.toggle('on', cur==='中立');
  });
}

function fpTrack(id, idx) {
  const t = getTracked();
  t[id] = !t[id]; if (!t[id]) delete t[id];
  saveTracked(t);
  const btn = document.getElementById('fp-tb-'+idx);
  if (btn) { btn.textContent=t[id]?'✓ 已關注':'+ 關注'; btn.classList.toggle('on', !!t[id]); }
  renderClarifyList();
}

function filterHighPriority() {
  const dates = Object.keys(MONITOR_DATA).sort();
  const latest = dates[dates.length-1]||'';
  document.getElementById('dateFrom').value   = latest;
  document.getElementById('dateTo').value     = latest;
  document.getElementById('sentFilter').value = '負面';
  document.getElementById('sortBy').value     = 'neg-first';
  document.getElementById('searchBox').value  = '';
  activeCatGroup = null;
  highPriorityOnly = true;
  document.querySelectorAll('.cat-circle').forEach(c=>c.classList.remove('active'));
  applyFilters();
  document.getElementById('newsList').scrollIntoView({behavior:'smooth'});
}

function filterBySentiment(sent) {
  highPriorityOnly = false;
  document.getElementById('sentFilter').value = sent;
  applyFilters();
  document.getElementById('newsList').scrollIntoView({behavior:'smooth'});
}

function resetHome() {
  highPriorityOnly = false;
  const dates = Object.keys(MONITOR_DATA).sort();
  const latest = dates[dates.length-1]||'';
  const thirtyBack = new Date(Date.now()-30*86400000).toISOString().slice(0,10);
  document.getElementById('dateFrom').value   = thirtyBack < dates[0] ? dates[0] : thirtyBack;
  document.getElementById('dateTo').value     = latest;
  document.getElementById('sentFilter').value = '';
  document.getElementById('sortBy').value     = 'date-desc';
  document.getElementById('searchBox').value  = '';
  activeCatGroup = null;
  document.querySelectorAll('.cat-circle').forEach(c=>c.classList.remove('active'));
  applyFilters();
}

/* ══════════════════════════════════════════
   輿情分析圓環（對應日期範圍）
══════════════════════════════════════════ */
function renderDonut(groupName) {
  const el = document.getElementById('sentimentDonuts');
  document.getElementById('donutCatLabel').textContent = groupName||'全部分類';
  const from = document.getElementById('dateFrom')?.value||'';
  const to   = document.getElementById('dateTo')?.value||'';
  let pos=0,neg=0,neu=0;
  const cats = groupName ? CAT_GROUPS[groupName].cats : null;
  allItemsFlat.forEach(x=>{
    if (cats && !cats.includes(x.category||'')) return;
    const nd = normalizeDate(x.date||x.published||'');
    if (from && nd < from) return;
    if (to   && nd > to)   return;
    const s = getSentiment(x);
    if (s==='正面') pos++; else if (s==='負面') neg++; else neu++;
  });
  document.getElementById('donutPos').textContent = pos;
  document.getElementById('donutNeg').textContent = neg;
  const t=pos+neg+neu||1, pn=Math.round(neg/t*100), pu=Math.round(neu/t*100), pp=100-pn-pu;
  const mksvg=(pct,clr,lbl,cnt)=>{
    const r=15.9,c=+(2*Math.PI*r).toFixed(2),d=+(pct/100*c).toFixed(2),g=+(c-d).toFixed(2);
    return `<div class="don-wrap">
      <svg width="60" height="60" viewBox="0 0 36 36">
        <circle cx="18" cy="18" r="${r}" fill="none" stroke="#1a2e4a" stroke-width="4"/>
        <circle cx="18" cy="18" r="${r}" fill="none" stroke="${clr}" stroke-width="4"
          stroke-dasharray="${d} ${g}" stroke-dashoffset="25"/>
        <text x="18" y="21" text-anchor="middle" font-size="7" font-weight="bold" fill="${clr}">${pct}%</text>
      </svg>
      <div style="color:${clr};font-size:.9rem;font-weight:800;line-height:1">${pct}%</div>
      <div style="color:${clr};font-size:.72rem;font-weight:600;margin-top:.1rem">${cnt} 篇</div>
      <div class="don-lbl">${lbl}</div>
    </div>`;
  };
  el.innerHTML = mksvg(pn,'#ef4444','🔴 負面',neg)+mksvg(pu,'#94a3b8','⚪ 中立',neu)+mksvg(pp,'#22c55e','🟢 正面',pos);
}

/* ══════════════════════════════════════════
   4 分類圓圈（固定尺寸）
══════════════════════════════════════════ */
function renderCatCircles() {
  const el = document.getElementById('catCircles');
  const counts = {};
  Object.keys(CAT_GROUPS).forEach(g=>{
    const cats = CAT_GROUPS[g].cats;
    counts[g] = allItemsFlat.filter(x=>cats.includes(x.category||'')).length;
  });

  el.innerHTML = Object.entries(CAT_GROUPS).map(([name, cfg])=>{
    const count = counts[name]||0;
    return `<div class="cat-circle" id="cc-${name.replace(/\s/g,'_')}" onclick="selectCat('${name}',this)">
      <div class="cat-ring" style="background:${cfg.grad}">
        <div style="font-size:1.5rem;line-height:1">${cfg.icon}</div>
        <div style="font-size:1.15rem;font-weight:900;line-height:1.1">${count}</div>
        <div style="font-size:.72rem;opacity:.85">則</div>
      </div>
      <div class="cat-name text-slate-600 font-semibold">${name}</div>
    </div>`;
  }).join('');
}

function selectCat(name, el) {
  highPriorityOnly = false;
  activeCatGroup = (activeCatGroup===name) ? null : name;
  document.querySelectorAll('.cat-circle').forEach(c=>c.classList.remove('active'));
  if (activeCatGroup && el) el.classList.add('active');
  applyFilters();
}

/* ══════════════════════════════════════════
   今日負面輿情（取代今日緊急預警）
══════════════════════════════════════════ */
function renderTodayNeg(latest) {
  const items = (MONITOR_DATA[latest]?.items||[]).filter(x=>getSentiment(x)==='負面' && normalizeDate(x.pub_date||x.published||x.date||'')===latest);
  const el = document.getElementById('todayNegList');
  const countEl = document.getElementById('todayNegCount');
  if (!items.length) {
    el.innerHTML='';
    document.getElementById('todayNegEmpty').classList.remove('hidden'); return;
  }
  document.getElementById('todayNegEmpty').classList.add('hidden');
  countEl.textContent = items.length+'則';
  const tracked = getTracked();
  el.innerHTML = items.map((item,i)=>{
    const id = getItemId(item);
    let domain='';
    try{ domain = new URL(item.url||'').hostname; }catch(e){}
    const isTracked = !!tracked[id];
    const pri = item.priority==='高' ? '<span class="text-xs bg-red-200 text-red-700 px-1.5 py-0.5 rounded-full ml-1">高優先</span>' : '';
    return `<div class="urg-card flex gap-0 overflow-hidden" id="tdn-${i}">
      <div style="width:44px;min-width:44px;background:linear-gradient(135deg,#7f1d1d,#dc2626);display:flex;align-items:center;justify-content:center">
        ${domain ? `<img src="https://www.google.com/s2/favicons?sz=32&domain=${domain}" class="w-6 h-6 rounded" onerror="this.style.display='none'">` : '<span class="text-white text-xs">📰</span>'}
      </div>
      <div class="flex-1 p-2 min-w-0">
        <a href="${item.url||'#'}" target="_blank" rel="noopener"
           class="link-title text-xs font-semibold block mb-1 leading-snug line-clamp-2">${item.title||''}${pri}</a>
        <div class="flex items-center gap-2 flex-wrap">
          <span class="text-xs text-slate-400">${item.source||''}</span>
          <span class="text-xs text-slate-300">${toROC(item.pub_date||item.published||item.date)}</span>
          <button onclick="todayNegTrack('${id}',${i})"
            id="tdn-btn-${i}"
            class="ml-auto text-xs px-2 py-0.5 rounded-full font-medium border transition ${isTracked?'bg-blue-600 text-white border-blue-600':'bg-white text-blue-600 border-blue-300 hover:bg-blue-50'}">
            ${isTracked?'✓ 已關注':'+ 關注'}
          </button>
          ${item.line_message?`<button onclick="cpText('tdnmsg-${i}',this)" class="text-xs bg-green-500 text-white px-2 py-0.5 rounded-full font-medium">📋 LINE</button>`:''}
        </div>
      </div>
      ${item.line_message?`<p id="tdnmsg-${i}" class="hidden">${item.line_message}</p>`:''}
    </div>`;
  }).join('');
}

function todayNegTrack(id, idx) {
  const t=getTracked();
  t[id]=!t[id]; if(!t[id]) delete t[id];
  saveTracked(t);
  const btn=document.getElementById('tdn-btn-'+idx);
  if(btn){
    btn.textContent=t[id]?'✓ 已關注':'+ 關注';
    btn.className='ml-auto text-xs px-2 py-0.5 rounded-full font-medium border transition '+(t[id]?'bg-blue-600 text-white border-blue-600':'bg-white text-blue-600 border-blue-300 hover:bg-blue-50');
  }
  renderClarifyList();
}

/* ══════════════════════════════════════════
   澄清追蹤列表
══════════════════════════════════════════ */
function renderClarifyList() {
  const tracked = getTracked();
  const workflows = getWorkflows();
  const el = document.getElementById('clarifyList');
  const empty = document.getElementById('clarifyEmpty');
  const trackedItems = allItemsFlat.filter(x=>tracked[getItemId(x)]);
  document.getElementById('trackCount').textContent = trackedItems.length ? `共${trackedItems.length}則` : '';

  if (!trackedItems.length) {
    el.classList.add('hidden'); empty.classList.remove('hidden'); return;
  }
  el.classList.remove('hidden'); empty.classList.add('hidden');

  const stages = ['澄清文稿','長官同意','確認發布','歸檔'];
  el.innerHTML = trackedItems.map(item=>{
    const id = getItemId(item);
    const wf = workflows[id]||{stage:1};
    const cur = wf.stage||1;
    const stageHtml = stages.map((s,i)=>{
      const n=i+1;
      const cls = n<cur?'wf-stage done':n===cur?'wf-stage current':'wf-stage';
      return `<button class="${cls}" onclick="wfAction('${id}',${n})">${n}.${s}</button>`;
    }).join('');
    return `<div class="border border-slate-100 rounded-lg p-2.5 hover:bg-slate-50 transition">
      <div class="flex items-start gap-2 mb-2">
        <a href="${item.url||'#'}" target="_blank" rel="noopener"
           class="link-title text-xs font-semibold flex-1 leading-snug line-clamp-1">${item.title||''}</a>
        <span class="text-xs text-slate-400 shrink-0">${toROC(item.pub_date||item.published||item.date)}</span>
        <button onclick="untrack('${id}')" class="text-slate-300 hover:text-red-400 text-xs shrink-0" title="移除追蹤">✕</button>
      </div>
      <div class="flex flex-wrap gap-1">${stageHtml}</div>
    </div>`;
  }).join('');
}

function wfAction(id, stage) {
  const wf = getWorkflows();
  if (!wf[id]) wf[id] = {stage:1};
  if (stage === 1) { openModal(id); return; }
  if (stage === 4) { archiveToForm(id); return; }
  // 點擊後往前推一步（已超過則不退回）
  const cur = wf[id].stage || 1;
  wf[id].stage = cur <= stage ? stage + 1 : cur;
  saveWorkflows(wf);
  renderClarifyList();
}


function archiveToForm(id) {
  const item = allItemsFlat.find(x=>getItemId(x)===id);
  if (!item) return;
  const wf = getWorkflows();
  if(!wf[id]) wf[id]={stage:1};
  wf[id].stage = 5;  // 5 = 所有步驟完成，按鈕全部顯示藍色
  const lineMsg = wf[id].edited_text || item.line_message || '';
  saveWorkflows(wf);
  // 用 GET + action=archive 寫入歸檔試算表（避免 CORS 問題）
  if (_SHEETS_GET_URL) {
    const p = new URLSearchParams({
      action:       'archive',
      date:         item.date || item.published || '',
      title:        (item.title || '').slice(0, 150),
      source:       item.source || '',
      url:          (item.url || '').slice(0, 200),
      sentiment:    item.sentiment || '負面',
      category:     item.category || '',
      line_message: lineMsg.slice(0, 500)
    });
    fetch(_SHEETS_GET_URL + '?' + p.toString(), {redirect:'follow'})
      .then(r=>r.json())
      .then(d=>{ showToast(d.error ? '歸檔失敗：'+d.error : '已歸檔 ✓'); })
      .catch(()=>{ showToast('歸檔失敗，請稍後再試'); });
  }
  // 先移除追蹤，再渲染，避免短暫閃爍
  const t=getTracked(); delete t[id]; saveTracked(t);
  renderClarifyList();
  const dates = Object.keys(MONITOR_DATA).sort();
  renderTodayNeg(dates[dates.length-1]||'');
}

function untrack(id) {
  const t=getTracked(); delete t[id]; saveTracked(t); renderClarifyList();
}

/* ══════════════════════════════════════════
   工作流 Modal
══════════════════════════════════════════ */
function _modalBase(id, title, bodyHtml) {
  document.getElementById('wfModalContent').innerHTML = `
    <div class="mb-3">
      <div class="text-xs text-slate-400 mb-1">新聞標題</div>
      <div class="text-sm font-medium text-slate-700 leading-snug">${title}</div>
    </div>
    ${bodyHtml}`;
  document.getElementById('wfModal').classList.remove('hidden');
}

function openModal(id) {
  const item = allItemsFlat.find(x=>getItemId(x)===id);
  const wf   = getWorkflows()[id]||{stage:1};
  const text = wf.edited_text || '';
  _modalBase(id, item?.title||'', `
    <div class="mb-4">
      <div class="text-xs text-slate-400 mb-1">澄清文稿（可手動修正）</div>
      <textarea id="wfTextarea" rows="6"
        class="w-full border border-slate-200 rounded-lg p-3 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300">${text}</textarea>
    </div>
    <div class="flex gap-2 justify-end">
      <button onclick="closeModal()" class="text-xs border border-slate-200 rounded-lg px-4 py-2 hover:bg-slate-50">取消</button>
      <button id="wfSaveBtn" onclick="saveEdit('${id}')"
        class="text-xs bg-blue-600 text-white rounded-lg px-4 py-2 hover:bg-blue-700 font-medium">儲存修正</button>
    </div>`);
}

function saveEdit(id) {
  const text = document.getElementById('wfTextarea').value;
  const wf = getWorkflows();
  if (!wf[id]) wf[id]={stage:1};
  wf[id].edited_text = text;
  wf[id].stage = Math.max(wf[id].stage||1, 2);
  saveWorkflows(wf);
  closeModal();
  renderClarifyList();
}

function closeModal() { document.getElementById('wfModal').classList.add('hidden'); }

/* ══════════════════════════════════════════
   Excel / CSV 匯出
══════════════════════════════════════════ */
function exportCSV() {
  const tracked = getTracked();
  const wf = getWorkflows();
  const items = allItemsFlat.filter(x=>tracked[getItemId(x)]);
  if (!items.length) { alert('尚無追蹤中的輿情'); return; }
  const stages = ['','澄清文稿','長官同意','確認發布','歸檔'];
  const rows = items.map(item=>{
    const id=getItemId(item), w=wf[id]||{};
    return [toROC(item.published),item.title||'',item.source||'',item.url||'',
      getSentiment(item), item.category||'', stages[w.stage||1]||'', w.edited_text||item.line_message||'']
      .map(v=>`"${String(v).replace(/"/g,'""')}"`).join(',');
  });
  const csv='日期,標題,來源,網址,情感,分類,進度,澄清文字\n'+rows.join('\n');
  dlFile('﻿'+csv,'輿情追蹤_'+TODAY+'.csv','text/csv;charset=utf-8');
}

function dlFile(content, name, type) {
  const blob=new Blob([content],{type});
  const url=URL.createObjectURL(blob);
  const a=document.createElement('a'); a.href=url; a.download=name; a.click(); URL.revokeObjectURL(url);
}

/* ══════════════════════════════════════════
   篩選
══════════════════════════════════════════ */
function applyFilters() {
  const sent   = document.getElementById('sentFilter').value;
  const sortBy = document.getElementById('sortBy').value;
  const kw     = document.getElementById('searchBox').value.toLowerCase();
  const from   = document.getElementById('dateFrom').value;
  const to     = document.getElementById('dateTo').value;
  const tracked = getTracked();

  let f = [...allItemsFlat];

  if (activeCatGroup) {
    const cats = CAT_GROUPS[activeCatGroup].cats;
    f = f.filter(x=>cats.includes(x.category||''));
  }

  if (sent) f = f.filter(x=>getSentiment(x)===sent);
  if (highPriorityOnly) f = f.filter(x=>x.priority==='高');

  if (from) f = f.filter(x=>normalizeDate(x.pub_date||x.published||x.date||'')>=from);
  if (to)   f = f.filter(x=>normalizeDate(x.pub_date||x.published||x.date||'')<=to);

  if (kw) f = f.filter(x=>(x.title||'').toLowerCase().includes(kw)||(x.keyword||'').toLowerCase().includes(kw)||(x.content||'').toLowerCase().includes(kw));

  const so={'負面':0,'中立':1,'正面':2}, po={'高':0,'中':1,'低':2};
  if      (sortBy==='date-desc') f.sort((a,b)=>(normalizeDate(b.pub_date||b.published||b.date||'')>normalizeDate(a.pub_date||a.published||a.date||'')?1:-1));
  else if (sortBy==='date-asc')  f.sort((a,b)=>(normalizeDate(a.pub_date||a.published||a.date||'')>normalizeDate(b.pub_date||b.published||b.date||'')?1:-1));
  else if (sortBy==='tracked')   f.sort((a,b)=>(tracked[getItemId(b)]?1:0)-(tracked[getItemId(a)]?1:0));
  else f.sort((a,b)=>{ const s=(so[getSentiment(a)]||2)-(so[getSentiment(b)]||2); return s!==0?s:(po[a.priority]||2)-(po[b.priority]||2); });

  document.getElementById('showCount').textContent = f.length;
  document.getElementById('showNeg').textContent   = f.filter(x=>getSentiment(x)==='負面').length;
  document.getElementById('showPos').textContent   = f.filter(x=>getSentiment(x)==='正面').length;
  document.getElementById('showNeu').textContent   = f.filter(x=>getSentiment(x)==='中立').length;

  filteredItems = f;
  currentPage = 1;

  // 更新側邊欄圓環（對應當前日期範圍）
  renderDonut(activeCatGroup);
  renderPage();
}

/* ══════════════════════════════════════════
   分頁
══════════════════════════════════════════ */
function renderPage() {
  const total=filteredItems.length, pages=Math.max(1,Math.ceil(total/PAGE_SIZE));
  currentPage=Math.min(currentPage,pages);
  const start=(currentPage-1)*PAGE_SIZE;
  document.getElementById('pageInfo').textContent=total>0?`第${currentPage}/${pages}頁（每頁${PAGE_SIZE}則）`:'';
  renderNewsList(filteredItems.slice(start,start+PAGE_SIZE));
  renderPagination(pages);
}

function renderPagination(pages) {
  const pg=document.getElementById('pagination');
  if(pages<=1){pg.innerHTML='';return;}
  let b=[];
  b.push(`<button class="pg-btn" ${currentPage===1?'disabled':''} onclick="goPage(${currentPage-1})">‹</button>`);
  let s=Math.max(1,currentPage-2),e=Math.min(pages,currentPage+2);
  if(s>1){b.push(`<button class="pg-btn" onclick="goPage(1)">1</button>`);if(s>2)b.push(`<span class="text-slate-300 px-1 text-sm">…</span>`);}
  for(let i=s;i<=e;i++) b.push(`<button class="pg-btn ${i===currentPage?'on':''}" onclick="goPage(${i})">${i}</button>`);
  if(e<pages){if(e<pages-1)b.push(`<span class="text-slate-300 px-1 text-sm">…</span>`);b.push(`<button class="pg-btn" onclick="goPage(${pages})">${pages}</button>`);}
  b.push(`<button class="pg-btn" ${currentPage===pages?'disabled':''} onclick="goPage(${currentPage+1})">›</button>`);
  pg.innerHTML=b.join('');
}

function goPage(p){currentPage=p;renderPage();document.getElementById('newsList').scrollIntoView({behavior:'smooth',block:'start'});}

/* ══════════════════════════════════════════
   新聞列表
══════════════════════════════════════════ */
function renderNewsList(items) {
  const c=document.getElementById('newsList'), e=document.getElementById('emptyState');
  if(!items.length){c.innerHTML='';e.classList.remove('hidden');return;}
  e.classList.add('hidden');
  const tracked=getTracked();
  c.innerHTML=items.map((item,idx)=>{
    const id=getItemId(item);
    const sent=getSentiment(item);
    const neg=sent==='負面',pos=sent==='正面';
    const bc=neg?'card-neg':pos?'card-pos':'card-neu';
    const bg=item.priority==='高'&&neg?'bg-red-50':'';
    const sc=neg?'bg-red-100 text-red-700':pos?'bg-green-100 text-green-700':'bg-slate-100 text-slate-500';
    const isTracked=!!tracked[id];
    const clarify=neg&&item.line_message?`
      <div class="line-box p-3 mt-2.5">
        <div class="flex justify-between items-center mb-1.5">
          <span class="text-xs font-semibold text-green-700">📱 AI 澄清建議（一鍵複製傳 LINE）</span>
          <button onclick="cpText('cl-${idx}',this)" class="text-xs bg-green-500 hover:bg-green-600 text-white px-3 py-0.5 rounded-full font-medium">複製</button>
        </div>
        <p id="cl-${idx}" class="text-xs text-slate-700 leading-relaxed">${item.line_message}</p>
      </div>`:'';
    return `<div class="news-card p-3.5 border border-slate-100 ${bg} ${bc}" id="card-${idx}">
      <div class="flex flex-wrap gap-1.5 mb-2 items-center">
        <span class="text-xs px-2 py-0.5 rounded-full font-medium ${sc}">${sent}</span>
        <span class="text-xs px-2 py-0.5 rounded-full bg-blue-50 text-blue-600">${item.category||''}</span>
        <span class="text-xs px-2 py-0.5 rounded-full bg-purple-50 text-purple-500">${item.platform||''}</span>
        ${item.priority==='高'?'<span class="text-xs px-2 py-0.5 rounded-full bg-orange-100 text-orange-600">高優先</span>':''}
        <span class="text-xs text-slate-300 ml-auto">${item.source||''}</span>
      </div>
      <a href="${item.url||'#'}" target="_blank" rel="noopener"
         class="link-title font-semibold text-sm block mb-1 leading-snug">${item.title||''}</a>
      <p class="text-xs text-slate-400 mb-2">${item.content?item.content.slice(0,80)+'…':''}</p>
      ${clarify}
      <div class="mt-2.5 pt-2 border-t border-slate-100 flex items-center gap-2 flex-wrap">
        <span class="text-xs text-slate-400" title="發布日期">${toROC(item.pub_date||item.published||item.date)}</span>
        <div class="flex items-center gap-1 ml-auto">
          <span class="text-xs text-slate-400">修正：</span>
          <button class="corr-btn corr-neg ${sent==='負面'?'on':''}" onclick="correct('${id}','負面',${idx})">負面</button>
          <button class="corr-btn corr-pos ${sent==='正面'?'on':''}" onclick="correct('${id}','正面',${idx})">正面</button>
          <button class="corr-btn corr-neu ${sent==='中立'?'on':''}" onclick="correct('${id}','中立',${idx})">中立</button>
          <button class="track-btn ml-2 ${isTracked?'on':''}" onclick="toggleTrack('${id}',${idx})"
            id="tb-${idx}">${isTracked?'✓ 已關注':'+ 關注'}</button>
        </div>
      </div>
    </div>`;
  }).join('');
}

/* ══════════════════════════════════════════
   修正情感
══════════════════════════════════════════ */
function correct(id, newSent, idx) {
  const c=getCorrections();
  if(c[id]===newSent){delete c[id];}else{c[id]=newSent;}
  saveCorrections(c);
  renderDonut(activeCatGroup);
  const cur=c[id]||allItemsFlat.find(x=>getItemId(x)===id)?.sentiment||'中立';
  ['負面','正面','中立'].forEach(s=>{
    const btn=document.querySelector(`#card-${idx} .corr-${s==='負面'?'neg':s==='正面'?'pos':'neu'}`);
    if(btn){btn.classList.toggle('on',cur===s);}
  });
  const sentEl=document.querySelector(`#card-${idx} .rounded-full.font-medium`);
  if(sentEl){
    sentEl.textContent=cur;
    sentEl.className='text-xs px-2 py-0.5 rounded-full font-medium '+(cur==='負面'?'bg-red-100 text-red-700':cur==='正面'?'bg-green-100 text-green-700':'bg-slate-100 text-slate-500');
  }
}

/* ══════════════════════════════════════════
   追蹤切換
══════════════════════════════════════════ */
function toggleTrack(id, idx) {
  const t=getTracked();
  t[id]=!t[id]; if(!t[id]) delete t[id];
  saveTracked(t);
  const btn=document.getElementById('tb-'+idx);
  if(btn){btn.textContent=t[id]?'✓ 已關注':'+ 關注'; btn.classList.toggle('on',!!t[id]);}
  renderClarifyList();
}

/* ══════════════════════════════════════════
   關鍵字頻率排行 + 點擊 Modal
══════════════════════════════════════════ */
function renderKwRanking() {
  const el = document.getElementById('kwRanking');
  if (!el || !KEYWORD_RANKING.length) { if(el) el.innerHTML='<p class="text-xs text-blue-400">暫無資料</p>'; return; }
  const max = KEYWORD_RANKING[0][1] || 1;
  el.innerHTML = KEYWORD_RANKING.map(([kw, cnt]) => {
    const pct = Math.round(cnt / max * 100);
    return `<div class="sb-clickable py-0.5" onclick="filterByKeyword('${kw.replace(/'/g,"\\'")}')">
      <div class="flex justify-between text-xs mb-0.5">
        <span class="text-blue-200 truncate" title="${kw}">${kw}</span>
        <span class="text-yellow-400 font-bold ml-1 shrink-0">${cnt}</span>
      </div>
      <div style="height:4px;background:#1a2e4a;border-radius:2px">
        <div style="height:4px;width:${pct}%;background:#2d6a9f;border-radius:2px"></div>
      </div>
    </div>`;
  }).join('');
}

function filterByKeyword(kw) {
  const items = allItemsFlat.filter(x => (x.keyword||'') === kw || (x.title||'').includes(kw));
  showKwModal(kw, items);
}

function showKwModal(kw, items) {
  document.getElementById('kwModalTitle').textContent = `「${kw}」共 ${items.length} 則`;
  const sorted = [...items].sort((a,b)=>
    (normalizeDate(b.date||b.published||'')>normalizeDate(a.date||a.published||''))?1:-1
  );
  document.getElementById('kwModalContent').innerHTML = sorted.length
    ? sorted.map(item=>{
        const s=getSentiment(item);
        const sc=s==='負面'?'bg-red-100 text-red-700':s==='正面'?'bg-green-100 text-green-700':'bg-slate-100 text-slate-500';
        return `<div class="border border-slate-100 rounded-lg p-2.5 hover:bg-slate-50">
          <div class="flex flex-wrap gap-1.5 mb-1 items-center">
            <span class="text-xs px-2 py-0.5 rounded-full font-medium ${sc}">${s}</span>
            <span class="text-xs text-slate-400">${item.source||''}</span>
            <span class="text-xs text-slate-300 ml-auto">${normalizeDate(item.pub_date||item.published||item.date||'')}</span>
          </div>
          <a href="${item.url||'#'}" target="_blank" rel="noopener"
             class="link-title text-sm font-medium block leading-snug">${item.title||''}</a>
          ${item.content?`<p class="text-xs text-slate-400 mt-1">${item.content.slice(0,80)}…</p>`:''}
        </div>`;
      }).join('')
    : '<p class="text-center text-slate-400 py-8 text-sm">此關鍵字無相關文章</p>';
  document.getElementById('kwModal').classList.remove('hidden');
}

function closeKwModal() { document.getElementById('kwModal').classList.add('hidden'); }

/* ══════════════════════════════════════════
   複製工具
══════════════════════════════════════════ */
function cpText(id,btn){
  const el=document.getElementById(id); if(!el) return;
  navigator.clipboard.writeText(el.textContent.trim()).then(()=>{
    const o=btn.textContent; btn.textContent='✓ 已複製'; btn.classList.replace('bg-green-500','bg-slate-400');
    setTimeout(()=>{btn.textContent=o;btn.classList.replace('bg-slate-400','bg-green-500');},2000);
  });
}

/* ══════════════════════════════════════════
   資料載入：優先從 Google Sheets，失敗才用 data.js
══════════════════════════════════════════ */
const _SHEETS_GET_URL = typeof SHEETS_API_URL !== 'undefined' ? SHEETS_API_URL : '';

async function loadFromSheets() {
  if (!_SHEETS_GET_URL) return false;
  try {
    const resp = await fetch(_SHEETS_GET_URL + '?action=getAll', {redirect:'follow'});
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    const data = await resp.json();
    if (data.error || !data.monitor_data) throw new Error(data.error || 'no monitor_data');
    // Sheets 回傳空資料時，保留 data.js 的本地資料，不覆蓋
    if (Object.keys(data.monitor_data).length === 0) throw new Error('Sheets monitor_data 為空，使用本地資料');
    if (typeof MONITOR_DATA !== 'undefined') Object.assign(window, {
      MONITOR_DATA:    data.monitor_data,
      TODAY:           data.today           || TODAY,
      TOPIC_HEAT:      data.topic_heat      || TOPIC_HEAT,
      KEYWORD_RANKING: data.keyword_ranking || KEYWORD_RANKING,
      TOTAL_ALL:       data.total_all       != null ? data.total_all       : TOTAL_ALL,
      TOTAL_NEG_ALL:   data.total_neg_all   != null ? data.total_neg_all   : TOTAL_NEG_ALL
    });
    console.log('[Sheets] 載入成功，共', Object.keys(data.monitor_data).length, '天');
    return true;
  } catch(e) {
    console.warn('[Sheets] 讀取失敗，使用 data.js 備援:', e.message);
    return false;
  }
}

window.addEventListener('DOMContentLoaded', async () => {
  await loadFromSheets();
  init();
});
</script>
</body>
</html>"""
    with open(os.path.join(DOCS_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)

if __name__ == "__main__":
    main()
