# v2 architecture

The source is based on the supplied v1 project, with new orchestration gates and local Excel exports. SQLite remains the source of truth. Excel is a generated projection, not an editable input database; changes made manually to an exported workbook are not imported back.

- app.py: authenticated Flask routes, CSRF, sessions, exports and legacy APIs.
- run.py: starts the app and worker in one process for simpler local use.
- pipeline.py: scrape/poll/dataset/filter stages, then awaiting_research, explicit research, review and completion.
- vault.py: UI setting validation, encrypted configuration with Fernet; master key at data/vault.key.
- contacts.py: verified owner/business recipient policies and same-address deduplication.
- excel.py: automatic per-discovery workbooks and on-demand download. Text cells are forced to string type to prevent formulas from provider/user input.
- outreach.py: immutable previews, individual sends, global pacing, suppression and SMTP ambiguity handling.
- inbox.py: read-only IMAP sync, checkpoints, thread matching, unassigned messages, conversation replies and demo chat.
- mail_transport.py: TLS SMTP login and correctly threaded email construction.
- web_v2.py: connection forms, research start, friendly review forms, workbook downloads and inbox endpoints.

## Persistence

Existing v1 tables remain. The migration rebuilds emails with business+recipient+mode and recipient+mode unique constraints. It adds recipient_kind and account_id, an integrations table for encrypted settings, messages for incoming/chat replies and mailbox_state for IMAP UID checkpoints. Every query uses bound data values; dynamic table/column names in migrations are internal constants.

Outgoing initial messages and replies reserve a sending state before SMTP. A crash/uncertain acceptance becomes unknown and is not automatically retried. Pre-send connection/auth errors are retried with backoff. SMTP cannot provide universal exactly-once delivery; this conservative behavior prefers avoiding duplicate mail over guaranteed delivery. Explicit chat replies are intentional new messages, not automatic follow-ups.

Account fingerprints bind queued messages and conversations to the original SMTP host/user/from identity. Changing an app password does not change that identity. Changing SMTP identity blocks old live queue records rather than sending from an unintended account. Migrated v1 emails lack this verified binding and are not automatically adopted.

## Processing and Excel

The OS lock serializes worker ticks and critical mutations across processes on one machine. Short SQLite transactions avoid holding a database write transaction during provider calls. UI changes can return 409 while a stage is working; retry shortly. A tick processes one pipeline step, at most one conversation delivery followed by one outreach delivery if pacing allows (conversation replies have priority), optional inbox sync and dirty Excel projections.

Automatic Excel files are written atomically under data/exports. If an open Excel application locks the destination, the previous file is retained and the UI shows an export error until retry succeeds. Download Excel generates a fresh workbook from a consistent database snapshot.

## Security and scope

Same-origin scripts and CSRF remain. Incoming email HTML is never rendered; links and email contents are untrusted text. Credentials are encrypted at rest but require OS protection because the decryption key lives on the same machine. The authenticated operator can configure external service hosts; do not grant operator credentials to untrusted users.

Single host/operator only. No OAuth, attachment viewer, automatic public deployment, bounce-webhook processor, universal open tracking, or guaranteed reply detection. No need for Sheets URLs. The legacy Sheets adapter remains only for historical compatibility tests, not the v2 pipeline.
