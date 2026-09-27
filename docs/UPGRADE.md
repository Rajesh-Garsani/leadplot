# Upgrade from LeadPilot v1 without losing data

1. Stop the old app.py and worker.py terminals. Pause your n8n schedule.
2. Make a backup of the old `.env`, complete `data/` folder and any credentials folder. Do not copy a live SQLite WAL file by itself while the application is running.
3. Extract the updated ZIP to a new folder. Open its inner `leadpilot` directory in PyCharm.
4. Copy your old `.env` and complete `data/` folder into that directory. The ZIP contains no production database or passwords, so do not replace your old data with an empty file.
5. Create a fresh virtual environment in the new folder, or select a compatible existing one. Install `requirements-lock.txt` to add openpyxl and the updated dependencies.
6. Run `setup_local.py`. It preserves an existing .env.
7. Start `run.py`. It starts the app and worker together and upgrades the database schema in place. Do not also launch the old worker against the same data.
8. Sign in using your existing password. Open Connections and enter/verify your integrations. Existing .env credentials remain fallbacks until replaced from the UI. Google Sheets settings are no longer required or used by the v2 pipeline.
9. Check saved discovery history and email counts before starting new work. Test a new Demo discovery through all three steps.

## Important compatibility notes

- Saved leads and first-email history retain their IDs and statuses. Migration changes the old one-email-per-business constraint so you may now email owner and business separately, while preserving recipient deduplication.
- Old live send records have no reliable sender-account identity. They remain visible, but v2 will not silently assign them to your newly configured sender or auto-match replies. Inbox automation is designed for emails created with a v2 connection. Old queued live messages are blocked if their account cannot be verified. Review them before any action; do not delete sent/unknown history to force a resend.
- Draft/blocked previews can be rebuilt with the new sender settings. Queued/sent/failed/unknown records remain unchanged.
- Old criteria remain attached to existing discoveries. New v2 discoveries accept a verified owner or business email by default. A v1 discovery that required the business email still retains that requirement; create a new discovery if you want new criteria.
- New discoveries stop after scraping at awaiting_research. Click Step 2 to start research. Completed old discoveries are not automatically re-researched.
- `data/vault.key` is created when UI credentials are first saved. Back it up together with the database. The encryption key is needed to decrypt credentials on another machine.
- Reverting to the old v1 code against an upgraded database is not supported. To roll back, stop v2 and restore your untouched pre-upgrade backup into the old project folder.

## Files changed or added

Changed: app.py, database migrations, rules, pipeline, providers, outreach, dashboard HTML/JS/CSS, requirements, launch scripts, default configuration and n8n integration notes.

Added: run.py, leadpilot/vault.py, contacts.py, excel.py, inbox.py, mail_transport.py, web_v2.py and v2 tests.

No external emails are sent simply by upgrading. However, saved pending work resumes when a worker runs, subject to sender/account and qualification checks. Inspect or stop your old work before upgrading if you do not want processing to resume.
