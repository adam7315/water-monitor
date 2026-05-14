/**
 * 水資源輿情監控系統 — Google Apps Script
 *
 * 更新說明：
 *  1. doGet 支援三個 action：status / getAll / clarify
 *  2. doPost 補強去重邏輯
 *
 * 操作步驟：
 *  1. 開啟 Apps Script 編輯器（script.google.com）
 *  2. 全選貼上此檔案內容（取代現有全部代碼）
 *  3. 設定 Gemini API Key：
 *     左側 ⚙️ 專案設定 → 指令碼屬性 → 新增屬性
 *     屬性名稱：GEMINI_API_KEY　值：你的 Gemini API Key
 *  4. 儲存 → 部署 → 管理部署 → 新版本 → 部署（URL 不變）
 */

// ─────────────────────────────────────────────────────────
//  GET：讓網頁讀取 Sheets 裡全部新聞資料
// ─────────────────────────────────────────────────────────
function doGet(e) {
  try {
    const action = e && e.parameter && e.parameter.action;

    // health check（沒帶 action 或 action=status）
    if (!action || action === 'status') {
      return ContentService
        .createTextOutput(JSON.stringify({status:'ok', message:'Water Monitor Sheets API'}))
        .setMimeType(ContentService.MimeType.JSON);
    }

    // action=getAll → 回傳 MONITOR_DATA 格式給網頁使用
    if (action === 'getAll') {
      const ss    = SpreadsheetApp.openById('1rZ9C78bMJsU8JLCwxfmWE4X_snXXRaBFo-8sfCEqST0');
      const sheet = ss.getSheetByName('輿情資料') || ss.getSheets()[0];
      const lastRow = sheet.getLastRow();

      if (lastRow < 2) {
        return _emptyResponse();
      }

      const lastCol = sheet.getLastColumn();
      const headers = sheet.getRange(1, 1, 1, lastCol).getValues()[0]
                           .map(h => String(h).trim());
      const rows    = sheet.getRange(2, 1, lastRow - 1, lastCol).getValues();

      // 轉成物件陣列，過濾空列
      const items = rows.map(row => {
        const obj = {};
        headers.forEach((h, i) => { obj[h] = row[i] === '' ? null : row[i]; });
        return obj;
      }).filter(x => x.title || x.date);

      // 近 90 天截止日
      const cutoff = new Date();
      cutoff.setDate(cutoff.getDate() - 90);
      const cutoffStr = Utilities.formatDate(cutoff, 'Asia/Taipei', 'yyyy-MM-dd');

      // 依日期分組 → MONITOR_DATA 格式
      const monitorData = {};
      items.forEach(item => {
        const rawDate = item.date || item.published || '';
        const date = String(rawDate).slice(0, 10);
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
        if (item.priority === '高')         monitorData[date].stats.high_priority++;
      });

      // 關鍵字頻率 TOP 20
      const kwCount = {};
      items.forEach(x => { if (x.keyword) kwCount[String(x.keyword)] = (kwCount[String(x.keyword)]||0)+1; });
      const kwRanking = Object.entries(kwCount).sort((a,b)=>b[1]-a[1]).slice(0,20);

      // 分類熱度
      const topicHeat = {};
      items.forEach(x => {
        const cat = String(x.category || '其他');
        if (!topicHeat[cat]) topicHeat[cat] = {total:0, negative:0, positive:0};
        topicHeat[cat].total++;
        if (x.sentiment==='負面')      topicHeat[cat].negative++;
        else if (x.sentiment==='正面') topicHeat[cat].positive++;
      });

      const todayStr   = Utilities.formatDate(new Date(), 'Asia/Taipei', 'yyyy-MM-dd');
      const totalAll   = items.length;
      const totalNeg   = items.filter(x => x.sentiment === '負面').length;

      const result = {
        monitor_data:    monitorData,
        today:           todayStr,
        topic_heat:      topicHeat,
        keyword_ranking: kwRanking,
        total_all:       totalAll,
        total_neg_all:   totalNeg
      };

      return ContentService
        .createTextOutput(JSON.stringify(result))
        .setMimeType(ContentService.MimeType.JSON);
    }

    // action=clarify → 呼叫 Gemini 產生澄清文稿
    if (action === 'clarify') {
      const title    = e.parameter.title    || '';
      const content  = e.parameter.content  || '';
      const source   = e.parameter.source   || '';
      const category = e.parameter.category || '';

      const apiKey = PropertiesService.getScriptProperties().getProperty('GEMINI_API_KEY');
      if (!apiKey) {
        return ContentService.createTextOutput(JSON.stringify({error: 'GEMINI_API_KEY 未設定（請在指令碼屬性設定）'}))
          .setMimeType(ContentService.MimeType.JSON);
      }

      // 去除 HTML 標籤，避免 Gemini 接到 <a href=...> 等雜訊
      const cleanContent = content.replace(/<[^>]+>/g, '').trim();

      const prompt =
        '這則新聞被判斷為負面輿情，請務必用繁體中文撰寫約200字的澄清說明，' +
        '適合直接傳送到 LINE 群組使用。\n' +
        '標題：' + title + '\n' +
        '內容摘要：' + (cleanContent || title) + '\n' +
        '來源：' + source + '\n分類：' + category + '\n\n' +
        '重要：只回傳繁體中文澄清文字，不要 JSON、不要英文、不要標題或前言。';

      const payload = {
        contents: [{ parts: [{ text: prompt }] }],
        generationConfig: {
          maxOutputTokens: 1024,
          temperature: 0.3,
          responseMimeType: 'text/plain'
        }
      };

      const resp = UrlFetchApp.fetch(
        'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=' + apiKey,
        {
          method: 'post',
          contentType: 'application/json',
          payload: JSON.stringify(payload),
          muteHttpExceptions: true
        }
      );

      const respData = JSON.parse(resp.getContentText());
      if (resp.getResponseCode() !== 200) {
        return ContentService.createTextOutput(JSON.stringify({error: 'Gemini API 失敗：' + (respData.error?.message || resp.getResponseCode())}))
          .setMimeType(ContentService.MimeType.JSON);
      }

      // gemini-2.5-flash 是 thinking model，parts[0] 是思考內容（thought:true），
      // 必須過濾掉，只取實際回覆的 parts
      const parts = respData.candidates?.[0]?.content?.parts || [];
      const text = parts.filter(p => !p.thought).map(p => p.text || '').join('').trim()
                   || parts.map(p => p.text || '').join('').trim()
                   || '';
      return ContentService.createTextOutput(JSON.stringify({text}))
        .setMimeType(ContentService.MimeType.JSON);
    }

    // 未知 action
    return ContentService
      .createTextOutput(JSON.stringify({error: 'unknown action: ' + action}))
      .setMimeType(ContentService.MimeType.JSON);

  } catch(err) {
    return ContentService
      .createTextOutput(JSON.stringify({error: err.toString()}))
      .setMimeType(ContentService.MimeType.JSON);
  }
}

function _emptyResponse() {
  return ContentService
    .createTextOutput(JSON.stringify({
      monitor_data:{}, today:'', topic_heat:{},
      keyword_ranking:[], total_all:0, total_neg_all:0
    }))
    .setMimeType(ContentService.MimeType.JSON);
}

// ─────────────────────────────────────────────────────────
//  POST：每日新聞寫入 Sheets（原有功能，保持不變）
// ─────────────────────────────────────────────────────────
function doPost(e) {
  try {
    const payload = JSON.parse(e.postData.contents);
    const items   = payload.items || [];

    const ss    = SpreadsheetApp.openById('1rZ9C78bMJsU8JLCwxfmWE4X_snXXRaBFo-8sfCEqST0');
    const sheet = ss.getSheetByName('輿情資料') || ss.getSheets()[0];

    // 若空表，先建標題列
    if (sheet.getLastRow() === 0) {
      const headers = [
        'id','title','url','source','published','content',
        'keyword','category','priority','platform','feed_source',
        'sentiment','summary','is_credible_threat','line_message','date'
      ];
      sheet.appendRow(headers);
    }

    const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn())
                         .getValues()[0].map(h => String(h).trim());

    // 讀取現有 id 集合（去重）
    const existingIds = new Set();
    if (sheet.getLastRow() > 1) {
      const idCol = headers.indexOf('id') + 1;
      if (idCol > 0) {
        sheet.getRange(2, idCol, sheet.getLastRow()-1, 1)
             .getValues().forEach(r => { if (r[0]) existingIds.add(String(r[0])); });
      }
    }

    let added = 0;
    items.forEach(item => {
      const id = String(item.id || '');
      if (id && existingIds.has(id)) return; // 跳過重複
      const row = headers.map(h => {
        const v = item[h];
        return v == null ? '' : (typeof v === 'object' ? JSON.stringify(v) : v);
      });
      sheet.appendRow(row);
      if (id) existingIds.add(id);
      added++;
    });

    return ContentService
      .createTextOutput(JSON.stringify({status:'ok', count:added}))
      .setMimeType(ContentService.MimeType.JSON);

  } catch(err) {
    return ContentService
      .createTextOutput(JSON.stringify({status:'error', message:err.toString()}))
      .setMimeType(ContentService.MimeType.JSON);
  }
}
