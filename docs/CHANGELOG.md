# v2 changes

- Removed required Google Sheets setup from the active pipeline and dashboard.
- Added automatic Excel generation and Download Excel.
- Added encrypted UI connections for Apify, Gemini, SMTP and IMAP with read-only/login tests.
- Separated scraping and research into two explicit steps.
- Added normal research-review fields instead of requiring JSON edits.
- Added owner/business recipient selection, same-address deduplication and separate individual sends.
- Added rebuild action for unsent draft/blocked previews.
- Added inbox sync, matched reply badges, unassigned incoming-message review and email conversation replies.
- Added synthetic demo incoming messages and local simulated replies.
- Added sender-account binding and durable reply queues with ambiguous-send protection.
- Added one-command run.py launcher with an integrated worker.
- Added automatic database migration, upgrade instructions and regression tests.

Known limits: single-host/operator, password/app-password mail only (no OAuth), newest 100 messages on first inbox sync, 2 MB message limit, no attachments, no instant chat guarantee. Local Excel edits are not imported. Website/contact evidence still requires operator verification before outreach.
