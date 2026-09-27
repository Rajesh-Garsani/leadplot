"""SQLite is the source of truth; Sheets are idempotent export projections."""
import json, os, sqlite3, time
from contextlib import contextmanager
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.environ.get('LEADPILOT_DB', ROOT / 'data' / 'leadpilot.sqlite3'))

@contextmanager
def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB_PATH, timeout=30)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    c.execute('PRAGMA busy_timeout=30000')
    try:
        with c:
            yield c
    finally:
        c.close()

def init():
    with connect() as c:
        c.execute('PRAGMA journal_mode=WAL')
        c.executescript('''
        CREATE TABLE IF NOT EXISTS runs (
          id INTEGER PRIMARY KEY, request_key TEXT UNIQUE, config TEXT NOT NULL,
          status TEXT DEFAULT 'queued', stage TEXT DEFAULT 'scrape', created REAL,
          actor_run TEXT, dataset TEXT, key_id TEXT, offset INTEGER DEFAULT 0,
          attempts INTEGER DEFAULT 0, next_at REAL DEFAULT 0, error TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS businesses (
          id INTEGER PRIMARY KEY, identity TEXT UNIQUE NOT NULL);
        CREATE TABLE IF NOT EXISTS leads (
          id INTEGER PRIMARY KEY, run_id INTEGER REFERENCES runs(id),
          business_id INTEGER REFERENCES businesses(id), raw TEXT NOT NULL,
          research TEXT DEFAULT '{}', status TEXT DEFAULT 'initial', reason TEXT DEFAULT '',
          initial_synced INTEGER DEFAULT 0, qualified_synced INTEGER DEFAULT 0,
          sheet_present INTEGER DEFAULT 0, reviewed INTEGER DEFAULT 0, reviewed_at REAL, email TEXT DEFAULT '',
          UNIQUE(run_id,business_id));
        CREATE TABLE IF NOT EXISTS logs (
          id INTEGER PRIMARY KEY, run_id INTEGER, lead_id INTEGER, stage TEXT,
          status TEXT, message TEXT, created REAL);
        CREATE TABLE IF NOT EXISTS keys (
          id TEXT PRIMARY KEY, label TEXT, status TEXT DEFAULT 'ready', until REAL DEFAULT 0,
          requests INTEGER DEFAULT 0, last_code INTEGER);
        CREATE TABLE IF NOT EXISTS emails (
          id INTEGER PRIMARY KEY, lead_id INTEGER REFERENCES leads(id), business_id INTEGER,
          recipient TEXT, subject TEXT, body TEXT, mode TEXT, status TEXT DEFAULT 'draft',
          attempts INTEGER DEFAULT 0, created REAL, sent_at REAL, next_at REAL DEFAULT 0,
          error TEXT DEFAULT '', message_id TEXT, UNIQUE(business_id,mode), UNIQUE(recipient,mode));
        CREATE TABLE IF NOT EXISTS suppression (email TEXT PRIMARY KEY, created REAL);
        CREATE TABLE IF NOT EXISTS integrations(name TEXT PRIMARY KEY,sealed TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY,value TEXT);
        ''')

    migrate()

def migrate():
    with connect() as c:
        # Version 1 used one email per business, preventing separate owner/business contacts.
        sql=c.execute("SELECT sql FROM sqlite_master WHERE name='emails'").fetchone()[0]
        if 'UNIQUE(business_id,mode)' in sql.replace(' ',''):
            c.executescript("""
            CREATE TABLE emails_v2 (
              id INTEGER PRIMARY KEY, lead_id INTEGER REFERENCES leads(id), business_id INTEGER,
              recipient TEXT, subject TEXT, body TEXT, mode TEXT, status TEXT DEFAULT 'draft',
              attempts INTEGER DEFAULT 0, created REAL, sent_at REAL, next_at REAL DEFAULT 0,
              error TEXT DEFAULT '', message_id TEXT,
              UNIQUE(business_id,recipient,mode), UNIQUE(recipient,mode));
            INSERT INTO emails_v2 SELECT * FROM emails;
            DROP TABLE emails;
            ALTER TABLE emails_v2 RENAME TO emails;
            """)
        for table, columns in {
            'emails':{'recipient_kind':"TEXT DEFAULT 'business'",'account_id':"TEXT DEFAULT ''"},
            'runs':{'export_error':"TEXT DEFAULT ''",'exported_at':'REAL'},
        }.items():
            existing={r[1] for r in c.execute('PRAGMA table_info('+table+')')}
            for name,definition in columns.items():
                if name not in existing:c.execute('ALTER TABLE '+table+' ADD COLUMN '+name+' '+definition)
        c.executescript("""
        CREATE TABLE IF NOT EXISTS messages (
          id INTEGER PRIMARY KEY, root_id INTEGER REFERENCES emails(id), account_id TEXT NOT NULL,
          direction TEXT NOT NULL, sender TEXT, recipient TEXT, subject TEXT, body TEXT,
          message_id TEXT, in_reply_to TEXT, refs TEXT DEFAULT '', status TEXT,
          created REAL, sent_at REAL, attempts INTEGER DEFAULT 0, next_at REAL DEFAULT 0,
          error TEXT DEFAULT '', request_key TEXT UNIQUE, mailbox_key TEXT, uidvalidity TEXT, uid INTEGER,
          UNIQUE(mailbox_key,uidvalidity,uid));
        CREATE INDEX IF NOT EXISTS message_threads ON messages(root_id,created);
        CREATE TABLE IF NOT EXISTS mailbox_state (
          mailbox_key TEXT PRIMARY KEY, uidvalidity TEXT, last_uid INTEGER DEFAULT 0,
          synced_at REAL, error TEXT DEFAULT '');
        PRAGMA user_version=2;
        """)

def all_rows(sql, args=()):
    with connect() as c: return [dict(r) for r in c.execute(sql,args).fetchall()]
def one(sql,args=()):
    rows=all_rows(sql,args); return rows[0] if rows else None
def execute(sql,args=()):
    with connect() as c: return c.execute(sql,args).lastrowid
def log(run,lead,stage,status,message=''):
    execute('INSERT INTO logs(run_id,lead_id,stage,status,message,created) VALUES(?,?,?,?,?,?)',
            (run,lead,stage,status,message[:800],time.time()))
def setting(key,default=None):
    r=one('SELECT value FROM settings WHERE key=?',(key,)); return json.loads(r['value']) if r else default
def save_setting(key,value):
    execute('INSERT INTO settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(key,json.dumps(value)))
