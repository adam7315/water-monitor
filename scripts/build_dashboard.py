"""
產生 GitHub Pages 靜態儀表板（v3 危機管理版）
以「長官快速掌握負面輿情並立即回應」為核心設計
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

def calc_trend(all_data, days=30):
    trend = []
    dates = sorted(all_data.keys())[-days:]
    data_list = [all_data[d].get("stats", {}) for d in dates]
    for i, (d, s) in enumerate(zip(dates, data_list)):
        neg = s.get("negative", 0)
        # 7日移動平均
        window = data_list[max(0, i-6):i+1]
        avg = round(sum(x.get("negative",0) for x in window) / len(window), 1)
        trend.append({"date": d[5:], "negative": neg, "avg7": avg,
                      "positive": s.get("positive",0), "neutral": s.get("neutral",0)})
    return trend

def calc_topic_heat(all_data):
    heat = defaultdict(lambda: {"total": 0, "negative": 0, "positive": 0})
    for day_data in all_data.values():
        for item in day_data.get("items", []):
            cat = item.get("category", "其他")
            heat[cat]["total"] += 1
            if item.get("sentiment") == "負面":  heat[cat]["negative"] += 1
            elif item.get("sentiment") == "正面": heat[cat]["positive"] += 1
    return {k: dict(v) for k, v in heat.items()}

def calc_spotlight(all_data, n=6):
    items = []
    for day_data in all_data.values():
        for item in day_data.get("items", []):
            if item.get("sentiment") == "負面" or item.get("priority") == "高":
                items.append(item)
    items.sort(key=lambda x: (x.get("date",""), x.get("priority","低") == "高"), reverse=True)
    return items[:n]

def calc_keyword_ranking(all_data, top_n=10):
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

    trend_data      = calc_trend(all_data)
    topic_heat      = calc_topic_heat(all_data)
    spotlight       = calc_spotlight(all_data)
    keyword_ranking = calc_keyword_ranking(all_data)
    total_all       = sum(d.get("stats", {}).get("total", 0) for d in all_data.values())
    total_neg_all   = sum(d.get("stats", {}).get("negative", 0) for d in all_data.values())

    data_js = (
        f"const MONITOR_DATA = {json.dumps(all_data, ensure_ascii=False)};\n"
        f"const TODAY = '{TODAY}';\n"
        f"const TREND_DATA = {json.dumps(trend_data, ensure_ascii=False)};\n"
        f"const TOPIC_HEAT = {json.dumps(topic_heat, ensure_ascii=False)};\n"
        f"const SPOTLIGHT = {json.dumps(spotlight, ensure_ascii=False)};\n"
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
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
  body { font-family: -apple-system,"Noto Sans TC",sans-serif; background:#f0f4f8; }
  /* ── Dark Sidebar ── */
  .sidebar { background:#0f2040; color:#e8eef5; }
  .sidebar-label { color:#7eb4d8; font-size:.7rem; text-transform:uppercase; letter-spacing:.05em; margin-bottom:.375rem; display:block; }
  .sidebar-select { width:100%; background:#1a3050; border:1px solid #2d4a6e; color:#e8eef5; border-radius:.5rem; padding:.375rem .625rem; font-size:.8rem; outline:none; appearance:none; }
  .sidebar-select:focus { border-color:#4a8fc4; }
  .sidebar-section { border-bottom:1px solid #1e3a60; padding:1rem; }
  .sidebar-section:last-child { border-bottom:none; }
  .sidebar-title { color:#a8c8e8; font-size:.8rem; font-weight:700; margin-bottom:.75rem; letter-spacing:.03em; }
  /* ── KPI Cards ── */
  .kpi-card { background:white; border-radius:1rem; padding:1rem 1.25rem; box-shadow:0 2px 8px rgba(0,0,0,.07); }
  .kpi-num  { font-size:2.25rem; font-weight:800; line-height:1; }
  /* ── News Cards ── */
  .card-neg  { border-left:4px solid #ef4444; }
  .card-pos  { border-left:4px solid #22c55e; }
  .card-neu  { border-left:4px solid #cbd5e1; }
  .news-card { background:white; border-radius:.75rem; box-shadow:0 1px 4px rgba(0,0,0,.06); transition:box-shadow .15s; }
  .news-card:hover { box-shadow:0 4px 16px rgba(0,0,0,.12); }
  .link-title { color:#1d4ed8; text-decoration:underline; text-underline-offset:2px; cursor:pointer; }
  .link-title:hover { color:#1e40af; }
  .line-box   { background:linear-gradient(135deg,#f0fdf4,#dcfce7); border:1px solid #86efac; border-radius:.75rem; }
  .urgent-card{ background:#fff1f2; border:1px solid #fca5a5; border-radius:.75rem; }
  /* ── Bubble Cloud ── */
  .bubble-cloud { display:flex; flex-wrap:wrap; gap:8px; align-items:center; padding:.5rem 0; min-height:4rem; justify-content:center; }
  .bubble { border-radius:50%; display:inline-flex; align-items:center; justify-content:center;
    color:white; font-weight:700; cursor:pointer; transition:transform .15s, opacity .15s; text-align:center; line-height:1.2; }
  .bubble:hover { transform:scale(1.12); opacity:.85; }
  /* ── Donut ── */
  .donut-wrap { display:flex; flex-direction:column; align-items:center; gap:.2rem; cursor:pointer; }
  .donut-pct  { font-size:1.1rem; font-weight:800; line-height:1; }
  .donut-lbl  { font-size:.65rem; color:#7eb4d8; }
  /* ── Misc ── */
  .ai-badge  { background:linear-gradient(135deg,#667eea,#764ba2); }
  .pulse     { animation:pulse 2s infinite; }
  @keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}
  .bar-fill  { transition:width .8s ease; }
  .tag-btn   { font-size:.7rem; padding:.25rem .75rem; border-radius:9999px; transition:opacity .15s; cursor:pointer; }
  .tag-btn:hover { opacity:.7; }
  @media(max-width:1023px){ .sidebar{ display:none !important; } .layout-grid{ grid-template-columns:1fr !important; } }
</style>
</head>
<body class="bg-slate-50 min-h-screen">

<!-- ── Header ── -->
<header style="background:linear-gradient(135deg,#1a3a5c 0%,#1e5799 100%)" class="text-white shadow-lg">
  <div class="max-w-7xl mx-auto px-4 py-3">
    <div class="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-2">
      <div class="flex items-center gap-3">
        <div class="text-3xl">💧</div>
        <div>
          <div class="text-xs text-blue-200 tracking-wide">114–115年度 臺南海水淡化廠暨南區水資源推廣計畫</div>
          <h1 class="text-lg font-bold tracking-tight">輿情監控系統</h1>
        </div>
      </div>
      <div class="flex items-center gap-4">
        <div class="ai-badge text-white text-xs px-3 py-1.5 rounded-full flex items-center gap-1.5 shadow">
          <span class="pulse w-1.5 h-1.5 bg-white rounded-full inline-block"></span>
          🤖 每日自動更新
        </div>
        <div class="text-right">
          <div class="text-2xl font-bold" id="headerNegCount">-</div>
          <div class="text-blue-200 text-xs">今日負面</div>
        </div>
      </div>
    </div>
    <div class="mt-1.5 text-blue-200 text-xs flex flex-wrap gap-x-3">
      <span>🕐 每日 07:00 自動蒐集分析</span>
      <span>|</span>
      <span id="lastUpdate">載入中...</span>
      <span>|</span>
      <span>累計 <strong class="text-white" id="totalAllCount">-</strong> 則 ／ 負面 <strong class="text-red-300" id="totalNegCount">-</strong> 則</span>
    </div>
  </div>
</header>

<!-- ── Alert Bar ── -->
<div id="alertBar" class="hidden text-white px-4 py-2.5 shadow" style="background:#c0392b">
  <div class="max-w-7xl mx-auto flex items-start gap-2">
    <span class="shrink-0 mt-0.5">🚨</span>
    <span id="alertText" class="font-medium text-sm leading-relaxed flex-1"></span>
    <button onclick="document.getElementById('filterSent').value='負面';applyFilters()"
      class="shrink-0 text-xs bg-white text-red-700 font-semibold px-3 py-1 rounded-full hover:bg-red-50 transition ml-2">
      查看全部負面 →
    </button>
  </div>
</div>

<!-- ── Stats Row ── -->
<div class="max-w-7xl mx-auto px-4 pt-4 pb-3">
  <div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
    <div class="kpi-card border-t-4 border-blue-400">
      <div class="text-xs text-slate-400 mb-1">今日蒐集</div>
      <div class="kpi-num text-slate-700" id="statTotal">-</div>
      <div class="text-xs text-slate-400 mt-1">則新聞</div>
    </div>
    <div class="kpi-card border-t-4 border-red-500">
      <div class="text-xs text-slate-400 mb-1">今日負面</div>
      <div class="kpi-num text-red-600" id="statNeg">-</div>
      <div class="text-xs text-slate-400 mt-1">則需關注</div>
    </div>
    <div class="kpi-card border-t-4 border-green-500">
      <div class="text-xs text-slate-400 mb-1">今日正面</div>
      <div class="kpi-num text-green-600" id="statPos">-</div>
      <div class="text-xs text-slate-400 mt-1">則正向報導</div>
    </div>
    <div class="kpi-card border-t-4 border-orange-500">
      <div class="text-xs text-slate-400 mb-1">高優先</div>
      <div class="kpi-num text-orange-500" id="statHigh">-</div>
      <div class="text-xs text-slate-400 mt-1">則待立即處理</div>
    </div>
  </div>
</div>

<!-- ── Urgent Today Section ── -->
<div id="urgentSection" class="hidden max-w-7xl mx-auto px-4 pb-2">
  <div class="bg-red-50 border-2 border-red-300 rounded-xl p-4">
    <div class="flex items-center gap-2 mb-3">
      <span class="text-lg">🚨</span>
      <h2 class="font-bold text-red-700 text-sm">今日緊急預警 — 需立即處理</h2>
      <span class="text-xs text-red-400 ml-auto" id="urgentCount"></span>
    </div>
    <div id="urgentList" class="space-y-2"></div>
  </div>
</div>

<!-- ── Main Layout ── -->
<div class="max-w-7xl mx-auto px-4 py-3 pb-10">
  <div class="layout-grid" style="display:grid;grid-template-columns:272px 1fr;gap:16px;align-items:start">

    <!-- ── Sidebar (dark) ── -->
    <aside class="sidebar rounded-xl overflow-hidden shadow-xl" style="position:sticky;top:12px">

      <!-- Filters -->
      <div class="sidebar-section">
        <div class="sidebar-title">🔍 篩選條件</div>
        <div class="space-y-3">
          <div>
            <label class="sidebar-label">日期</label>
            <select id="filterDate" class="sidebar-select">
              <option value="ALL">📋 全部（近30天）</option>
            </select>
          </div>
          <div>
            <label class="sidebar-label">分類</label>
            <select id="filterCat" class="sidebar-select">
              <option value="">全部分類</option>
              <option value="海淡廠">海淡廠</option>
              <option value="南部水資源">南部水資源</option>
              <option value="全台水資源">全台水資源</option>
              <option value="社群輿情">社群輿情</option>
              <option value="國際">國際</option>
            </select>
          </div>
          <div>
            <label class="sidebar-label">情感傾向</label>
            <select id="filterSent" class="sidebar-select">
              <option value="">全部</option>
              <option value="負面">🔴 負面</option>
              <option value="正面">🟢 正面</option>
              <option value="中立">⚪ 中立</option>
            </select>
          </div>
          <div>
            <label class="sidebar-label">平台</label>
            <select id="filterPlatform" class="sidebar-select">
              <option value="">全部平台</option>
              <option value="新聞">新聞媒體</option>
              <option value="PTT">PTT</option>
              <option value="FB">Facebook</option>
              <option value="Dcard">Dcard</option>
            </select>
          </div>
          <button onclick="resetFilters()"
            class="w-full text-xs border border-blue-500 text-blue-300 rounded-lg py-1.5 hover:bg-blue-900 transition">
            重置篩選
          </button>
        </div>
      </div>

      <!-- Sentiment Donut -->
      <div class="sidebar-section">
        <div class="sidebar-title">📊 近30天情感分析</div>
        <div class="flex justify-around items-center py-2" id="sentimentDonuts"></div>
      </div>

      <!-- Topic Heat -->
      <div class="sidebar-section">
        <div class="sidebar-title">🌡 議題負面熱度</div>
        <div id="topicHeat" class="space-y-2.5"></div>
      </div>

      <!-- Spotlight -->
      <div class="sidebar-section">
        <div class="sidebar-title">📌 近期焦點新聞</div>
        <div id="spotlightList" class="space-y-3"></div>
      </div>

    </aside>

    <!-- ── Main Content ── -->
    <main class="space-y-4">

      <!-- Trend Chart -->
      <div class="bg-white rounded-xl shadow-sm p-4 border border-slate-100">
        <div class="flex justify-between items-center mb-2">
          <h3 class="font-semibold text-slate-600 text-sm">📉 負面聲浪趨勢（近30天）</h3>
          <span class="text-xs text-blue-400 cursor-pointer select-none">👆 點擊長條篩選當日負面新聞</span>
        </div>
        <div style="height:170px">
          <canvas id="trendChart"></canvas>
        </div>
      </div>

      <!-- Keyword Bubble Cloud -->
      <div class="bg-white rounded-xl shadow-sm p-4 border border-slate-100">
        <div class="flex justify-between items-center mb-3">
          <h3 class="font-semibold text-slate-600 text-sm">☁ 關鍵詞熱度</h3>
          <span class="text-xs text-slate-400">泡泡大小 = 出現頻率 · 點擊搜尋</span>
        </div>
        <div id="keywordCloud" class="bubble-cloud"></div>
      </div>

      <!-- Quick tags + search -->
      <div class="bg-white rounded-xl shadow-sm p-3 border border-slate-100">
        <div class="flex flex-wrap gap-2 items-center">
          <span class="text-xs text-slate-400 shrink-0">快速搜尋：</span>
          <button onclick="quickSearch('海淡廠')"    class="tag-btn bg-blue-50 text-blue-600">海淡廠</button>
          <button onclick="quickSearch('鹵水')"      class="tag-btn bg-red-50 text-red-500">鹵水</button>
          <button onclick="quickSearch('漁民')"      class="tag-btn bg-red-50 text-red-500">漁民</button>
          <button onclick="quickSearch('環評')"      class="tag-btn bg-orange-50 text-orange-500">環評</button>
          <button onclick="quickSearch('補償')"      class="tag-btn bg-orange-50 text-orange-500">補償</button>
          <button onclick="quickSearch('噪音')"      class="tag-btn bg-orange-50 text-orange-500">噪音</button>
          <button onclick="quickSearch('曾文水庫')"  class="tag-btn bg-blue-50 text-blue-600">曾文水庫</button>
          <button onclick="quickSearch('缺水')"      class="tag-btn bg-red-50 text-red-500">缺水</button>
          <input type="text" id="searchBox" placeholder="搜尋關鍵字…"
            oninput="applyFilters()"
            class="ml-auto border border-slate-200 rounded-lg px-3 py-1.5 text-sm w-40 focus:outline-none focus:ring-2 focus:ring-blue-300">
        </div>
      </div>

      <!-- Count bar -->
      <div class="flex justify-between items-center px-1 text-sm">
        <div class="text-slate-500">
          顯示 <strong id="showCount">0</strong> 則
          <span class="ml-2 text-red-500">負面 <strong id="showNeg">0</strong></span>
          <span class="ml-1.5 text-green-500">正面 <strong id="showPos">0</strong></span>
          <span class="ml-1.5 text-slate-400">中立 <strong id="showNeu">0</strong></span>
        </div>
        <span class="text-xs text-slate-300">預設：負面優先顯示</span>
      </div>

      <!-- News List -->
      <div id="newsList" class="space-y-3"></div>
      <div id="emptyState" class="hidden text-center py-12 text-slate-400">
        <div class="text-5xl mb-3">🔍</div>
        <div class="text-sm">目前無符合條件的資料</div>
      </div>

    </main>
  </div>
</div>

<!-- Footer -->
<footer class="border-t border-slate-200 bg-white py-3 mt-2">
  <div class="max-w-7xl mx-auto px-4 text-center text-xs text-slate-400 space-x-2">
    <span>114-115年度 臺南海水淡化廠暨南區水資源推廣計畫</span>
    <span>·</span>
    <span>每日 07:00（台灣時間）自動蒐集分析</span>
    <span>·</span>
    <span>Powered by Google Gemini AI &amp; GitHub Actions</span>
  </div>
</footer>

<style>
  .tag-btn { font-size:.7rem; padding:.25rem .75rem; border-radius:9999px; transition:opacity .15s; cursor:pointer; }
  .tag-btn:hover { opacity:.7; }
</style>

<script src="data.js"></script>
<script>
let currentItems = [];
let trendChartObj = null;

/* ── 初始化 ── */
function init() {
  document.getElementById('totalAllCount').textContent = (TOTAL_ALL||0).toLocaleString();
  document.getElementById('totalNegCount').textContent = (TOTAL_NEG_ALL||0).toLocaleString();

  // 填入日期選單（所有有資料的日期，最新在前）
  const sel = document.getElementById('filterDate');
  const availDates = Object.keys(MONITOR_DATA).sort().reverse();
  availDates.forEach(d => {
    const opt = document.createElement('option');
    opt.value = d; opt.textContent = d;
    sel.appendChild(opt);
  });
  // 預設：全部近30天
  sel.value = 'ALL';

  renderTrendChart();
  renderSentimentDonut();
  renderKeywordCloud();
  renderSpotlight();
  renderTopicHeat();
  renderDay('ALL');

  sel.addEventListener('change', e => renderDay(e.target.value));
  ['filterCat','filterSent','filterPlatform'].forEach(id =>
    document.getElementById(id).addEventListener('change', applyFilters));
}

/* ── 載入某天或全部 ── */
function renderDay(day) {
  if (day === 'ALL') {
    // 全部模式：合併所有日期的 items
    currentItems = [];
    let totPos=0, totNeg=0, totNeu=0, totHigh=0;
    Object.values(MONITOR_DATA).forEach(d => {
      currentItems = currentItems.concat(d.items || []);
      const s = d.stats || {};
      totPos  += s.positive||0; totNeg += s.negative||0;
      totNeu  += s.neutral||0;  totHigh+= s.high_priority||0;
    });
    document.getElementById('lastUpdate').textContent = '顯示全部近30天資料';
    updateStats({total:currentItems.length, positive:totPos, negative:totNeg, neutral:totNeu, high_priority:totHigh});
    const high = currentItems.filter(x => x.priority==='高' && x.sentiment==='負面');
    if (high.length) {
      document.getElementById('alertBar').classList.remove('hidden');
      document.getElementById('alertText').textContent =
        '近30天共 ' + totNeg + ' 則負面，其中 ' + high.length + ' 則高優先';
      renderUrgent(high.slice(0,3));
      document.getElementById('urgentCount').textContent = '共 '+high.length+' 則';
      document.getElementById('urgentSection').classList.remove('hidden');
    } else { hideUrgent(); document.getElementById('alertBar').classList.add('hidden'); }
    applyFilters();
    return;
  }

  const dayData = MONITOR_DATA[day];
  if (!dayData) {
    document.getElementById('lastUpdate').textContent = day + ' 無資料';
    updateStats({});
    currentItems = [];
    hideUrgent();
    applyFilters();
    return;
  }
  const s = dayData.stats || {};
  document.getElementById('lastUpdate').textContent = '最後更新：' + day;
  updateStats(s);
  currentItems = dayData.items || [];

  const high = currentItems.filter(x => x.priority === '高' && x.sentiment === '負面');
  const allNeg = currentItems.filter(x => x.sentiment === '負面');
  const bar = document.getElementById('alertBar');

  if (allNeg.length > 0) {
    bar.classList.remove('hidden');
    document.getElementById('alertText').textContent =
      '今日共 ' + allNeg.length + ' 則負面輿情，其中 ' + high.length + ' 則高優先需立即處理';
  } else {
    bar.classList.add('hidden');
  }

  if (high.length > 0) {
    renderUrgent(high.slice(0, 3));
    document.getElementById('urgentCount').textContent = '共 ' + high.length + ' 則';
    document.getElementById('urgentSection').classList.remove('hidden');
  } else {
    hideUrgent();
  }

  applyFilters();
}

function updateStats(s) {
  document.getElementById('statTotal').textContent = s.total || 0;
  document.getElementById('statNeg').textContent   = s.negative || 0;
  document.getElementById('statPos').textContent   = s.positive || 0;
  document.getElementById('statHigh').textContent  = s.high_priority || 0;
  document.getElementById('headerNegCount').textContent = s.negative || 0;
}

function hideUrgent() {
  document.getElementById('urgentSection').classList.add('hidden');
}

/* ── 今日緊急預警卡 ── */
function renderUrgent(items) {
  document.getElementById('urgentList').innerHTML = items.map((item, idx) => `
    <div class="urgent-card p-3">
      <a href="${item.url||'#'}" target="_blank" rel="noopener"
         class="link-title font-semibold text-sm block mb-1">${item.title||''}</a>
      <div class="flex flex-wrap gap-2 items-center">
        <span class="text-xs text-slate-400">${item.source||''}</span>
        <span class="text-xs text-slate-300">·</span>
        <span class="text-xs text-slate-400">${item.published?.slice(0,10)||''}</span>
        ${item.line_message ? `
        <button onclick="copyUrgent('urg-${idx}', this)"
          class="ml-auto text-xs bg-green-500 hover:bg-green-600 text-white px-3 py-0.5 rounded-full transition font-medium">
          📋 複製LINE澄清
        </button>` : ''}
      </div>
      ${item.line_message ? `<p id="urg-${idx}" class="hidden">${item.line_message}</p>` : ''}
    </div>`).join('');
}

/* ── 篩選（預設負面優先）── */
function applyFilters() {
  const cat      = document.getElementById('filterCat').value;
  const sent     = document.getElementById('filterSent').value;
  const platform = document.getElementById('filterPlatform').value;
  const kw       = document.getElementById('searchBox').value.toLowerCase();

  let f = [...currentItems];
  if (cat)      f = f.filter(x => x.category  === cat);
  if (sent)     f = f.filter(x => x.sentiment === sent);
  if (platform) f = f.filter(x => x.platform  === platform);
  if (kw)       f = f.filter(x =>
    (x.title||'').toLowerCase().includes(kw) ||
    (x.summary||'').toLowerCase().includes(kw) ||
    (x.keyword||'').toLowerCase().includes(kw));

  // 預設排序：負面高優先 → 負面中 → 負面低 → 中立 → 正面
  const sentOrder = {'負面':0,'中立':1,'正面':2};
  const priOrder  = {'高':0,'中':1,'低':2};
  f.sort((a,b) => {
    const sd = (sentOrder[a.sentiment]||2) - (sentOrder[b.sentiment]||2);
    return sd !== 0 ? sd : (priOrder[a.priority]||2) - (priOrder[b.priority]||2);
  });

  document.getElementById('showCount').textContent = f.length;
  document.getElementById('showNeg').textContent   = f.filter(x=>x.sentiment==='負面').length;
  document.getElementById('showPos').textContent   = f.filter(x=>x.sentiment==='正面').length;
  document.getElementById('showNeu').textContent   = f.filter(x=>x.sentiment==='中立').length;
  renderList(f);
}

function quickSearch(kw) { document.getElementById('searchBox').value = kw; applyFilters(); }

function resetFilters() {
  ['filterCat','filterSent','filterPlatform'].forEach(id => document.getElementById(id).value='');
  document.getElementById('searchBox').value='';
  document.getElementById('filterDate').value='ALL';
  renderDay('ALL');
}

/* ── 新聞列表 ── */
function renderList(items) {
  const container = document.getElementById('newsList');
  const empty     = document.getElementById('emptyState');
  if (!items.length) { container.innerHTML=''; empty.classList.remove('hidden'); return; }
  empty.classList.add('hidden');

  container.innerHTML = items.map((item, idx) => {
    const neg = item.sentiment === '負面';
    const pos = item.sentiment === '正面';
    const borderCls = neg ? 'card-neg' : pos ? 'card-pos' : 'card-neu';
    const bgCls     = item.priority === '高' && neg ? 'bg-red-50' : 'bg-white';
    const sentCls   = neg ? 'bg-red-100 text-red-700' : pos ? 'bg-green-100 text-green-700' : 'bg-slate-100 text-slate-500';
    const priCls    = item.priority==='高' ? 'bg-red-100 text-red-700' : item.priority==='中' ? 'bg-amber-100 text-amber-700' : 'bg-slate-100 text-slate-400';
    const priLabel  = item.priority==='高' ? '🚨 高優先' : item.priority==='中' ? '⚠ 中' : '低';

    const clarify = neg && item.line_message ? `
      <div class="line-box rounded-xl p-3 mt-3">
        <div class="flex justify-between items-center mb-2">
          <span class="text-xs font-semibold text-green-700">📱 AI 即時澄清建議（一鍵複製傳 LINE）</span>
          <button onclick="copyText('cl-${idx}',this)"
            class="text-xs bg-green-500 hover:bg-green-600 text-white px-3 py-1 rounded-full font-medium transition">複製</button>
        </div>
        <p id="cl-${idx}" class="text-sm text-slate-700 leading-relaxed">${item.line_message}</p>
      </div>` : '';

    return `
    <div class="news-card rounded-xl shadow-sm p-4 border border-slate-100 ${bgCls} ${borderCls}">
      <div class="flex flex-wrap gap-1.5 mb-2 items-center">
        <span class="text-xs px-2 py-0.5 rounded-full font-medium ${sentCls}">${item.sentiment||'中立'}</span>
        <span class="text-xs px-2 py-0.5 rounded-full font-medium ${priCls}">${priLabel}</span>
        <span class="text-xs px-2 py-0.5 rounded-full bg-blue-50 text-blue-600">${item.category||''}</span>
        <span class="text-xs px-2 py-0.5 rounded-full bg-purple-50 text-purple-500">${item.platform||''}</span>
        <span class="text-xs text-slate-300 ml-auto">${item.source||''}</span>
      </div>
      <a href="${item.url||'#'}" target="_blank" rel="noopener"
         class="link-title font-semibold text-sm block mb-1 leading-snug">
        ${item.title||''}
      </a>
      <p class="text-xs text-slate-400 leading-relaxed">${item.summary||item.content?.slice(0,80)||''}</p>
      ${clarify}
      <div class="mt-2 flex items-center justify-between">
        <span class="text-xs text-slate-300">${item.published?.slice(0,10)||''}</span>
        <a href="${item.url||'#'}" target="_blank" rel="noopener"
           class="text-xs text-blue-400 hover:text-blue-600 transition">↗ 閱讀原文</a>
      </div>
    </div>`;
  }).join('');
}

/* ── 情感三圓環（SVG）── */
function renderSentimentDonut() {
  const el = document.getElementById('sentimentDonuts');
  let pos=0, neg=0, neu=0;
  Object.values(MONITOR_DATA).forEach(d => {
    const s = d.stats || {};
    pos += s.positive||0; neg += s.negative||0; neu += s.neutral||0;
  });
  const total = pos + neg + neu || 1;
  const pctNeg = Math.round(neg/total*100);
  const pctNeu = Math.round(neu/total*100);
  const pctPos = 100 - pctNeg - pctNeu;

  const makeSVG = (pct, color, label) => {
    const r = 15.9, circ = +(2 * Math.PI * r).toFixed(2);
    const dash = +(pct / 100 * circ).toFixed(2);
    const gap  = +(circ - dash).toFixed(2);
    return `<div class="donut-wrap" onclick="setFilter('filterSent','${label}')">
      <svg width="68" height="68" viewBox="0 0 36 36">
        <circle cx="18" cy="18" r="${r}" fill="none" stroke="#1e3a60" stroke-width="3.8"/>
        <circle cx="18" cy="18" r="${r}" fill="none" stroke="${color}" stroke-width="3.8"
          stroke-dasharray="${dash} ${gap}" stroke-dashoffset="25"/>
        <text x="18" y="21" text-anchor="middle" font-size="7.5" font-weight="bold" fill="${color}">${pct}%</text>
      </svg>
      <div class="donut-pct" style="color:${color}">${pct}%</div>
      <div class="donut-lbl">${label === '負面' ? '🔴 負面' : label === '正面' ? '🟢 正面' : '⚪ 中立'}</div>
    </div>`;
  };

  el.innerHTML =
    makeSVG(pctNeg, '#ef4444', '負面') +
    makeSVG(pctNeu, '#94a3b8', '中立') +
    makeSVG(pctPos, '#22c55e', '正面');
}

/* ── 關鍵詞氣泡雲 ── */
function renderKeywordCloud() {
  const el = document.getElementById('keywordCloud');
  if (!KEYWORD_RANKING || !KEYWORD_RANKING.length) {
    el.innerHTML = '<span class="text-xs text-slate-400">暫無資料</span>'; return;
  }
  const negKws = ['缺水','乾旱','限水','停水','汙染','污染','危機','警戒','漏水','不足','告急'];
  const maxCount = KEYWORD_RANKING[0][1] || 1;
  el.innerHTML = KEYWORD_RANKING.slice(0, 20).map(([kw, count]) => {
    const ratio = count / maxCount;
    const size  = Math.round(44 + ratio * 54);
    const fsize = Math.max(10, Math.round(size / 4.8));
    const isNeg = negKws.some(n => kw.includes(n));
    let color;
    if (isNeg) {
      color = ratio > .6 ? '#b91c1c' : ratio > .3 ? '#dc2626' : '#ef4444';
    } else {
      color = ratio > .6 ? '#1a3a6c' : ratio > .3 ? '#1e5799' : '#3d7ab5';
    }
    return `<div class="bubble" style="width:${size}px;height:${size}px;font-size:${fsize}px;background:${color}"
      onclick="quickSearch('${kw}')" title="${kw}：${count}次">${kw}</div>`;
  }).join('');
}

/* ── 側欄：近期焦點新聞 ── */
function renderSpotlight() {
  const el = document.getElementById('spotlightList');
  if (!SPOTLIGHT || !SPOTLIGHT.length) {
    el.innerHTML = '<p class="text-xs text-blue-400">暫無資料</p>'; return;
  }
  el.innerHTML = SPOTLIGHT.map(item => `
    <div style="border-bottom:1px solid #1e3a60" class="pb-2 last:border-0 last:pb-0">
      <a href="${item.url||'#'}" target="_blank" rel="noopener"
         class="text-xs font-medium block leading-snug mb-1 text-blue-100 hover:text-white transition">
        ${(item.title||'').slice(0,45)}${(item.title?.length||0)>45?'…':''}
      </a>
      <div class="flex items-center gap-1.5 text-xs text-blue-300">
        <span style="background:#3b1d1d;color:#f87171" class="px-1.5 py-0.5 rounded">${item.sentiment||''}</span>
        <span>${item.source||''}</span>
        <span class="ml-auto">${item.date?.slice(5)||''}</span>
      </div>
    </div>`).join('');
}

/* ── 側欄：議題負面熱度 ── */
function renderTopicHeat() {
  const el = document.getElementById('topicHeat');
  if (!TOPIC_HEAT || !Object.keys(TOPIC_HEAT).length) {
    el.innerHTML = '<p class="text-xs text-blue-400">暫無資料</p>'; return;
  }
  const sorted = Object.entries(TOPIC_HEAT).sort((a,b) => (b[1].negative||0) - (a[1].negative||0));
  const maxNeg = sorted[0]?.[1]?.negative || 1;
  el.innerHTML = sorted.map(([cat, s]) => {
    const pct  = Math.round((s.negative||0)/maxNeg*100);
    const rate = s.total > 0 ? Math.round((s.negative||0)/s.total*100) : 0;
    return `
    <div class="cursor-pointer group" onclick="setFilter('filterCat','${cat}')">
      <div class="flex justify-between text-xs mb-1">
        <span class="text-blue-200 group-hover:text-white transition">${cat}</span>
        <span class="text-red-400 font-medium">${s.negative||0}則 <span class="text-blue-400">(${rate}%)</span></span>
      </div>
      <div class="h-1.5 rounded-full overflow-hidden" style="background:#1e3a60">
        <div class="h-full bar-fill rounded-full bg-red-500" style="width:${pct}%"></div>
      </div>
    </div>`;
  }).join('');
}

/* ── 趨勢圖（負面長條 + 7日平均線）── */
function renderTrendChart() {
  if (!TREND_DATA || !TREND_DATA.length) return;
  const ctx = document.getElementById('trendChart').getContext('2d');
  if (trendChartObj) trendChartObj.destroy();
  trendChartObj = new Chart(ctx, {
    data: {
      labels: TREND_DATA.map(d => d.date),
      datasets: [
        { type:'bar',  label:'每日負面', data:TREND_DATA.map(d=>d.negative),
          backgroundColor:'rgba(239,68,68,.55)', borderColor:'rgba(239,68,68,.8)',
          borderWidth:1, borderRadius:3, order:2 },
        { type:'line', label:'7日平均', data:TREND_DATA.map(d=>d.avg7),
          borderColor:'#991b1b', backgroundColor:'transparent',
          tension:.4, pointRadius:2, borderWidth:2.5, order:1 }
      ]
    },
    options: {
      responsive:true, maintainAspectRatio:false,
      onClick: (evt, elements) => {
        if (!elements.length) return;
        const idx = elements[0].index;
        const mmdd = TREND_DATA[idx].date; // "MM-DD"
        const fullDate = Object.keys(MONITOR_DATA).find(d => d.slice(5) === mmdd);
        if (!fullDate) return;
        // 設定篩選條件：該日 + 負面
        document.getElementById('filterDate').value = fullDate;
        document.getElementById('filterSent').value = '負面';
        renderDay(fullDate);
        // 滾動到新聞列表
        setTimeout(() => document.getElementById('newsList').scrollIntoView({behavior:'smooth'}), 100);
        // 高亮選中的長條
        const colors = TREND_DATA.map((_, i) =>
          i === idx ? 'rgba(239,68,68,.95)' : 'rgba(239,68,68,.35)');
        trendChartObj.data.datasets[0].backgroundColor = colors;
        trendChartObj.update('none');
      },
      onHover: (evt, elements) => {
        evt.native.target.style.cursor = elements.length ? 'pointer' : 'default';
      },
      plugins:{ legend:{ position:'top', labels:{ font:{size:11}, boxWidth:12, padding:12 }}},
      scales:{
        x:{ grid:{display:false}, ticks:{font:{size:10}, maxRotation:45} },
        y:{ beginAtZero:true, grid:{color:'rgba(0,0,0,.04)'}, ticks:{font:{size:10},stepSize:1} }
      }
    }
  });
}

/* ── 工具 ── */
function setFilter(id, val) { document.getElementById(id).value=val; applyFilters(); }

function copyText(id, btn) {
  const el = document.getElementById(id);
  if (!el) return;
  navigator.clipboard.writeText(el.textContent.trim()).then(() => {
    const orig = btn.textContent;
    btn.textContent = '已複製 ✓';
    btn.classList.replace('bg-green-500','bg-slate-400');
    setTimeout(()=>{ btn.textContent=orig; btn.classList.replace('bg-slate-400','bg-green-500'); }, 2000);
  });
}

function copyUrgent(id, btn) {
  const el = document.getElementById(id);
  if (!el) return;
  navigator.clipboard.writeText(el.textContent.trim()).then(() => {
    const orig = btn.textContent;
    btn.textContent = '已複製 ✓';
    setTimeout(()=>btn.textContent=orig, 2000);
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
