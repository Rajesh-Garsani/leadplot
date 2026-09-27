# v2 API and optional n8n

Automation uses X-API-Key: N8N_API_TOKEN. Browser mutations use a session cookie plus CSRF header. n8n/leadpilot-integrated.json remains importable as an entry form/webhook and schedule; assign header credentials using the generated .env token. Local run.py already contains the worker, so n8n is optional.

The n8n integrated workflow now creates manual_research discoveries. After scraping, use Step 2 in the dashboard or POST the research endpoint. Credentials for Apify/Gemini live in the backend UI and do not flow through n8n items. The original sanitized workflow is retained as a historical reference.

| Route | Purpose |
|---|---|
| GET/POST /api/connections | Nonsecret state / save encrypted integration fields |
| POST /api/connections/test/apify | Read-only account access tests for saved keys |
| POST /api/connections/test/gemini | Read-only API key access test |
| POST /api/connections/test/smtp | TLS login test; no email sent |
| POST /api/connections/test/imap | TLS mailbox login test |
| POST /api/runs | Create discovery; sync_sheets is forced off in v2 |
| POST /api/runs/ID/research | Start per-lead research with prompt and optional model |
| GET /api/runs/ID/export.xlsx | Current workbook with five tabs |
| POST /api/leads/ID/form-review | Normal UI fields + evidence URLs + verification flags |
| POST /api/runs/ID/drafts | Create individual recipient previews |
| POST /api/runs/ID/reset-drafts | Remove only draft/blocked previews, preserving actual sends |
| POST /api/runs/ID/queue | Queue next batch; confirm_live required for live mode |
| GET /api/inbox | Conversations, matched reply counts and unassigned messages |
| GET /api/inbox/ID | Initial outgoing email plus message timeline |
| POST /api/inbox/sync | Request background mailbox sync |
| POST /api/inbox/ID/reply | body, unique request_key, confirm_live if live |
| POST /api/inbox/ID/demo-reply | Synthetic inbound message on a simulated demo thread |
| POST /api/inbox/unmatched/ID/link | Explicitly link to root_id with same sender/account |

Recipient policies: prefer_owner, prefer_business, owner_only, business_only, both. Default required_fields is contact_email (at least one verified owner or business email). Both must have independently checked sources if both are to receive outreach. Manual review remains required for live findings.

Additional v1 read/log/export/recovery routes remain in app.py. Obsolete v1 docs are under docs/legacy-v1; they describe the old Google Sheets setup, not this release.
