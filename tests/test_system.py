import json, os, tempfile, unittest
from pathlib import Path
from unittest.mock import patch, Mock
os.environ.update(APP_SECRET='test-secret',ADMIN_PASSWORD='test-password',N8N_API_TOKEN='test-token',EMAIL_PROVIDER='dry_run')
from leadpilot import db, pipeline, rules, providers, outreach
from app import create_app
class SystemTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.old=db.DB_PATH;db.DB_PATH=Path(self.tmp.name)/'db.sqlite3';db.init()
  self.cfg=rules.config({});self.raw=pipeline.fixtures(self.cfg)[0];self.research=pipeline.demo_research(self.raw)
 def tearDown(self):db.DB_PATH=self.old;self.tmp.cleanup()
 def completed(self):
  rid=pipeline.create({})
  for _ in range(40):
   pipeline.tick()
   if db.one('SELECT status FROM runs WHERE id=?',(rid,))['status']=='awaiting_research':pipeline.start_research(rid,'Verify public contacts')
  self.assertEqual(db.one('SELECT status FROM runs WHERE id=?',(rid,))['status'],'complete');return rid
 def test_old_reviews(self):
  self.raw['reviews']=[{'publishedAtDate':'2020-01-01T00:00:00Z'}];self.assertIn('dated review',rules.basic(self.raw,self.cfg))
 def test_undated_future_reviews(self):
  for value in ['yesterday','2099-01-01T00:00:00Z',None]:
   self.raw['reviews']=[{'publishedAtDate':value}];self.assertTrue(rules.basic(self.raw,self.cfg))
 def test_thresholds(self):
  self.raw.update(totalScore=2,reviewsCount=30);self.assertEqual(rules.basic(self.raw,self.cfg),'')
  self.raw['reviewsCount']=29;self.assertTrue(rules.basic(self.raw,self.cfg))
 def test_closed_website(self):
  self.raw['closed']=True;self.assertTrue(rules.basic(self.raw,self.cfg));self.raw['closed']=False;self.raw['website']='https://business.test';self.assertTrue(rules.basic(self.raw,self.cfg))
 def test_manual_review_required(self):self.assertIn('human',rules.qualified(self.raw,self.research,self.cfg))
 def test_two_sources(self):
  self.research['sources']=self.research['sources'][:1];self.assertIn('two',rules.qualified(self.raw,self.research,self.cfg,True))
 def test_probable_email(self):
  self.research['email_status']='probable';self.research['decision_email_status']='probable';self.assertIn('Verify',rules.qualified(self.raw,self.research,self.cfg,True))
 def test_location(self):
  self.research['location_match']=False;self.assertIn('location',rules.qualified(self.raw,self.research,self.cfg,True))
 def test_no_name_fabrication(self):
  self.research['decision_status']='probable';_,body=rules.personalize(self.raw,self.research,self.cfg,rules.TEMPLATE);self.assertTrue(body.startswith('Hi there,'))
 def test_template_variable(self):
  with self.assertRaises(ValueError):outreach.template({'subject':'{{InventedName}}'})
 def test_branch_identity(self):self.assertNotEqual(rules.identity(self.raw),rules.identity({**self.raw,'placeId':'another'}))
 def test_duplicate_ingestion(self):
  rid=pipeline.create({});pipeline.ingest(rid,[self.raw,self.raw]);self.assertEqual(db.one('SELECT COUNT(*) n FROM leads')['n'],1)
 def test_idempotent_create(self):
  self.assertEqual(pipeline.create({},'abc'),pipeline.create({},'abc'))
  with self.assertRaises(ValueError):pipeline.create({'niche':'dentist'},'abc')
 def test_complete_demo_resume(self):
  self.completed();before=db.one('SELECT COUNT(*) n FROM leads')['n'];pipeline.tick();self.assertEqual(db.one('SELECT COUNT(*) n FROM leads')['n'],before)
  self.assertGreater(db.one("SELECT COUNT(*) n FROM leads WHERE status='qualified'")['n'],0)
 def test_send_dedup_across_runs(self):
  first=self.completed();self.assertGreater(outreach.drafts(first),0);self.assertEqual(outreach.drafts(first),0)
  second=self.completed();self.assertEqual(outreach.drafts(second),0)
 def test_demo_cannot_send_live(self):
  rid=self.completed()
  with patch.dict(os.environ,{'EMAIL_PROVIDER':'smtp'}):
   outreach.drafts(rid);outreach.queue(rid)
   with patch('smtplib.SMTP') as smtp:pipeline.tick();smtp.assert_not_called()
  self.assertTrue(db.one("SELECT id FROM emails WHERE status='simulated'"));self.assertTrue(list((db.DB_PATH.parent/'outbox').glob('*.eml')))
 def test_suppression(self):
  rid=self.completed();outreach.drafts(rid);outreach.queue(rid)
  e=db.one('SELECT * FROM emails LIMIT 1');db.execute('INSERT INTO suppression VALUES(?,0)',(e['recipient'],));pipeline.tick()
  self.assertEqual(db.one('SELECT status FROM emails WHERE id=?',(e['id'],))['status'],'blocked')
 def test_sending_recovery(self):
  rid=self.completed();outreach.drafts(rid);e=db.one('SELECT * FROM emails LIMIT 1');db.execute("UPDATE emails SET status='sending' WHERE id=?",(e['id'],));pipeline.tick()
  self.assertEqual(db.one('SELECT status FROM emails WHERE id=?',(e['id'],))['status'],'unknown')
 def test_expired_activity_blocks_send(self):
  rid=self.completed();outreach.drafts(rid);outreach.queue(rid);e=db.one('SELECT * FROM emails LIMIT 1');l=db.one('SELECT * FROM leads WHERE id=?',(e['lead_id'],));raw=json.loads(l['raw']);raw['reviews'][0]['publishedAtDate']='2020-01-01';db.execute('UPDATE leads SET raw=? WHERE id=?',(json.dumps(raw),l['id']));pipeline.tick();self.assertEqual(db.one('SELECT status FROM emails WHERE id=?',(e['id'],))['status'],'blocked')
 def test_smtp_ambiguous(self):
  rid=self.completed();outreach.drafts(rid);e=db.one('SELECT * FROM emails LIMIT 1')
  db.execute('UPDATE runs SET config=? WHERE id=?',(json.dumps({**self.cfg,'mode':'live'}),rid));db.execute("UPDATE emails SET mode='live',status='pending' WHERE id=?",(e['id'],))
  smtp=Mock();smtp.send_message.side_effect=ConnectionError()
  with patch.dict(os.environ,{'EMAIL_PROVIDER':'smtp','SMTP_SECURITY':'starttls'}),patch('leadpilot.mail_transport.smtp_connection',return_value=smtp):pipeline.tick();pipeline.tick()
  self.assertEqual(smtp.send_message.call_count,1);self.assertEqual(db.one('SELECT status FROM emails WHERE id=?',(e['id'],))['status'],'unknown')
 def test_actor_unknown(self):
  rid=pipeline.create({'mode':'live'})
  with patch.object(providers,'start_actor',side_effect=providers.AmbiguousStart('Unknown')) as start:pipeline.tick();pipeline.tick();self.assertEqual(start.call_count,1)
  self.assertEqual(db.one('SELECT status FROM runs WHERE id=?',(rid,))['status'],'start_unknown')
 def test_key_failover(self):
  bad=Mock(status_code=401,headers={});good=Mock(status_code=201,ok=True);good.json.return_value={'data':{'id':'run1'}}
  with patch.dict(os.environ,{'APIFY_API_KEYS':'key-a,key-b'}),patch.object(providers,'request',side_effect=[bad,good]):
   actor,kid=providers.start_actor(self.cfg);self.assertEqual(actor,'run1');self.assertEqual(db.one("SELECT COUNT(*) n FROM keys WHERE status='disabled'")['n'],1)
 def test_original_run_key(self):
  with patch.dict(os.environ,{'APIFY_API_KEYS':'key-a,key-b'}):
   kid=providers.keys()[1][0];response=Mock(ok=True,status_code=200);response.json.return_value={'data':{}}
   with patch.object(providers,'request',return_value=response) as call:
    providers.apify_get('actor-runs/abc',kid);self.assertEqual(call.call_args.kwargs['headers']['Authorization'],'Bearer key-b')
 def test_grounding_required(self):
  response=Mock(ok=True,status_code=200);response.json.return_value={'candidates':[{'content':{'parts':[{'text':json.dumps(self.research)}]}}]}
  with patch.dict(os.environ,{'GEMINI_API_KEY':'secret'}),patch.object(providers,'request',return_value=response):r=providers.research(self.raw,self.cfg)
  self.assertEqual(r['website_status'],'unknown');self.assertEqual(r['email_status'],'probable')
 def test_auth_csrf_and_template(self):
  c=create_app().test_client();self.assertEqual(c.get('/api/state').status_code,401);c.get('/login')
  with c.session_transaction() as s: token=s['login_csrf']
  self.assertEqual(c.post('/login',data={'password':'test-password','csrf':token}).status_code,302)
  self.assertEqual(c.post('/api/runs',json={}).status_code,403)
  with c.session_transaction() as s: token=s['csrf']
  self.assertEqual(c.post('/api/runs',json={},headers={'X-CSRF-Token':token}).status_code,201);self.assertEqual(c.get('/').status_code,200)
 def test_api_no_secrets(self):
  c=create_app().test_client();r=c.get('/api/state',headers={'X-API-Key':'test-token'});self.assertEqual(r.status_code,200);self.assertNotIn('test-token',r.text)
 def test_live_confirmation(self):
  rid=self.completed();outreach.drafts(rid);db.execute("UPDATE emails SET mode='live'")
  with self.assertRaises(ValueError):outreach.queue(rid)
 def test_target_cap(self):
  rid=pipeline.create({'lead_count':1})
  for _ in range(30):
   pipeline.tick()
   if db.one('SELECT status FROM runs WHERE id=?',(rid,))['status']=='awaiting_research':pipeline.start_research(rid,'Verify')
  self.assertEqual(db.one("SELECT COUNT(*) n FROM leads WHERE status='qualified'")['n'],1)
 def test_website_conflict(self):
  self.research['website_url']='https://business.example';self.assertIn('conflicts',rules.qualified(self.raw,self.research,self.cfg,True))
 def test_sheet_projection_idempotent_and_clear(self):
  from google.oauth2 import service_account
  from google.auth.transport.requests import AuthorizedSession
  rid=self.completed();lead=db.one("SELECT * FROM leads WHERE status='qualified' LIMIT 1")
  cfg={**self.cfg,'mode':'live','sync_sheets':True};session=Mock();session.put.return_value=Mock(ok=True)
  with patch.dict(os.environ,{'INITIAL_SHEET_ID':'initial','QUALIFIED_SHEET_ID':'qualified'}),patch.object(service_account.Credentials,'from_service_account_file',return_value=Mock()),patch('google.auth.transport.requests.AuthorizedSession',return_value=session):
   providers.sync_sheet(lead,cfg,True);providers.sync_sheet(lead,cfg,True)
   self.assertEqual(session.put.call_args_list[1].args[0],session.put.call_args_list[3].args[0])
   self.assertEqual(session.put.call_args.kwargs['params']['valueInputOption'],'RAW')
   lead['status']='review';providers.sync_sheet(lead,cfg,True)
   self.assertEqual(session.put.call_args.kwargs['json']['values'],[['']*24])
 def test_review_downgrade_schedules_clear(self):
  rid=self.completed();lead=db.one("SELECT * FROM leads WHERE status='qualified' LIMIT 1")
  self.assertEqual(lead['sheet_present'],1)
  pipeline.review(lead['id'],json.loads(lead['research']),False)
  pipeline.tick()
  changed=db.one('SELECT * FROM leads WHERE id=?',(lead['id'],))
  self.assertEqual(changed['sheet_present'],0);self.assertEqual(changed['status'],'review')
if __name__=='__main__':unittest.main()
