import json, time, re
from flask import Blueprint, jsonify, request, Response
from . import db, vault, providers, pipeline, rules, contacts, excel, inbox, mail_transport
from .lock import pipeline_lock
bp=Blueprint('v2',__name__)
def busy():return jsonify(error='A background step is finishing. Please retry in a moment.'),409
@bp.get('/api/connections')
def connection_state():return jsonify(vault.public())
@bp.post('/api/connections')
def connection_save():
    with pipeline_lock() as ok:
        if not ok:return busy()
        result=vault.save(request.get_json())
    return jsonify(result)
@bp.post('/api/connections/test/<kind>')
def connection_test(kind):
    with pipeline_lock() as ok:
        if not ok:return busy()
        try:
            if kind=='apify':
                keys=providers.keys()
                if not keys:raise ValueError('Save an Apify key first')
                result=[]
                for kid,key in keys:
                    r=providers.request('GET','https://api.apify.com/v2/users/me',headers={'Authorization':'Bearer '+key})
                    result.append({'key_id':kid,'ok':r.ok,'http_status':r.status_code})
                return jsonify(results=result)
            if kind=='gemini':
                key=vault.get('GEMINI_API_KEY','')
                if not key:raise ValueError('Save your Gemini key first')
                r=providers.request('GET','https://generativelanguage.googleapis.com/v1beta/models',headers={'x-goog-api-key':key})
                if not r.ok:raise ValueError(f'Gemini authentication HTTP {r.status_code}')
                return jsonify(ok=True,message='Key accepted. Model/search support is checked on your research run.')
            if kind=='smtp':
                c=mail_transport.smtp_connection();c.close();return jsonify(ok=True,message='SMTP login worked. No message sent.')
            if kind=='imap':
                c=inbox.connect();c.logout();return jsonify(ok=True,message='IMAP login worked.')
            raise ValueError('Unknown integration')
        except Exception as exc:
            # Never return SMTP/IMAP exceptions that can include submitted credentials.
            return jsonify(error=f'{kind.upper()} connection failed ({type(exc).__name__}). Check saved settings and account permissions.'),400
@bp.post('/api/runs/<int:rid>/research')
def start_research(rid):
    data=request.get_json()
    with pipeline_lock() as ok:
        if not ok:return busy()
        pipeline.start_research(rid,data.get('prompt',''),data.get('model',''))
    return jsonify(ok=True)
@bp.get('/api/runs/<int:rid>/export.xlsx')
def export(rid):
    data=excel.workbook(rid)
    return Response(data,mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',headers={'Content-Disposition':f'attachment; filename=LeadPilot-discovery-{rid}.xlsx'})
@bp.post('/api/leads/<int:lid>/form-review')
def review_form(lid):
    data=request.get_json()
    with pipeline_lock() as ok:
        if not ok:return busy()
        lead=db.one('SELECT * FROM leads WHERE id=?',(lid,))
        if not lead:raise ValueError('Lead not found')
        result=json.loads(lead['research'])
        for field in ['decision_name','decision_position','decision_email','email','decision_email_source','email_source','facebook_url','instagram_url','linkedin_url','website_status','website_url','website_reason','custom_research_field']:
            if field in data:result[field]=str(data[field]).strip()[:3000]
        for field in ['identity_match','niche_match','location_match']:result[field]=data.get(field) is True
        for status,field,flag in [('email_status','email','business_verified'),('decision_email_status','decision_email','owner_verified'),('decision_status','decision_name','name_verified')]:
            result[status]='verified' if data.get(flag) is True and result.get(field) else ('probable' if result.get(field) else 'not_found')
        if 'source_urls' in data:
            urls=[u.strip() for u in str(data['source_urls']).splitlines() if u.strip()]
            if any(not u.startswith(('https://','http://')) for u in urls):raise ValueError('Source URLs must begin with https:// or http://')
            result['sources']=[{'url':u,'claim':'Operator-reviewed business evidence'} for u in dict.fromkeys(urls)]
        approve=data.get('approve') is True
        if approve and data.get('confirmed') is not True:raise ValueError('Confirm that you checked the evidence')
        pipeline.review(lid,result,approve)
    return jsonify(ok=True)
@bp.post('/api/runs/<int:rid>/reset-drafts')
def reset_drafts(rid):
    with pipeline_lock() as ok:
        if not ok:return busy()
        db.execute("DELETE FROM emails WHERE lead_id IN (SELECT id FROM leads WHERE run_id=?) AND status IN ('draft','blocked') AND NOT EXISTS (SELECT 1 FROM messages m WHERE m.root_id=emails.id)",(rid,))
        excel.mark(rid)
    return jsonify(ok=True)
@bp.get('/api/inbox')
def inbox_list():
    threads=db.all_rows("""SELECT e.*,l.raw,
      (SELECT COUNT(*) FROM messages m WHERE m.root_id=e.id AND m.direction='inbound' AND m.status='received') replies,
      (SELECT MAX(created) FROM messages m WHERE m.root_id=e.id) last_message
      FROM emails e JOIN leads l ON l.id=e.lead_id WHERE e.status IN ('sent','simulated','unknown')
      ORDER BY COALESCE(last_message,e.sent_at,e.created) DESC LIMIT 250""")
    for t in threads:t['business_name']=json.loads(t.pop('raw')).get('title','')
    unmatched=db.all_rows("SELECT * FROM messages WHERE root_id IS NULL AND direction='inbound' ORDER BY id DESC LIMIT 100")
    return jsonify(threads=threads,unmatched=unmatched,sync=db.setting('inbox_sync_status',{'status':'not_connected'}),enabled=vault.get('IMAP_ENABLED','false')=='true')
@bp.get('/api/inbox/<int:root>')
def conversation(root):
    record=db.one('SELECT * FROM emails WHERE id=?',(root,))
    if not record:raise ValueError('Conversation not found')
    return jsonify(initial=record,messages=db.all_rows('SELECT * FROM messages WHERE root_id=? ORDER BY created,id',(root,)))
@bp.post('/api/inbox/sync')
def request_sync():
    if vault.get('IMAP_ENABLED','false')!='true':raise ValueError('Enable inbox sync in Connections first')
    db.save_setting('inbox_sync_requested',True);return jsonify(ok=True,message='Inbox sync requested. Keep the app or worker running.')
@bp.post('/api/inbox/<int:root>/reply')
def reply(root):
    data=request.get_json()
    with pipeline_lock() as ok:
        if not ok:return busy()
        mid=inbox.queue_reply(root,data.get('body'),data.get('request_key'),data.get('confirm_live') is True)
    return jsonify(id=mid)
@bp.post('/api/inbox/<int:root>/demo-reply')
def demo_reply(root):
    with pipeline_lock() as ok:
        if not ok:return busy()
        inbox.demo_reply(root)
    return jsonify(ok=True)
@bp.post('/api/inbox/unmatched/<int:mid>/link')
def link_message(mid):
    root=int(request.get_json().get('root_id',0))
    with pipeline_lock() as ok:
        if not ok:return busy()
        m=db.one("SELECT * FROM messages WHERE id=? AND root_id IS NULL",(mid,))
        e=db.one('SELECT * FROM emails WHERE id=?',(root,))
        if not m or not e or e['recipient']!=m['sender'] or e['account_id']!=m['account_id']:raise ValueError('Choose a conversation with this exact sender and account')
        db.execute("UPDATE messages SET root_id=?,status=CASE WHEN status='automatic' THEN 'automatic' ELSE 'received' END WHERE id=?",(root,mid));inbox.mark_root(root)
    return jsonify(ok=True)
