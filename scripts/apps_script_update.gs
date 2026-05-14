/**
 * 水資源輿情監控系統 — Google Apps Script
 *
 * 支援中英文欄位名稱，統一以發布日（pub_date）分組
 */

// ─────────────────────────────────────────────────────────
//  工具：將各種日期格式統一轉為 YYYY-MM-DD
// ─────────────────────────────────────────────────────────
function normalizeDate_(s) {
  if (!s) return '';
  var str = String(s).trim();
  if (/^\d{4}-\d{2}-\d{2}/.test(str)) return str.slice(0, 10);
  try {
    var d = new Date(str);
    if (!isNaN(d.getTime())) {
      return Utilities.formatDate(d, 'Asia/Taipei', 'yyyy-MM-dd');
    }
  } catch(ex) {}
  return '';
}

// ─────────────────────────────────────────────────────────
//  工具：將中文欄位名稱對應到英文欄位名稱
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
//  工具：找欄位索引（支援中英文名稱）
// ─────────────────────────────────────────────────────────
function findCol_(headers, ...names) {
  for (const name of names) {
    const idx = headers.indexOf(name);
    if (idx >= 0) return idx + 1;
  }
  return 0;
}

// ─────────────────────────────────────────────────────────
//  GET
// ─────────────────────────────────────────────────────────
function doGet(e) {
  try {
    const action = e && e.parameter && e.parameter.action;

    if (!action || action === 'status') {
      return ContentService
        .createTextOutput(JSON.stringify({status:'ok', message:'Water Monitor Sheets API v15'}))
        .setMimeType(ContentService.MimeType.JSON);
    }

    if (action === 'getAll') {
      const ss    = SpreadsheetApp.openById('1rZ9C78bMJsU8JLCwxfmWE4X_snXXRaBFo-8sfCEqST0');
      const sheet = ss.getSheetByName('輿情資料') || ss.getSheets()[0];
      const lastRow = sheet.getLastRow();
      if (lastRow < 2) return _emptyResponse();

      const lastCol = sheet.getLastColumn();
      const rawHeaders = sheet.getRange(1, 1, 1, lastCol).getValues()[0].map(h => String(h).trim());
      const headers    = mapHeaders_(rawHeaders);   // 中文→英文
      const rows       = sheet.getRange(2, 1, lastRow - 1, lastCol).getValues();

      const items = rows.map(row => {
        const obj = {};
        headers.forEach((h, i) => { obj[h] = row[i] === '' ? null : row[i]; });
        return obj;
      }).filter(x => x.title || x.date);

      // 近 90 天截止日
      const cutoff = new Date();
      cutoff.setDate(cutoff.getDate() - 90);
      const cutoffStr = Utilities.formatDate(cutoff, 'Asia/Taipei', 'yyyy-MM-dd');

      // 依實際發布日分組（pub_date → published → date）
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

    // action=batchUpdateDates：批次將「日期」欄位更新為實際發布日
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

      // 建立 URL → pub_date 對照表
      const updates = payload.updates || [];
      const urlMap  = {};
      updates.forEach(u => { if (u.url && u.pub_date) urlMap[String(u.url)] = String(u.pub_date); });

      // 一次讀取所有 URL 和日期
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

    // 預設：寫入每日新聞
    const items = payload.items || [];
    const ss    = SpreadsheetApp.openById('1rZ9C78bMJsU8JLCwxfmWE4X_snXXRaBFo-8sfCEqST0');
    const sheet = ss.getSheetByName('輿情資料') || ss.getSheets()[0];

    if (sheet.getLastRow() === 0) {
      sheet.appendRow(['id','title','url','source','published','pub_date','content',
        'keyword','category','priority','platform','feed_source',
        'sentiment','summary','is_credible_threat','line_message','date']);
    }

    const rawHeaders = sheet.getRange(1,1,1,sheet.getLastColumn()).getValues()[0].map(h=>String(h).trim());
    const headers    = mapHeaders_(rawHeaders);   // 中英文皆可讀

    // 去重：讀現有 URL 集合（同標題+來源視為重複）
    const existingIds = new Set();
    if (sheet.getLastRow() > 1) {
      const idIdx = headers.indexOf('id');
      const urlIdx = headers.indexOf('url');
      if (idIdx >= 0 || urlIdx >= 0) {
        const colIdx = idIdx >= 0 ? idIdx : urlIdx;
        sheet.getRange(2, colIdx+1, sheet.getLastRow()-1, 1)
             .getValues().forEach(r => { if (r[0]) existingIds.add(String(r[0])); });
      }
    }

    let added = 0;
    items.forEach(item => {
      const id = String(item.id || item.url || '');
      if (id && existingIds.has(id)) return;
      const row = rawHeaders.map(h => {
        const englishKey = ({'日期':'date','標題':'title','來源媒體':'source','新聞網址':'url',
                             '情感':'sentiment','分類':'category','優先級':'priority','平台':'platform',
                             '關鍵字':'keyword','摘要':'summary','AI澄清文字':'line_message'})[h] || h;
        if (englishKey === 'date') {
          return normalizeDate_(item.pub_date || item.published || item.date || '') || '';
        }
        const v = item[englishKey];
        return v == null ? '' : (typeof v === 'object' ? JSON.stringify(v) : v);
      });
      sheet.appendRow(row);
      if (id) existingIds.add(id);
      added++;
    });

    return ContentService.createTextOutput(JSON.stringify({status:'ok', count:added})).setMimeType(ContentService.MimeType.JSON);

  } catch(err) {
    return ContentService.createTextOutput(JSON.stringify({status:'error', message:err.toString()})).setMimeType(ContentService.MimeType.JSON);
  }
}
