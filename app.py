import csv, hmac, io, json, os, re, secrets, time
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent/'.env')
from flask import Flask, Response, jsonify, redirect, render_template, request, session
from leadpilot import db, pipeline, providers, rules, outreach, vault, contacts
from leadpilot.lock import pipeline_lock

def create_app():
    app=Flask(__name__)
    app.secret_key=os.getenv('APP_SECRET')
    if not app.secret_key or not os.getenv('ADMIN_PASSWORD') or not os.getenv('N8N_API_TOKEN'):
        raise RuntimeError('Run python setup_local.py first')
    app.config.update(MAX_CONTENT_LENGTH=4*1024*1024,SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE='Strict',
        SESSION_COOKIE_SECURE=os.getenv('COOKIE_SECURE','false').lower()=='true',PERMANENT_SESSION_LIFETIME=28800)
    db.init(); attempts={}
    @app.before_request
    def protect():
        if request.path.startswith('/static/') or request.path in ('/login','/health','/unsubscribe'): return
        token=request.headers.get('X-API-Key','')
        if token and hmac.compare_digest(token,os.environ['N8N_API_TOKEN']) and request.path.startswith('/api/'): return
        if not session.get('user'):
            return (jsonify(error='Login required'),401) if request.path.startswith('/api/') else redirect('/login')
        if request.method not in ('GET','HEAD','OPTIONS'):
            if not hmac.compare_digest(request.headers.get('X-CSRF-Token',''),session.get('csrf','!')): return jsonify(error='Invalid CSRF token'),403
    @app.after_request
    def headers(response):
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['X-Frame-Options']='SAMEORIGIN'
        response.headers['Referrer-Policy']='no-referrer'
        response.headers.setdefault('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; frame-src 'self'; frame-ancestors 'self'; form-action 'self'; base-uri 'none'")
        response.headers['Cache-Control']='no-store'
        return response
    @app.errorhandler(ValueError)
    def bad_request(exc): return jsonify(error=str(exc)),400
    @app.errorhandler(500)
    def internal(exc): return jsonify(error='Internal error. Check terminal and retry the saved stage.'),500
    @app.get('/health')
    def health(): return jsonify(status='ok')
    @app.route('/login',methods=['GET','POST'])
    def login():
        error=''; session.setdefault('login_csrf',secrets.token_urlsafe(32))
        if request.method=='POST':
            ip=request.remote_addr; now=time.time(); seen=[t for t in attempts.get(ip,[]) if now-t<600]
            attempts[ip]=seen
            if len(seen)>=10: return render_template('login.html',error='Too many attempts. Wait 10 minutes.'),429
            if not hmac.compare_digest(request.form.get('csrf',''),session['login_csrf']): return 'Invalid form token',403
            seen.append(now)
            if hmac.compare_digest(request.form.get('password',''),os.environ['ADMIN_PASSWORD']):
                session.clear(); session.update(user=True,csrf=secrets.token_urlsafe(32)); session.permanent=True
                attempts.pop(ip,None); return redirect('/')
            error='Incorrect password'
        return render_template('login.html',error=error)
    @app.post('/api/logout')
    def logout(): session.clear(); return jsonify(ok=True)
    @app.get('/')
    def index(): return render_template('index.html',csrf=session['csrf'])
    @app.get('/api/state')
    def state():
        providers.keys()
        runs=db.all_rows('SELECT * FROM runs ORDER BY id DESC LIMIT 100')
        for r in runs:
            r['config']=json.loads(r['config'])
            r['counts']={x['status']:x['n'] for x in db.all_rows('SELECT status,COUNT(*) n FROM leads WHERE run_id=? GROUP BY status',(r['id'],))}
        return jsonify(runs=runs,keys=db.all_rows('SELECT * FROM keys'),template=db.setting('outreach',rules.TEMPLATE),defaults=rules.DEFAULTS,
          integrations=vault.public(),
          stats={'qualified':db.one("SELECT COUNT(*) n FROM leads WHERE status='qualified'")['n'],
            'review':db.one("SELECT COUNT(*) n FROM leads WHERE status='review'")['n'],
            'sent':db.one("SELECT COUNT(*) n FROM emails WHERE status='sent'")['n'],
            'simulated':db.one("SELECT COUNT(*) n FROM emails WHERE status='simulated'")['n']})
    @app.post('/api/runs')
    def create_run():
        data=request.get_json(); key=request.headers.get('Idempotency-Key') or data.pop('request_key',None)
        with pipeline_lock() as acquired:
            if not acquired: return jsonify(error='Worker busy; retry shortly'),409
            rid=pipeline.create(data,key)
        return jsonify(id=rid),201
    @app.get('/api/runs/<int:rid>')
    def detail(rid):
        run=db.one('SELECT * FROM runs WHERE id=?',(rid,))
        if not run: return jsonify(error='Run not found'),404
        run['config']=json.loads(run['config'])
        leads=db.all_rows('SELECT * FROM leads WHERE run_id=? ORDER BY id',(rid,))
        for lead in leads:
            lead['raw']=json.loads(lead['raw']); lead['research']=json.loads(lead['research'])
            lead['selected_recipients']=contacts.pick(lead['research'],db.setting('outreach',{}).get('recipient_policy','prefer_owner'))
        return jsonify(run=run,leads=leads,logs=db.all_rows('SELECT * FROM logs WHERE run_id=? ORDER BY id DESC LIMIT 200',(rid,)),
            emails=db.all_rows('SELECT e.* FROM emails e JOIN leads l ON e.lead_id=l.id WHERE l.run_id=? ORDER BY e.id',(rid,)))
    @app.post('/api/tick')
    def tick(): return jsonify(pipeline.tick())
    @app.post('/api/runs/<int:rid>/resume')
    def resume(rid):
        with pipeline_lock() as acquired:
            if not acquired: return jsonify(error='Worker busy'),409
            run=db.one('SELECT * FROM runs WHERE id=?',(rid,))
            if not run: raise ValueError('Run not found')
            if run['status']=='start_unknown': raise ValueError('Attach existing Apify run before resuming; prevents duplicate paid runs')
            db.execute("UPDATE runs SET status='running',attempts=0,next_at=0,error='' WHERE id=? AND status='failed'",(rid,))
        return jsonify(ok=True)
    @app.post('/api/runs/<int:rid>/attach')
    def attach(rid):
        data=request.get_json(); actor=str(data.get('actor_run','')); kid=str(data.get('key_id',''))
        if not re.fullmatch(r'[A-Za-z0-9_-]{3,100}',actor) or kid not in dict(providers.keys()): raise ValueError('Valid actor run ID and configured key ID are required')
        with pipeline_lock() as acquired:
            if not acquired: return jsonify(error='Worker busy'),409
            run=db.one('SELECT * FROM runs WHERE id=?',(rid,))
            if not run or run['stage'] not in ('scrape','poll'): raise ValueError('Only an unstarted/polling run can be attached')
            # Verify that the token can access the run before changing the binding.
            try: providers.apify_get('actor-runs/'+actor,kid)
            except providers.ProviderError as exc: raise ValueError(str(exc)) from None
            db.execute("UPDATE runs SET actor_run=?,key_id=?,stage='poll',status='running',attempts=0,next_at=0,error='' WHERE id=?",(actor,kid,rid))
        return jsonify(ok=True)
    @app.post('/api/runs/<int:rid>/import')
    def import_dataset(rid):
        items=request.get_json().get('items')
        if not isinstance(items,list) or len(items)>1500: raise ValueError('items must be an Apify dataset array (max 1500)')
        with pipeline_lock() as acquired:
            if not acquired: return jsonify(error='Worker busy'),409
            run=db.one('SELECT * FROM runs WHERE id=?',(rid,))
            if not run or run['stage']!='scrape' or run['status'] not in ('queued','start_unknown','failed'): raise ValueError('Import requires a run that has not scraped yet')
            pipeline.ingest(rid,items)
            db.execute("UPDATE runs SET status='running',stage='initial',error='',attempts=0 WHERE id=?",(rid,))
        return jsonify(ok=True)
    @app.post('/api/leads/<int:lid>/review')
    def review(lid):
        data=request.get_json()
        with pipeline_lock() as acquired:
            if not acquired: return jsonify(error='Worker busy; retry shortly'),409
            pipeline.review(lid,data.get('research'),data.get('approve') is True)
        return jsonify(ok=True)
    @app.get('/api/leads/<int:lid>/grounding')
    def grounding(lid):
        lead=db.one('SELECT research FROM leads WHERE id=?',(lid,))
        if not lead: return 'Not found',404
        rendered=json.loads(lead['research']).get('grounding',{}).get('searchEntryPoint',{}).get('renderedContent','No Search Suggestions returned.')
        response=Response(rendered,mimetype='text/html')
        response.headers['Content-Security-Policy']="default-src 'none'; style-src 'unsafe-inline'; img-src https: data:; sandbox allow-popups allow-popups-to-escape-sandbox"
        return response
    @app.post('/api/template')
    def save_template(): db.save_setting('outreach',outreach.template(request.get_json())); return jsonify(ok=True)
    @app.post('/api/runs/<int:rid>/drafts')
    def drafts(rid):
        with pipeline_lock() as acquired:
            if not acquired: return jsonify(error='Worker busy'),409
            n=outreach.drafts(rid)
        return jsonify(created=n)
    @app.post('/api/runs/<int:rid>/queue')
    def queue(rid):
        with pipeline_lock() as acquired:
            if not acquired: return jsonify(error='Worker busy'),409
            n=outreach.queue(rid,request.get_json().get('confirm_live') is True)
        return jsonify(queued=n)
    @app.post('/api/keys/reset')
    def key_reset():
        db.execute("UPDATE keys SET status='ready',until=0 WHERE id=?",(request.get_json().get('id'),)); return jsonify(ok=True)
    @app.post('/api/suppress')
    def suppress():
        email=str(request.get_json().get('email','')).strip().lower()
        if not rules.valid_email(email): raise ValueError('Invalid email')
        db.execute('INSERT OR IGNORE INTO suppression VALUES(?,?)',(email,time.time())); return jsonify(ok=True)
    @app.route('/unsubscribe',methods=['GET','POST'])
    def unsubscribe():
        email=request.args.get('email',''); token=request.args.get('token','')
        if not hmac.compare_digest(token,outreach.unsubscribe_token(email)): return 'Invalid unsubscribe link',400
        if request.method=='POST':
            db.execute('INSERT OR IGNORE INTO suppression VALUES(?,?)',(email,time.time()))
            return 'You have been unsubscribed.'
        return '<!doctype html><title>Unsubscribe</title><form method="post"><p>Stop receiving emails from this sender?</p><button>Unsubscribe</button></form>'
    @app.get('/api/runs/<int:rid>/export.csv')
    def export(rid):
        run=db.one('SELECT config FROM runs WHERE id=?',(rid,))
        if not run: return jsonify(error='Run not found'),404
        cfg=json.loads(run['config']); out=io.StringIO(); writer=csv.writer(out); writer.writerow(providers.COLUMNS)
        sql='SELECT * FROM leads WHERE run_id=?'+(" AND status='qualified'" if request.args.get('qualified')=='true' else '')
        for lead in db.all_rows(sql,(rid,)):
            row=providers.sheet_row(lead,cfg)
            writer.writerow(["'"+str(v) if str(v).startswith(('=','+','-','@','\t','\r')) else v for v in row])
        return Response(out.getvalue(),mimetype='text/csv',headers={'Content-Disposition':f'attachment; filename=leads-{rid}.csv'})
    from leadpilot.web_v2 import bp
    app.register_blueprint(bp)
    return app

if __name__=='__main__':
    from waitress import serve
    print('LeadPilot: http://127.0.0.1:'+os.getenv('PORT','8000'))
    serve(create_app(),host=os.getenv('BIND_HOST','127.0.0.1'),port=int(os.getenv('PORT','8000')),threads=8)
