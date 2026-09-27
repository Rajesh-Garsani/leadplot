"""Read-only IMAP synchronization and durable, threaded replies. No HTML is executed."""
import email, hashlib, imaplib, json, re, ssl, time, uuid
from email import policy
from email.utils import parseaddr
from html.parser import HTMLParser
from . import db, vault, mail_transport, outreach, excel
class TextOnly(HTMLParser):
    def __init__(self):super().__init__();self.out=[];self.hidden=0
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style'):self.hidden+=1
        if tag in ('br','p','div','li'):self.out.append('\n')
    def handle_endtag(self,tag):
        if tag in ('script','style'):self.hidden=max(0,self.hidden-1)
    def handle_data(self,data):
        if not self.hidden:self.out.append(data)
def text_body(msg):
    texts=[];html=[]
    for part in msg.walk():
        if part.get_content_disposition()=='attachment' or part.is_multipart():continue
        if part.get_content_type() not in ('text/plain','text/html'):continue
        try:content=part.get_content()
        except Exception:continue
        if not isinstance(content,str):continue
        (texts if part.get_content_type()=='text/plain' else html).append(content[:200000])
    if texts:return '\n'.join(texts)[:200000]
    parser=TextOnly();parser.feed('\n'.join(html));return ''.join(parser.out)[:200000]
def ids(value):return re.findall(r'<[^<>\s]+>',str(value or ''))
def connect():
    host=vault.get('IMAP_HOST','');user=vault.get('IMAP_USER','')
    if not host or not user:raise ValueError('Save IMAP host and username first')
    client=imaplib.IMAP4_SSL(host,int(vault.get('IMAP_PORT','993')),ssl_context=ssl.create_default_context(),timeout=25)
    try:client.login(user,vault.get('IMAP_PASSWORD',''));return client
    except Exception:
        try:client.logout()
        except Exception:pass
        raise

def find_root(sender,refs,account):
    for ref in reversed(ids(refs)):
        root=db.one("SELECT * FROM emails WHERE message_id=? AND account_id=? AND mode='live' AND recipient=? AND status IN ('sent','unknown')",(ref,account,sender))
        if root:return root['id']
        child=db.one("SELECT e.* FROM messages m JOIN emails e ON e.id=m.root_id WHERE m.message_id=? AND m.account_id=? AND e.recipient=? AND m.direction='outbound' AND m.status IN ('sent','unknown')",(ref,account,sender))
        if child:return child['id']
    return None

def ingest(raw,account,mailbox,validity,uid):
    msg=email.message_from_bytes(raw,policy=policy.default)
    sender=parseaddr(str(msg.get('From','')))[1].lower();mid=(ids(msg.get('Message-ID')) or [''])[0]
    contacts=db.all_rows("SELECT id FROM emails WHERE account_id=? AND recipient=? AND mode='live' AND status IN ('sent','unknown')",(account,sender))
    if not contacts:return False
    if mid and db.one("SELECT id FROM messages WHERE account_id=? AND message_id=? AND direction='inbound'",(account,mid)):return False
    refs=' '.join(ids(str(msg.get('References',''))+' '+str(msg.get('In-Reply-To',''))))
    root=find_root(sender,refs,account)
    auto=str(msg.get('Auto-Submitted','no')).lower()!='no' or bool(msg.get('X-Autoreply')) or msg.get_content_type()=='multipart/report'
    status='automatic' if auto else ('received' if root else 'unmatched')
    row=db.execute('INSERT OR IGNORE INTO messages(root_id,account_id,direction,sender,recipient,subject,body,message_id,in_reply_to,refs,status,created,mailbox_key,uidvalidity,uid) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(root,account,'inbound',sender,vault.get('SMTP_FROM',''),str(msg.get('Subject',''))[:1000],text_body(msg),mid,' '.join(ids(msg.get('In-Reply-To'))),refs,status,time.time(),mailbox,validity,uid))
    if root:mark_root(root)
    return bool(row)
def mark_root(root):
    r=db.one('SELECT l.run_id FROM emails e JOIN leads l ON l.id=e.lead_id WHERE e.id=?',(root,))
    if r:excel.mark(r['run_id'])

def sync():
    if vault.get('IMAP_ENABLED','false')!='true':return {'status':'disabled','added':0}
    account=vault.account_id();folder=vault.get('IMAP_FOLDER','INBOX')
    if not re.fullmatch(r'[A-Za-z0-9 _./\[\]-]{1,100}',folder):raise ValueError('Unsupported folder name; use INBOX')
    key=hashlib.sha256('|'.join([account,vault.get('IMAP_HOST',''),vault.get('IMAP_USER',''),folder]).encode()).hexdigest()
    client=None;added=0
    db.execute('INSERT OR IGNORE INTO mailbox_state(mailbox_key) VALUES(?)',(key,))
    try:
        client=connect();status,_=client.select('"'+folder+'"',readonly=True)
        if status!='OK':raise ValueError('Mailbox cannot be selected')
        answer=client.response('UIDVALIDITY')[1]
        if not answer or not answer[0]:raise ValueError('Mailbox did not supply UIDVALIDITY')
        validity=answer[0].decode();state=db.one('SELECT * FROM mailbox_state WHERE mailbox_key=?',(key,))
        last=state['last_uid'] if state['uidvalidity']==validity else 0
        status,data=client.uid('search',None,'ALL' if not last else f'UID {last+1}:*')
        if status!='OK':raise ValueError('IMAP search failed')
        found=sorted(int(x) for x in data[0].split() if int(x)>last)
        # Initial connection inspects newest 100 messages, then advances in ascending order.
        todo=sorted(found[-100:] if not last else found[:100])
        for uid in todo:
            status,parts=client.uid('fetch',str(uid),'(RFC822.SIZE BODY.PEEK[HEADER.FIELDS (FROM MESSAGE-ID REFERENCES IN-REPLY-TO)])')
            if status!='OK':raise ValueError('IMAP header fetch failed')
            headers=b''.join(p[1] for p in parts if isinstance(p,tuple) and isinstance(p[1],bytes))
            meta=b' '.join(p[0] for p in parts if isinstance(p,tuple))
            size=re.search(rb'RFC822.SIZE (\d+)',meta)
            header=email.message_from_bytes(headers,policy=policy.default)
            sender=parseaddr(str(header.get('From','')))[1].lower()
            related=db.one("SELECT id FROM emails WHERE account_id=? AND recipient=? AND mode='live' AND status IN ('sent','unknown')",(account,sender))
            if related and (not size or int(size[1])<=2_000_000):
                status,full=client.uid('fetch',str(uid),'(BODY.PEEK[])')
                if status!='OK':raise ValueError('IMAP body fetch failed')
                raw=b''.join(p[1] for p in full if isinstance(p,tuple) and isinstance(p[1],bytes))
                if not raw:raise ValueError('IMAP returned an empty message')
                added+=int(ingest(raw,account,key,validity,uid))
            elif related:
                db.log(None,None,'inbox','skipped','Related message exceeds 2 MB; read it in your email provider')
            db.execute('UPDATE mailbox_state SET uidvalidity=?,last_uid=? WHERE mailbox_key=?',(validity,uid,key))
        db.execute("UPDATE mailbox_state SET uidvalidity=?,synced_at=?,error='' WHERE mailbox_key=?",(validity,time.time(),key))
        db.save_setting('inbox_sync_status',{'status':'ok','added':added,'time':time.time()})
        return {'status':'ok','added':added}
    except Exception as exc:
        error=type(exc).__name__+'; check IMAP host, app password and account policy'
        db.execute('UPDATE mailbox_state SET error=? WHERE mailbox_key=?',(error,key))
        db.save_setting('inbox_sync_status',{'status':'error','message':error,'time':time.time()})
        return {'status':'error','message':error}
    finally:
        if client:
            try:client.logout()
            except Exception:pass

def queue_reply(root_id,body,request_key,confirm_live=False):
    root=db.one('SELECT * FROM emails WHERE id=?',(root_id,))
    if not root:raise ValueError('Conversation not found')
    if root['mode']=='live' and (not confirm_live or vault.get('EMAIL_PROVIDER')!='smtp' or root['account_id']!=vault.account_id()):raise ValueError('Confirm live reply using the original sender account')
    if root['status'] not in ('sent','unknown','simulated'):raise ValueError('Send the first message before replying')
    if not isinstance(body,str) or not body.strip() or len(body)>20000:raise ValueError('Reply must contain 1-20000 characters')
    if not isinstance(request_key,str) or not re.fullmatch(r'[a-zA-Z0-9-]{12,100}',request_key):raise ValueError('Reply request ID required')
    existing=db.one('SELECT * FROM messages WHERE request_key=?',(request_key,))
    if existing:
        if existing['root_id']!=root_id or existing['body']!=body.strip():raise ValueError('Request ID already used for another reply')
        return existing['id']
    if db.one('SELECT email FROM suppression WHERE email=?',(root['recipient'],)):raise ValueError('This contact is suppressed')
    last=db.one("SELECT * FROM messages WHERE root_id=? AND direction='inbound' AND status='received' ORDER BY id DESC LIMIT 1",(root_id,))
    parent=(last['message_id'] if last else '') or root['message_id']
    refs=' '.join(dict.fromkeys(ids(root['message_id']+' '+(last['refs'] if last else '')+' '+parent)))
    subject=root['subject'] if root['subject'].lower().startswith('re:') else 'Re: '+root['subject']
    mid=f'<{uuid.uuid4()}@leadpilot.local>'
    n=db.execute('INSERT INTO messages(root_id,account_id,direction,sender,recipient,subject,body,message_id,in_reply_to,refs,status,created,request_key) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',(root_id,root['account_id'],'outbound',vault.get('SMTP_FROM') or 'demo@example.test',root['recipient'],subject,body.strip(),mid,parent,refs,'pending',time.time(),request_key))
    mark_root(root_id);return n

def deliver_reply():
    m=db.one("SELECT * FROM messages WHERE direction='outbound' AND status='pending' AND next_at<=? ORDER BY id LIMIT 1",(time.time(),))
    if not m:return
    root=db.one('SELECT * FROM emails WHERE id=?',(m['root_id'],))
    if not outreach.pacing(root['mode']):return
    if db.one('SELECT email FROM suppression WHERE email=?',(m['recipient'],)) or (root['mode']=='live' and (m['account_id']!=vault.account_id() or vault.get('EMAIL_PROVIDER')!='smtp')):
        db.execute("UPDATE messages SET status='blocked',error='Suppressed recipient or sender account changed' WHERE id=?",(m['id'],));mark_root(m['root_id']);return
    db.execute("UPDATE messages SET status='sending',sent_at=?,attempts=attempts+1 WHERE id=?",(time.time(),m['id']))
    smtp=None;started=False
    try:
        msg=mail_transport.message(m['sender'],m['recipient'],m['subject'],m['body'],m['message_id'],m['in_reply_to'],m['refs'])
        if root['mode']=='live':smtp=mail_transport.smtp_connection();started=True;smtp.send_message(msg);status='sent'
        else:
            folder=db.DB_PATH.parent/'outbox';folder.mkdir(exist_ok=True);(folder/f"reply-{m['id']}.eml").write_bytes(bytes(msg));status='simulated'
        db.execute('UPDATE messages SET status=?,error=? WHERE id=?',(status,'',m['id']))
    except Exception as exc:
        state='unknown' if started else ('pending' if m['attempts']<2 else 'failed')
        db.execute('UPDATE messages SET status=?,next_at=?,error=? WHERE id=?',(state,time.time()+60*2**m['attempts'],type(exc).__name__,m['id']))
    finally:
        if smtp:
            try:smtp.close()
            except Exception:pass
        mark_root(m['root_id'])

def demo_reply(root_id):
    root=db.one('SELECT * FROM emails WHERE id=?',(root_id,))
    if not root or root['mode']!='demo' or root['status']!='simulated':raise ValueError('Choose a simulated demo conversation')
    key='demo-inbound-'+str(root_id)
    db.execute('INSERT OR IGNORE INTO messages(root_id,account_id,direction,sender,recipient,subject,body,message_id,in_reply_to,status,created,request_key) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(root_id,root['account_id'],'inbound',root['recipient'],'demo@example.test','Re: '+root['subject'],'Thanks for reaching out! Could you share more details about your website service? (Demo reply)',f'<demo-reply-{root_id}@example.test>',root['message_id'],'received',time.time(),key));mark_root(root_id)
