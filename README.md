# LeadPilot v2 — Find, Research, Email, Reply

Your updated local project has a three-step dashboard and automatically generates Excel workbooks. **No Google Sheets configuration, service account, spreadsheet URL, or n8n installation is required to run the app.** n8n remains available as an optional integration.

## Run in PyCharm / Windows

Open the inner `leadpilot` folder containing `run.py`. In the PyCharm terminal:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe setup_local.py
.\.venv\Scripts\python.exe run.py
```

If you already have `.venv`, skip creating it and install the updated requirements. `run.py` starts the web app **and background worker**; only one terminal is needed. Open **http://127.0.0.1:8000** and use the generated password (`ADMIN_PASSWORD` in `.env`). You can alternatively double-click `start_windows.bat`.

Every later start:

```powershell
.\.venv\Scripts\python.exe run.py
```

Python 3.11+ is intended; automated verification used Python 3.12/Linux. Windows execution still needs testing on your laptop. Linux/macOS: `bash start_local.sh`.

## If upgrading your original project

Read **docs/UPGRADE.md first**. Stop the old app and worker; back up `.env` and the entire `data/` folder. Use this complete v2 folder, and copy your old `.env` and `data/` into it before starting. The database migrates on startup and preserves saved leads and email records. Never overwrite your real data with a fresh empty database. The earlier PDF describes v1; this README and current docs replace its workflow instructions.

## Step 1: Find businesses

1. Click **Connections**.
2. Paste one or more Apify API keys, one per line. Save, then test the saved keys if desired.
3. Enter business type, location, target count, rating, review count and active days.
4. Choose **Demo** for a free local test or **Live** for Apify scraping.
5. Click **Find businesses**. Results are saved, and the run stops at **awaiting research**.

You no longer have to configure a Google spreadsheet. Use **Download Excel**, or open the automatically updated `data/exports/discovery-ID.xlsx` file. Keep the workbook closed while the app updates it; if Excel locks the file, the app retries and you can still download a fresh copy.

## Step 2: Research and refine

1. Save your Gemini API key and supported model ID in **Connections**.
2. Select the completed scrape, enter your research prompt in Step 2, and click **Start lead-by-lead research**.
3. Gemini researches each eligible business automatically, preserving sources and grounding metadata.
4. Click **Review**. You now edit ordinary fields and checkboxes rather than JSON.
5. Verify owner/business contact sources and the website finding, then **Approve for outreach**.

Only a documented no-website finding qualifies. Existing, broken, unknown, closed or insufficiently active businesses do not qualify. AI contact claims remain probable until reviewed. Default qualification accepts at least one verified owner **or** business email; both are not required.

The Excel workbook contains:

- **Initial**: all candidate businesses and their current stored fields.
- **Refined**: researched businesses, including review/rejected statuses.
- **Qualified**: only approved qualifying leads.
- **Outreach**: recipients, messages, modes and delivery status.
- **Conversations**: matched incoming messages and your replies.

The first eight lead columns are exactly: **Business Name, Owner Name, Owner Email, Business Email, Owner or Business Email, Location, Google Map URL, Social Media URL (Facebook preferred)**. Additional status/source columns explain the evidence quality. “Owner Name” contains the researched owner/decision-maker; verify their actual role in Review. The combined contact column includes selected verified addresses only; probable addresses remain visible in their separate columns for research.

## Step 3: Send individual emails

In **Connections**, enter your sender account, SMTP server and credentials. Keep **Test only** selected initially. Enter your template and choose:

- Owner first, otherwise business.
- Business first, otherwise owner.
- Owner only.
- Business only.
- Both, as **separate individual emails**.

If both fields contain the same address, only one recipient is created. Missing or unverified contacts are skipped. Save your template, create previews, and click **Send next batch**. A live batch asks for confirmation. Delay, daily limit, retries and duplicate prevention are retained. Template variables from v1 still work.

**Rebuild unsent previews** updates draft/blocked messages using your current template, preferences and sender. Queued, sent, failed and unknown records are not rewritten or automatically resent. First-outreach deduplication is per business+recipient+mode and also recipient+mode; deliberate conversation replies are separate messages.

## Read replies and chat through email

In Connections enable **Inbox sync**, then enter your IMAP host, TLS port (usually 993), username and app password. Save and test the inbox login. SMTP sends; IMAP receives. A sender address alone is not enough to connect to a mailbox.

**Inbox & replies** shows conversations after first emails are sent/simulated. Replies with matching email thread headers are attached to the correct conversation. Messages from a contacted address without matching headers appear under **Messages needing a conversation match**; you can link them manually. Recognized automatic replies are labelled automatic and are not counted as human replies.

Open a conversation, type your response, and send. Replies retain `In-Reply-To` / `References` headers, use the original sender account and obey pacing/suppression. Incoming mail is displayed as plain text; attachments are not downloaded/rendered.

The first sync inspects the newest 100 INBOX messages, then advances through newer UIDs in batches of up to 100. It imports only messages from contacted addresses on the configured account. Messages larger than 2 MB are skipped with a log entry; open them in your normal mail client. Enablement checks approximately once a minute while the app is running. This is email messaging, not an instant-chat protocol; provider delivery and polling add delay.

## Try the complete demo

Start a Demo discovery; wait for **awaiting research**; click Step 2. With defaults, the seven synthetic businesses yield three qualified leads. Create previews and send a test batch. In Inbox, select a simulated conversation and click **Simulate an incoming reply**. Type a response: it becomes a local `data/outbox/reply-ID.eml` file, with no real network delivery. You can test all three steps and the conversation view without credentials.

## Credentials and mailbox compatibility

Secrets entered in the UI are encrypted in SQLite using `data/vault.key`. The UI receives only nonsecret settings and saved/not-saved flags. Leave a secret field blank to preserve it. New Apify lists replace older lists. Changes take effect without restarting. .env integration values remain legacy fallbacks unless overridden from the UI.

Keep the database and vault key together in protected backups. Encryption does not protect against someone who can read both files on your computer. Losing the vault key prevents decryption; the app fails closed rather than replacing it silently.

The Gmail preset fills server names and supports eligible Google app passwords. Some accounts do not permit them. OAuth-only accounts, including many organizational mailboxes, are **not supported by this password-based connector**. OAuth sign-in and provider APIs are not implemented. See **docs/SETUP.md** for accurate account setup expectations.

## Verification and limits

Automated tests cover both-contact selection, encryption, staged research, formula-safe Excel output, database migration, IMAP read-only UID handling, thread matching, idempotent replies, suppression and ambiguous-send recovery. Provider behavior is mocked; no real scraping, mail delivery or mailbox access was performed here. Run `python -m unittest discover -s tests -v` in your virtual environment.

No promise of guaranteed lead volume, mailbox deliverability or universal reply detection. An ambiguous SMTP result remains `unknown` and is not automatically retried. Public real outreach needs a reachable HTTPS unsubscribe URL, not localhost. This remains a single-operator, single-host application. n8n imports/runtime, live provider integrations and Windows still need a small local smoke test.

## More documentation

- `docs/SETUP.md`: connection fields and email provider setup.
- `docs/UPGRADE.md`: safe upgrade from v1.
- `docs/ARCHITECTURE.md`: modules, Excel, queues and inbox design.
- `docs/API.md`: endpoints and n8n integration.
- `docs/TROUBLESHOOTING.md`: common errors.
- `docs/legacy-v1/`: historical reference only.
