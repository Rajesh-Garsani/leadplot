# Architecture, persistence and evidence rules

The dashboard and authenticated n8n form/webhook create immutable run settings in SQLite. A local worker or n8n schedule executes one bounded stage per tick under a cross-process lock. External network requests do not hold SQLite write transactions. The app uses WAL and a busy timeout to reduce database-lock conflicts.

Pipeline: input → saved run → Apify start → poll existing actor → paginated dataset → initial Sheet → basic checks → one-business grounded research → evidence review → qualified Sheet → email drafts → approved queue → delivery log.

## Durable state

| Table | Role |
|---|---|
| runs | Immutable config snapshot, actor/run/key binding, dataset offset, stage, retries, errors |
| businesses | Stable cross-run identity: place ID, CID, Maps URL, then normalized name/address/phone hash |
| leads | Per-run business snapshot, raw data, research, review, qualification, Sheet status |
| keys | Nonsecret key fingerprints, labels, cooldown/disabled state, API request counts |
| emails | Frozen personalized content, delivery mode, recipient, stable Message-ID, send status and attempts |
| suppression | Permanent do-not-contact addresses |
| logs | Run/lead, stage, status, timestamp and redacted error category |
| settings | Outreach template, limits, pacing |

Same-name businesses with different place IDs stay distinct. The same identity can appear in several run snapshots, but the unique business ID and normalized recipient constraints prevent a second email in the same delivery mode. A business whose Maps identity changes could receive a different business ID; the recipient constraint is a second check, not universal entity resolution.

## Restart and retry semantics

- Create endpoint accepts an idempotency key; mismatched input with the same key is rejected.
- Persist actor-start intent before the POST. A timeout or crash without a saved response enters `start_unknown`, requiring an operator to inspect the Apify account and attach its run.
- Persist the actor ID/key together. Resume polls the same run; it does not re-scrape on dashboard refresh.
- Dataset pages use an offset saved after idempotent ingestion. A crash can re-read a page without duplicate leads.
- All initial-sheet writes precede research. Sheet rows are deterministic (`lead.id + 1`), so lost responses can be retried without append duplication.
- Research is saved per lead. A lost response before commit may require repeating an AI call; there is no universal external exactly-once AI API. Finished lead research is reused.
- A stage retries three times with exponential backoff; failed state remains inspectable. Resume resets that stage's attempts, not completed stages.
- After a lead is approved, its qualified Sheet write is scheduled. Downgrading an exported lead schedules a row clear. A Sheet outage can temporarily leave the remote projection stale; SQLite and local send checks remain authoritative.
- Before SMTP, persist `sending`. A crash leaves an `unknown` state on recovery. Unknown deliveries are never automatically retried. At-most-once attempts prioritize avoiding duplicate outreach over guaranteed delivery.
- File locks are released by the operating system on process death. No stale lock-file deletion is needed; the lock file's existence alone is harmless.

## Qualification rules

The backend enforces: business title/address; no listed website; not closed; rating and review minimums; at least one parseable, nonfuture review within configured days; identity/niche/location matches; no website found; no conflicting website URL; operator evidence review; at least two source hosts; configured required fields; verified email with valid syntax and an evidence source when an email is supplied. Lead count caps qualified results; additional research candidates remain available for review.

A distinct source host is a mechanical check, not proof of source independence or truth. Human review must check that the cited pages support the relevant business/claims. Website absence cannot be proven by exhaustive internet search. No direct arbitrary-URL server crawler is used; Gemini performs grounded search and the operator opens sources. Consequently this implementation does not provide an autonomous HTTP uptime test for an alleged broken site. Broken sites remain excluded.

AI claims begin probable. Missing grounding metadata forces unknown website status. Decision-maker and social/registration fields are optional unless supported as required configuration. Missing verified names use the configured fallback. Email syntax checks do not verify inbox deliverability. Contact phone values are retained from evidence; no claim is made that a phone is reachable or belongs personally to an owner.

## Security boundaries

Single operator password, signed HttpOnly SameSite session, CSRF protection for browser mutations, login throttling, server-side secret files, constant-time token comparison, no API keys in Sheet/lead output. n8n authenticates with `X-API-Key`. Anyone holding that token has operator API access; treat it like a password. Provider URLs are fixed; actor/model identifiers are encoded or validated. UI uses text nodes, template escaping, same-origin scripts and CSP; Google Search HTML is sandboxed without scripts. CSV exports guard formula prefixes; Sheets writes use RAW.

Research results are untrusted text. The prompt discourages prompt injection, and independent backend qualification gates constrain AI output, but it is not a guarantee against deceptive pages. The operator approves evidence and live batches. Signed unsubscribe links only suppress their associated recipient after confirmation; email generation also consults the suppression list.

## Scope decisions

- SQLite is the source of truth; Sheets are initial and qualified projections, not a mutable transactional queue.
- Credential editing is in .env; the browser shows nonsecret readiness/status instead of a secret editor.
- Gemini is the implemented research provider; email provider is SMTP or dry-run. Other AI/email API adapters are extension work.
- Only first outreach is implemented. Follow-ups are disabled to respect the one-message-per-business requirement.
- No guarantee of lead volume, zero false findings, inbox placement, or exactly-once SMTP delivery.
- Single-host local app, not a multi-tenant platform or multiworker distributed queue.
