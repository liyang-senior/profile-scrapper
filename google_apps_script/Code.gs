/**
 * getprog scraper — paste into the Apps Script project bound to YOUR Google Sheet.
 *
 * Setup:
 * 1. Open your Google Sheet → Extensions → Apps Script (script must be created FROM the sheet)
 * 2. Paste this file → Save
 * 3. Run testSetup() once from the editor (not doGet) to verify the sheet connection
 * 4. Deploy → New deployment → Web app → Execute as: Me | Who has access: Anyone
 * 5. Copy the /exec URL into the scraper sidebar + paste the same Sheet URL
 *
 * This script only writes candidate rows. Email templates live in a separate
 * spreadsheet (TEMPLATES_URL in EmailOutreach.gs) — do not seed them here.
 *
 * Do NOT click Run on doGet — it only works when called as a deployed web app URL.
 */

var COLUMNS = [
  'photo', 'name', 'email', 'sender', 'sent', 'role', 'current_company', 'years_experience',
  'github_url', 'linkedin_url', 'location', 'languages', 'phone_numbers'
];

var PHOTO_COL = 1;
var PHOTO_ROW_HEIGHT = 72;
var PHOTO_COL_WIDTH = 88;
var SENDER_COL = COLUMNS.indexOf('sender') + 1;
var SENT_COL = COLUMNS.indexOf('sent') + 1;
var S3_AVATAR_BASE = 'https://s3.us-west-1.amazonaws.com/progai-linkedin-avatars/';
var MAX_ROWS_PER_TAB = 1000;
/** Never write/purge these — templates live in a separate spreadsheet (TEMPLATES_URL). */
var SKIP_TABS = { Templates: true, templates: true };

/**
 * Run this from the Apps Script editor (Run ▶ testSetup) to verify your setup.
 */
function testSetup() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  if (!ss) {
    throw new Error(
      'No spreadsheet linked to this script.\n\n' +
      'Fix: Open your Google Sheet in the browser → Extensions → Apps Script.\n' +
      'The script must be created from inside that sheet, not as a standalone script project.'
    );
  }
  Logger.log('Connected to spreadsheet: ' + ss.getName());
  Logger.log('Spreadsheet ID (paste in scraper sidebar): ' + ss.getId());
  Logger.log('Next: Deploy → New deployment → Web app → Anyone → copy /exec URL');
  return ss.getId();
}

function doPost(e) {
  try {
    if (!e || !e.postData || !e.postData.contents) {
      return jsonResponse({ error: 'Empty POST body. Send JSON with spreadsheet_id and candidates.' }, 400);
    }
    var body = JSON.parse(e.postData.contents);
    var candidates = body.candidates || [];
    var spreadsheetId = body.spreadsheet_id || '';
    if (!spreadsheetId) {
      return jsonResponse({ error: 'Missing spreadsheet_id in POST body.' }, 400);
    }
    if (body.purge_no_email) {
      var ss = openSpreadsheet(spreadsheetId);
      var removed = purgeNoEmailRows(ss);
      return jsonResponse({ ok: true, purged: removed });
    }
    var counts = appendCandidates(candidates, spreadsheetId);
    return jsonResponse({ ok: true, counts: counts });
  } catch (err) {
    return jsonResponse({ error: String(err) }, 500);
  }
}

function doGet(e) {
  try {
    var params = (e && e.parameter) ? e.parameter : {};
    var spreadsheetId = params.spreadsheet_id || '';

    if (!spreadsheetId) {
      return jsonResponse({
        ok: true,
        message: 'getprog scraper web app is running.',
        hint: 'Pass ?spreadsheet_id=YOUR_SHEET_ID to test a connection, or use Test Sheets connection in the scraper app.',
        editor_test: 'To test in the editor, run testSetup() — not doGet().'
      });
    }

    var ss = openSpreadsheet(spreadsheetId);
    return jsonResponse({
      ok: true,
      message: 'Connected to spreadsheet',
      spreadsheet: ss.getName(),
      spreadsheet_id: ss.getId()
    });
  } catch (err) {
    return jsonResponse({ ok: false, error: String(err) }, 500);
  }
}

function jsonResponse(obj, code) {
  code = code || 200;
  var out = ContentService.createTextOutput(JSON.stringify(obj));
  out.setMimeType(ContentService.MimeType.JSON);
  return out;
}

function openSpreadsheet(spreadsheetId) {
  var ss = null;

  if (spreadsheetId) {
    try {
      ss = SpreadsheetApp.openById(spreadsheetId);
    } catch (e) {
      throw new Error(
        'Cannot open spreadsheet ID: ' + spreadsheetId + '. ' +
        'Check the URL in the scraper sidebar and that this Google account owns the sheet.'
      );
    }
  } else {
    ss = SpreadsheetApp.getActiveSpreadsheet();
  }

  if (!ss) {
    throw new Error(
      'No spreadsheet found. Open your Google Sheet → Extensions → Apps Script ' +
      '(the script must be bound to that sheet), or send spreadsheet_id in the request.'
    );
  }

  return ss;
}

function appendCandidates(candidates, spreadsheetId) {
  var ss = openSpreadsheet(spreadsheetId);
  var byTab = {};

  candidates.forEach(function (c) {
    var tab = sanitizeTabName(c.role_tab || 'Other');
    if (!byTab[tab]) byTab[tab] = [];
    byTab[tab].push(c);
  });

  var counts = {};
  var totals = { appended: 0, updated: 0 };
  Object.keys(byTab).forEach(function (tabName) {
    var result = appendToTab(ss, tabName, byTab[tabName]);
    counts[tabName] = result.appended;
    totals.appended += result.appended;
    totals.updated += result.updated;
  });
  counts._updated = totals.updated;
  counts._appended = totals.appended;
  return counts;
}

function isSkippedTab(sheet) {
  return !!SKIP_TABS[String(sheet.getName() || '').trim()];
}

function purgeNoEmailRows(ss) {
  var removed = 0;
  ss.getSheets().forEach(function (sheet) {
    if (isSkippedTab(sheet)) return;
    var lastRow = sheet.getLastRow();
    if (lastRow < 2) return;
    var emailIdx = COLUMNS.indexOf('email') + 1;
    for (var r = lastRow; r >= 2; r--) {
      var val = sheet.getRange(r, emailIdx).getValue();
      var gmails = gmailOnlyFromCell(val);
      if (!gmails.length) {
        sheet.deleteRow(r);
        removed += 1;
      } else {
        var cleaned = gmails.join('\n');
        if (cleaned !== String(val || '').trim()) {
          sheet.getRange(r, emailIdx).setValue(cleaned);
        }
      }
    }
  });
  return removed;
}

/**
 * Run once from the Apps Script editor to delete sheet rows with no email.
 */
function purgeNoEmailFromAllTabs() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  if (!ss) throw new Error('Open the bound spreadsheet first.');
  var n = purgeNoEmailRows(ss);
  Logger.log('Removed ' + n + ' rows without email.');
  return n;
}

function rowHasEmail(row) {
  var e = String(row.email || '').trim();
  if (!e) return false;
  var parts = e.split(/[\n;,]+/);
  for (var i = 0; i < parts.length; i++) {
    if (isGmailAddress(parts[i])) return true;
  }
  return false;
}

function isGmailAddress(addr) {
  var a = String(addr || '').trim().toLowerCase();
  if (a.indexOf('@') === -1) return false;
  var domain = a.split('@').pop();
  return domain === 'gmail.com' || domain === 'googlemail.com';
}

function gmailOnlyFromCell(value) {
  var parts = String(value || '').split(/[\n;,]+/);
  var out = [];
  for (var i = 0; i < parts.length; i++) {
    var a = parts[i].trim();
    if (isGmailAddress(a)) out.push(a);
  }
  return out;
}

function appendToTab(ss, tabName, rows) {
  var sheet = getOrCreateSheetWithCapacity(ss, tabName, rows.length);
  ensureHeader(sheet);
  applySheetStyle(sheet);

  var existing = loadExistingKeys(sheet);
  var existingByLinkedin = loadExistingRowIndex(sheet);
  var toAppend = [];
  var updated = 0;

  rows.forEach(function (row) {
    if (!rowHasEmail(row)) return;
    // Keep only Gmail addresses in the sheet cell.
    var gmails = gmailOnlyFromCell(row.email);
    if (!gmails.length) return;
    row = Object.assign({}, row, { email: gmails.join('\n') });
    var linkedin = linkedinSlug(row.linkedin_url);
    if (linkedin && existingByLinkedin[linkedin]) {
      if (updateIncompleteRow(sheet, existingByLinkedin[linkedin], row)) {
        updated += 1;
      }
      return;
    }

    var key = dedupeKey(row);
    if (existing[key]) return;
    existing[key] = true;
    if (linkedin) {
      existingByLinkedin[linkedin] = sheet.getLastRow() + toAppend.length + 1;
    }
    toAppend.push(rowToValues(row));
  });

  if (toAppend.length > 0) {
    var startRow = sheet.getLastRow() + 1;
    sheet.getRange(startRow, 1, toAppend.length, COLUMNS.length).setValues(toAppend);
    sheet.setRowHeights(startRow, toAppend.length, PHOTO_ROW_HEIGHT);
    applySheetStyle(sheet);
  }
  return { appended: toAppend.length, updated: updated };
}

function loadExistingRowIndex(sheet) {
  var index = {};
  var lastRow = sheet.getLastRow();
  if (lastRow < 2) return index;

  var linkedinIdx = COLUMNS.indexOf('linkedin_url');
  var data = sheet.getRange(2, 1, lastRow - 1, COLUMNS.length).getValues();
  data.forEach(function (r, i) {
    var slug = linkedinSlug(r[linkedinIdx]);
    if (slug) index[slug] = i + 2;
  });
  return index;
}

function photoFromCell(value) {
  var s = String(value || '').trim();
  var m = s.match(/^=IMAGE\("([^"]+)"/i);
  if (m) return m[1];
  return s;
}

function cellPhotoIsMissing(value) {
  var s = String(value || '').trim();
  if (!s) return true;
  var url = photoFromCell(s);
  if (!url || url.indexOf('http') !== 0) return true;
  if (isGetprogPhoto(url) && !photoUrlLoads(url)) return true;
  if (s.indexOf('=IMAGE(') === 0) return false;
  return s.indexOf('http') !== 0;
}

function updateIncompleteRow(sheet, rowNum, row) {
  var changed = false;
  var photoIdx = COLUMNS.indexOf('photo') + 1;
  var emailIdx = COLUMNS.indexOf('email') + 1;

  var photoCell = sheet.getRange(rowNum, photoIdx);
  var currentPhoto = photoCell.getValue();
  if (cellPhotoIsMissing(currentPhoto)) {
    var photo = resolvePhotoUrl(row);
    if (photo.indexOf('http') === 0) {
      photoCell.setValue('=IMAGE("' + photo.replace(/"/g, '') + '", 1)');
      changed = true;
    }
  } else {
    var existingUrl = photoFromCell(currentPhoto);
    if (isGetprogPhoto(existingUrl) && !photoUrlLoads(existingUrl)) {
      var repaired = resolvePhotoUrl(row);
      if (repaired.indexOf('http') === 0 && repaired !== existingUrl) {
        photoCell.setValue('=IMAGE("' + repaired.replace(/"/g, '') + '", 1)');
        changed = true;
      }
    }
  }

  var emailCell = sheet.getRange(rowNum, emailIdx);
  var currentEmail = String(emailCell.getValue() || '').trim();
  var newEmails = gmailOnlyFromCell(row.email);
  var newEmail = newEmails.join('\n');
  if ((!currentEmail || !gmailOnlyFromCell(currentEmail).length) && newEmail) {
    emailCell.setValue(newEmail);
    changed = true;
  } else if (currentEmail && newEmail) {
    // Prefer Gmail-only content if the cell still has company emails mixed in.
    var cleaned = gmailOnlyFromCell(currentEmail).join('\n');
    if (cleaned && cleaned !== currentEmail) {
      emailCell.setValue(cleaned);
      changed = true;
    }
  }

  if (changed) {
    sheet.setRowHeight(rowNum, PHOTO_ROW_HEIGHT);
  }
  return changed;
}

function getOrCreateSheetWithCapacity(ss, baseName, incomingCount) {
  var safe = sanitizeTabName(baseName);
  var sheet = ss.getSheetByName(safe);
  if (!sheet) {
    sheet = ss.insertSheet(safe);
    applySheetStyle(sheet);
    return sheet;
  }

  var dataRows = Math.max(sheet.getLastRow() - 1, 0);
  if (dataRows + incomingCount <= MAX_ROWS_PER_TAB) {
    return sheet;
  }

  var part = 2;
  while (part < 100) {
    var name = safe + ' ' + part;
    var alt = ss.getSheetByName(name);
    if (!alt) {
      alt = ss.insertSheet(name);
      applySheetStyle(alt);
      return alt;
    }
    var altRows = Math.max(alt.getLastRow() - 1, 0);
    if (altRows + incomingCount <= MAX_ROWS_PER_TAB) {
      return alt;
    }
    part += 1;
  }
  return sheet;
}

function formatListCell(val) {
  if (val === null || val === undefined) return '';
  if (Array.isArray(val)) {
    return val.map(function (item) { return String(item).trim(); })
      .filter(function (s) { return s; })
      .join('\n');
  }
  var s = String(val).trim();
  if (!s || s === '[]') return '';
  if (s.charAt(0) === '[' && s.charAt(s.length - 1) === ']') {
    var quoted = s.match(/['"]([^'"]+)['"]/g);
    if (quoted && quoted.length) {
      return quoted.map(function (part) {
        return part.replace(/^['"]|['"]$/g, '').trim();
      }).filter(function (item) { return item; }).join('\n');
    }
  }
  return s;
}

function linkedinSlug(url) {
  var m = String(url || '').match(/linkedin\.com\/in\/([^/?#]+)/i);
  return m ? m[1].toLowerCase() : '';
}

function isGetprogPhoto(url) {
  return String(url || '').toLowerCase().indexOf('progai-linkedin-avatars') !== -1;
}

function isFallbackPhoto(url) {
  var u = String(url || '').toLowerCase();
  if (!u) return true;
  if (isGetprogPhoto(u)) return false;
  return u.indexOf('ui-avatars.com') !== -1 || u.indexOf('avatars.githubusercontent.com') !== -1;
}

function photoUrlLoads(url) {
  if (!url || url.indexOf('http') !== 0) return false;
  try {
    var res = UrlFetchApp.fetch(url, {
      method: 'get',
      muteHttpExceptions: true,
      followRedirects: true
    });
    var code = res.getResponseCode();
    if (code !== 200) return false;
    var ctype = String(res.getHeaders()['Content-Type'] || '').toLowerCase();
    return !ctype || ctype.indexOf('image') !== -1;
  } catch (e) {
    return false;
  }
}

function initialsPhotoUrl(name) {
  var n = String(name || '').trim();
  if (!n) return '';
  return 'https://ui-avatars.com/api/?name=' + encodeURIComponent(n) +
    '&size=128&background=1F4E78&color=ffffff&bold=true';
}

function resolvePhotoUrl(row) {
  var photo = String(row.photo || '').trim();
  if (isGetprogPhoto(photo)) {
    if (photoUrlLoads(photo)) return photo;
    photo = '';
  }
  if (photo.indexOf('http') === 0 && isFallbackPhoto(photo)) {
    return photo;
  }
  if (photo.indexOf('http') === 0 && !isFallbackPhoto(photo) && photoUrlLoads(photo)) {
    return photo;
  }
  var slug = linkedinSlug(row.linkedin_url);
  if (slug) {
    var s3 = S3_AVATAR_BASE + slug + '.png';
    if (photoUrlLoads(s3)) return s3;
  }
  var gh = String(row.github_url || '').trim();
  var gm = gh.match(/github\.com\/([^/?#]+)/i);
  if (gm) {
    return 'https://avatars.githubusercontent.com/' + gm[1] + '?v=4';
  }
  if (photo.indexOf('http') === 0) return photo;
  return initialsPhotoUrl(row.name);
}

function rowToValues(row) {
  var photo = resolvePhotoUrl(row);
  if (photo.indexOf('http') === 0) {
    photo = '=IMAGE("' + photo.replace(/"/g, '') + '", 1)';
  }
  var emails = gmailOnlyFromCell(row.email).join('\n');
  return [
    photo,
    row.name || '',
    emails,
    row.sender || '',
    row.sent || '',
    row.role || '',
    row.current_company || '',
    row.years_experience || '',
    row.github_url || '',
    row.linkedin_url || '',
    row.location || '',
    formatListCell(row.languages),
    formatListCell(row.phone_numbers)
  ];
}

function formatPhotoColumn(sheet) {
  sheet.setColumnWidth(PHOTO_COL, PHOTO_COL_WIDTH);
}

function applySheetStyle(sheet) {
  var lastRow = Math.max(sheet.getLastRow(), 1);
  var lastCol = COLUMNS.length;

  formatPhotoColumn(sheet);
  sheet.setFrozenRows(1);

  // Header style
  var headerRange = sheet.getRange(1, 1, 1, lastCol);
  headerRange
    .setBackground('#1F4E78')
    .setFontColor('#FFFFFF')
    .setFontWeight('bold')
    .setHorizontalAlignment('center')
    .setVerticalAlignment('middle');

  // Data alignment
  if (lastRow > 1) {
    var dataRange = sheet.getRange(2, 1, lastRow - 1, lastCol);
    dataRange.setVerticalAlignment('middle');
    dataRange.setHorizontalAlignment('center');

    // Light zebra stripe for readability
    for (var r = 2; r <= lastRow; r++) {
      var bg = (r % 2 === 0) ? '#F7FAFF' : '#FFFFFF';
      sheet.getRange(r, 1, 1, lastCol).setBackground(bg);
    }
  }

  // Keep sender / sent columns readable
  if (SENDER_COL > 0) sheet.setColumnWidth(SENDER_COL, 180);
  if (SENT_COL > 0) sheet.setColumnWidth(SENT_COL, 140);
}

function normalizePhoto(val) {
  var s = String(val || '').trim().toLowerCase().replace(/\/+$/, '');
  var m = s.match(/^=image\("([^"]+)"/i);
  if (m) return m[1].replace(/\/+$/, '');
  return s;
}

function dedupeKey(row) {
  var linkedin = linkedinSlug(row.linkedin_url);
  if (linkedin) return 'li:' + linkedin;
  var name = String(row.name || '').trim().toLowerCase();
  var role = String(row.role || '').trim().toLowerCase();
  var company = String(row.current_company || '').trim().toLowerCase();
  var photo = normalizePhoto(row.photo);
  return name + '\t' + role + '\t' + company + '\t' + photo;
}

function loadExistingKeys(sheet) {
  var keys = {};
  var lastRow = sheet.getLastRow();
  if (lastRow < 2) return keys;

  var data = sheet.getRange(2, 1, lastRow - 1, COLUMNS.length).getValues();
  var photoIdx = COLUMNS.indexOf('photo');
  var nameIdx = COLUMNS.indexOf('name');
  var roleIdx = COLUMNS.indexOf('role');
  var companyIdx = COLUMNS.indexOf('current_company');
  var linkedinIdx = COLUMNS.indexOf('linkedin_url');

  data.forEach(function (r) {
    keys[dedupeKey({
      name: r[nameIdx],
      role: r[roleIdx],
      current_company: r[companyIdx],
      photo: r[photoIdx],
      linkedin_url: r[linkedinIdx]
    })] = true;
  });
  return keys;
}

function ensureHeader(sheet) {
  var header = sheet.getRange(1, 1, 1, Math.max(sheet.getLastColumn(), COLUMNS.length)).getValues()[0];
  var same = header.length >= COLUMNS.length;
  if (same) {
    for (var i = 0; i < COLUMNS.length; i++) {
      if (String(header[i] || '') !== COLUMNS[i]) { same = false; break; }
    }
  }
  if (!same) {
    migrateHeader_(sheet, header);
    applySheetStyle(sheet);
  }
}

/**
 * Migrate old header (email_sent checkbox) → sender + sent text columns.
 */
function migrateHeader_(sheet, oldHeader) {
  var lastCol = Math.max(sheet.getLastColumn(), 1);
  var emailSentIdx = -1;
  for (var i = 0; i < oldHeader.length; i++) {
    if (String(oldHeader[i] || '').trim() === 'email_sent') {
      emailSentIdx = i + 1; // 1-based
      break;
    }
  }

  if (emailSentIdx > 0) {
    // Replace email_sent checkbox column with sender, then insert sent beside it.
    sheet.getRange(1, emailSentIdx).setValue('sender');
    // Clear checkbox validation / boolean values in that column for data rows.
    var lastRow = sheet.getLastRow();
    if (lastRow > 1) {
      var range = sheet.getRange(2, emailSentIdx, lastRow - 1, 1);
      range.clearDataValidations();
      var vals = range.getValues();
      for (var r = 0; r < vals.length; r++) {
        // Keep TRUE checkbox as a marker that something was "sent" historically,
        // but leave sender blank so outreach can still claim if needed.
        if (vals[r][0] === true || vals[r][0] === 'TRUE') {
          vals[r][0] = '';
        } else if (vals[r][0] === false || vals[r][0] === 'FALSE') {
          vals[r][0] = '';
        }
      }
      range.setValues(vals);
    }
    sheet.insertColumnAfter(emailSentIdx);
    sheet.getRange(1, emailSentIdx + 1).setValue('sent');
  }

  sheet.getRange(1, 1, 1, COLUMNS.length).setValues([COLUMNS]);
}

function getOrCreateSheet(ss, name) {
  return getOrCreateSheetWithCapacity(ss, name, 1);
}

function onEdit(e) {
  // Reserved for future sheet edit hooks (sender/sent are written by EmailOutreach.gs).
}

function onChange(e) {
  // Reserved for future insert-row hooks.
}

/**
 * Optional: run once to apply formatting to all tabs (new sender/sent headers).
 */
function beautifyAllTabs() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  if (!ss) return;
  ss.getSheets().forEach(function (sheet) {
    if (isSkippedTab(sheet)) return;
    ensureHeader(sheet);
    applySheetStyle(sheet);
  });
}

/**
 * Run once to delete rows that have no Gmail address (company-only emails).
 */
function purgeNonGmailFromAllTabs() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  if (!ss) throw new Error('Open the bound spreadsheet first.');
  var removed = 0;
  ss.getSheets().forEach(function (sheet) {
    if (isSkippedTab(sheet)) return;
    var lastRow = sheet.getLastRow();
    if (lastRow < 2) return;
    var emailIdx = COLUMNS.indexOf('email') + 1;
    for (var r = lastRow; r >= 2; r--) {
      var val = sheet.getRange(r, emailIdx).getValue();
      var gmails = gmailOnlyFromCell(val);
      if (!gmails.length) {
        sheet.deleteRow(r);
        removed += 1;
      } else {
        var cleaned = gmails.join('\n');
        if (cleaned !== String(val || '').trim()) {
          sheet.getRange(r, emailIdx).setValue(cleaned);
        }
      }
    }
  });
  Logger.log('Removed ' + removed + ' non-Gmail rows.');
  return removed;
}

function sanitizeTabName(name) {
  var invalid = /[\\/?*[\]]/g;
  var cleaned = String(name).replace(invalid, '_').substring(0, 100) || 'Other';
  if (SKIP_TABS[cleaned]) return 'Other';
  return cleaned;
}
