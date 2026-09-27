# Local REST API

Use `X-API-Key: <N8N_API_TOKEN>` for automation. Browser calls use the login cookie and `X-CSRF-Token` for POSTs. All routes except `/health`, `/login`, static assets and signed unsubscribe require authentication. Secrets are never included in state responses.

| Method / route | Purpose |
|---|---|
| GET /health | Liveness only |
| GET /api/state | Recent runs, stats, key status, integration readiness and template |
| POST /api/runs | Create run with config; optional Idempotency-Key header or request_key body |
| GET /api/runs/ID | Lead records, evidence, emails and last 200 logs |
| POST /api/tick | Process one stage and at most one eligible email; busy if lock held |
| POST /api/runs/ID/resume | Resume a failed stage; uncertain starts need attach |
| POST /api/runs/ID/attach | Attach actor_run and key_id after checking an uncertain Apify start |
| POST /api/runs/ID/import | Import raw dataset as items array before scraping; max 1500 records / 4 MiB |
| POST /api/leads/ID/review | Body: research object and approve boolean |
| GET /api/leads/ID/grounding | Sandboxed Search Suggestions HTML |
| POST /api/template | Save subject, body, fallback, daily_limit, delay_seconds, batch_size |
| POST /api/runs/ID/drafts | Create idempotent email previews for qualified leads |
| POST /api/runs/ID/queue | Queue next batch; confirm_live:true required if live |
| POST /api/keys/reset | Reset a recovered key by its nonsecret id |
| POST /api/suppress | Suppress a business email address |
| GET /api/runs/ID/export.csv | All leads; add ?qualified=true for qualified only |
| POST /api/logout | End browser session |

Config example:

```json
{"niche":"Dentist","location":"Karachi, Pakistan","lead_count":10,"min_rating":2,"min_reviews":30,"active_days":30,"mode":"demo","sync_sheets":false,"required_fields":["email"],"model":"","research_prompt":"Prioritize public business contacts."}
```

Required fields supported: email, decision_name, phone, address. Other collected fields are optional. No website filter toggle can admit existing/broken/unknown websites to final qualification.

Run statuses: queued, running, complete, failed, start_unknown. Complete means automatic processing is complete; it can still have candidates awaiting review. Stages: scrape, poll, dataset, initial, research, qualified_sheet.

Lead statuses: initial, rejected, research_pending, review, qualified.

Email statuses: draft, pending, sending, sent, simulated, failed, unknown, blocked. Retry count, timestamp and redacted failure type are stored per message. `sent` means SMTP accepted it, not that the recipient opened/received it in the inbox.

PowerShell API example (use your token privately; do not paste it into shared screenshots):

```powershell
$headers = @{ 'X-API-Key' = 'YOUR_N8N_API_TOKEN' }
$body = @{ niche='Dentist'; location='Karachi, Pakistan'; mode='demo'; lead_count=5 } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/runs -Headers $headers -ContentType application/json -Body $body
```
