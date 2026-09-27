# Integration setup and deployment

## 1. Local account and configuration

`python setup_local.py` creates random `ADMIN_PASSWORD`, `APP_SECRET` and `N8N_API_TOKEN` values. It never overwrites an existing `.env`. Do not share `.env`, the service-account JSON, or production database backups. Secrets stay on the server and are not returned by `/api/state`.

Windows hides dotfile extensions sometimes; ensure the file is named `.env`, not `.env.txt`. Reopen it using PyCharm or Notepad. Restart **both** processes after changing environment settings. The dashboard exposes nonsecret integration readiness, key labels, request counts and last HTTP statuses.

## 2. Apify

1. Sign into your Apify account and obtain an API token from its integration settings.
2. Confirm your account can run `compass/crawler-google-places` and has sufficient balance/permissions.
3. Set `APIFY_API_KEYS=token1,token2`. Only use accounts/tokens you are authorized to use.
4. Keep `APIFY_ACTOR_ID=compass~crawler-google-places` unless intentionally changing to a compatible actor.

Original input options are preserved in `providers.actor_input`: niche/location, 3× candidate overfetch, no listed website, skip closed, newest one review, configured activity window, English, Facebook enrichment, no review personal data, no images. The fixed two-star actor prefilter is replaced with exact backend rating checks so lower or higher dashboard thresholds work. The backend checks actual timestamps rather than trusting that a nonempty reviews array is recent. Actor output must use the original `title`, `placeId/cid/url`, `totalScore`, `reviewsCount`, `reviews[].publishedAtDate`, `address`, `phone`, `website` fields.

On a definitive 401/402/403 the token is disabled locally and the next available token is tried for a new run. HTTP 429 causes a Retry-After-aware cooldown (minimum 60 seconds), then another available token may be tried. Reset a recovered key using **Integrations** after resolving the account problem. Request counts are not billing/credit balances; actual balances remain in Apify.

An accepted actor run ID and original key fingerprint are saved. Polling or reading its dataset never silently changes account. Removing its key prevents access; restore it. A network loss during actor submission is ambiguous: inspect Apify, then attach the existing run ID and key ID in the dashboard. If no actor was created, start a new discovery; the uncertain record is kept for audit. This conservative behavior avoids duplicate paid launches.

## 3. Gemini and website research

1. Obtain a Gemini API key from Google AI Studio; enable billing if your account/model/search tool requires it.
2. Set `GEMINI_API_KEY` and the exact `GEMINI_MODEL` identifier your account supports.
3. Choose a model that supports `generateContent` with the `google_search` tool. A per-run override is available.

The complete research prompt is `providers.PROMPT`. It asks for identity, niche and location matches, website search, business contacts, decision maker, social profiles, registration information, source URLs and field certainty. Your additional research focus is appended. Provider/model support beyond Gemini is not implemented; the adapter is isolated to simplify extending it.

Each business is researched individually. Grounding metadata and Search Suggestions are preserved and displayed in a sandboxed frame. Missing grounded search output forces unknown website status. Contacts are stored as probable until an operator checks sources. Do not change `email_status` to verified unless the exact address is publicly present on `email_source`; this URL must also appear in the evidence sources list. Decision-maker names can stay missing: the fallback greeting is used.

Review checklist:
- Same business name, address and phone—not a similarly named business elsewhere.
- Correct niche and target area.
- At least two independent public sources. Check ownership/editorial independence yourself; distinct URL hosts alone do not establish it.
- Search the exact business name/address for an official standalone site. Existing, broken and uncertain websites do not qualify.
- Public business email checked against its source. Syntax checks are not mailbox verification.
- Record probable/missing fields honestly; optional fields do not need to be invented.

To approve: edit JSON if necessary, set verified contact status only after checking, tick the review confirmation and click **Approve qualification**. Broken/outdated websites are recorded but excluded because the supplied final qualification rule explicitly allows only no-website findings.

## 4. Google Sheets

1. In a Google Cloud project enable the **Google Sheets API**.
2. Create a service account; download its JSON credentials to `credentials/google-service-account.json`.
3. Create **two separate spreadsheet documents**: Initial Leads and Qualified Leads.
4. In each document rename the working tab to `Leads` (or set `SHEET_TAB` to your chosen identical tab name).
5. Share both documents with the service account's `client_email`, granting Editor access.
6. Copy each document ID from `/spreadsheets/d/DOCUMENT_ID/edit` into `.env`:
   - `INITIAL_SHEET_ID=...`
   - `QUALIFIED_SHEET_ID=...`
7. Add at least 10,000 rows and 24 columns (A:X) to each tab for local testing. If lead IDs grow beyond available rows, expand both tabs before resuming a failed Sheet stage.
8. Enable the dashboard's Sheet sync option for new live runs.

Sheets are user-created because service-account ownership/Drive quotas vary; the application creates headers and updates rows, not spreadsheet documents. The initial sheet is written before individual research. The qualified sheet contains only approved leads. Dequalifying an already exported record clears its qualified row on the next successful processing tick. Do not manually reorder rows; internal lead ID + 1 is a stable projection row, including intentional blank rows for rejected leads. Use a separate tab with QUERY/FILTER formulas for sorted views. `RAW` writes prevent spreadsheet formula execution. CSV exports also escape formula prefixes.

Columns: Lead ID, Business Name, Business Category, Business Phone, Business Email, Business Address, Google Maps URL, Rating, Review Count, Website Status, Decision Maker Name, Decision Maker Position, Decision Maker Email, Decision Maker Phone, Facebook URL, Instagram URL, LinkedIn URL, Other Social Profile, Business Registration Information, Lead Status, Source URLs, Evidence, Run ID, Demo.

## 5. SMTP and outreach

Configure an SMTP provider of your choice:

```dotenv
EMAIL_PROVIDER=smtp
SMTP_HOST=smtp.your-provider.example
SMTP_PORT=587
SMTP_SECURITY=starttls
SMTP_USER=your_username
SMTP_PASSWORD=your_app_password
SMTP_FROM=you@your-domain.example
SENDER_POSTAL_ADDRESS=Your business mailing address
PUBLIC_BASE_URL=https://your-reachable-app-domain.example
```

For implicit TLS use `SMTP_SECURITY=ssl` and the provider's TLS port (usually 465). Plain, unencrypted SMTP is not supported. Provider-specific app passwords, verified sender domains and SPF/DKIM settings may be required.

For local testing keep `EMAIL_PROVIDER=dry_run`; no provider credentials are needed. A localhost unsubscribe link only works on your own computer. Before sending to real recipients, use a reachable HTTPS `PUBLIC_BASE_URL`. A signed unsubscribe link is added automatically; visiting it presents a confirmation form, and submitting it permanently suppresses the address.

Template tokens: `{{FirstName}}`, `{{FullName}}`, `{{BusinessName}}`, `{{BusinessCategory}}`, `{{Location}}`, `{{WebsiteStatus}}`, `{{CustomResearchField}}`. Unknown tokens and multiline subjects are rejected. Save the template before creating previews. Each preview stores its content and provider mode permanently for audit; changing the template does not silently rewrite existing previews.

Queue one approved batch at a time. Limits use UTC calendar days and are global per delivery mode, not per discovery. Delay is global between deliveries. Safe pre-send connection/auth failures retry up to three attempts with backoff; SMTP recipient rejection fails; any possibly accepted delivery becomes unknown and is not retried. The email Message-ID is stable, but SMTP itself offers no universal exactly-once delivery guarantee. A conservative unknown result may mean an email was delivered, or none was sent. Check provider history; there is deliberately no one-click resend of unknown deliveries.

## 6. Backups and deployment

For local backups, stop both processes and copy `data/`, `.env` and `credentials/` to protected storage. Alternatively use SQLite's online backup API; do not blindly copy an active WAL database file alone. Restore all state together. Never commit secrets or SQLite databases into git.

A small private Linux server can run the same code without Docker:

1. Install Python, create a virtual environment and install requirements.
2. Run setup, configure .env, and copy credentials securely.
3. Run `app.py` and `worker.py` under a process supervisor (e.g. systemd) with a private service user.
4. Put HTTPS Nginx/Caddy in front of localhost port 8000; set `COOKIE_SECURE=true` and your public base URL.
5. Restrict operator access, retain strong passwords, protect n8n credentials and keep dependencies patched.
6. Back up the durable local database and outbox. Do not deploy the SQLite file on a shared/network filesystem or in ephemeral storage.

`BIND_HOST` can override localhost if needed for private networking. Exposing it publicly requires the controls above. Use PostgreSQL plus a transactional job queue before adding multiple machines or tenants; this package deliberately uses a single-host OS lock and SQLite to stay easy to run locally.
