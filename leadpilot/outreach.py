import hashlib, hmac, json, os, smtplib, time, uuid
from datetime import datetime, timezone
from urllib.parse import urlencode
from . import db, vault, contacts, mail_transport, excel
from .rules import TEMPLATE, personalize, qualified, valid_email

def template(data):
    result={**TEMPLATE,**{k:v for k,v in data.items() if k in TEMPLATE}}
    for k,lo,hi in [('daily_limit',1,500),('delay_seconds',5,86400),('batch_size',1,100)]:
        result[k]=int(result[k])
        if not lo<=result[k]<=hi:raise ValueError(f'{k} must be between {lo} and {hi}')
    for k in ['body','subject','fallback']:
        result[k]=str(result[k]).strip()
        if not result[k] or len(result[k])>20000:raise ValueError(f'Invalid {k}')
    if result['recipient_policy'] not in contacts.POLICIES:raise ValueError('Invalid recipient preference')
    personalize({}, {}, {'location':''},result);return result

def drafts(run_id):
    run=db.one('SELECT * FROM runs WHERE id=?',(run_id,))
    if not run:raise ValueError('Discovery not found')
    cfg=json.loads(run['config']);tpl=db.setting('outreach',TEMPLATE);count=0
    for lead in db.all_rows("SELECT * FROM leads WHERE run_id=? AND status='qualified'",(run_id,)):
        raw=json.loads(lead['raw']);r=json.loads(lead['research'])
        if qualified(raw,r,cfg,bool(lead['reviewed'])):continue
        for kind,email in contacts.pick(r,tpl.get('recipient_policy','prefer_owner')):
            if db.one('SELECT email FROM suppression WHERE email=?',(email,)):continue
            subject,body=personalize(raw,r,cfg,tpl)
            mode='demo' if cfg['mode']=='demo' else ('live' if vault.get('EMAIL_PROVIDER')=='smtp' else 'dry_run')
            with db.connect() as c:
                cursor=c.execute('INSERT OR IGNORE INTO emails(lead_id,business_id,recipient,subject,body,mode,created,message_id,recipient_kind,account_id) VALUES(?,?,?,?,?,?,?,?,?,?)',(lead['id'],lead['business_id'],email,subject,body,mode,time.time(),f'<{uuid.uuid4()}@leadpilot.local>',kind,vault.account_id()))
                count+=cursor.rowcount
    excel.mark(run_id);return count

def queue(run_id,live_confirmation=False):
    tpl=db.setting('outreach',TEMPLATE)
    rows=db.all_rows("SELECT e.* FROM emails e JOIN leads l ON e.lead_id=l.id WHERE l.run_id=? AND e.status='draft' ORDER BY e.id LIMIT ?",(run_id,tpl['batch_size']))
    if any(e['mode']=='live' for e in rows):
        if not live_confirmation:raise ValueError('Confirm the previewed live batch before sending')
        if not vault.get('SMTP_FROM') or not vault.get('SMTP_HOST') or not vault.get('SENDER_POSTAL_ADDRESS'):raise ValueError('Save sender email, SMTP connection and mailing address first')
    for e in rows:db.execute("UPDATE emails SET status='pending' WHERE id=? AND status='draft'",(e['id'],))
    excel.mark(run_id);return len(rows)

def unsubscribe_token(email):return hmac.new(os.environ['APP_SECRET'].encode(),email.encode(),hashlib.sha256).hexdigest()
def pacing(mode):
    tpl=db.setting('outreach',TEMPLATE);now=time.time()
    last=db.one("SELECT MAX(t) n FROM (SELECT sent_at t FROM emails WHERE status IN ('sent','simulated','sending','unknown') UNION ALL SELECT sent_at t FROM messages WHERE direction='outbound' AND status IN ('sent','sending','unknown'))")['n']
    if last and now-last<tpl['delay_seconds']:return False
    midnight=datetime.now(timezone.utc).replace(hour=0,minute=0,second=0,microsecond=0).timestamp()
    n=db.one("SELECT COUNT(*) n FROM emails WHERE mode=? AND status IN ('sent','simulated','sending','unknown') AND sent_at>=?",(mode,midnight))['n']
    if mode=='live':n+=db.one("SELECT COUNT(*) n FROM messages WHERE direction='outbound' AND status IN ('sent','sending','unknown') AND sent_at>=?",(midnight,))['n']
    return n<tpl['daily_limit']

def deliver_one():
    e=db.one("SELECT * FROM emails WHERE status='pending' AND next_at<=? ORDER BY id LIMIT 1",(time.time(),))
    if not e or not pacing(e['mode']):return
    lead=db.one('SELECT * FROM leads WHERE id=?',(e['lead_id'],));cfg=json.loads(db.one('SELECT config FROM runs WHERE id=?',(lead['run_id'],))['config'])
    reason=qualified(json.loads(lead['raw']),json.loads(lead['research']),cfg,bool(lead['reviewed']))
    valid=[email for _,email in contacts.available(json.loads(lead['research']))]
    if reason or lead['status']!='qualified' or e['recipient'] not in valid or db.one('SELECT email FROM suppression WHERE email=?',(e['recipient'],)):
        db.execute("UPDATE emails SET status='blocked',error=? WHERE id=?",(reason or 'Recipient changed or suppressed',e['id']));excel.mark(lead['run_id']);return
    if e['mode']=='live' and (cfg['mode']=='demo' or vault.get('EMAIL_PROVIDER')!='smtp' or e['account_id']!=vault.account_id()):
        db.execute("UPDATE emails SET status='blocked',error='Sender account or delivery mode changed; rebuild unsent preview' WHERE id=?",(e['id'],));excel.mark(lead['run_id']);return
    db.execute("UPDATE emails SET status='sending',sent_at=?,attempts=attempts+1 WHERE id=?",(time.time(),e['id']))
    smtp=None;started=False
    try:
        url=vault.get('PUBLIC_BASE_URL','http://127.0.0.1:8000').rstrip('/')+'/unsubscribe?'+urlencode({'email':e['recipient'],'token':unsubscribe_token(e['recipient'])})
        body=e['body']+'\n\n'+vault.get('SENDER_POSTAL_ADDRESS','Demo sender')+'\nTo stop receiving emails: '+url
        msg=mail_transport.message(vault.get('SMTP_FROM') or 'demo@example.test',e['recipient'],e['subject'],body,e['message_id']);msg['List-Unsubscribe']='<'+url+'>'
        if e['mode']!='live':
            folder=db.DB_PATH.parent/'outbox';folder.mkdir(exist_ok=True);(folder/f"{e['id']}.eml").write_bytes(bytes(msg));status='simulated'
        else:
            smtp=mail_transport.smtp_connection();started=True;smtp.send_message(msg);status='sent'
        db.execute('UPDATE emails SET status=?,error=? WHERE id=?',(status,'',e['id']));db.log(lead['run_id'],lead['id'],'email',status)
    except Exception as exc:
        state='unknown' if started else ('pending' if e['attempts']<2 else 'failed')
        if isinstance(exc,smtplib.SMTPRecipientsRefused):state='failed'
        db.execute('UPDATE emails SET status=?,next_at=?,error=? WHERE id=?',(state,time.time()+60*2**e['attempts'],type(exc).__name__+'; check connection or provider log',e['id']))
    finally:
        if smtp:
            try:smtp.close()
            except Exception:pass
        excel.mark(lead['run_id'])
