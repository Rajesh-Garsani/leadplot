# Troubleshooting and live smoke test

## Common issues

- **Page does not open:** run app.py, check the terminal and use 127.0.0.1:8000. If the port is occupied, change PORT in .env and update n8n URLs too.
- **No processing:** keep worker.py open or activate the n8n schedule. “Process next step” advances one stage. Demo runs need several ticks. A recent poll can wait ten seconds; retryable failures wait longer.
- **Worker busy / HTTP 409:** another tick holds the process lock; wait and repeat the dashboard action. Do not delete the database.
- **Login fails:** use ADMIN_PASSWORD from your .env. After ten failed logins wait ten minutes. Setup never overwrites an existing password.
- **Missing requirements:** `python -m pip install -r requirements-lock.txt`; include `-r`. Select the project virtual environment.
- **Permission error on .env:** keep your project in a folder writable by your account. A fresh setup uses restricted file permissions where supported.
- **Apify unavailable:** check balance, account permission and actor access. Key status is shown under Integrations. After fixing an account reset its key and resume the failed stage.
- **Apify uncertain start:** inspect your Apify runs. Attach the accepted run ID/key in Recovery. Do not simply repeat a possibly accepted paid actor launch.
- **Gemini 400/404:** verify the exact model name and that it supports Google Search with generateContent. Select a supported model via the per-run override. Model availability can change.
- **Gemini 429:** wait for quota recovery, then resume. The pipeline pauses after three failures and preserves earlier leads.
- **No grounded sources / invalid JSON:** retry the failed stage; if no search evidence exists the website finding remains unknown. Never approve made-up sources.
- **Zero qualified leads:** strict review dates, website discovery, required contacts, or niche/location matching can reject candidates. Inspect reasons. A missing Maps website field alone never qualifies a live record.
- **Sheet HTTP 403:** enable Sheets API and share both documents with the service account as Editor.
- **Sheet HTTP 400:** confirm the Leads tab exists and A:X plus sufficient rows are available. Two spreadsheet IDs must refer to separate dedicated documents.
- **Email previews absent:** select a completed discovery with qualified leads and verified email. Review missing fields; the same business/recipient may already have a preview in another run.
- **Nothing in inbox:** demo/dry-run writes data/outbox .eml files. For SMTP inspect sent/failed/unknown; sent means provider acceptance. Check provider sender verification and delivery events separately.
- **Unknown email:** inspect the provider's log and saved Message-ID. Never delete/recreate the send record just to retry. This package intentionally does not auto-resend uncertain deliveries.
- **n8n cannot reach backend:** localhost means the n8n host/container. See N8N.md for Windows/WSL/Docker addressing.
- **database locked:** ensure all processes use the same local data path and worker lock; avoid network drives and external writes. This implementation serializes pipeline work and uses short transactions with WAL. Back up then investigate competing programs; do not delete the database to recover.

## Small live smoke test

1. Keep EMAIL_PROVIDER=dry_run. Configure Apify and Gemini.
2. Create a live run with target 3, and inspect the saved actor run ID in the API/Apify console.
3. Restart worker mid-poll and confirm the same actor ID is reused.
4. Verify initial records, research evidence and exclusion reasons.
5. Configure the two Sheets, create a fresh run with sync enabled, confirm header/row writes.
6. Verify and approve one real lead. Confirm its qualified Sheet row appears.
7. Create previews, inspect tokens and fallback names. Queue a test batch and inspect .eml files.
8. Recreate previews/restart worker and confirm no duplicate send records.
9. Configure live SMTP with a verified sender and reachable unsubscribe link. Use your own public test business address for the first real delivery, then check suppression before real outreach.

Do not label these external smoke checks complete until you run them with your accounts. No live credentials are included in the package.

## Tests

From the project root with requirements installed:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The tests use temporary databases and mocked external services. They do not scrape businesses, modify real Sheets or send real emails.
