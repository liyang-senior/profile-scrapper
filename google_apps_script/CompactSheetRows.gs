/**
 * Fill missed rows in candidate tabs and shift data up.
 *
 * A "missed" row = no email between the first and last row that has an email.
 * For each missed row: copy the last row with email into the gap, clear that
 * last row, then scan the same row again.
 *
 * Uses copyTo (row-by-row) instead of bulk setValues — bulk writes fail on
 * large tabs with IMAGE() formulas in the photo column.
 *
 * Setup:
 * 1. Paste your spreadsheet URL in SHEET_URL
 * 2. Run compactRowsInAllTabs() or compactRowsInTab("AI Engineer")
 */

var SHEET_URL = '';

/** Scraper columns: photo, name, email, sender, sent, role, ... */
var DATA_COLUMNS = 13;

function compactRowsInAllTabs() {
  var ss = openSpreadsheetByUrl_();
  var lines = [];
  var compacted = 0;
  var unchanged = 0;
  var skipped = 0;

  ss.getSheets().forEach(function (sheet) {
    var result = compactRowsInSheet_(sheet);
    if (result.status === 'compacted') {
      compacted++;
      lines.push('✓ ' + sheet.getName() + ': filled ' + result.filled + ' missed row(s)');
    } else if (result.status === 'unchanged') {
      unchanged++;
      lines.push('· ' + sheet.getName() + ': ' + result.message);
    } else {
      skipped++;
      lines.push('✗ ' + sheet.getName() + ': ' + result.message);
    }
  });

  lines.unshift(
    'Done — compacted ' + compacted + ' tab(s), ' + unchanged + ' unchanged, ' + skipped + ' skipped.'
  );
  showSummary_(lines.join('\n'));
}

function compactRowsInTab(tabName) {
  var ss = openSpreadsheetByUrl_();
  var sheet = ss.getSheetByName(String(tabName || '').trim());
  if (!sheet) throw new Error('Tab not found: ' + tabName);
  var result = compactRowsInSheet_(sheet);
  showSummary_(sheet.getName() + ': ' + result.message);
  return result;
}

function openSpreadsheetByUrl_() {
  var url = String(SHEET_URL || '').trim();
  if (!url) throw new Error('Set SHEET_URL first.');
  return SpreadsheetApp.openByUrl(url);
}

/**
 * @return {{status:string, message:string, filled:number, missed:number}}
 */
function compactRowsInSheet_(sheet) {
  var lastRow = sheet.getLastRow();
  if (lastRow < 2) {
    return { status: 'unchanged', message: 'No data rows.', filled: 0, missed: 0 };
  }

  var lastCol = Math.max(1, Number(DATA_COLUMNS) || 13);
  var emailCol = findEmailCol1Based_(sheet, lastCol);
  var rowCount = lastRow - 1;

  var emailColValues;
  try {
    emailColValues = sheet.getRange(2, emailCol, rowCount, 1).getValues();
  } catch (err) {
    return {
      status: 'error',
      message: 'Could not read email column: ' + err,
      filled: 0,
      missed: 0
    };
  }

  var emails = normalizeEmailColumn_(emailColValues);
  var bounds = emailBounds_(emails);
  if (bounds.first < 0) {
    return {
      status: 'unchanged',
      message: 'No rows with an email address.',
      filled: 0,
      missed: 0
    };
  }

  var missed = countMissedBetween_(emails, bounds.first, bounds.last);
  if (missed === 0) {
    return {
      status: 'unchanged',
      message: 'No missed rows between the first and last email rows.',
      filled: 0,
      missed: 0
    };
  }

  var rowIdx = 0;
  var filled = 0;
  var maxOps = missed + emails.length + 10;

  while (rowIdx < emails.length && filled < maxOps) {
    bounds = emailBounds_(emails);
    if (bounds.first < 0) break;

    if (rowIdx < bounds.first || rowIdx > bounds.last || emails[rowIdx]) {
      rowIdx++;
      continue;
    }

    var srcIdx = -1;
    for (var i = emails.length - 1; i >= rowIdx; i--) {
      if (emails[i]) {
        srcIdx = i;
        break;
      }
    }
    if (srcIdx <= rowIdx) break;

    var gapSheetRow = rowIdx + 2;
    var srcSheetRow = srcIdx + 2;

    try {
      moveSheetRowUp_(sheet, srcSheetRow, gapSheetRow, lastCol);
    } catch (err) {
      return {
        status: 'error',
        message: 'Could not move row ' + srcSheetRow + ' → ' + gapSheetRow + ': ' + err,
        filled: filled,
        missed: missed
      };
    }

    emails[rowIdx] = emails[srcIdx];
    emails[srcIdx] = '';
    filled++;

    if (filled % 15 === 0) SpreadsheetApp.flush();
    // Scan same row index again.
  }

  SpreadsheetApp.flush();

  if (filled === 0) {
    return {
      status: 'error',
      message: 'Missed rows found but none could be moved (check protected ranges).',
      filled: 0,
      missed: missed
    };
  }

  return {
    status: 'compacted',
    message: 'Filled ' + filled + ' missed row(s).',
    filled: filled,
    missed: missed
  };
}

/**
 * Move one row up using copyTo (keeps IMAGE formulas). Falls back to single-row setValues.
 */
function moveSheetRowUp_(sheet, srcRow, dstRow, lastCol) {
  var src = sheet.getRange(srcRow, 1, 1, lastCol);
  var dst = sheet.getRange(dstRow, 1, 1, lastCol);
  try {
    src.copyTo(dst);
    src.clearContent();
    return;
  } catch (copyErr) {
    // Fallback: one row only — avoids bulk-setValues payload errors.
    var values = src.getValues();
    dst.setValues(values);
    src.clearContent();
  }
}

function findEmailCol1Based_(sheet, lastCol) {
  var header = sheet.getRange(1, 1, 1, lastCol).getValues()[0];
  for (var c = 0; c < header.length; c++) {
    if (String(header[c] || '').trim().toLowerCase() === 'email') return c + 1;
  }
  return 3;
}

function normalizeEmailColumn_(emailColValues) {
  var out = [];
  for (var i = 0; i < emailColValues.length; i++) {
    out.push(String(emailColValues[i][0] || '').trim());
  }
  return out;
}

function emailBounds_(emails) {
  var first = -1;
  var last = -1;
  for (var i = 0; i < emails.length; i++) {
    if (!emails[i]) continue;
    if (first < 0) first = i;
    last = i;
  }
  return { first: first, last: last };
}

function countMissedBetween_(emails, first, last) {
  var n = 0;
  for (var i = first; i <= last; i++) {
    if (!emails[i]) n++;
  }
  return n;
}

function showSummary_(text) {
  Logger.log(text);
  try {
    SpreadsheetApp.getUi().alert('Compact rows', text, SpreadsheetApp.getUi().ButtonSet.OK);
  } catch (e) {
    // Running from editor without UI — Logger only.
  }
}
