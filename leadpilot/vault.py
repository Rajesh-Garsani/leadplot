"""Encrypted UI configuration. The vault key stays on this host, never in API responses."""
import json, os, re, hashlib
from cryptography.fernet import Fernet, InvalidToken
from . import db
SECRET_FIELDS={'APIFY_API_KEYS','GEMINI_API_KEY','SMTP_PASSWORD','IMAP_PASSWORD'}
FIELDS=SECRET_FIELDS|{'GEMINI_MODEL','EMAIL_PROVIDER','SMTP_HOST','SMTP_PORT','SMTP_SECURITY','SMTP_USER','SMTP_FROM','IMAP_HOST','IMAP_PORT','IMAP_USER','IMAP_FOLDER','IMAP_ENABLED','SENDER_POSTAL_ADDRESS','PUBLIC_BASE_URL'}
DEFAULTS={'GEMINI_MODEL':'gemini-2.5-flash','EMAIL_PROVIDER':'dry_run','SMTP_PORT':'587','SMTP_SECURITY':'starttls','IMAP_PORT':'993','IMAP_FOLDER':'INBOX','IMAP_ENABLED':'false','PUBLIC_BASE_URL':'http://127.0.0.1:8000'}
def cipher():
    path=db.DB_PATH.parent/'vault.key';path.parent.mkdir(parents=True,exist_ok=True)
    if not path.exists():
        # Never replace a lost key if encrypted credentials already exist.
        if db.one('SELECT name FROM integrations LIMIT 1'): raise ValueError('Vault key missing. Restore data/vault.key from backup.')
        try:
            fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(fd,'wb') as f:f.write(Fernet.generate_key())
        except FileExistsError:pass
    return Fernet(path.read_bytes())
def values():
    row=db.one("SELECT sealed FROM integrations WHERE name='main'")
    if not row:return {}
    try:return json.loads(cipher().decrypt(row['sealed'].encode()))
    except (InvalidToken,ValueError):raise ValueError('Unable to open saved credentials. Restore the matching vault.key.') from None
def get(name,default=None):
    return values().get(name,os.getenv(name,DEFAULTS.get(name,default)))
def public():
    saved=values();result={k:saved.get(k,os.getenv(k,DEFAULTS.get(k,''))) for k in FIELDS-SECRET_FIELDS}
    result['secrets']={k:bool(saved.get(k,os.getenv(k,''))) for k in SECRET_FIELDS}
    result['apify_key_count']=len([s for s in str(get('APIFY_API_KEYS','')).split(',') if s.strip()])
    return result

def save(data):
    if not isinstance(data,dict):raise ValueError('Settings must be an object')
    unknown=set(data)-FIELDS-{'clear_secrets'}
    if unknown:raise ValueError('Unsupported settings field')
    current=values()
    for k,v in data.items():
        if k=='clear_secrets':continue
        if not isinstance(v,(str,bool,int)):raise ValueError('Invalid setting value')
        value=str(v).strip()
        if len(value)>12000:raise ValueError('Setting too long')
        if k in SECRET_FIELDS and not value:continue # blank means preserve
        if k=='APIFY_API_KEYS':value=','.join(x.strip() for x in re.split(r'[,\n]+',value) if x.strip())
        if k.endswith('_PORT'):
            if not value.isdigit() or not 1<=int(value)<=65535:raise ValueError('Invalid port')
        if k in ('SMTP_HOST','IMAP_HOST') and value and not re.fullmatch(r'[a-zA-Z0-9.-]+',value):raise ValueError('Enter a hostname, without https:// or a path')
        if '\n' in value or '\r' in value:raise ValueError('Settings must be single-line values')
        current[k]=value
    for k in data.get('clear_secrets',[]):
        if k not in SECRET_FIELDS:raise ValueError('Invalid secret field')
        current[k]=''
    if current.get('EMAIL_PROVIDER','dry_run') not in ('dry_run','smtp'):raise ValueError('Invalid email delivery mode')
    if current.get('SMTP_SECURITY','starttls') not in ('starttls','ssl'):raise ValueError('SMTP must use TLS')
    if current.get('IMAP_ENABLED','false').lower() not in ('true','false'):raise ValueError('Invalid inbox toggle')
    current['IMAP_ENABLED']=current.get('IMAP_ENABLED','false').lower()
    if current.get('PUBLIC_BASE_URL') and not current['PUBLIC_BASE_URL'].startswith(('https://','http://127.0.0.1:','http://localhost:')):raise ValueError('Public base URL must use HTTPS, or localhost for testing')
    from .rules import valid_email
    if current.get('SMTP_FROM') and not valid_email(current['SMTP_FROM']):raise ValueError('Enter a plain sender email address')
    db.execute("INSERT INTO integrations(name,sealed) VALUES('main',?) ON CONFLICT(name) DO UPDATE SET sealed=excluded.sealed",(cipher().encrypt(json.dumps(current).encode()).decode(),))
    return public()

def account_id():
    parts=[get('SMTP_HOST',''),get('SMTP_USER',''),get('SMTP_FROM','')]
    return hashlib.sha256('|'.join(str(x).lower() for x in parts).encode()).hexdigest()[:24]
