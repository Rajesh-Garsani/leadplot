import json, time
from datetime import datetime, timedelta, timezone
from . import db, providers, rules, outreach, excel, inbox, vault
from .lock import pipeline_lock

def create(data,request_key=None):
    cfg=rules.config(data)
    cfg['sync_sheets']=False # v2 uses automatic local Excel; no Sheets credentials required
    if request_key:
        existing=db.one('SELECT * FROM runs WHERE request_key=?',(request_key,))
        if existing:
            if json.loads(existing['config'])!=cfg: raise ValueError('Idempotency key reused with different settings')
            return existing['id']
    return db.execute('INSERT INTO runs(request_key,config,created) VALUES(?,?,?)',(request_key,json.dumps(cfg),time.time()))

def ingest(run_id,items):
    run=db.one('SELECT config FROM runs WHERE id=?',(run_id,))
    if not run: raise ValueError('Run not found')
    cfg=json.loads(run['config'])
    checked_at=datetime.now(timezone.utc)
    for raw in items:
        if not isinstance(raw,dict): continue
        # Filter before creating either a business identity or a lead record.
        # Dataset offsets still count all fetched items, including skipped ones.
        if rules.basic(raw,cfg,now=checked_at): continue
        ident=rules.identity(raw)
        with db.connect() as c:
            c.execute('INSERT OR IGNORE INTO businesses(identity) VALUES(?)',(ident,))
            bid=c.execute('SELECT id FROM businesses WHERE identity=?',(ident,)).fetchone()[0]
            c.execute('INSERT OR IGNORE INTO leads(run_id,business_id,raw) VALUES(?,?,?)',(run_id,bid,json.dumps(raw)))

def fixtures(cfg):
    now=datetime.now(timezone.utc)
    rows=[]
    for i in range(min(cfg['lead_count']*3,7)):
        rows.append({'placeId':f'DEMO-{i}','title':f'Demo {cfg["niche"]} {i+1}','categoryName':cfg['niche'],
          'address':f'{i+1} Sample Street, {cfg["location"]}','phone':'+1 202-555-01'+str(i).zfill(2),
          'url':f'https://example.test/maps/{i}','totalScore':4.6,'reviewsCount':75,
          'website':'https://example.test' if i==2 else '',
          'reviews':[{'publishedAtDate':(now-timedelta(days=90 if i==3 else 2)).isoformat()}],
          '_demo_index':i})
    return rows

def demo_research(raw):
    i=raw['_demo_index']
    return {'website_status':'exists' if i==4 else 'no_website_found','website_reason':'Synthetic demo evidence. Not real businesses.',
       'identity_match':True,'niche_match':True,'location_match':True,'email':f'demo{i}@example.test' if i!=5 else '',
       'email_status':'verified' if i!=5 else 'not_found','email_source':'https://directory.example.test/business',
       'decision_email':f'owner{i}@example.test' if i==0 else '', 'decision_email_status':'verified' if i==0 else 'not_found', 'decision_email_source':'https://directory.example.test/business',
       'decision_name':'Alex Example' if i==0 else '', 'decision_position':'Owner' if i==0 else '',
       'decision_status':'verified' if i==0 else 'not_found',
       'sources':[{'url':'https://directory.example.test/business','claim':'Synthetic business directory'},
                  {'url':'https://social.example.org/business','claim':'Synthetic social profile'}]}

def reset_progress(run_id,stage=None):
    if stage: db.execute('UPDATE runs SET stage=?,attempts=0,next_at=0,error=? WHERE id=?',(stage,'',run_id))
    else: db.execute('UPDATE runs SET attempts=0,next_at=0,error=? WHERE id=?',('',run_id))

def process(run):
    rid=run['id']; cfg=json.loads(run['config']); stage=run['stage']
    if stage=='scrape':
        if cfg['mode']=='demo':
            ingest(rid,fixtures(cfg)); reset_progress(rid,'initial'); return
        # Persist intent first: a crash between provider acceptance and local save must not start a second actor.
        db.execute("UPDATE runs SET status='start_unknown' WHERE id=?",(rid,))
        try: actor,kid=providers.start_actor(cfg)
        except providers.AmbiguousStart: raise
        except providers.ProviderError:
            db.execute("UPDATE runs SET status='running' WHERE id=?",(rid,)); raise
        except Exception:
            raise providers.AmbiguousStart('Unexpected actor-start failure; inspect Apify before resuming') from None
        db.execute("UPDATE runs SET actor_run=?,key_id=?,stage='poll',status='running',attempts=0,error='' WHERE id=?",(actor,kid,rid))
        db.log(rid,None,'scrape','started',f'Apify run {actor}; key {kid}'); return
    if stage=='poll':
        data=providers.apify_get('actor-runs/'+run['actor_run'],run['key_id'])['data']
        if data['status'] in ('FAILED','TIMED-OUT','ABORTED'): raise providers.ProviderError('Apify run '+data['status']+'; inspect Apify and attach a successful run if needed')
        if data['status']!='SUCCEEDED':
            db.execute('UPDATE runs SET next_at=? WHERE id=?',(time.time()+10,rid)); return
        db.execute("UPDATE runs SET dataset=?,stage='dataset',attempts=0 WHERE id=?",(data['defaultDatasetId'],rid)); return
    if stage=='dataset':
        items=providers.apify_get('datasets/'+run['dataset']+'/items',run['key_id'],{'clean':'true','format':'json','offset':run['offset'],'limit':100})
        if not isinstance(items,list): raise providers.ProviderError('Unexpected dataset response')
        ingest(rid,items)
        db.execute('UPDATE runs SET offset=offset+?,attempts=0 WHERE id=?',(len(items),rid))
        if len(items)<100: reset_progress(rid,'initial')
        return
    if stage=='initial':
        lead=db.one('SELECT * FROM leads WHERE run_id=? AND initial_synced=0 ORDER BY id LIMIT 1',(rid,))
        if not lead:
            reset_progress(rid,'research')
            if cfg.get('manual_research',True):db.execute("UPDATE runs SET status='awaiting_research' WHERE id=?",(rid,))
            excel.mark(rid)
            return
        # Local Excel replaces remote Sheet writes.
        reason=rules.basic(json.loads(lead['raw']),cfg)
        db.execute('UPDATE leads SET initial_synced=1,status=?,reason=? WHERE id=?',('rejected' if reason else 'research_pending',reason,lead['id']))
        db.log(rid,lead['id'],'initial','rejected' if reason else 'passed',reason); reset_progress(rid); return
    if stage=='research':
        lead=db.one("SELECT * FROM leads WHERE run_id=? AND status='research_pending' ORDER BY id LIMIT 1",(rid,))
        if not lead: reset_progress(rid,'qualified_sheet'); return
        raw=json.loads(lead['raw'])
        result=demo_research(raw) if cfg['mode']=='demo' else providers.research(raw,cfg)
        reviewed=cfg['mode']=='demo'
        reason=rules.qualified(raw,result,cfg,reviewed)
        if result.get('website_status') in ('exists','broken'): status='rejected'
        else: status='review' if reason else 'qualified'
        # Qualification cap; keep additional candidates available for manual review.
        qualified_count=db.one("SELECT COUNT(*) n FROM leads WHERE run_id=? AND status='qualified'",(rid,))['n']
        if status=='qualified' and qualified_count>=cfg['lead_count']: status='review'; reason='Target count reached'
        db.execute('UPDATE leads SET research=?,status=?,reason=?,reviewed=?,email=? WHERE id=?',
           (json.dumps(result),status,reason,int(reviewed),str(result.get('email') or '').strip().lower(),lead['id']))
        db.log(rid,lead['id'],'research',status,reason); reset_progress(rid); return
    if stage=='qualified_sheet':
        lead=db.one("SELECT * FROM leads WHERE run_id=? AND (status='qualified' OR sheet_present=1) AND qualified_synced=0 ORDER BY id LIMIT 1",(rid,))
        if lead:
            # Local Excel is rebuilt from the authoritative database.
            db.execute('UPDATE leads SET qualified_synced=1,sheet_present=? WHERE id=?',(int(lead['status']=='qualified'),lead['id'])); reset_progress(rid); return
        db.execute("UPDATE runs SET status='complete',attempts=0,error='' WHERE id=?",(rid,))
        db.log(rid,None,'pipeline','complete','Review candidates, then generate email previews')

def review(lead_id,result,approve):
    lead=db.one('SELECT * FROM leads WHERE id=?',(lead_id,))
    if not lead: raise ValueError('Lead not found')
    cfg=json.loads(db.one('SELECT config FROM runs WHERE id=?',(lead['run_id'],))['config'])
    if db.one("SELECT id FROM emails WHERE lead_id=? AND status NOT IN ('draft','blocked')",(lead_id,)): raise ValueError('Cannot edit evidence after email queueing; suppress the address if necessary')
    if not isinstance(result,dict): raise ValueError('Evidence must be a JSON object')
    if approve:
        reason=rules.qualified(json.loads(lead['raw']),result,cfg,True)
        if reason: raise ValueError(reason)
        count=db.one("SELECT COUNT(*) n FROM leads WHERE run_id=? AND status='qualified' AND id<>?",(lead['run_id'],lead_id))['n']
        if count>=cfg['lead_count']: raise ValueError('Qualified lead target already reached')
    status='qualified' if approve else 'review'
    db.execute('UPDATE leads SET research=?,email=?,status=?,reason=?,reviewed=?,reviewed_at=?,qualified_synced=0 WHERE id=?',
       (json.dumps(result),str(result.get('email') or '').strip().lower(),status,'' if approve else 'Saved for review',int(approve),time.time(),lead_id))
    db.execute("DELETE FROM emails WHERE lead_id=? AND status IN ('draft','blocked')",(lead_id,))
    # Update/clear an existing projection on next tick; preserve ongoing research stage.
    db.execute("UPDATE runs SET status='running',stage=CASE WHEN status='complete' THEN 'qualified_sheet' ELSE stage END WHERE id=? AND status IN ('complete','running','queued')",(lead['run_id'],))
    excel.mark(lead['run_id'])
    db.log(lead['run_id'],lead_id,'review',status,'Operator reviewed source evidence' if approve else 'Evidence saved')

def tick():
    with pipeline_lock() as locked:
        if not locked: return {'status':'busy'}
        db.execute("UPDATE messages SET status='unknown',error='Interrupted during delivery; check provider' WHERE direction='outbound' AND status='sending'")
        # Only one worker can reach this point. Leftover sending means previous process crashed.
        db.execute("UPDATE emails SET status='unknown',error='Worker interrupted during send; check provider before any resend' WHERE status='sending'")
        for run in db.all_rows("SELECT * FROM runs WHERE status IN ('queued','running') AND next_at<=? ORDER BY id LIMIT 1",(time.time(),)):
            db.execute("UPDATE runs SET status='running' WHERE id=?",(run['id'],))
            try:
                process(run)
                excel.mark(run['id'])
            except providers.AmbiguousStart as exc:
                db.execute("UPDATE runs SET status='start_unknown',error=? WHERE id=?",(str(exc),run['id']))
                db.log(run['id'],None,run['stage'],'start_unknown',str(exc))
            except Exception as exc:
                # Never persist provider response bodies/URLs or secret-bearing exception strings.
                message=str(exc) if isinstance(exc,providers.ProviderError) else type(exc).__name__+'; see troubleshooting guide'
                attempts=run['attempts']+1
                current=db.one('SELECT status FROM runs WHERE id=?',(run['id'],))
                if current['status']=='start_unknown':
                    db.execute('UPDATE runs SET error=? WHERE id=?',('Actor start uncertain; inspect Apify before resuming',run['id']))
                    continue
                db.execute('UPDATE runs SET status=?,attempts=?,next_at=?,error=? WHERE id=?',
                   ('failed' if attempts>=3 else 'running',attempts,time.time()+30*2**attempts,message,run['id']))
                db.log(run['id'],None,run['stage'],'error',message)
        inbox.deliver_reply()
        outreach.deliver_one()
        if vault.get('IMAP_ENABLED','false')=='true' and (db.setting('inbox_sync_requested',False) or time.time()-db.setting('inbox_last_attempt',0)>60):
            db.save_setting('inbox_last_attempt',time.time());db.save_setting('inbox_sync_requested',False);inbox.sync()
        excel.flush()
        return {'status':'processed'}

def start_research(run_id,prompt,model=''):
    run=db.one('SELECT * FROM runs WHERE id=?',(run_id,))
    if not run:raise ValueError('Discovery not found')
    if run['status'] not in ('awaiting_research','failed'):raise ValueError('Wait until scraping finishes before starting research')
    if run['stage']!='research':raise ValueError('This failure belongs to another stage; use Resume')
    cfg=json.loads(run['config']);cfg['research_prompt']=str(prompt).strip()[:5000];cfg['model']=str(model).strip()[:100]
    if cfg['mode']=='live' and not vault.get('GEMINI_API_KEY'):raise ValueError('Save your Gemini API key in Connections first')
    db.execute("UPDATE runs SET config=?,status='running',attempts=0,next_at=0,error='' WHERE id=?",(json.dumps(cfg),run_id))
