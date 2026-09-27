# LeadPilot v2 verification

55 automated unittest cases passed on Python 3.12/Linux, including:

- v1 migration preserves IDs, send history and adds multiple-recipient support;
- credentials encrypted in SQLite, secrets redacted from APIs, missing vault key fails closed;
- scrape stage pauses until explicit research click; prompt persists;
- owner-first/business-first/both recipient selection and equal-address dedup;
- Excel tabs, requested column names, formula-safe text and downloadable XLSX;
- normal form-based review and qualification guards;
- IMAP selects read-only, uses UID checkpoints and BODY.PEEK;
- unrelated sender mail is ignored; unmatched messages stay unassigned;
- known automatic replies do not count as human replies;
- reply thread headers, idempotency, sender-account binding and suppression;
- uncertain SMTP outcomes are not automatically retried;
- demo conversation messages stay local.

A headless Chromium 134 desktop/mobile flow also passed with no page JavaScript errors and no horizontal page overflow at 390px. It exercised UI credential save, demo scraping, explicit research, friendly evidence approval, four separate owner/business previews, XLSX download, queueing, synthetic incoming reply and chat composer. Screenshots were visually inspected. The app's CSP remained enabled during the browser flow.

The standalone Excel download was opened with openpyxl in tests; cell values, tab names and string types were checked. No real Apify/Gemini calls, Sheet writes, SMTP sends or IMAP account access were performed. External responses were mocked. Windows execution and n8n runtime/import remain unverified here.

Repeat the suite using `python -m unittest discover -s tests -v` after installing the locked dependencies. Run a small live smoke test with your own accounts before operational use.
