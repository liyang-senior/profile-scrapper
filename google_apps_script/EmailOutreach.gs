/**
 * Gmail outreach sender — paste this file into EACH sender Gmail’s Apps Script.
 * Do NOT deploy as a web app. After installSchedule(), Google sends mail even if
 * your PC is off. Logs: left sidebar → Executions.
 *
 * ── What you must fill in below (CONFIG) ──────────────────────────────────
 *
 * Required:
 *   SPREADSHEET_URL      Full candidates Sheet URL of the TAB you want (must include gid=…)
 *   TEMPLATES_URL        Templates-only Sheet URL (columns: No | Title | Templates)
 *   SENDER_DISPLAY_NAME  Your real name as it should appear in the email (not an address)
 *
 * Optional test (then run sendTestEmail):
 *   TEST_TEMPLATE_NO     Number from the templates sheet “No” column
 *   TEST_RECEIVER_NAME   Test recipient’s full name
 *   TEST_RECEIVER_EMAIL  Test recipient’s email
 *
 * Usually leave as-is:
 *   EMAILS_PER_RUN       1  (one email per 2-hour slot)
 *   EMAIL_SUBJECT        Fallback subject if Title column is empty
 *   SEND_START_HOUR      First send of the day (0–23, local timezone)
 *   SEND_START_MINUTE    Minutes past that hour (0–59)
 *
 * ── Setup (once per sender Gmail) ─────────────────────────────────────────
 * 1. Share BOTH spreadsheets with this Gmail as Editor
 * 2. https://script.google.com → New project → paste this file → Save
 * 3. Fill SPREADSHEET_URL (open the role tab, copy the browser URL with #gid=), TEMPLATES_URL, SENDER_DISPLAY_NAME
 * 4. Set SEND_START_HOUR / SEND_START_MINUTE (first slot; then every 2 hours)
 * 5. Run authorizeOnce  (approve Gmail + Sheets)
 * 6. Optional: fill TEST_* → run sendTestEmail
 * 7. Run installSchedule  (starts the ~2 hour automatic sends)
 * Stop later: run uninstallSchedule
 *
 * Live send: rows top-to-bottom on the tab identified by SPREADSHEET_URL’s gid (not random, not other tabs).
 * Skip a profile only if it has no usable email, or every listed address fails.
 * One email per 2-hour slot starting at SEND_START_HOUR:SEND_START_MINUTE,
 * random time in a 20-minute window (e.g. 9:00 → 8:50–9:10).
 * After each attempt: sender = this Gmail; sent = Sent (green) or Failed (red).
 * {{receiver}} = first name · {{sender}} = SENDER_DISPLAY_NAME
 */

// ─── CONFIG (edit these) ───────────────────────────────────────────────────

/** Paste the full Google Sheets URL of the candidates TAB (must include gid=). */
var SPREADSHEET_URL =
  'https://docs.google.com/spreadsheets/d/10LVHiDHeurThQRiB5BfoiwHU8Vem7Mp5B20nE3ofXJE/edit?gid=372334308#gid=372334308';

/**
 * Paste the templates-only Google Sheet URL here (not the candidates sheet).
 * That spreadsheet should contain only template rows.
 * Columns: No | Title | Templates
 * Title = email subject. Templates = email body.
 * Each send picks one Title at random and one Templates body at random.
 */
var TEMPLATES_URL = 'https://docs.google.com/spreadsheets/d/16D74xRpl5u4K2PKbxzh10PaqPwPmvFvdVYHmEMPeyJ4/edit?gid=315526240#gid=315526240';

/** Fallback subject if the Title column is empty. Placeholders: {{receiver}} {{sender}} */
var EMAIL_SUBJECT = 'Hi {{receiver}}';

/** How many emails this account sends per scheduled run. */
var EMAILS_PER_RUN = 1;

/**
 * YOUR NAME used for {{sender}} in the template. Required.
 * Example: 'Alex Rivera'   — do not put a Gmail address here.
 */
var SENDER_DISPLAY_NAME = 'William Lee';

/** Timezone for schedule math and the "sent" column. */
var TIMEZONE = Session.getScriptTimeZone() || 'America/New_York';

/**
 * First send of the day (local TIMEZONE), then every ANCHOR_EVERY_HOURS.
 * Example: 9 and 0 → 9:00, 11:00, 13:00, … (each ±10 minutes).
 */
var SEND_START_HOUR = 5;
var SEND_START_MINUTE = 0;
var ANCHOR_EVERY_HOURS = 2;
var JITTER_MINUTES = 10;     // ±10 minutes around each slot (20-minute window)

/**
 * Test mode — edit these, then run sendTestEmail() from the editor.
 * Body = Templates row whose No matches TEST_TEMPLATE_NO.
 * Subject = a random Title from the Title column (not tied to that row).
 * Does not touch the candidates sheet.
 */
var TEST_TEMPLATE_NO = 2;
var TEST_RECEIVER_NAME = 'Jack Li';
var TEST_RECEIVER_EMAIL = 'liyang7097@gmail.com';

/** Candidate tabs to skip (safety if a Templates tab was ever added to the candidates sheet). */
var SKIP_TABS_ = { Templates: true, templates: true };

// ─── Public entry points ───────────────────────────────────────────────────

/** Run once to grant Gmail + Sheets permissions. */
function authorizeOnce() {
  var opened = openCandidatesTab_();
  Logger.log('OK — spreadsheet: ' + opened.ss.getName());
  Logger.log('OK — tab: ' + opened.sheet.getName() + ' (gid=' + opened.sheet.getSheetId() + ')');
  var me = Session.getActiveUser().getEmail() || Session.getEffectiveUser().getEmail();
  Logger.log('Sender account: ' + me);
  Logger.log('Sender display name: ' + requireSenderName_());
  var copy = loadTemplates_();
  Logger.log('Active templates found: ' + copy.bodies.length);
  Logger.log('Active titles found: ' + copy.titles.length);
  if (!copy.bodies.length) {
    throw new Error(
      'No templates found. Set TEMPLATES_URL to the templates-only spreadsheet ' +
        '(columns: No | Title | Templates), share it with this Gmail as Editor, then re-run authorizeOnce().'
    );
  }
  if (!copy.titles.length) {
    Logger.log('WARNING: no Title column values — will fall back to EMAIL_SUBJECT.');
  }
  copy.titles.forEach(function (t, i) {
    Logger.log('  Title ' + (i + 1) + ': ' + t);
  });
  copy.bodies.forEach(function (t) {
    Logger.log('  No ' + t.no + ': ' + t.body.substring(0, 60).replace(/\n/g, ' ') + '…');
  });
  GmailApp.getAliases();
  Logger.log('Gmail access OK.');
  Logger.log(
    'Schedule: first slot ' + pad_(clampHour_(SEND_START_HOUR)) + ':' +
      pad_(clampMinute_(SEND_START_MINUTE)) +
      ', then every ' + (Number(ANCHOR_EVERY_HOURS) || 2) +
      'h (±' + JITTER_MINUTES + ' min).'
  );
  Logger.log('Next: optional sendTestEmail() (fill TEST_* first), then installSchedule().');
}

/**
 * Send one test email using TEST_TEMPLATE_NO + TEST_RECEIVER_NAME + TEST_RECEIVER_EMAIL.
 * Run this manually from the Apps Script editor after authorizeOnce().
 */
function sendTestEmail() {
  var to = String(TEST_RECEIVER_EMAIL || '').trim();
  if (!to || to.indexOf('@') === -1) {
    throw new Error('Set TEST_RECEIVER_EMAIL to the test recipient address.');
  }
  var fullName = String(TEST_RECEIVER_NAME || '').trim();
  if (!fullName) {
    throw new Error('Set TEST_RECEIVER_NAME to the receiver’s full name.');
  }

  var copy = loadTemplates_();
  if (!copy.bodies.length) {
    throw new Error('No templates found. Set TEMPLATES_URL and share that sheet as Editor.');
  }
  var tpl = findTemplateByNo_(copy.bodies, TEST_TEMPLATE_NO);
  if (!tpl) {
    throw new Error(
      'Template No ' + TEST_TEMPLATE_NO + ' not found. Check the No column in the templates sheet.'
    );
  }

  var meEmail = Session.getActiveUser().getEmail() || Session.getEffectiveUser().getEmail() || '';
  var meName = requireSenderName_();
  var receiverName = firstName_(fullName) || fullName;
  var ctx = { receiver: receiverName, sender: meName };
  var titleText = pickRandom_(copy.titles) || EMAIL_SUBJECT;
  var subject = String(render_(titleText, ctx) || '').replace(/\s+/g, ' ').trim();
  if (!subject) subject = render_(EMAIL_SUBJECT, ctx);
  var body = prepareEmailBody_(tpl.body, ctx);

  GmailApp.sendEmail(to, subject, body);
  Logger.log('Test email sent.');
  Logger.log('  Template No: ' + tpl.no);
  Logger.log('  From: ' + meEmail + ' (' + meName + ')');
  Logger.log('  To:   ' + to + ' (' + fullName + ')');
  Logger.log('  Subj: ' + subject);
  Logger.log('  Body preview:\n' + body.substring(0, 400) + (body.length > 400 ? '…' : ''));
  Logger.log('Next: run installSchedule() if this Gmail should send on the 2-hour schedule.');
  return { to: to, subject: subject, from: meEmail, sender_name: meName, template_no: tpl.no };
}

/** Install / refresh the time-driven trigger for the next jittered window. */
function installSchedule() {
  clearOutreachTriggers_();
  var when = nextFireTime_(new Date());
  ScriptApp.newTrigger('runOutreach')
    .timeBased()
    .at(when)
    .create();
  Logger.log('Next run scheduled for: ' + Utilities.formatDate(when, TIMEZONE, 'yyyy-MM-dd HH:mm:ss'));
  return when;
}

/**
 * Main job — claim + send + reschedule.
 * Also safe to run manually from the editor for a test send.
 */
function runOutreach() {
  var lock = LockService.getScriptLock();
  try {
    lock.waitLock(30000);
  } catch (e) {
    Logger.log('Could not get lock — another run in progress. Skipping.');
    scheduleAfter_(new Date());
    return;
  }

  var results = null;
  try {
    results = sendBatch_();
    Logger.log(JSON.stringify(results));
  } catch (err) {
    Logger.log('Outreach error: ' + err);
  } finally {
    try { lock.releaseLock(); } catch (e2) {}
    scheduleAfter_(new Date());
  }
}

/** Remove all outreach triggers (stop auto-sending). */
function uninstallSchedule() {
  clearOutreachTriggers_();
  Logger.log('Outreach triggers removed.');
}

// ─── Core send logic ───────────────────────────────────────────────────────

function sendBatch_() {
  var opened = openCandidatesTab_();
  var ss = opened.ss;
  var sheet = opened.sheet;
  var tabName = sheet.getName();
  var meEmail = Session.getActiveUser().getEmail() || Session.getEffectiveUser().getEmail();
  if (!meEmail) throw new Error('Cannot resolve sender Gmail address.');

  var meName = requireSenderName_();
  var copy = loadTemplates_();
  if (!copy.bodies.length) {
    throw new Error(
      'No templates found. Set TEMPLATES_URL to the templates-only spreadsheet ' +
        '(columns: No | Title | Templates). Do not point it at the candidates sheet.'
    );
  }
  if (!copy.titles.length) {
    Logger.log('WARNING: Title column is empty — using EMAIL_SUBJECT fallback.');
  }

  var sent = [];
  var failed = [];
  var skipped = 0;

  if (alreadySentThisSlot_()) {
    Logger.log('Already sent in this 2-hour slot — not sending another email.');
    return {
      sender_email: meEmail,
      sender_name: meName,
      tab: tabName,
      gid: sheet.getSheetId(),
      templates: copy.bodies.length,
      titles: copy.titles.length,
      sent: sent,
      failed: failed,
      skipped_claimed_or_empty: skipped,
      skipped_slot: true
    };
  }

  if (isSkippedTab_(tabName) || looksLikeTemplatesSheet_(sheet)) {
    throw new Error(
      'SPREADSHEET_URL points at tab "' + tabName + '", which looks like a templates sheet. ' +
        'Copy the URL of a candidates role tab instead.'
    );
  }

  var lastRow = sheet.getLastRow();
  if (lastRow < 2) {
    Logger.log(tabName + ': no profile rows.');
    return {
      sender_email: meEmail,
      sender_name: meName,
      tab: tabName,
      gid: sheet.getSheetId(),
      templates: copy.bodies.length,
      titles: copy.titles.length,
      sent: sent,
      failed: failed,
      skipped_claimed_or_empty: skipped
    };
  }

  var header = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  var idx = headerIndex_(header);
  if (idx.email < 0 || idx.sender < 0 || idx.sent < 0) {
    throw new Error(
      'Tab "' + tabName + '" is missing required headers (email, sender, sent).'
    );
  }

  var data = sheet.getRange(2, 1, lastRow - 1, header.length).getValues();

  for (var i = 0; i < data.length && sent.length < EMAILS_PER_RUN; i++) {
      var rowNum = i + 2;
      var row = data[i];
      var senderVal = String(row[idx.sender] || '').trim();
      var sentVal = String(row[idx.sent] || '').trim().toLowerCase();

      // Already finished (Sent / Failed).
      if (sentVal) {
        skipped += 1;
        continue;
      }

      var isMineInProgress =
        senderVal && senderVal.toLowerCase() === meEmail.toLowerCase();
      var isUnclaimed = !senderVal;

      // Claimed by another sender — leave it for that account.
      if (senderVal && !isMineInProgress) {
        skipped += 1;
        continue;
      }

      var gmails = gmailAddresses_(row[idx.email]);
      if (!gmails.length) {
        skipped += 1;
        Logger.log(tabName + ' row ' + rowNum + ': no usable email — skip.');
        continue;
      }

      if (isUnclaimed) {
        sheet.getRange(rowNum, idx.sender + 1).setValue(meEmail);
        SpreadsheetApp.flush();

        var claimedBy = String(sheet.getRange(rowNum, idx.sender + 1).getValue() || '').trim();
        if (claimedBy && claimedBy.toLowerCase() !== meEmail.toLowerCase()) {
          skipped += 1;
          continue;
        }
      } else {
        sheet.getRange(rowNum, idx.sender + 1).setValue(meEmail);
      }

      var receiverName = firstName_(String(row[idx.name] || '').trim()) || 'there';
      var tpl = pickRandom_(copy.bodies);
      var titleText = pickRandom_(copy.titles) || EMAIL_SUBJECT;
      var ctx = { receiver: receiverName, sender: meName };
      var subject = String(render_(titleText, ctx) || '').replace(/\s+/g, ' ').trim();
      if (!subject) subject = render_(EMAIL_SUBJECT, ctx);
      var body = prepareEmailBody_(tpl.body, ctx);

      var delivered = false;
      var lastErr = '';
      for (var a = 0; a < gmails.length; a++) {
        var nextAddr = gmails[a];
        try {
          GmailApp.sendEmail(nextAddr, subject, body);
          Logger.log('Random subject: ' + subject);
          markSentStatus_(sheet, rowNum, idx.sent + 1, 'Sent');
          markSlotSent_();
          delivered = true;
          sent.push({
            tab: tabName,
            row: rowNum,
            to: nextAddr,
            template_no: tpl.no,
            title: subject,
            at: 'Sent',
            sender_name: meName
          });
          break;
        } catch (sendErr) {
          lastErr = String(sendErr);
          Logger.log(
            'Send failed for ' + tabName + ' row ' + rowNum + ' to ' + nextAddr + ': ' + sendErr
          );
        }
      }

      if (!delivered) {
        markSentStatus_(sheet, rowNum, idx.sent + 1, 'Failed');
        failed.push({
          tab: tabName,
          row: rowNum,
          tried: gmails,
          reason: lastErr || 'all_emails_failed'
        });
        Logger.log(
          tabName + ' row ' + rowNum + ': all listed emails failed — skip to next profile.'
        );
      }
    }

  return {
    sender_email: meEmail,
    sender_name: meName,
    tab: tabName,
    gid: sheet.getSheetId(),
    templates: copy.bodies.length,
    titles: copy.titles.length,
    sent: sent,
    failed: failed,
    skipped_claimed_or_empty: skipped
  };
}

/**
 * Write the sent column status with color:
 *   "Sent"   → green
 *   "Failed" → red
 */
function markSentStatus_(sheet, rowNum, sentCol, status) {
  var raw = String(status || '').trim().toLowerCase();
  var value = raw === 'failed' ? 'Failed' : 'Sent';
  var range = sheet.getRange(rowNum, sentCol);
  range.setValue(value);
  range.setFontWeight('bold');
  range.setHorizontalAlignment('center');
  if (value === 'Failed') {
    range.setFontColor('#C62828');
    range.setBackground('#FFEBEE');
  } else {
    range.setFontColor('#2E7D32');
    range.setBackground('#E8F5E9');
  }
  SpreadsheetApp.flush();
}

var SLOT_PROP_ = 'outreach_slot_key';

function alreadySentThisSlot_() {
  var last = PropertiesService.getScriptProperties().getProperty(SLOT_PROP_) || '';
  return last === slotKey_(new Date());
}

function markSlotSent_() {
  PropertiesService.getScriptProperties().setProperty(SLOT_PROP_, slotKey_(new Date()));
}

/** Slot id for the nearest 2-hour anchor (e.g. 2026-08-19-07 for the 7:00 window). */
function slotKey_(date) {
  var p = localParts_(date);
  var minutes = p.H * 60 + p.mnt;
  var start = anchorStartMinutes_();
  var step = Math.max(1, Number(ANCHOR_EVERY_HOURS) || 2) * 60;
  var bestMins = start;
  var bestDist = 24 * 60;
  for (var mins = start; mins < 24 * 60; mins += step) {
    var dist = Math.abs(minutes - mins);
    if (dist < bestDist) {
      bestDist = dist;
      bestMins = mins;
    }
  }
  return p.y + '-' + pad_(p.m) + '-' + pad_(p.day) + '-' + pad_(bestMins);
}

// ─── Schedule helpers ──────────────────────────────────────────────────────

function scheduleAfter_(fromDate) {
  clearOutreachTriggers_();
  var when = nextFireTime_(fromDate);
  ScriptApp.newTrigger('runOutreach')
    .timeBased()
    .at(when)
    .create();
  Logger.log('Rescheduled next run: ' + Utilities.formatDate(when, TIMEZONE, 'yyyy-MM-dd HH:mm:ss'));
}

/** Schedule the next runOutreach soon (e.g. 2 minutes after a failed Gmail). */
function scheduleInMinutes_(minutes) {
  clearOutreachTriggers_();
  var mins = Math.max(1, Number(minutes) || 2);
  var when = new Date(new Date().getTime() + mins * 60 * 1000);
  ScriptApp.newTrigger('runOutreach')
    .timeBased()
    .at(when)
    .create();
  Logger.log(
    'Retry scheduled in ' + mins + ' min: ' +
      Utilities.formatDate(when, TIMEZONE, 'yyyy-MM-dd HH:mm:ss')
  );
  return when;
}

/**
 * Next fire time = next 2h slot after SEND_START_HOUR:SEND_START_MINUTE, plus random ±JITTER_MINUTES.
 * Example: start 9:00 → next is 11:00, fire somewhere in [10:50, 11:10].
 */
function nextFireTime_(from) {
  var now = from ? new Date(from.getTime()) : new Date();
  var local = localParts_(now);
  var start = anchorStartMinutes_();
  var step = Math.max(1, Number(ANCHOR_EVERY_HOURS) || 2) * 60;

  for (var dayOffset = 0; dayOffset < 3; dayOffset++) {
    var d = addDays_(local, dayOffset);
    for (var mins = start; mins < 24 * 60; mins += step) {
      var jitter = Math.floor(Math.random() * (2 * JITTER_MINUTES + 1)) - JITTER_MINUTES;
      var fire = makeLocalDate_(d.y, d.m, d.day, 0, mins + jitter);
      if (fire.getTime() > now.getTime() + 30 * 1000) {
        return fire;
      }
    }
  }

  var fallbackJitter = Math.floor(Math.random() * (2 * JITTER_MINUTES + 1)) - JITTER_MINUTES;
  return new Date(now.getTime() + (2 * 60 + fallbackJitter) * 60 * 1000);
}

function clampHour_(h) {
  h = Math.floor(Number(h));
  if (isNaN(h)) h = 9;
  return Math.max(0, Math.min(23, h));
}

function clampMinute_(m) {
  m = Math.floor(Number(m));
  if (isNaN(m)) m = 0;
  return Math.max(0, Math.min(59, m));
}

function anchorStartMinutes_() {
  return clampHour_(SEND_START_HOUR) * 60 + clampMinute_(SEND_START_MINUTE);
}

function localParts_(date) {
  var s = Utilities.formatDate(date, TIMEZONE, 'yyyy|M|d|H|m');
  var p = s.split('|');
  return {
    y: parseInt(p[0], 10),
    m: parseInt(p[1], 10),
    day: parseInt(p[2], 10),
    H: parseInt(p[3], 10),
    mnt: parseInt(p[4], 10)
  };
}

function addDays_(parts, n) {
  // Build noon local and add days to avoid DST edge issues.
  var noon = makeLocalDate_(parts.y, parts.m, parts.day, 12, 0);
  noon = new Date(noon.getTime() + n * 24 * 60 * 60 * 1000);
  var p = localParts_(noon);
  return { y: p.y, m: p.m, day: p.day };
}

/**
 * Build a Date for a local wall-clock time in TIMEZONE.
 * minutesOffset can be negative (e.g. hour=9, minutesOffset=-10 → 8:50).
 */
function makeLocalDate_(year, month, day, hour, minutesOffset) {
  minutesOffset = minutesOffset || 0;
  // Approximate with script timezone via formatted string parse.
  var totalMinutes = hour * 60 + minutesOffset;
  var dayAdj = 0;
  while (totalMinutes < 0) {
    totalMinutes += 24 * 60;
    dayAdj -= 1;
  }
  while (totalMinutes >= 24 * 60) {
    totalMinutes -= 24 * 60;
    dayAdj += 1;
  }
  var h = Math.floor(totalMinutes / 60);
  var m = totalMinutes % 60;

  var base = new Date(year, month - 1, day + dayAdj, h, m, 0);
  // Correct for TIMEZONE vs server timezone using a format round-trip.
  var want = pad_(year) + '-' + pad_(month) + '-' + pad_(day + dayAdj) +
    ' ' + pad_(h) + ':' + pad_(m) + ':00';
  // If dayAdj moved calendar day, recompute Y-M-D from a temp date.
  if (dayAdj !== 0) {
    var tmp = new Date(year, month - 1, day + dayAdj, 12, 0, 0);
    want = Utilities.formatDate(tmp, Session.getScriptTimeZone(), 'yyyy-MM-dd') +
      ' ' + pad_(h) + ':' + pad_(m) + ':00';
    // Prefer TIMEZONE formatting for the date part when possible.
    want = Utilities.formatDate(tmp, TIMEZONE, 'yyyy-MM-dd') +
      ' ' + pad_(h) + ':' + pad_(m) + ':00';
  } else {
    want = pad_(year) + '-' + pad_(month) + '-' + pad_(day) +
      ' ' + pad_(h) + ':' + pad_(m) + ':00';
  }

  // Convert "local wall time in TIMEZONE" → absolute Date via offset probe.
  return wallTimeToDate_(want, TIMEZONE);
}

function wallTimeToDate_(wall, tz) {
  // Binary-search a UTC Date whose formatted wall time in tz matches.
  // Start near "now" interpretation.
  var parts = wall.match(/(\d+)-(\d+)-(\d+) (\d+):(\d+):(\d+)/);
  if (!parts) return new Date();
  var guess = new Date(
    parseInt(parts[1], 10),
    parseInt(parts[2], 10) - 1,
    parseInt(parts[3], 10),
    parseInt(parts[4], 10),
    parseInt(parts[5], 10),
    parseInt(parts[6], 10)
  );

  for (var i = 0; i < 8; i++) {
    var formatted = Utilities.formatDate(guess, tz, 'yyyy-MM-dd HH:mm:ss');
    if (formatted === wall) return guess;
    var diffMs = parseWall_(wall) - parseWall_(formatted);
    guess = new Date(guess.getTime() + diffMs);
  }
  return guess;
}

function parseWall_(s) {
  var p = s.match(/(\d+)-(\d+)-(\d+) (\d+):(\d+):(\d+)/);
  return Date.UTC(
    parseInt(p[1], 10),
    parseInt(p[2], 10) - 1,
    parseInt(p[3], 10),
    parseInt(p[4], 10),
    parseInt(p[5], 10),
    parseInt(p[6], 10)
  );
}

function pad_(n) {
  n = Math.floor(n);
  return (n < 10 ? '0' : '') + n;
}

function clearOutreachTriggers_() {
  ScriptApp.getProjectTriggers().forEach(function (t) {
    if (t.getHandlerFunction() === 'runOutreach') {
      ScriptApp.deleteTrigger(t);
    }
  });
}

// ─── Sheet / template helpers ──────────────────────────────────────────────

function openCandidatesTab_() {
  return openSpreadsheetByUrl_(SPREADSHEET_URL, 'SPREADSHEET_URL', { requireGid: true });
}

/**
 * Parse spreadsheet id + gid from a full Google Sheets URL.
 * Tab URLs look like: .../edit#gid=123456  or  .../edit?gid=123456#gid=123456
 */
function parseSheetUrl_(urlOrId) {
  var raw = String(urlOrId || '').trim();
  var id = raw;
  var gid = null;

  var idMatch = raw.match(/\/spreadsheets\/d\/([a-zA-Z0-9-_]+)/);
  if (idMatch) id = idMatch[1];

  var gidMatch = raw.match(/[?#&]gid=([0-9]+)/);
  if (gidMatch) gid = parseInt(gidMatch[1], 10);

  return { id: id, gid: gid, raw: raw };
}

function openSpreadsheetByUrl_(urlOrId, label, opts) {
  opts = opts || {};
  var parsed = parseSheetUrl_(urlOrId);
  if (!parsed.id) {
    throw new Error('Set ' + label + ' at the top of EmailOutreach.gs to a full Google Sheets URL.');
  }

  var ss;
  try {
    ss = SpreadsheetApp.openById(parsed.id);
  } catch (e) {
    throw new Error(
      'Cannot open spreadsheet (' + label + '). Share it with this Gmail account as Editor. ' + e
    );
  }

  var needGid = !!opts.requireGid || (parsed.gid !== null && !isNaN(parsed.gid));
  if (opts.requireGid && (parsed.gid === null || isNaN(parsed.gid))) {
    throw new Error(
      label + ' must be the full URL of the tab you want, including gid. ' +
        'Open that tab in the browser and copy the address bar URL (it contains gid=…).'
    );
  }

  var sheet = null;
  if (parsed.gid !== null && !isNaN(parsed.gid)) {
    sheet = getSheetByGid_(ss, parsed.gid);
    if (!sheet) {
      throw new Error(
        'No tab in this spreadsheet matches gid=' + parsed.gid + ' from ' + label + '.'
      );
    }
  }

  if (needGid && !sheet) {
    throw new Error('Could not find the tab for ' + label + ' (missing or invalid gid).');
  }

  return { ss: ss, sheet: sheet, gid: parsed.gid, url: parsed.raw };
}

function getSheetByGid_(ss, gid) {
  var sheets = ss.getSheets();
  for (var i = 0; i < sheets.length; i++) {
    if (sheets[i].getSheetId() === gid) return sheets[i];
  }
  return null;
}

function headerIndex_(header) {
  function find(name) {
    for (var i = 0; i < header.length; i++) {
      if (String(header[i]).trim() === name) return i;
    }
    return -1;
  }
  return {
    name: find('name'),
    email: find('email'),
    sender: find('sender'),
    sent: find('sent')
  };
}

function isGmailAddress_(addr) {
  var a = String(addr || '').trim().toLowerCase();
  if (a.indexOf('@') === -1) return false;
  var domain = a.split('@').pop();
  return domain === 'gmail.com' || domain === 'googlemail.com';
}

function gmailAddresses_(value) {
  var parts = String(value || '').split(/[\n;,]+/);
  var out = [];
  for (var i = 0; i < parts.length; i++) {
    var a = parts[i].trim();
    if (isGmailAddress_(a)) out.push(a);
  }
  return out;
}

function isSkippedTab_(tabName) {
  return !!SKIP_TABS_[String(tabName || '').trim()];
}

function looksLikeCandidateHeader_(header) {
  var h0 = String(header[0] || '').trim().toLowerCase();
  var h1 = String(header[1] || '').trim().toLowerCase();
  var h2 = String(header[2] || '').trim().toLowerCase();
  return h0 === 'photo' || (h1 === 'name' && h2 === 'email');
}

function looksLikeTemplatesSheet_(sheet) {
  if (!sheet) return false;
  if (isSkippedTab_(sheet.getName())) return true;
  var lastCol = sheet.getLastColumn();
  if (lastCol < 1) return false;
  var header = sheet.getRange(1, 1, 1, lastCol).getValues()[0];
  if (looksLikeCandidateHeader_(header)) return false;
  for (var c = 0; c < header.length; c++) {
    var h = String(header[c] || '').trim().toLowerCase();
    if (h === 'templates' || h === 'template' || h === 'body' || h === 'text') return true;
    if (h === 'title' || h === 'titles' || h === 'subject' || h === 'subjects') return true;
  }
  return false;
}

/**
 * Load copy from TEMPLATES_URL (templates-only spreadsheet).
 * Columns: No | Title | Templates
 * Returns { bodies: [{no, body}], titles: [string, ...] }.
 * Title and Templates are independent lists (empty cells are skipped).
 */
function loadTemplates_() {
  var url = String(TEMPLATES_URL || '').trim();
  if (!url) return { bodies: [], titles: [] };

  var opened = openSpreadsheetByUrl_(url, 'TEMPLATES_URL');
  var ss = opened.ss;
  if (!ss) return { bodies: [], titles: [] };

  if (opened.sheet) {
    return readTemplatesFromSheet_(opened.sheet);
  }

  var tried = {};
  var all = ss.getSheets();
  for (var s = 0; s < all.length; s++) {
    var sheet = all[s];
    var id = sheet.getSheetId();
    if (tried[id]) continue;
    tried[id] = true;
    var loaded = readTemplatesFromSheet_(sheet);
    if (loaded.bodies.length || loaded.titles.length) return loaded;
  }
  return { bodies: [], titles: [] };
}

function readTemplatesFromSheet_(sheet) {
  var empty = { bodies: [], titles: [] };
  if (!sheet) return empty;
  var lastRow = sheet.getLastRow();
  var lastCol = sheet.getLastColumn();
  if (lastRow < 2 || lastCol < 1) return empty;

  var header = sheet.getRange(1, 1, 1, lastCol).getValues()[0];
  if (looksLikeCandidateHeader_(header)) return empty;

  var noIdx = -1;
  var tplIdx = -1;
  var titleIdx = -1;
  for (var c = 0; c < header.length; c++) {
    var h = String(header[c] || '').trim().toLowerCase();
    if (h === 'no' || h === 'number' || h === '#' || h === 'id') noIdx = c;
    else if (h === 'title' || h === 'titles' || h === 'subject' || h === 'subjects') titleIdx = c;
    else if (h === 'templates' || h === 'template' || h === 'body' || h === 'text') tplIdx = c;
  }
  if (tplIdx < 0) {
    // Fallback: No | Title | Templates  or  No | Templates
    if (lastCol >= 3 && titleIdx < 0) {
      noIdx = noIdx >= 0 ? noIdx : 0;
      titleIdx = 1;
      tplIdx = 2;
    } else if (lastCol >= 2) {
      noIdx = noIdx >= 0 ? noIdx : 0;
      tplIdx = titleIdx === 1 ? 2 : 1;
    } else {
      tplIdx = 0;
    }
  }

  var rows = sheet.getRange(2, 1, lastRow - 1, lastCol).getValues();
  var bodies = [];
  var titles = [];
  for (var i = 0; i < rows.length; i++) {
    var body = String(rows[i][tplIdx] || '').trim();
    if (body) {
      var no = noIdx >= 0 ? String(rows[i][noIdx] || '').trim() : String(i + 1);
      if (!no) no = String(i + 1);
      var rowTitle = titleIdx >= 0 ? String(rows[i][titleIdx] || '').trim() : '';
      bodies.push({ no: no, body: body, title: rowTitle });
    }
    if (titleIdx >= 0) {
      var title = String(rows[i][titleIdx] || '').trim();
      if (title) titles.push(title);
    }
  }
  return { bodies: bodies, titles: titles };
}

function pickRandom_(arr) {
  if (!arr || !arr.length) return null;
  return arr[Math.floor(Math.random() * arr.length)];
}

function findTemplateByNo_(bodies, no) {
  var want = String(no || '').trim();
  if (!want) return null;
  for (var i = 0; i < (bodies || []).length; i++) {
    if (String(bodies[i].no || '').trim() === want) return bodies[i];
  }
  return null;
}

/**
 * Run once to write sample rows into the templates-only spreadsheet (TEMPLATES_URL).
 * Does nothing if that sheet already has template text.
 */
function seedEmailTemplates() {
  var url = String(TEMPLATES_URL || '').trim();
  if (!url) {
    throw new Error('Set TEMPLATES_URL to the templates-only spreadsheet first.');
  }
  var opened = openSpreadsheetByUrl_(url, 'TEMPLATES_URL', { requireGid: true });
  var sheet = opened.sheet;
  if (!sheet) {
    throw new Error('TEMPLATES_URL must include gid= of the templates tab. Copy that tab’s full URL.');
  }
  if (looksLikeCandidateHeader_(sheet.getRange(1, 1, 1, Math.max(sheet.getLastColumn(), 1)).getValues()[0])) {
    throw new Error(
      'TEMPLATES_URL points at a candidates sheet (photo/name/email). ' +
        'Use a separate spreadsheet that only has template rows.'
    );
  }

  var existing = readTemplatesFromSheet_(sheet);
  if (existing.bodies.length) {
    Logger.log('Templates already present (' + existing.bodies.length + '). Not overwriting.');
    return existing.bodies.length;
  }

  sheet.clear();
  sheet.getRange(1, 1, 1, 3).setValues([['No', 'Title', 'Templates']]);
  sheet.getRange(1, 1, 1, 3)
    .setBackground('#1F4E78')
    .setFontColor('#FFFFFF')
    .setFontWeight('bold');

  var samples = [
    [
      1,
      'Hi {{receiver}}',
      'Hi {{receiver}},\n\n' +
        'I hope you\'re doing well. I wanted to reach out and introduce myself.\n\n' +
        'Would you be open to a quick chat sometime?\n\n' +
        'Best regards,\n{{sender}}'
    ],
    [
      2,
      'Great to connect, {{receiver}}',
      'Hello {{receiver}},\n\n' +
        'I came across your profile and thought it would be great to connect.\n\n' +
        'Looking forward to hearing from you.\n\n' +
        '{{sender}}'
    ],
    [
      3,
      'A quick note from {{sender}}',
      'Hi {{receiver}},\n\n' +
        'Just a short note to say hello and see if you might be open to connecting.\n\n' +
        'Thanks,\n{{sender}}'
    ]
  ];
  sheet.getRange(2, 1, samples.length, 3).setValues(samples);
  sheet.setColumnWidth(1, 60);
  sheet.setColumnWidth(2, 280);
  sheet.setColumnWidth(3, 520);
  sheet.setWrap(true);
  Logger.log('Seeded ' + samples.length + ' templates in: ' + opened.ss.getName());
  return samples.length;
}

function firstName_(fullName) {
  var n = String(fullName || '').trim();
  if (!n) return '';
  return n.split(/\s+/)[0];
}

function requireSenderName_() {
  var name = String(SENDER_DISPLAY_NAME || '').trim();
  if (!name) {
    throw new Error(
      'Set SENDER_DISPLAY_NAME at the top of this file to your real name (not a Gmail address), then run again.'
    );
  }
  if (name.indexOf('@') !== -1) {
    throw new Error(
      'SENDER_DISPLAY_NAME looks like an email. Put a person’s name there, e.g. Alex Rivera.'
    );
  }
  return name;
}

/** Placeholders: {{receiver}} and {{sender}} only. */
function render_(template, ctx) {
  return String(template || '')
    .replace(/\{\{receiver\}\}/gi, ctx.receiver || '')
    .replace(/\{\{sender\}\}/gi, ctx.sender || '');
}

/**
 * Build the email body from a sheet template:
 * - Join accidental wraps (real line breaks with no \n token) using a single space
 * - Turn typed \n tokens into line breaks
 * - Do not add any other breaks, spaces, or HTML
 * - Replace {{receiver}} and {{sender}}
 */
function prepareEmailBody_(template, ctx) {
  var text = String(template || '');
  text = text.replace(/\r\n/g, '\n').replace(/\r/g, '\n');
  text = text.split('\n').join(' ');
  text = text.replace(/\\n/g, '\n');
  return render_(text, ctx);
}
