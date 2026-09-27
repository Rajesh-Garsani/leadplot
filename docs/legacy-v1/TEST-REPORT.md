# Verification report

- Python 3.12 / Linux: 31 unittest cases passed.
- Verified demo run completion, persisted states and simulated .eml output.
- Authentication, session CSRF and dashboard HTML rendering exercised with Flask's test client.
- JavaScript syntax checked with Node.js.
- n8n JSON structure and normalization code checked locally.
- Apify key failover, original-key polling, ambiguous start, Gemini grounding and fixed-row Sheets writes tested with mocks.
- SMTP ambiguity tested with a mocked connection loss; no actual email was sent.
- Headless browser test attempted; unavailable Chromium binary and failed download prevented rendered UI testing.
- Windows launcher, n8n import/runtime and live external integrations require local smoke tests.

Run `python -m unittest discover -s tests -v` to repeat the automated checks. Tests use temporary state and do not need provider keys.
