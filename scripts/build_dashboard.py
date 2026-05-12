"""
產生 GitHub Pages 靜態儀表板（v4 全面改版）
設計原則：日常預警 → 議題追蹤 → 政策評估
"""
import json, os, glob
from datetime import date
from collections import Counter, defaultdict

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
DOCS_DIR = os.path.join(os.path.dirname(__file__), "..", "docs")
os.makedirs(DOCS_DIR, exist_ok=True)
TODAY = date.today().isoformat()

def load_recent_data(days=30):
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
  /* Sidebar */
  .sidebar { background:#0a1628; }
  .sb-sec  { border-bottom:1px solid #1a2e4a; padding:.875rem 1rem; }
  .sb-sec:last-child { border-bottom:none; }
  .sb-title { color:#7eb4d8; font-size:.72rem; font-weight:700; letter-spacing:.06em; text-transform:uppercase; margin-bottom:.625rem; display:block; }
  .sb-lbl   { color:#5a85a8; font-size:.68rem; letter-spacing:.04em; text-transform:uppercase; display:block; margin-bottom:.3rem; }
  .sb-sel   { width:100%; background:#152035; border:1px solid #243c57; color:#d4e4f5; border-radius:.5rem; padding:.35rem .6rem; font-size:.78rem; outline:none; appearance:none; }
  .sb-sel:focus { border-color:#3d7ab5; }
  /* KPI */
  .kpi  { background:white; border-radius:.875rem; padding:.875rem 1.125rem; box-shadow:0 2px 10px rgba(0,0,0,.08); }
  .knum { font-size:2.4rem; font-weight:800; line-height:1; letter-spacing:-.03em; }
  /* Cards */
  .card-neg { border-left:4px solid #ef4444; }
  .card-pos { border-left:4px solid #22c55e; }
  .card-neu { border-left:4px solid #cbd5e1; }
  .news-card { background:white; border-radius:.75rem; box-shadow:0 1px 4px rgba(0,0,0,.06); transition:box-shadow .15s; }
  .news-card:hover { box-shadow:0 4px 16px rgba(0,0,0,.12); }
  .link-title { color:#1d4ed8; text-decoration:underline; text-underline-offset:2px; cursor:pointer; }
  .link-title:hover { color:#1e40af; }
  .line-box  { background:linear-gradient(135deg,#f0fdf4,#dcfce7); border:1px solid #86efac; border-radius:.75rem; }
  .urg-card  { background:#fff1f2; border:1px solid #fca5a5; border-radius:.625rem; }
  /* Bubble */
  .bubble { border-radius:50%; display:inline-flex; align-items:center; justify-content:center; color:white; font-weight:700; cursor:pointer; transition:transform .15s; text-align:center; line-height:1.2; }
  .bubble:hover { transform:scale(1.1); }
  /* Donut */
  .don-wrap { display:flex; flex-direction:column; align-items:center; gap:.15rem; cursor:pointer; }
  .don-lbl  { font-size:.62rem; color:#5a85a8; }
  /* Chip */
  .chip { font-size:.72rem; padding:.25rem .75rem; border-radius:9999px; cursor:pointer; border:1px solid #cbd5e1; color:#64748b; background:white; transition:all .15s; }
  .chip.on { background:#1e5799; border-color:#1e5799; color:white; }
  .chip:hover:not(.on) { border-color:#94a3b8; background:#f8fafc; }
  /* Spotlight filter */
  .spl-btn { font-size:.68rem; padding:.2rem .6rem; border-radius:9999px; cursor:pointer; border:1px solid #243c57; color:#7eb4d8; background:transparent; transition:all .15s; }
  .spl-btn.on { background:#1e5799; border-color:#1e5799; color:white; }
  /* Badge */
  .bdg-done { background:#dcfce7; color:#15803d; font-size:.65rem; padding:.15rem .5rem; border-radius:9999px; white-space:nowrap; }
  .bdg-todo { background:#fef3c7; color:#92400e; font-size:.65rem; padding:.15rem .5rem; border-radius:9999px; white-space:nowrap; }
  /* Pagination */
  .pg-btn { padding:.3rem .7rem; border-radius:.5rem; font-size:.8rem; border:1px solid #e2e8f0; background:white; cursor:pointer; transition:all .15s; color:#475569; }
  .pg-btn:hover:not(:disabled) { background:#1e5799; color:white; border-color:#1e5799; }
  .pg-btn.on { background:#1e5799; color:white; border-color:#1e5799; }
  .pg-btn:disabled { opacity:.4; cursor:not-allowed; }
  /* Misc */
  .ai-badge { background:linear-gradient(135deg,#667eea,#764ba2); }
  .pulse    { animation:pulse 2s infinite; }
  @keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}
  .bar-fill { transition:width .8s ease; }
  .tag-btn  { font-size:.7rem; padding:.25rem .7rem; border-radius:9999px; cursor:pointer; transition:opacity .15s; }
  .tag-btn:hover { opacity:.7; }
  @media(max-width:1023px){ .layout-sidebar{ display:none !important; } .layout-main{ grid-template-columns:1fr !important; } }
</style>
</head>
<body>

<!-- ── Header ── -->
<header style="background:linear-gradient(160deg,#0a1628 0%,#0e2d5e 60%,#1a4a8a 100%)" class="text-white shadow-xl">
  <div class="max-w-7xl mx-auto px-5 py-4">
    <div class="flex justify-between items-start gap-4 flex-wrap">
      <div class="flex items-center gap-4">
        <div style="background:rgba(255,255,255,.1);border:1px solid rgba(255,255,255,.2)"
             class="w-12 h-12 rounded-xl flex items-center justify-center text-2xl shrink-0">💧</div>
        <div>
          <div class="text-blue-300 text-xs tracking-widest mb-0.5">114–115年度 臺南海水淡化廠暨南區水資源推廣計畫</div>
          <h1 class="text-xl font-extrabold tracking-tight">輿情監控系統</h1>
          <div class="flex items-center gap-1.5 mt-1.5 flex-wrap">
            <span style="background:rgba(255,255,255,.15)" class="text-xs px-2.5 py-0.5 rounded-full text-blue-100 font-medium">日常預警</span>
            <span class="text-blue-400 text-xs">→</span>
            <span style="background:rgba(255,255,255,.15)" class="text-xs px-2.5 py-0.5 rounded-full text-blue-100 font-medium">議題追蹤</span>
            <span class="text-blue-400 text-xs">→</span>
            <span style="background:rgba(255,255,255,.15)" class="text-xs px-2.5 py-0.5 rounded-full text-blue-100 font-medium">政策評估</span>
          </div>
        </div>
      </div>
      <div class="flex items-start gap-5 shrink-0 flex-wrap">
        <div class="text-right hidden sm:block">
          <div class="text-blue-300 text-xs mb-0.5">最新資料日期</div>
          <div class="text-white font-bold text-base" id="latestDateDisplay">-</div>
          <div class="text-blue-400 text-xs mt-0.5">🕐 每日 07:00 更新</div>
        </div>
        <div class="text-right">
          <div class="text-blue-300 text-xs mb-1">近30天累計</div>
          <div class="flex items-baseline gap-3">
            <div><span class="text-2xl font-bold" id="totalAllCount">-</span><span class="text-blue-300 text-xs ml-1">則</span></div>
            <div><span class="text-xl font-bold text-red-300" id="totalNegCount">-</span><span class="text-blue-300 text-xs ml-1">負面</span></div>
          </div>
        </div>
        <div class="ai-badge text-white text-xs px-3 py-1.5 rounded-full flex items-center gap-1.5 self-start shadow">
          <span class="pulse w-1.5 h-1.5 bg-white rounded-full"></span>🤖 AI 自動分析
        </div>
      </div>
    </div>
  </div>
</header>

<!-- ── Alert Bar ── -->
<div id="alertBar" class="hidden text-white px-5 py-2" style="background:#b91c1c">
  <div class="max-w-7xl mx-auto flex items-center gap-2">
    <span class="shrink-0">🚨</span>
    <span id="alertText" class="font-medium text-sm flex-1"></span>
    <button onclick="document.getElementById('sentFilter').value='負面';applyFilters()"
      class="shrink-0 text-xs bg-white text-red-700 font-semibold px-3 py-1 rounded-full hover:bg-red-50 ml-2">
      查看全部負面 →
    </button>
  </div>
</div>

<!-- ── Stats Row ── -->
<div class="max-w-7xl mx-auto px-5 pt-4 pb-3">
  <div class="flex items-center gap-2 mb-2.5">
    <span class="text-xs text-slate-400">最新資料：</span>
    <span class="text-sm font-semibold text-slate-600" id="statsDateLabel">-</span>
    <span class="text-xs text-slate-300 ml-1">（以新聞發布日期為準）</span>
  </div>
  <div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
    <div class="kpi border-t-4 border-blue-400">
      <div class="text-xs text-slate-400 mb-1.5">當日蒐集</div>
      <div class="knum text-slate-700" id="statTotal">-</div>
      <div class="text-xs text-slate-400 mt-1">則新聞</div>
    </div>
    <div class="kpi border-t-4 border-red-500">
      <div class="text-xs text-slate-400 mb-1.5">當日負面</div>
      <div class="knum text-red-600" id="statNeg">-</div>
      <div class="text-xs text-red-300 mt-1">則需關注</div>
    </div>
    <div class="kpi border-t-4 border-green-500">
      <div class="text-xs text-slate-400 mb-1.5">當日正面</div>
      <div class="knum text-green-600" id="statPos">-</div>
      <div class="text-xs text-slate-400 mt-1">則正向報導</div>
    </div>
    <div class="kpi border-t-4 border-orange-500">
      <div class="text-xs text-slate-400 mb-1.5">高優先</div>
      <div class="knum text-orange-500" id="statHigh">-</div>
      <div class="text-xs text-orange-300 mt-1">則待立即處理</div>
    </div>
  </div>
</div>

<!-- ── Middle: Urgent + Clarify ── -->
<div class="max-w-7xl mx-auto px-5 pb-3">
  <div class="grid grid-cols-1 lg:grid-cols-5 gap-3">

    <!-- 今日緊急預警 -->
    <div class="lg:col-span-2 bg-red-50 border border-red-200 rounded-xl p-3.5">
      <div class="flex items-center justify-between mb-2.5">
        <div class="flex items-center gap-1.5">
          <span>🚨</span><span class="font-bold text-red-700 text-sm">今日緊急預警</span>
        </div>
        <span class="text-xs text-red-400" id="urgentCount"></span>
      </div>
      <div id="urgentList" class="space-y-2"></div>
      <div id="urgentEmpty" class="hidden text-center py-4 text-green-600 text-xs">✅ 今日無高優先負面輿情</div>
    </div>

    <!-- 負面輿情澄清追蹤 -->
    <div class="lg:col-span-3 bg-white border border-slate-100 rounded-xl p-3.5 shadow-sm">
      <div class="flex items-center justify-between mb-2.5">
        <div class="flex items-center gap-1.5">
          <span>📋</span><span class="font-bold text-slate-600 text-sm">近7日負面輿情 · 澄清追蹤</span>
        </div>
        <span class="text-xs text-slate-400">✅ = 已有AI澄清文</span>
      </div>
      <div id="clarifyList" class="space-y-1 max-h-52 overflow-y-auto pr-1"></div>
    </div>

  </div>
</div>

<!-- ── Main Layout ── -->
<div class="max-w-7xl mx-auto px-5 pb-10">
  <div class="layout-main" style="display:grid;grid-template-columns:248px 1fr;gap:16px;align-items:start">

    <!-- ── Sidebar ── -->
    <aside class="layout-sidebar sidebar rounded-xl overflow-hidden shadow-xl" style="position:sticky;top:12px">

      <!-- Sentiment Donut -->
      <div class="sb-sec">
        <span class="sb-title">📊 近30天情感分析</span>
        <div class="flex justify-around items-center py-1.5" id="sentimentDonuts"></div>
      </div>

      <!-- Topic Heat -->
      <div class="sb-sec">
        <span class="sb-title">🌡 議題負面熱度</span>
        <div id="topicHeat" class="space-y-2.5"></div>
      </div>

      <!-- Spotlight 2 weeks -->
      <div class="sb-sec">
        <div class="flex items-center justify-between mb-2.5">
          <span class="sb-title mb-0">📌 近2週焦點</span>
          <div class="flex gap-1">
            <button class="spl-btn on" onclick="setSpotlight('',this)">全部</button>
            <button class="spl-btn"    onclick="setSpotlight('正面',this)">正面</button>
            <button class="spl-btn"    onclick="setSpotlight('負面',this)">負面</button>
          </div>
        </div>
        <div id="spotlightList" class="space-y-2.5"></div>
      </div>

    </aside>

    <!-- ── Main Content ── -->
    <main class="space-y-3">

      <!-- Keyword Bubble -->
      <div class="bg-white rounded-xl shadow-sm p-4 border border-slate-100">
        <div class="flex justify-between items-center mb-3">
          <h3 class="font-semibold text-slate-600 text-sm">☁ 關鍵詞熱度</h3>
          <span class="text-xs text-slate-400">大小 = 出現頻率 · 點擊搜尋</span>
        </div>
        <div id="keywordCloud" class="flex flex-wrap gap-2 justify-center min-h-12 items-center"></div>
      </div>

      <!-- Filters -->
      <div class="bg-white rounded-xl shadow-sm p-4 border border-slate-100">
        <div class="flex flex-wrap gap-4 items-start">

          <!-- 1. 議題多選 -->
          <div class="flex-1 min-w-0">
            <div class="text-xs text-slate-400 mb-2">① 議題分類（可複選）</div>
            <div class="flex flex-wrap gap-1.5">
              <button class="chip" data-cat="海淡廠"    onclick="toggleCat(this)">海淡廠</button>
              <button class="chip" data-cat="南部水資源" onclick="toggleCat(this)">南部水資源</button>
              <button class="chip" data-cat="全台水資源" onclick="toggleCat(this)">全台水資源</button>
              <button class="chip" data-cat="社群輿情"   onclick="toggleCat(this)">社群輿情</button>
              <button class="chip" data-cat="國際"       onclick="toggleCat(this)">國際</button>
            </div>
          </div>

          <!-- 2. 日期範圍 -->
          <div class="shrink-0">
            <div class="text-xs text-slate-400 mb-2">② 日期範圍</div>
            <div class="flex items-center gap-1.5">
              <input type="date" id="dateFrom" oninput="applyFilters()"
                class="border border-slate-200 rounded-lg px-2 py-1 text-xs focus:outline-none focus:ring-2 focus:ring-blue-300">
              <span class="text-slate-400 text-xs">至</span>
              <input type="date" id="dateTo"   oninput="applyFilters()"
                class="border border-slate-200 rounded-lg px-2 py-1 text-xs focus:outline-none focus:ring-2 focus:ring-blue-300">
            </div>
          </div>

          <!-- 3. 情感 + 排序 -->
          <div class="shrink-0">
            <div class="text-xs text-slate-400 mb-2">③ 情感 ／ 排序</div>
            <div class="flex items-center gap-2">
              <select id="sentFilter" onchange="applyFilters()"
                class="border border-slate-200 rounded-lg px-2 py-1 text-xs focus:outline-none">
                <option value="">全部情感</option>
                <option value="負面">🔴 負面</option>
                <option value="正面">🟢 正面</option>
                <option value="中立">⚪ 中立</option>
              </select>
              <select id="sortBy" onchange="applyFilters()"
                class="border border-slate-200 rounded-lg px-2 py-1 text-xs focus:outline-none">
                <option value="neg-first">負面優先</option>
                <option value="date-desc">日期新→舊</option>
                <option value="date-asc">日期舊→新</option>
                <option value="priority">優先程度</option>
              </select>
            </div>
          </div>

          <!-- 搜尋 + 重置 -->
          <div class="shrink-0 self-end flex gap-2">
            <input type="text" id="searchBox" placeholder="關鍵字搜尋…" oninput="applyFilters()"
              class="border border-slate-200 rounded-lg px-3 py-1.5 text-xs w-36 focus:outline-none focus:ring-2 focus:ring-blue-300">
            <button onclick="resetFilters()"
              class="text-xs text-blue-500 border border-blue-200 rounded-lg px-3 py-1.5 hover:bg-blue-50 transition whitespace-nowrap">重置</button>
          </div>
        </div>

        <!-- Quick tags -->
        <div class="flex flex-wrap gap-1.5 mt-3 pt-3 border-t border-slate-100 items-center">
          <span class="text-xs text-slate-400 shrink-0">快速：</span>
          <button onclick="quickSearch('海淡廠')"   class="tag-btn bg-blue-50 text-blue-600">海淡廠</button>
          <button onclick="quickSearch('鹵水')"     class="tag-btn bg-red-50 text-red-500">鹵水</button>
          <button onclick="quickSearch('漁民')"     class="tag-btn bg-red-50 text-red-500">漁民</button>
          <button onclick="quickSearch('環評')"     class="tag-btn bg-orange-50 text-orange-500">環評</button>
          <button onclick="quickSearch('補償')"     class="tag-btn bg-orange-50 text-orange-500">補償</button>
          <button onclick="quickSearch('曾文水庫')" class="tag-btn bg-blue-50 text-blue-600">曾文水庫</button>
          <button onclick="quickSearch('缺水')"     class="tag-btn bg-red-50 text-red-500">缺水</button>
        </div>
      </div>

      <!-- Count + page info -->
      <div class="flex justify-between items-center px-1">
        <div class="text-sm text-slate-500">
          共 <strong id="showCount">0</strong> 則
          <span class="ml-2 text-red-500">負面 <strong id="showNeg">0</strong></span>
          <span class="ml-1.5 text-green-500">正面 <strong id="showPos">0</strong></span>
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
    <span>·</span><span>每日 07:00（台灣時間）自動蒐集分析</span>
    <span>·</span><span>Powered by Google Gemini AI &amp; GitHub Actions</span>
  </div>
</footer>

<script src="data.js"></script>
<script>
/* ── 狀態 ── */
let allItemsFlat = [];
let filteredItems = [];
let currentPage = 1;
const PAGE_SIZE = 30;
let selectedCats = new Set();

/* ── 初始化 ── */
function init() {
  document.getElementById('totalAllCount').textContent = (TOTAL_ALL||0).toLocaleString();
  document.getElementById('totalNegCount').textContent = (TOTAL_NEG_ALL||0).toLocaleString();

  const dates = Object.keys(MONITOR_DATA).sort();
  const latestDate = dates[dates.length-1] || '';
  document.getElementById('latestDateDisplay').textContent = latestDate;
  document.getElementById('statsDateLabel').textContent   = latestDate;

  if (latestDate && MONITOR_DATA[latestDate]) {
    const s = MONITOR_DATA[latestDate].stats || {};
    document.getElementById('statTotal').textContent = s.total || 0;
    document.getElementById('statNeg').textContent   = s.negative || 0;
    document.getElementById('statPos').textContent   = s.positive || 0;
    document.getElementById('statHigh').textContent  = s.high_priority || 0;
    if ((s.negative||0) > 0) {
      document.getElementById('alertBar').classList.remove('hidden');
      document.getElementById('alertText').textContent =
        latestDate + ' 共 ' + s.negative + ' 則負面，其中 ' + (s.high_priority||0) + ' 則高優先需立即處理';
    }
  }

  // 全部項目展平
  allItemsFlat = [];
  Object.values(MONITOR_DATA).forEach(d => { allItemsFlat = allItemsFlat.concat(d.items||[]); });

  // 日期範圍預設（最近14天）
  if (dates.length) {
    document.getElementById('dateFrom').value = dates[Math.max(0, dates.length-14)];
    document.getElementById('dateTo').value   = latestDate;
  }

  renderSentimentDonut();
  renderKeywordCloud();
  renderTopicHeat();
  renderSpotlight('');
  renderUrgent(latestDate);
  renderClarifyTrack();
  applyFilters();
}

/* ── 今日緊急預警 ── */
function renderUrgent(latestDate) {
  const items = (MONITOR_DATA[latestDate]?.items||[]).filter(x=>x.priority==='高'&&x.sentiment==='負面');
  const el = document.getElementById('urgentList');
  if (!items.length) {
    el.classList.add('hidden');
    document.getElementById('urgentEmpty').classList.remove('hidden');
    return;
  }
  document.getElementById('urgentCount').textContent = '共 '+items.length+' 則';
  el.classList.remove('hidden');
  document.getElementById('urgentEmpty').classList.add('hidden');
  el.innerHTML = items.slice(0,5).map((item,i) => `
    <div class="urg-card p-2.5">
      <a href="${item.url||'#'}" target="_blank" rel="noopener"
         class="link-title text-xs font-semibold block mb-1 leading-snug">${item.title||''}</a>
      <div class="flex items-center gap-2 flex-wrap">
        <span class="text-xs text-slate-400">${item.source||''}</span>
        <span class="text-xs text-slate-300">${(item.published||'').slice(0,10)}</span>
        ${item.line_message?`<button onclick="cpUrgent('ul-${i}',this)"
          class="ml-auto text-xs bg-green-500 text-white px-2 py-0.5 rounded-full">📋 複製</button>`:''}
      </div>
      ${item.line_message?`<p id="ul-${i}" class="hidden">${item.line_message}</p>`:''}
    </div>`).join('');
}

/* ── 澄清追蹤表 ── */
function renderClarifyTrack() {
  const el = document.getElementById('clarifyList');
  const dates = Object.keys(MONITOR_DATA).sort().reverse().slice(0,7);
  const items = [];
  dates.forEach(d => (MONITOR_DATA[d].items||[]).filter(x=>x.sentiment==='負面').forEach(x=>items.push(x)));
  const po = {'高':0,'中':1,'低':2};
  items.sort((a,b)=>(po[a.priority]||2)-(po[b.priority]||2));
  if (!items.length) { el.innerHTML='<div class="text-xs text-slate-400 py-2 text-center">近7日無負面輿情</div>'; return; }
  el.innerHTML = items.slice(0,25).map(item => {
    const has = !!item.line_message;
    const pc  = item.priority==='高'?'bg-red-100 text-red-700':'bg-amber-100 text-amber-700';
    const pl  = item.priority==='高'?'🚨高':'⚠中';
    return `<div class="flex items-center gap-2 py-1.5 border-b border-slate-50 last:border-0 text-xs hover:bg-slate-50 rounded px-1 transition">
      <span class="text-slate-400 shrink-0 w-10">${(item.published||'').slice(5,10)}</span>
      <a href="${item.url||'#'}" target="_blank" rel="noopener"
         class="flex-1 link-title truncate" style="max-width:250px" title="${item.title||''}">${item.title||''}</a>
      <span class="px-1.5 py-0.5 rounded-full shrink-0 ${pc}">${pl}</span>
      <span class="shrink-0">${has?'<span class="bdg-done">✅ 已澄清</span>':'<span class="bdg-todo">⏳ 待處理</span>'}</span>
    </div>`;
  }).join('');
}

/* ── 套用篩選 ── */
function applyFilters() {
  const sent   = document.getElementById('sentFilter').value;
  const sortBy = document.getElementById('sortBy').value;
  const kw     = document.getElementById('searchBox').value.toLowerCase();
  const from   = document.getElementById('dateFrom').value;
  const to     = document.getElementById('dateTo').value;

  let f = [...allItemsFlat];
  if (selectedCats.size > 0) f = f.filter(x => selectedCats.has(x.category));
  if (sent)  f = f.filter(x => x.sentiment === sent);
  if (from)  f = f.filter(x => (x.published||x.date||'') >= from);
  if (to)    f = f.filter(x => (x.published||x.date||'').slice(0,10) <= to);
  if (kw)    f = f.filter(x => (x.title||'').toLowerCase().includes(kw)||(x.keyword||'').toLowerCase().includes(kw));

  const so={'負面':0,'中立':1,'正面':2}, po={'高':0,'中':1,'低':2};
  if      (sortBy==='date-desc') f.sort((a,b)=>((b.published||b.date||'')>(a.published||a.date||'')?1:-1));
  else if (sortBy==='date-asc')  f.sort((a,b)=>((a.published||a.date||'')>(b.published||b.date||'')?1:-1));
  else if (sortBy==='priority')  f.sort((a,b)=>(po[a.priority]||2)-(po[b.priority]||2));
  else f.sort((a,b)=>{ const s=(so[a.sentiment]||2)-(so[b.sentiment]||2); return s!==0?s:(po[a.priority]||2)-(po[b.priority]||2); });

  document.getElementById('showCount').textContent = f.length;
  document.getElementById('showNeg').textContent   = f.filter(x=>x.sentiment==='負面').length;
  document.getElementById('showPos').textContent   = f.filter(x=>x.sentiment==='正面').length;
  document.getElementById('showNeu').textContent   = f.filter(x=>x.sentiment==='中立').length;

  filteredItems = f;
  currentPage = 1;
  renderPage();
}

/* ── 分頁 ── */
function renderPage() {
  const total = filteredItems.length;
  const pages = Math.max(1, Math.ceil(total/PAGE_SIZE));
  currentPage = Math.min(currentPage, pages);
  const start = (currentPage-1)*PAGE_SIZE;

  document.getElementById('pageInfo').textContent =
    total>0 ? `第 ${currentPage}/${pages} 頁（每頁${PAGE_SIZE}則）` : '';

  renderNewsList(filteredItems.slice(start, start+PAGE_SIZE));
  renderPagination(pages);
}

function renderPagination(pages) {
  const pg = document.getElementById('pagination');
  if (pages<=1) { pg.innerHTML=''; return; }
  let btns = [];
  btns.push(`<button class="pg-btn" ${currentPage===1?'disabled':''} onclick="goPage(${currentPage-1})">‹</button>`);
  let s=Math.max(1,currentPage-2), e=Math.min(pages,currentPage+2);
  if (s>1)  { btns.push(`<button class="pg-btn" onclick="goPage(1)">1</button>`); if(s>2) btns.push(`<span class="text-slate-300 text-sm px-1">…</span>`); }
  for (let i=s;i<=e;i++) btns.push(`<button class="pg-btn ${i===currentPage?'on':''}" onclick="goPage(${i})">${i}</button>`);
  if (e<pages) { if(e<pages-1) btns.push(`<span class="text-slate-300 text-sm px-1">…</span>`); btns.push(`<button class="pg-btn" onclick="goPage(${pages})">${pages}</button>`); }
  btns.push(`<button class="pg-btn" ${currentPage===pages?'disabled':''} onclick="goPage(${currentPage+1})">›</button>`);
  pg.innerHTML = btns.join('');
}

function goPage(p) {
  currentPage = p; renderPage();
  document.getElementById('newsList').scrollIntoView({behavior:'smooth',block:'start'});
}

/* ── 新聞列表 ── */
function renderNewsList(items) {
  const c = document.getElementById('newsList');
  const e = document.getElementById('emptyState');
  if (!items.length) { c.innerHTML=''; e.classList.remove('hidden'); return; }
  e.classList.add('hidden');
  c.innerHTML = items.map((item,idx) => {
    const neg = item.sentiment==='負面', pos = item.sentiment==='正面';
    const bc = neg?'card-neg':pos?'card-pos':'card-neu';
    const bg = item.priority==='高'&&neg?'bg-red-50':'';
    const sc = neg?'bg-red-100 text-red-700':pos?'bg-green-100 text-green-700':'bg-slate-100 text-slate-500';
    const pc = item.priority==='高'?'bg-red-100 text-red-700':item.priority==='中'?'bg-amber-100 text-amber-700':'bg-slate-100 text-slate-400';
    const pl = item.priority==='高'?'🚨 高優先':item.priority==='中'?'⚠ 中':'低';
    const clarify = neg&&item.line_message?`
      <div class="line-box p-3 mt-2.5">
        <div class="flex justify-between items-center mb-1.5">
          <span class="text-xs font-semibold text-green-700">📱 AI 澄清建議（一鍵複製傳 LINE）</span>
          <button onclick="cpText('cl-${idx}',this)" class="text-xs bg-green-500 hover:bg-green-600 text-white px-3 py-0.5 rounded-full font-medium">複製</button>
        </div>
        <p id="cl-${idx}" class="text-xs text-slate-700 leading-relaxed">${item.line_message}</p>
      </div>`:'';
    return `<div class="news-card p-3.5 border border-slate-100 ${bg} ${bc}">
      <div class="flex flex-wrap gap-1.5 mb-2 items-center">
        <span class="text-xs px-2 py-0.5 rounded-full font-medium ${sc}">${item.sentiment||'中立'}</span>
        <span class="text-xs px-2 py-0.5 rounded-full font-medium ${pc}">${pl}</span>
        <span class="text-xs px-2 py-0.5 rounded-full bg-blue-50 text-blue-600">${item.category||''}</span>
        <span class="text-xs px-2 py-0.5 rounded-full bg-purple-50 text-purple-500">${item.platform||''}</span>
        <span class="text-xs text-slate-300 ml-auto">${item.source||''}</span>
      </div>
      <a href="${item.url||'#'}" target="_blank" rel="noopener"
         class="link-title font-semibold text-sm block mb-1 leading-snug">${item.title||''}</a>
      <p class="text-xs text-slate-400">${item.summary||''}</p>
      ${clarify}
      <div class="mt-2 flex items-center justify-between">
        <span class="text-xs text-slate-300">${(item.published||'').slice(0,10)}</span>
        <a href="${item.url||'#'}" target="_blank" rel="noopener" class="text-xs text-blue-400 hover:text-blue-600">↗ 閱讀原文</a>
      </div>
    </div>`;
  }).join('');
}

/* ── 情感圓環 ── */
function renderSentimentDonut() {
  const el = document.getElementById('sentimentDonuts');
  let pos=0,neg=0,neu=0;
  Object.values(MONITOR_DATA).forEach(d=>{ const s=d.stats||{}; pos+=s.positive||0; neg+=s.negative||0; neu+=s.neutral||0; });
  const t=pos+neg+neu||1, pn=Math.round(neg/t*100), pu=Math.round(neu/t*100), pp=100-pn-pu;
  const svg=(pct,clr,lbl)=>{
    const r=15.9,c=+(2*Math.PI*r).toFixed(2),d=+(pct/100*c).toFixed(2),g=+(c-d).toFixed(2);
    return `<div class="don-wrap" onclick="document.getElementById('sentFilter').value='${lbl}';applyFilters()">
      <svg width="64" height="64" viewBox="0 0 36 36">
        <circle cx="18" cy="18" r="${r}" fill="none" stroke="#1a2e4a" stroke-width="4"/>
        <circle cx="18" cy="18" r="${r}" fill="none" stroke="${clr}" stroke-width="4"
          stroke-dasharray="${d} ${g}" stroke-dashoffset="25"/>
        <text x="18" y="21" text-anchor="middle" font-size="7.5" font-weight="bold" fill="${clr}">${pct}%</text>
      </svg>
      <div style="color:${clr};font-size:1rem;font-weight:800;line-height:1">${pct}%</div>
      <div class="don-lbl">${lbl==='負面'?'🔴 負面':lbl==='正面'?'🟢 正面':'⚪ 中立'}</div>
    </div>`;
  };
  el.innerHTML = svg(pn,'#ef4444','負面')+svg(pu,'#94a3b8','中立')+svg(pp,'#22c55e','正面');
}

/* ── 關鍵詞氣泡 ── */
function renderKeywordCloud() {
  const el = document.getElementById('keywordCloud');
  if (!KEYWORD_RANKING?.length) { el.innerHTML='<span class="text-xs text-slate-400">暫無資料</span>'; return; }
  const nk=['缺水','乾旱','限水','停水','汙染','污染','危機','警戒','漏水','不足','告急'];
  const mx=KEYWORD_RANKING[0][1]||1;
  el.innerHTML = KEYWORD_RANKING.slice(0,20).map(([kw,cnt])=>{
    const r=cnt/mx, sz=Math.round(44+r*54), fs=Math.max(10,Math.round(sz/4.8));
    const isN=nk.some(n=>kw.includes(n));
    const cl=isN?(r>.6?'#b91c1c':r>.3?'#dc2626':'#ef4444'):(r>.6?'#1a3a6c':r>.3?'#1e5799':'#3d7ab5');
    return `<div class="bubble" style="width:${sz}px;height:${sz}px;font-size:${fs}px;background:${cl}"
      onclick="quickSearch('${kw}')" title="${kw}：${cnt}次">${kw}</div>`;
  }).join('');
}

/* ── 議題熱度 ── */
function renderTopicHeat() {
  const el = document.getElementById('topicHeat');
  if (!TOPIC_HEAT||!Object.keys(TOPIC_HEAT).length) { el.innerHTML='<p class="text-xs text-blue-400">暫無資料</p>'; return; }
  const sorted=Object.entries(TOPIC_HEAT).sort((a,b)=>(b[1].negative||0)-(a[1].negative||0));
  const mx=sorted[0]?.[1]?.negative||1;
  el.innerHTML=sorted.map(([cat,s])=>{
    const pct=Math.round((s.negative||0)/mx*100), rate=s.total>0?Math.round((s.negative||0)/s.total*100):0;
    return `<div class="cursor-pointer group" onclick="toggleCatByName('${cat}')">
      <div class="flex justify-between text-xs mb-1">
        <span class="text-blue-200 group-hover:text-white transition">${cat}</span>
        <span class="text-red-400">${s.negative||0}則 <span class="text-blue-400">(${rate}%)</span></span>
      </div>
      <div class="h-1.5 rounded-full overflow-hidden" style="background:#1a2e4a">
        <div class="h-full bar-fill rounded-full bg-red-500" style="width:${pct}%"></div>
      </div>
    </div>`;
  }).join('');
}

/* ── 近2週焦點 ── */
let splFilter = '';
function renderSpotlight(filter) {
  splFilter = filter;
  const el = document.getElementById('spotlightList');
  const cut = new Date(Date.now()-14*86400000).toISOString().slice(0,10);
  let items = [];
  Object.values(MONITOR_DATA).forEach(d=>{
    (d.items||[]).forEach(x=>{ if((x.published||x.date||'')>=cut) items.push(x); });
  });
  if (filter) items = items.filter(x=>x.sentiment===filter);
  const po={'高':0,'中':1,'低':2};
  items.sort((a,b)=>{ const p=(po[a.priority]||2)-(po[b.priority]||2); return p!==0?p:((b.published||b.date||'')>(a.published||a.date||'')?1:-1); });
  if (!items.length) { el.innerHTML='<p class="text-xs text-blue-400">近2週暫無資料</p>'; return; }
  el.innerHTML=items.slice(0,8).map(item=>{
    const sc=item.sentiment==='負面'?'#f87171':item.sentiment==='正面'?'#4ade80':'#94a3b8';
    const sbg=item.sentiment==='負面'?'#3b1d1d':item.sentiment==='正面'?'#1a3b1a':'#1e2e3b';
    return `<div style="border-bottom:1px solid #1a2e4a" class="pb-2 last:border-0 last:pb-0">
      <a href="${item.url||'#'}" target="_blank" rel="noopener"
         class="text-xs font-medium block leading-snug mb-1 text-blue-100 hover:text-white transition">
        ${(item.title||'').slice(0,40)}${(item.title?.length||0)>40?'…':''}
      </a>
      <div class="flex items-center gap-1.5 text-xs text-blue-300">
        <span style="background:${sbg};color:${sc}" class="px-1.5 py-0.5 rounded">${item.sentiment||''}</span>
        <span class="truncate">${item.source||''}</span>
        <span class="ml-auto shrink-0">${(item.published||item.date||'').slice(5,10)}</span>
      </div>
    </div>`;
  }).join('');
}

function setSpotlight(filter, btn) {
  document.querySelectorAll('.spl-btn').forEach(b=>b.classList.remove('on'));
  btn.classList.add('on'); renderSpotlight(filter);
}

/* ── 分類 chip ── */
function toggleCat(btn) {
  const cat=btn.dataset.cat;
  if (selectedCats.has(cat)) { selectedCats.delete(cat); btn.classList.remove('on'); }
  else { selectedCats.add(cat); btn.classList.add('on'); }
  applyFilters();
}
function toggleCatByName(cat) {
  const btn=document.querySelector(`[data-cat="${cat}"]`);
  if (btn) toggleCat(btn); else { selectedCats.add(cat); applyFilters(); }
}
function quickSearch(kw) { document.getElementById('searchBox').value=kw; applyFilters(); }

function resetFilters() {
  selectedCats.clear();
  document.querySelectorAll('.chip').forEach(b=>b.classList.remove('on'));
  document.getElementById('sentFilter').value='';
  document.getElementById('sortBy').value='neg-first';
  document.getElementById('searchBox').value='';
  const dates=Object.keys(MONITOR_DATA).sort();
  if (dates.length) {
    document.getElementById('dateFrom').value=dates[Math.max(0,dates.length-14)];
    document.getElementById('dateTo').value=dates[dates.length-1];
  }
  applyFilters();
}

/* ── 複製 ── */
function cpText(id,btn) {
  const el=document.getElementById(id); if(!el) return;
  navigator.clipboard.writeText(el.textContent.trim()).then(()=>{
    const o=btn.textContent; btn.textContent='已複製 ✓'; btn.classList.replace('bg-green-500','bg-slate-400');
    setTimeout(()=>{btn.textContent=o;btn.classList.replace('bg-slate-400','bg-green-500');},2000);
  });
}
function cpUrgent(id,btn) {
  const el=document.getElementById(id); if(!el) return;
  navigator.clipboard.writeText(el.textContent.trim()).then(()=>{
    const o=btn.textContent; btn.textContent='✓'; setTimeout(()=>btn.textContent=o,2000);
  });
}

window.addEventListener('DOMContentLoaded', init);
</script>
</body>
</html>"""
    with open(os.path.join(DOCS_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)

if __name__ == "__main__":
    main()
