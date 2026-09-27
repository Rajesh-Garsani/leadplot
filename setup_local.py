"""Generate server-only credentials without requiring third-party packages."""
from pathlib import Path
import os, secrets
root=Path(__file__).parent; target=root/'.env'
if target.exists():
    print('.env already exists; preserved. ADMIN_PASSWORD is inside it.'); raise SystemExit()
text=(root/'.env.example').read_text()
password=secrets.token_urlsafe(18)
for name,value in [('ADMIN_PASSWORD',password),('APP_SECRET',secrets.token_hex(32)),('N8N_API_TOKEN',secrets.token_urlsafe(40))]:
    text=text.replace(name+'=\n',name+'='+value+'\n')
target.write_text(text); os.chmod(target,0o600)
(root/'data').mkdir(exist_ok=True); (root/'credentials').mkdir(exist_ok=True)
print('Setup complete. Your local dashboard password:',password)
print('Password and integration settings are saved in .env. Keep this file private.')
