# n8n integration and mapping to your supplied workflow

## Import and configure

Use an existing n8n installation. On Windows n8n can run in WSL or another supported host; the Python app itself does not need Docker. Follow your n8n version's official installation instructions. Import `n8n/leadpilot-integrated.json` using n8n's **Import from file** action.

1. Create an **HTTP Header Auth** credential: Name `X-API-Key`, Value equal to `N8N_API_TOKEN` from your Python `.env`.
2. Assign that credential to **Create saved discovery** and **Process next saved stages**. Credentials are deliberately not embedded in the JSON.
3. Protect **Authenticated discovery webhook** using a Header Auth credential as well. It may use the same secret or a separate inbound webhook secret.
4. Assign an **HTTP Basic Auth** credential to **On form submission**. Choose a private username and password for opening the form.
5. Both HTTP Request node URLs default to `http://127.0.0.1:8000`. Change both if n8n runs elsewhere.
6. Save and publish/activate the workflow. Use its Production Form URL or Production Webhook URL. Test URLs only listen while n8n is waiting for a test execution.
7. Submit `Niche`, `Location`, `LeadCount`, `ActivityWindow` (integer days), and `Mode` (`demo` or `live`). Blank mode defaults to demo.
8. Open the Python dashboard to review progress, evidence and email previews. The schedule advances work every minute. For faster local development also run `worker.py` (ticks every two seconds); shared locking prevents duplicate processing.

The form creates a run and returns quickly; it does not wait for Apify or research to finish. The HTTP API returns `{"id":123}`. A scheduled HTTP call processes one saved stage, so a larger run may take many schedule ticks. Keep the Python worker running for responsive processing of many businesses.

### Addressing Windows, WSL and containers

- Same machine/network namespace: `http://127.0.0.1:8000`.
- n8n in Docker Desktop: `http://host.docker.internal:8000`; set `BIND_HOST=0.0.0.0` in the app's .env and restart. Allow access only from your trusted private network/firewall rules.
- n8n in WSL: use the reachable Windows host IP if localhost forwarding is unavailable. Set the backend bind address appropriately.
- Remote n8n: use a private network or HTTPS URL reaching your deployed app. `localhost` on a remote n8n server does not mean your laptop.

The n8n form-trigger and HTTP-node versions are based on the supplied export and standard n8n nodes. Import and execution were not possible without a running n8n account in this build environment. If n8n reports an unknown form version, upgrade n8n or recreate the Form Trigger with the same five fields and reconnect it to Normalize.

## Node-by-node integration

| Supplied node | Integrated behavior |
|---|---|
| On form submission | Preserved as an authenticated n8n form, with the same four business inputs plus Mode |
| Run an Actor and get dataset | Refactored to `providers.actor_input`, `start_actor`, and durable poll/dataset stages; same Maps actor and scraping options, plus secure multiple keys |
| Filter Qualified & Active Leads | Reimplemented in `rules.basic` with real review-date checks, exact configurable rating/reviews, closed flags and listed-site exclusion |
| Edit Fields | `providers.sheet_row` retains original business/phone/address/rating/review/Maps/social data and adds source and research columns |
| Append or update row in sheet | Two idempotent service-account Sheet projections keyed by internal lead identity rather than business name |
| New research/verification | Gemini grounded Google Search per business; source evidence and operator approval |
| New outreach | Verified-field personalization, explicit batch approval, SMTP or local .eml test delivery |

Why the Apify node moved: the supplied node binds one n8n credential and returns a whole dataset after execution. That cannot safely implement persisted per-key failover and recovery without extra state. n8n remains the entry point and scheduler; Python owns durable stages and credentials. Your original field logic and scraper input are used, with defects corrected, rather than left as an unused attachment.

## Input through webhook

Send JSON to the production webhook URL with its configured authentication header:

```json
{
  "niche": "HVAC contractor",
  "location": "Austin, Texas, USA",
  "lead_count": 10,
  "active_days": 30,
  "min_reviews": 30,
  "min_rating": 2,
  "mode": "live",
  "sync_sheets": true,
  "required_fields": ["email"]
}
```

Original `Niche`, `Location`, `LeadCount`, `ActivityWindow` names are also accepted by the n8n normalization node. It supplies a request key based on the n8n execution ID, so retries of its Create node do not create duplicate discoveries. A brand-new n8n execution intentionally creates a new discovery; business/email dedup still applies across discoveries.

## Original workflow reference

`original-sanitized.json` retains your original five-node workflow with credentials/account IDs removed. It requires the Apify community node, an Apify credential and Google Sheets OAuth credential if you choose to run it independently. It still has the original limitations and is a reference, not the recommended live workflow.

If you already have raw Apify dataset JSON, you can avoid scraping it again:
1. Stop the worker and disable the n8n schedule briefly.
2. Create a fresh live discovery using the API.
3. POST `{"items":[...raw Apify records...]}` to `/api/runs/ID/import` before scraping starts.
4. Start the worker/schedule again. The same initial-sheet, research and verification stages run.

Import raw records, including review timestamps and place IDs. The original reduced Google Sheet rows discard those fields and cannot independently prove recent activity.
