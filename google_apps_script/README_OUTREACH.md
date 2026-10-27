# Gmail outreach — two spreadsheets

Keep candidates and templates in **separate** Google Sheets.

```
Scraper  →  candidates sheet (role tabs: photo, name, email, sender, sent, …)
                ↑
Sender Gmail Apps Script (EmailOutreach.gs) reads unsent rows, claims sender, sends mail
                ↑
            templates sheet (ONLY: No | Title | Templates)
```

## Config in EmailOutreach.gs (fill these)

```javascript
var SPREADSHEET_URL      = 'https://docs.google.com/spreadsheets/d/.../edit?gid=...#gid=...'; // candidates TAB URL
var TEMPLATES_URL        = 'https://docs.google.com/spreadsheets/d/.../edit'; // templates only
var SENDER_DISPLAY_NAME  = 'Alex Rivera'; // required — your name in the email, not a Gmail address
var SEND_START_HOUR      = 9;  // first send of the day (local time)
var SEND_START_MINUTE    = 0;  // then every 2 hours, ±10 minutes
```

Optional test send:

```javascript
var TEST_TEMPLATE_NO    = 1;
var TEST_RECEIVER_NAME  = 'Jane Doe';
var TEST_RECEIVER_EMAIL = 'jane@gmail.com';
```

Do **not** point `TEMPLATES_URL` at the candidates spreadsheet. Do **not** deploy this script as a web app.

## Templates sheet layout

That spreadsheet should contain **only** template rows (no profile data).

| No | Title | Templates |
|----|-------|-----------|
| 1  | Hi {{receiver}} | Hi {{receiver}}, … {{sender}} |
| 2  | Great to connect | Hello {{receiver}}, … |

Each send picks **one Title at random** (email subject) and **one Templates body at random**. They do not have to be from the same row.

The body uses only typed `\n` in the Templates cell as line breaks (`{{receiver}}` / `{{sender}}` are replaced). Accidental wrapping in the cell is joined with a space.

**Placeholders:** `{{receiver}}` (first name) · `{{sender}}` (`SENDER_DISPLAY_NAME`)

Example cell (sent as-is after placeholders):

```
Hi {{receiver}}, I hope you're doing well. I came across your profile and wanted to reach out. I'd love to connect and learn more about your work. Would you be open to a short chat sometime? Best regards, {{sender}}
```

## Sample template (paste into the Templates column)

```
Hi {{receiver}},

I hope you're doing well. I wanted to reach out and introduce myself.

Would you be open to a quick chat sometime?

Best regards,
{{sender}}
```

More samples: set `TEMPLATES_URL`, then run `seedEmailTemplates` in that sender project (skips if rows already exist).

## Multiple Gmails on one profile

1. Try addresses on that profile **in order** (same 2-hour slot until one succeeds).
2. If **all** listed addresses fail → write **Failed** (red) and go to the **next** profile.
3. If there is **no** usable email → skip that profile (do not write Failed).
4. On success → write **Sent** (green).
5. **sender** column = this Gmail address after each attempt.
6. At most **one successful email per 2-hour slot**.

## Sample email template

Paste into the **Templates** column (use `{{receiver}}` and `{{sender}}`):

```
Hi {{receiver}},

I hope you're doing well. I came across your profile and wanted to reach out.

I'd love to connect and learn more about your work — would you be open to a short chat sometime?

Best regards,
{{sender}}
```

Subject line: paste into the **Title** column (same placeholders). `EMAIL_SUBJECT` is only used if Title is empty.

## Install (each sender)

Do **not** use Deploy → Web app.

1. Share the **candidates** sheet and the **templates** sheet with that Gmail as **Editor**.
2. https://script.google.com → **New project** → paste `EmailOutreach.gs` → Save.
3. Fill in at the top of the file:
   - `SPREADSHEET_URL` (full URL of the **role tab**, including `gid=`)
   - `TEMPLATES_URL`
   - `SENDER_DISPLAY_NAME` (real name, e.g. `Alex Rivera`)
4. Run **`authorizeOnce`** (approve Gmail + Sheets).
5. Optional test: set `TEST_TEMPLATE_NO`, `TEST_RECEIVER_NAME`, `TEST_RECEIVER_EMAIL` → run **`sendTestEmail`**.
6. Run **`installSchedule`**. Mail then goes out every ~2 hours even if the PC is off.

Stop later: run **`uninstallSchedule`**.

Logs after a browser restart: Apps Script left sidebar → **Executions**.

### Test email

`sendTestEmail()` sends **one** message using that template **No** (same-row Title + body). It does **not** touch the candidates sheet.
