import io,json,os,sqlite3,tempfile,time,unittest
from pathlib import Path
from unittest.mock import Mock,patch
from email.message import EmailMessage
from openpyxl import load_workbook
os.environ.update(APP_SECRET='test-secret',ADMIN_PASSWORD='test-password',N8N_API_TOKEN='test-token',EMAIL_PROVIDER='dry_run')
from leadpilot import db,vault,pipeline,contacts,excel,outreach,inbox,rules,mail_transport
from app import create_app
class V2Tests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.old=db.DB_PATH;db.DB_PATH=Path(self.tmp.name)/'data.sqlite3';db.init()
 def tearDown(self):db.DB_PATH=self.old;self.tmp.cleanup()
 def finish(self):
  rid=pipeline.create({})
  for _ in range(40):
   pipeline.tick();r=db.one('SELECT * FROM runs WHERE id=?',(rid,))
   if r['status']=='awaiting_research':pipeline.start_research(rid,'Find the owner and business email')
  return rid
 def sent(self):
  rid=self.finish();outreach.drafts(rid);e=db.one('SELECT * FROM emails ORDER BY id LIMIT 1')
  db.execute("UPDATE emails SET mode='live',status='sent',account_id=? WHERE id=?",(vault.account_id(),e['id']))
  return db.one('SELECT * FROM emails WHERE id=?',(e['id'],))
 def mail(self,e,refs=None,sender=None,mid='<incoming@test.example>',auto=False):
  m=EmailMessage();m['From']=sender or e['recipient'];m['To']='me@example.com';m['Subject']='Re: hi';m['Message-ID']=mid
  if refs is not None:m['In-Reply-To']=refs
  if auto:m['Auto-Submitted']='auto-replied'
  m.set_content('Please send details.');return bytes(m)
 def test_credentials_encrypted_and_redacted(self):
  vault.save({'APIFY_API_KEYS':'secret-apify-one\nsecret-apify-two','GEMINI_API_KEY':'secret-gemini','SMTP_PASSWORD':'secret-mail'})
  self.assertEqual(vault.get('APIFY_API_KEYS'),'secret-apify-one,secret-apify-two')
  self.assertEqual(vault.public()['apify_key_count'],2)
  self.assertNotIn('secret-gemini',json.dumps(vault.public()))
  self.assertNotIn('secret-mail',db.one('SELECT sealed FROM integrations')['sealed'])
  self.assertNotIn(b'secret-gemini',db.DB_PATH.read_bytes())
  vault.save({'GEMINI_API_KEY':''});self.assertEqual(vault.get('GEMINI_API_KEY'),'secret-gemini')
  vault.save({'clear_secrets':['GEMINI_API_KEY']});self.assertEqual(vault.get('GEMINI_API_KEY'),'')
 def test_lost_key_fails_closed(self):
  vault.save({'GEMINI_API_KEY':'abc'});(db.DB_PATH.parent/'vault.key').unlink()
  with self.assertRaises(ValueError):vault.get('GEMINI_API_KEY')
 def test_credentials_validation_no_partial_save(self):
  with self.assertRaises(ValueError):vault.save({'GEMINI_API_KEY':'secret','SMTP_PORT':'0'})
  self.assertFalse(db.one('SELECT * FROM integrations'))
 def test_ui_settings_no_restart(self):
  c=create_app().test_client();h={'X-API-Key':'test-token'}
  r=c.post('/api/connections',json={'GEMINI_API_KEY':'private-value','GEMINI_MODEL':'model-test'},headers=h);self.assertEqual(r.status_code,200)
  self.assertEqual(vault.get('GEMINI_MODEL'),'model-test')
  self.assertNotIn('private-value',c.get('/api/state',headers=h).text)
  self.assertEqual(c.post('/api/connections',json={}).status_code,401)
 def test_scrape_pauses_for_research(self):
  rid=pipeline.create({})
  for _ in range(15):pipeline.tick()
  self.assertEqual(db.one('SELECT status FROM runs')['status'],'awaiting_research')
  self.assertEqual(db.one("SELECT COUNT(*) n FROM leads WHERE research!='{}'")['n'],0)
  pipeline.start_research(rid,'CUSTOM PROMPT');pipeline.tick()
  self.assertGreater(db.one("SELECT COUNT(*) n FROM leads WHERE research!='{}'")['n'],0)
  self.assertEqual(json.loads(db.one('SELECT config FROM runs')['config'])['research_prompt'],'CUSTOM PROMPT')
 def test_owner_fallback_and_both(self):
  r=pipeline.demo_research(pipeline.fixtures(rules.config({}))[0])
  self.assertEqual(len(contacts.pick(r,'both')),2)
  self.assertEqual(contacts.pick(r,'prefer_owner')[0][0],'owner')
  r['decision_email_status']='probable';self.assertEqual(contacts.pick(r,'prefer_owner')[0][0],'business')
  self.assertEqual(contacts.pick(r,'owner_only'),[])
 def test_same_owner_business_address_once(self):
  r=pipeline.demo_research(pipeline.fixtures(rules.config({}))[0]);r['decision_email']=r['email']
  self.assertEqual(len(contacts.pick(r,'both')),1)
 def test_both_creates_separate_messages(self):
  rid=self.finish();db.save_setting('outreach',{**rules.TEMPLATE,'recipient_policy':'both'});self.assertEqual(outreach.drafts(rid),4)
  self.assertEqual(outreach.drafts(rid),0)
 def test_workbook_tabs_columns_and_formula_safety(self):
  rid=self.finish();lead=db.one('SELECT * FROM leads LIMIT 1');raw=json.loads(lead['raw']);raw['title']='=HYPERLINK("https://bad.example")';db.execute('UPDATE leads SET raw=? WHERE id=?',(json.dumps(raw),lead['id']))
  content=excel.workbook(rid);wb=load_workbook(io.BytesIO(content));self.assertEqual(wb.sheetnames,['Initial','Refined','Qualified','Outreach','Conversations'])
  self.assertEqual([c.value for c in wb['Refined'][1]][:8],excel.COLUMNS[:8]);self.assertEqual(wb['Initial']['A2'].data_type,'s')
  self.assertTrue((db.DB_PATH.parent/'exports'/f'discovery-{rid}.xlsx').exists())
 def test_export_endpoint(self):
  rid=self.finish();r=create_app().test_client().get(f'/api/runs/{rid}/export.xlsx',headers={'X-API-Key':'test-token'})
  self.assertEqual(r.status_code,200);self.assertTrue(r.data.startswith(b'PK'))
 def test_form_review_no_json(self):
  rid=self.finish();lead=db.one("SELECT * FROM leads WHERE status='qualified' LIMIT 1");r=json.loads(lead['research'])
  payload={**r,'source_urls':'\n'.join(s['url'] for s in r['sources']),'business_verified':True,'owner_verified':True,'name_verified':True,'confirmed':True,'approve':True}
  res=create_app().test_client().post(f"/api/leads/{lead['id']}/form-review",json=payload,headers={'X-API-Key':'test-token'})
  self.assertEqual(res.status_code,200,res.text)
 def test_reply_thread_match_and_duplicate(self):
  e=self.sent();raw=self.mail(e,e['message_id']);self.assertTrue(inbox.ingest(raw,vault.account_id(),'box','1',1));self.assertFalse(inbox.ingest(raw,vault.account_id(),'box','1',1))
  self.assertEqual(db.one('SELECT root_id FROM messages')['root_id'],e['id'])
 def test_unrelated_mail_not_imported(self):
  e=self.sent();self.assertFalse(inbox.ingest(self.mail(e,e['message_id'],'unknown@example.com'),vault.account_id(),'box','1',1));self.assertFalse(db.one('SELECT * FROM messages'))
 def test_unmatched_not_counted_replied(self):
  e=self.sent();inbox.ingest(self.mail(e),vault.account_id(),'box','1',1);m=db.one('SELECT * FROM messages');self.assertEqual(m['status'],'unmatched');self.assertIsNone(m['root_id'])
 def test_auto_reply_not_human_reply(self):
  e=self.sent();inbox.ingest(self.mail(e,e['message_id'],auto=True),vault.account_id(),'box','1',1);self.assertEqual(db.one('SELECT status FROM messages')['status'],'automatic')
 def test_reply_idempotency_and_thread_headers(self):
  e=self.sent();inbox.ingest(self.mail(e,e['message_id']),vault.account_id(),'box','1',1)
  with patch.dict(os.environ,{'EMAIL_PROVIDER':'smtp'}):
   mid=inbox.queue_reply(e['id'],'Here are details','reply-request-00001',True);self.assertEqual(mid,inbox.queue_reply(e['id'],'Here are details','reply-request-00001',True))
   smtp=Mock()
   with patch.object(mail_transport,'smtp_connection',return_value=smtp):inbox.deliver_reply()
   sent=smtp.send_message.call_args.args[0];self.assertEqual(sent['In-Reply-To'],'<incoming@test.example>');self.assertIn(e['message_id'],sent['References'])
  self.assertEqual(db.one('SELECT status FROM messages WHERE id=?',(mid,))['status'],'sent')
 def test_reply_connection_loss_not_retried(self):
  e=self.sent()
  with patch.dict(os.environ,{'EMAIL_PROVIDER':'smtp'}):
   mid=inbox.queue_reply(e['id'],'Hi','reply-request-00002',True);smtp=Mock();smtp.send_message.side_effect=ConnectionError()
   with patch.object(mail_transport,'smtp_connection',return_value=smtp):inbox.deliver_reply();inbox.deliver_reply()
  self.assertEqual(smtp.send_message.call_count,1);self.assertEqual(db.one('SELECT status FROM messages WHERE id=?',(mid,))['status'],'unknown')
 def test_suppression_blocks_chat_reply(self):
  e=self.sent();db.execute('INSERT INTO suppression VALUES(?,0)',(e['recipient'],))
  with patch.dict(os.environ,{'EMAIL_PROVIDER':'smtp'}):
   with self.assertRaises(ValueError):inbox.queue_reply(e['id'],'Hi','reply-request-00003',True)
 def test_account_change_blocks_old_queue(self):
  e=self.sent()
  with patch.dict(os.environ,{'EMAIL_PROVIDER':'smtp'}):
   mid=inbox.queue_reply(e['id'],'Hi','reply-request-00004',True)
   vault.save({'SMTP_FROM':'different@example.com'})
   with patch.object(mail_transport,'smtp_connection') as smtp:inbox.deliver_reply();smtp.assert_not_called()
  self.assertEqual(db.one('SELECT status FROM messages WHERE id=?',(mid,))['status'],'blocked')
 def test_demo_chat_stays_local(self):
  rid=self.finish();outreach.drafts(rid);outreach.queue(rid);outreach.deliver_one();e=db.one("SELECT * FROM emails WHERE status='simulated'")
  inbox.demo_reply(e['id']);mid=inbox.queue_reply(e['id'],'Thanks for replying','reply-request-00005')
  db.execute('UPDATE emails SET sent_at=0')
  with patch.object(mail_transport,'smtp_connection') as smtp:inbox.deliver_reply();smtp.assert_not_called()
  self.assertEqual(db.one('SELECT status FROM messages WHERE id=?',(mid,))['status'],'simulated')
 def test_html_inbox_is_plain_text(self):
  m=EmailMessage();m.set_content('<div>Hello <b>there</b></div><script>evil()</script>',subtype='html')
  text=inbox.text_body(m);self.assertIn('Hello there',text);self.assertNotIn('evil()',text);self.assertNotIn('<b>',text)
 def test_imap_readonly_uid_cursor(self):
  e=self.sent();vault.save({'IMAP_ENABLED':'true','IMAP_HOST':'imap.example.com','IMAP_USER':'me@example.com'})
  # SMTP account fingerprint is unchanged by changing inbox settings.
  raw=self.mail(e,e['message_id']);fake=Mock();fake.select.return_value=('OK',[b'1']);fake.response.return_value=('UIDVALIDITY',[b'7'])
  fake.uid.side_effect=[('OK',[b'1']),('OK',[(b'1 (RFC822.SIZE 500)',raw)]),('OK',[(b'1',raw)])]
  with patch.object(inbox,'connect',return_value=fake):result=inbox.sync()
  self.assertEqual(result['status'],'ok');fake.select.assert_called_once_with('"INBOX"',readonly=True)
  self.assertTrue(all('PEEK' in call.args[-1] for call in fake.uid.call_args_list if call.args[0]=='fetch'))
  self.assertEqual(db.one('SELECT last_uid FROM mailbox_state')['last_uid'],1)
 def test_migration_preserves_old_records(self):
  legacy=Path(self.tmp.name)/'legacy.sqlite3';db.DB_PATH=legacy
  with sqlite3.connect(legacy) as c:
   c.executescript("""CREATE TABLE emails(id INTEGER PRIMARY KEY,lead_id INTEGER,business_id INTEGER,recipient TEXT,subject TEXT,body TEXT,mode TEXT,status TEXT DEFAULT 'draft',attempts INTEGER DEFAULT 0,created REAL,sent_at REAL,next_at REAL DEFAULT 0,error TEXT DEFAULT '',message_id TEXT,UNIQUE(business_id,mode),UNIQUE(recipient,mode));
   INSERT INTO emails(id,business_id,recipient,mode,status) VALUES(25,7,'old@example.com','live','sent');""")
  db.init();self.assertEqual(db.one('SELECT * FROM emails WHERE id=25')['status'],'sent')
  db.execute("INSERT INTO emails(business_id,recipient,mode) VALUES(7,'owner@example.com','live')")
  self.assertEqual(db.one('SELECT COUNT(*) n FROM emails')['n'],2)
 def test_missing_contact_source_is_not_verified(self):
  r={'email':'public@example.com','email_status':'verified','sources':[{}, {'url':'javascript:alert(1)'}]}
  self.assertEqual(contacts.available(r),[])
if __name__=='__main__':unittest.main()
