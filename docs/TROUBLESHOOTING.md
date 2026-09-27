# Troubleshooting v2

- **App asks for Google Sheets:** confirm you are running this version's run.py, not the old app. v2 has no Google Sheets setup requirement. Stop old terminals and check your PyCharm working directory/interpreter.
- **No module named openpyxl/cryptography:** install requirements-lock.txt with the exact .venv Python you use to run the project.
- **awaiting_research:** expected. Select the discovery, add your prompt and click Step 2.
- **Gemini button disabled:** scraping has not finished, research is already running, or the selected run is not at the research gate. Check its status/stage.
- **Connection says saved but API fails:** saving is not credential verification. Use Test, then a small live run. Model/actor permissions and quota still matter.
- **Blank password after saving:** intentional; saved secrets are never returned to the browser. Saved/not-set flags show whether a secret is present. Blank inputs preserve the old secret.
- **Worker busy:** a background stage holds the process lock. Retry after it finishes; do not repeatedly launch more processes.
- **Excel not updating:** close the workbook in Excel so Windows releases the file. Download Excel always generates a new copy. Manual edits to a workbook are not written back into the database.
- **Owner address is present but not selected:** it must be syntactically valid, marked verified and backed by a source URL listed in the evidence. Probable addresses are not sent to.
- **Changing recipient mode does not change previews:** save preferences and click Rebuild unsent previews. It affects draft/blocked records only; queued/sent messages are preserved.
- **No previews for a repeated business:** first-outreach deduplication spans discoveries. Check old previews/sends; do not erase history to force another initial outreach.
- **Incoming reply not visible:** verify IMAP login, enable sync, check the folder, and click Check for replies. Only contacted addresses for this v2 sender account are imported. First sync examines newest 100 messages; >2 MB messages are skipped. Threadless mail appears in the unmatched list.
- **Cannot connect Gmail:** your account may need an eligible app password; ordinary passwords may fail. Some accounts do not allow app passwords. OAuth-only accounts are outside this connector's scope.
- **Reply marked unknown:** inspect your provider history. It may already have been accepted; no automatic resend occurs.
- **Messages blocked after editing the sender:** v2 binds messages to their original account. Rebuild only unsent draft/blocked previews after reviewing the new account. Sent/unknown mail remains protected.
- **Old v1 conversations do not sync:** those records lack a reliable sender identity. New v2-created messages have a binding; legacy history is not guessed or reassigned.
- **Vault key missing/unreadable:** restore the matching data/vault.key and database from backup. Do not generate a new key over encrypted data.

For deployment use HTTPS, a reachable unsubscribe URL, persistent local data and a protected operator login. Keep localhost/test mode for laptop testing. Windows and actual provider behavior must be verified with your own accounts before operational use.
