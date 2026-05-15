/**
 * 水資源輿情監控系統 — Google Apps Script
 * v18: 修正 Date 物件序列化為 UTC 字串導致前端日期偏移問題；新增 sortByDate 動作
 */

// ─────────────────────────────────────────────────────────
//  工具：將各種日期格式統一轉為 YYYY-MM-DD（Asia/Taipei）
//  修正：Date 物件直接用 Utilities.formatDate；純日期字串原樣回傳；
//        ISO datetime 字串（含 T/Z）一律走時區轉換，不直接截斷
// ─────────────────────────────────────────────────────────
function normalizeDate_(s) {
  if (!s) return '';
  // Date 物件（Sheets getValues() 回傳）→ 直接用台灣時區格式化
  if (typeof s === 'object') {
    try { return Utilities.formatDate(s, 'Asia/Taipei', 'yyyy-MM-dd'); } catch(ex) {}
  }
  var str = String(s).trim();
  // 純 YYYY-MM-DD，沒有時間部分 → 直接回傳（無時區問題）
  if (/^\d{4}-\d{2}-\d{2}$/.test(str)) return str;
  // 其他格式（ISO datetime、RFC 822 等）→ 一律解析後轉台灣時區
  try {
    var d = new Date(str);
    if (!isNaN(d.getTime())) {
      return Utilities.formatDate(d, 'Asia/Taipei', 'yyyy-MM-dd');
    }
  } catch(ex) {}
  return '';
}

// ─────────────────────────────────────────────────────────
//  工具：中文欄位名稱 → 英文欄位名稱
// ─────────────────────────────────────────────────────────
function mapHeaders_(headers) {
  var map = {
    '日期': 'date', '標題': 'title', '來源媒體': 'source',
    '新聞網址': 'url', '情感': 'sentiment', '分類': 'category',
    '優先級': 'priority', '平台': 'platform', '關鍵字': 'keyword',
    '摘要': 'summary', 'AI澄清文字': 'line_message'
  };
  return headers.map(function(h) { return map[h] || h; });
}

// ─────────────────────────────────────────────────────────
//  工具：找欄位索引（支援中英文名稱，回傳 1-indexed 欄號）
// ─────────────────────────────────────────────────────────
function findCol_(headers) {
  var names = Array.prototype.slice.call(arguments, 1);
  for (var i = 0; i < names.length; i++) {
    var idx = headers.indexOf(names[i]);
    if (idx >= 0) return idx + 1;
  }
  return 0;
}

// ─────────────────────────────────────────────────────────
//  工具：根據 rawHeaders 和 item 組出一列資料
// ─────────────────────────────────────────────────────────
function buildRow_(rawHeaders, item) {
  var colMap = {
    '日期':'date','標題':'title','來源媒體':'source','新聞網址':'url',
    '情感':'sentiment','分類':'category','優先級':'priority','平台':'platform',
    '關鍵字':'keyword','摘要':'summary','AI澄清文字':'line_message'
  };
  return rawHeaders.map(function(h) {
    var key = colMap[h] || h;
    if (key === 'date') {
      return normalizeDate_(item.pub_date || item.published || item.date || '') || '';
    }
    var v = item[key];
    if (v == null) return '';
    if (typeof v === 'object') return JSON.stringify(v);
    return v;
  });
}

// ─────────────────────────────────────────────────────────
//  GET
// ─────────────────────────────────────────────────────────
function doGet(e) {
  try {
    const action = e && e.parameter && e.parameter.action;

    if (!action || action === 'status') {
      return ContentService
        .createTextOutput(JSON.stringify({status:'ok', message:'Water Monitor Sheets API v16'}))
        .setMimeType(ContentService.MimeType.JSON);
    }

    if (action === 'getAll') {
      const ss    = SpreadsheetApp.openById('1rZ9C78bMJsU8JLCwxfmWE4X_snXXRaBFo-8sfCEqST0');
      const sheet = ss.getSheetByName('輿情資料') || ss.getSheets()[0];
      const lastRow = sheet.getLastRow();
      if (lastRow < 2) return _emptyResponse();

      const lastCol = sheet.getLastColumn();
      const rawHeaders = sheet.getRange(1, 1, 1, lastCol).getValues()[0].map(h => String(h).trim());
      const headers    = mapHeaders_(rawHeaders);
      const rows       = sheet.getRange(2, 1, lastRow - 1, lastCol).getValues();

      const items = rows.map(row => {
        const obj = {};
        headers.forEach((h, i) => { obj[h] = row[i] === '' ? null : row[i]; });
        return obj;
      }).filter(x => x.title || x.date)
        .map(item => {
          // 清洗：Date 物件 → YYYY-MM-DD 台灣日期字串（避免 JSON.stringify 序列化成 UTC ISO 字串）
          const cleanDate = normalizeDate_(item.pub_date || item.published || item.date || '');
          item.date     = cleanDate;
          item.pub_date = cleanDate;  // 確保前端 pub_date 永遠有值
          if (item.published) item.published = cleanDate;
          return item;
        });

      // 近 90 天截止日
      const cutoff = new Date();
      cutoff.setDate(cutoff.getDate() - 90);
      const cutoffStr = Utilities.formatDate(cutoff, 'Asia/Taipei', 'yyyy-MM-dd');

      // 依實際發布日分組
      const monitorData = {};
      items.forEach(item => {
        const date = normalizeDate_(item.pub_date || item.published || item.date || '');
        if (!date || date < cutoffStr) return;
        if (!monitorData[date]) {
          monitorData[date] = {
            stats: {total:0, positive:0, negative:0, neutral:0, high_priority:0, date},
            items: []
          };
        }
        monitorData[date].items.push(item);
        monitorData[date].stats.total++;
        if (item.sentiment === '正面')      monitorData[date].stats.positive++;
        else if (item.sentiment === '負面') monitorData[date].stats.negative++;
        else                                monitorData[date].stats.neutral++;
        if (item.priority === '高' || item.priority === '高優先') monitorData[date].stats.high_priority++;
      });

      const kwCount = {};
      items.forEach(x => { if (x.keyword) kwCount[String(x.keyword)] = (kwCount[String(x.keyword)]||0)+1; });
      const kwRanking = Object.entries(kwCount).sort((a,b)=>b[1]-a[1]).slice(0,20);

      const topicHeat = {};
      items.forEach(x => {
        const cat = String(x.category || '其他');
        if (!topicHeat[cat]) topicHeat[cat] = {total:0, negative:0, positive:0};
        topicHeat[cat].total++;
        if (x.sentiment==='負面')      topicHeat[cat].negative++;
        else if (x.sentiment==='正面') topicHeat[cat].positive++;
      });

      const todayStr  = Utilities.formatDate(new Date(), 'Asia/Taipei', 'yyyy-MM-dd');
      const totalAll  = items.length;
      const totalNeg  = items.filter(x => x.sentiment === '負面').length;

      return ContentService
        .createTextOutput(JSON.stringify({
          monitor_data: monitorData,
          today: todayStr,
          topic_heat: topicHeat,
          keyword_ranking: kwRanking,
          total_all: totalAll,
          total_neg_all: totalNeg
        }))
        .setMimeType(ContentService.MimeType.JSON);
    }

    if (action === 'fixDates') {
      const ss    = SpreadsheetApp.openById('1rZ9C78bMJsU8JLCwxfmWE4X_snXXRaBFo-8sfCEqST0');
      const sheet = ss.getSheetByName('輿情資料') || ss.getSheets()[0];
      const lastRow = sheet.getLastRow();
      if (lastRow < 2) return ContentService.createTextOutput(JSON.stringify({status:'ok', updated:0})).setMimeType(ContentService.MimeType.JSON);

      const lastCol    = sheet.getLastColumn();
      const rawHeaders = sheet.getRange(1, 1, 1, lastCol).getValues()[0].map(h => String(h).trim());
      const dateCol    = findCol_(rawHeaders, 'date', '日期');
      const pubDateCol = findCol_(rawHeaders, 'pub_date');
      const publishedCol = findCol_(rawHeaders, 'published');

      if (!dateCol) return ContentService.createTextOutput(JSON.stringify({status:'error', message:'找不到日期欄位'})).setMimeType(ContentService.MimeType.JSON);
      if (!pubDateCol && !publishedCol) return ContentService.createTextOutput(JSON.stringify({status:'ok', updated:0, message:'無pub_date/published欄位可修正'})).setMimeType(ContentService.MimeType.JSON);

      const allRows = sheet.getRange(2, 1, lastRow - 1, lastCol).getValues();
      const dateColValues = sheet.getRange(2, dateCol, lastRow - 1, 1).getValues();
      let updated = 0;
      const newDates = dateColValues.map((row, i) => {
        const pubDate   = pubDateCol   > 0 ? String(allRows[i][pubDateCol-1]   || '') : '';
        const published = publishedCol > 0 ? String(allRows[i][publishedCol-1] || '') : '';
        const newDate   = normalizeDate_(pubDate || published || '');
        const current   = normalizeDate_(String(row[0] || ''));
        if (newDate && newDate !== current) { updated++; return [newDate]; }
        return [row[0]];
      });
      sheet.getRange(2, dateCol, lastRow - 1, 1).setValues(newDates);
      return ContentService.createTextOutput(JSON.stringify({status:'ok', updated})).setMimeType(ContentService.MimeType.JSON);
    }

    if (action === 'archive') {
      const ss    = SpreadsheetApp.openById('1ljNommiF8UsNQYqGBIHXTaMPPBODO_sFPXHkXgrwmRk');
      const sheet = ss.getSheetByName('澄清追蹤') || ss.getSheets()[0];
      if (sheet.getLastRow() === 0) {
        sheet.appendRow(['日期','標題','來源','網址','情感','分類','澄清文稿','歸檔時間']);
      }
      const archiveTime = Utilities.formatDate(new Date(), 'Asia/Taipei', 'yyyy-MM-dd HH:mm');
      sheet.appendRow([
        e.parameter.date || '', e.parameter.title || '', e.parameter.source || '',
        e.parameter.url || '', e.parameter.sentiment || '', e.parameter.category || '',
        e.parameter.line_message || '', archiveTime
      ]);
      return ContentService.createTextOutput(JSON.stringify({status:'ok'})).setMimeType(ContentService.MimeType.JSON);
    }

    if (action === 'clarify') {
      const title    = e.parameter.title    || '';
      const content  = e.parameter.content  || '';
      const source   = e.parameter.source   || '';
      const category = e.parameter.category || '';
      const apiKey   = PropertiesService.getScriptProperties().getProperty('GEMINI_API_KEY');
      if (!apiKey) return ContentService.createTextOutput(JSON.stringify({error:'GEMINI_API_KEY 未設定'})).setMimeType(ContentService.MimeType.JSON);

      const cleanContent = content.replace(/<[^>]+>/g, '').trim();
      const prompt =
        '這則新聞被判斷為負面輿情，請務必用繁體中文撰寫約200字的澄清說明，適合直接傳送到 LINE 群組使用。\n' +
        '標題：' + title + '\n內容摘要：' + (cleanContent || title) + '\n來源：' + source + '\n分類：' + category + '\n\n' +
        '重要：只回傳繁體中文澄清文字，不要 JSON、不要英文、不要標題或前言。';

      const resp = UrlFetchApp.fetch(
        'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=' + apiKey,
        { method:'post', contentType:'application/json',
          payload: JSON.stringify({
            contents:[{parts:[{text:prompt}]}],
            generationConfig:{maxOutputTokens:1024, temperature:0.3, responseMimeType:'text/plain'}
          }), muteHttpExceptions:true }
      );
      const respData = JSON.parse(resp.getContentText());
      if (resp.getResponseCode() !== 200) return ContentService.createTextOutput(JSON.stringify({error:'Gemini API 失敗：'+(respData.error?.message||resp.getResponseCode())})).setMimeType(ContentService.MimeType.JSON);
      const parts = respData.candidates?.[0]?.content?.parts || [];
      const text = parts.filter(p=>!p.thought).map(p=>p.text||'').join('').trim() || parts.map(p=>p.text||'').join('').trim() || '';
      return ContentService.createTextOutput(JSON.stringify({text})).setMimeType(ContentService.MimeType.JSON);
    }

    if (action === 'sortByDate') {
      const ss    = SpreadsheetApp.openById('1rZ9C78bMJsU8JLCwxfmWE4X_snXXRaBFo-8sfCEqST0');
      const sheet = ss.getSheetByName('輿情資料') || ss.getSheets()[0];
      const lastRow = sheet.getLastRow();
      if (lastRow < 3) return ContentService.createTextOutput(JSON.stringify({status:'ok', message:'資料不足，無需排序'})).setMimeType(ContentService.MimeType.JSON);

      const lastCol    = sheet.getLastColumn();
      const rawHeaders = sheet.getRange(1,1,1,lastCol).getValues()[0].map(h=>String(h).trim());
      const dateColIdx = rawHeaders.indexOf('日期') >= 0 ? rawHeaders.indexOf('日期') : rawHeaders.indexOf('date');  // 支援中英文欄位名
      if (dateColIdx < 0) return ContentService.createTextOutput(JSON.stringify({status:'error', message:'找不到「日期」欄位'})).setMimeType(ContentService.MimeType.JSON);

      // 先將所有日期欄位清洗為純 YYYY-MM-DD 字串，再排序
      const allValues = sheet.getRange(2,1,lastRow-1,lastCol).getValues();
      const cleaned = allValues.map(row => {
        const newRow = row.slice();
        newRow[dateColIdx] = normalizeDate_(row[dateColIdx]) || '';
        return newRow;
      });
      // 依日期由新到舊排序（降冪）
      cleaned.sort(function(a, b) {
        const da = String(a[dateColIdx] || '');
        const db = String(b[dateColIdx] || '');
        return db > da ? 1 : db < da ? -1 : 0;
      });
      sheet.getRange(2,1,cleaned.length,lastCol).setValues(cleaned);

      return ContentService.createTextOutput(JSON.stringify({status:'ok', sorted:cleaned.length})).setMimeType(ContentService.MimeType.JSON);
    }

    if (action === 'headers') {
      const ss    = SpreadsheetApp.openById('1rZ9C78bMJsU8JLCwxfmWE4X_snXXRaBFo-8sfCEqST0');
      const sheet = ss.getSheetByName('輿情資料') || ss.getSheets()[0];
      const lastRow = sheet.getLastRow();
      if (lastRow < 1) return ContentService.createTextOutput(JSON.stringify({headers:[], rows:0})).setMimeType(ContentService.MimeType.JSON);
      const lastCol  = sheet.getLastColumn();
      const headers  = sheet.getRange(1,1,1,lastCol).getValues()[0].map(h=>String(h).trim());
      const sample   = lastRow > 1 ? sheet.getRange(2,1,1,lastCol).getValues()[0] : [];
      return ContentService.createTextOutput(JSON.stringify({headers, sample, rows:lastRow, sheetName:sheet.getName()})).setMimeType(ContentService.MimeType.JSON);
    }

    return ContentService.createTextOutput(JSON.stringify({error:'unknown action: '+action})).setMimeType(ContentService.MimeType.JSON);

  } catch(err) {
    return ContentService.createTextOutput(JSON.stringify({error:err.toString()})).setMimeType(ContentService.MimeType.JSON);
  }
}

function _emptyResponse() {
  return ContentService
    .createTextOutput(JSON.stringify({monitor_data:{}, today:'', topic_heat:{}, keyword_ranking:[], total_all:0, total_neg_all:0}))
    .setMimeType(ContentService.MimeType.JSON);
}

// ─────────────────────────────────────────────────────────
//  POST
// ─────────────────────────────────────────────────────────
function doPost(e) {
  try {
    const payload = JSON.parse(e.postData.contents);

    // ── action=batchUpdateDates：批次更新「日期」欄位為實際發布日 ──
    if (payload.action === 'batchUpdateDates') {
      const ss    = SpreadsheetApp.openById('1rZ9C78bMJsU8JLCwxfmWE4X_snXXRaBFo-8sfCEqST0');
      const sheet = ss.getSheetByName('輿情資料') || ss.getSheets()[0];
      const lastRow = sheet.getLastRow();
      if (lastRow < 2) return ContentService.createTextOutput(JSON.stringify({status:'ok', updated:0})).setMimeType(ContentService.MimeType.JSON);

      const lastCol    = sheet.getLastColumn();
      const rawHeaders = sheet.getRange(1,1,1,lastCol).getValues()[0].map(h=>String(h).trim());
      const dateCol    = findCol_(rawHeaders, 'date', '日期');
      const urlCol     = findCol_(rawHeaders, 'url',  '新聞網址');

      if (!dateCol || !urlCol) {
        return ContentService.createTextOutput(JSON.stringify({status:'error', message:'找不到日期或網址欄位'})).setMimeType(ContentService.MimeType.JSON);
      }

      const updates = payload.updates || [];
      const urlMap  = {};
      updates.forEach(u => { if (u.url && u.pub_date) urlMap[String(u.url)] = String(u.pub_date); });

      const urlValues  = sheet.getRange(2, urlCol,  lastRow-1, 1).getValues();
      const dateValues = sheet.getRange(2, dateCol, lastRow-1, 1).getValues();

      let updated = 0;
      const newDates = dateValues.map((row, i) => {
        const url = String(urlValues[i][0] || '');
        if (url && urlMap[url]) {
          const newDate     = urlMap[url];
          const currentDate = normalizeDate_(String(row[0] || ''));
          if (newDate !== currentDate) { updated++; return [newDate]; }
        }
        return [row[0]];
      });

      sheet.getRange(2, dateCol, lastRow-1, 1).setValues(newDates);
      return ContentService.createTextOutput(JSON.stringify({status:'ok', updated})).setMimeType(ContentService.MimeType.JSON);
    }

    // ── action=deduplicateAll：清除重複行，以 URL 為唯一鍵，保留最後一筆 ──
    // 策略：一次讀取全部 → 記憶體去重 → 清除 → 一次寫回（速度快，避免逐行 deleteRow）
    if (payload.action === 'deduplicateAll') {
      const ss    = SpreadsheetApp.openById('1rZ9C78bMJsU8JLCwxfmWE4X_snXXRaBFo-8sfCEqST0');
      const sheet = ss.getSheetByName('輿情資料') || ss.getSheets()[0];
      const lastRow = sheet.getLastRow();
      if (lastRow < 3) {
        return ContentService.createTextOutput(JSON.stringify({status:'ok', deleted:0, message:'無重複行需清理'})).setMimeType(ContentService.MimeType.JSON);
      }

      const lastCol    = sheet.getLastColumn();
      const rawHeaders = sheet.getRange(1,1,1,lastCol).getValues()[0].map(h=>String(h).trim());
      const headers    = mapHeaders_(rawHeaders);
      const urlColIdx  = headers.indexOf('url');  // 0-indexed

      if (urlColIdx < 0) {
        return ContentService.createTextOutput(JSON.stringify({status:'error', message:'找不到 url 欄位'})).setMimeType(ContentService.MimeType.JSON);
      }

      // 一次讀取所有資料列
      const allValues = sheet.getRange(2, 1, lastRow-1, lastCol).getValues();
      const totalBefore = allValues.length;

      // 以 URL 為主鍵，保留最後出現的那筆（最新分析結果）
      const urlToLastRow = {};  // url → row data
      const noUrlRows = [];     // 沒有 URL 的列保留

      allValues.forEach(function(row) {
        const url = String(row[urlColIdx] || '').trim();
        if (url) {
          urlToLastRow[url] = row;  // 後者覆蓋前者 = 保留最後一筆
        } else {
          noUrlRows.push(row);
        }
      });

      const uniqueRows = Object.values(urlToLastRow).concat(noUrlRows);
      const deleted = totalBefore - uniqueRows.length;

      // 清除現有資料（保留第 1 列表頭）
      if (lastRow > 1) {
        sheet.getRange(2, 1, lastRow-1, lastCol).clearContent();
      }

      // 一次寫回所有去重後的列
      if (uniqueRows.length > 0) {
        sheet.getRange(2, 1, uniqueRows.length, lastCol).setValues(uniqueRows);
      }

      return ContentService.createTextOutput(JSON.stringify({
        status: 'ok',
        deleted: deleted,
        total_before: totalBefore,
        total_after: uniqueRows.length
      })).setMimeType(ContentService.MimeType.JSON);
    }

    // ── 預設：真正的 UPSERT（以 URL 為主鍵，更新已存在的列 OR 新增）──
    const items = payload.items || [];
    const ss    = SpreadsheetApp.openById('1rZ9C78bMJsU8JLCwxfmWE4X_snXXRaBFo-8sfCEqST0');
    const sheet = ss.getSheetByName('輿情資料') || ss.getSheets()[0];

    // 初始化表頭（若表格為空）
    if (sheet.getLastRow() === 0) {
      sheet.appendRow(['id','title','url','source','published','pub_date','content',
        'keyword','category','priority','platform','feed_source',
        'sentiment','summary','is_credible_threat','line_message','date']);
    }

    const rawHeaders = sheet.getRange(1,1,1,sheet.getLastColumn()).getValues()[0].map(h=>String(h).trim());
    const headers    = mapHeaders_(rawHeaders);
    const urlColIdx  = headers.indexOf('url');  // 0-indexed

    // 建立 URL → 行號 對照表（1-indexed，row 1 是表頭）
    const urlToRowNum = {};
    if (sheet.getLastRow() > 1 && urlColIdx >= 0) {
      const existingUrls = sheet.getRange(2, urlColIdx+1, sheet.getLastRow()-1, 1).getValues();
      existingUrls.forEach(function(r, i) {
        const u = String(r[0] || '').trim();
        if (u && !urlToRowNum[u]) {
          urlToRowNum[u] = i + 2;  // +2：表頭佔第 1 列，i 從 0 開始
        }
      });
    }

    let added = 0, updated = 0;
    items.forEach(function(item) {
      const url    = String(item.url || '').trim();
      const row    = buildRow_(rawHeaders, item);

      if (url && urlToRowNum[url]) {
        // 更新已存在的列
        sheet.getRange(urlToRowNum[url], 1, 1, rawHeaders.length).setValues([row]);
        updated++;
      } else {
        // 新增
        sheet.appendRow(row);
        if (url) urlToRowNum[url] = sheet.getLastRow();
        added++;
      }
    });

    return ContentService.createTextOutput(JSON.stringify({
      status: 'ok',
      added: added,
      updated: updated,
      count: added + updated
    })).setMimeType(ContentService.MimeType.JSON);

  } catch(err) {
    return ContentService.createTextOutput(JSON.stringify({status:'error', message:err.toString()})).setMimeType(ContentService.MimeType.JSON);
  }
}

// ─────────────────────────────────────────────────────────
//  一次性工具：刪除指定日期的所有列（直接在 Apps Script 編輯器執行）
// ─────────────────────────────────────────────────────────
function deleteRowsByDate() {
  var TARGET = '2026-05-15';
  var ss    = SpreadsheetApp.openById('1rZ9C78bMJsU8JLCwxfmWE4X_snXXRaBFo-8sfCEqST0');
  var sheet = ss.getSheetByName('輿情資料') || ss.getSheets()[0];
  var lastRow = sheet.getLastRow();
  if (lastRow < 2) { Logger.log('無資料'); return; }

  var lastCol    = sheet.getLastColumn();
  var rawHeaders = sheet.getRange(1, 1, 1, lastCol).getValues()[0].map(function(h){ return String(h).trim(); });
  var dateColIdx = rawHeaders.indexOf('date');
  if (dateColIdx < 0) dateColIdx = rawHeaders.indexOf('日期');
  if (dateColIdx < 0) { Logger.log('找不到日期欄位'); return; }

  var allValues = sheet.getRange(2, 1, lastRow - 1, lastCol).getValues();

  // 保留非 TARGET 的列
  var keepRows = allValues.filter(function(row) {
    var d = normalizeDate_(row[dateColIdx]);
    return d !== TARGET;
  });

  var deleted = allValues.length - keepRows.length;
  Logger.log('刪除: ' + deleted + ' 列，保留: ' + keepRows.length + ' 列');

  // 清除舊資料，寫回保留的列
  sheet.getRange(2, 1, lastRow - 1, lastCol).clearContent();
  if (keepRows.length > 0) {
    sheet.getRange(2, 1, keepRows.length, lastCol).setValues(keepRows);
  }

  Logger.log('完成。');
}
