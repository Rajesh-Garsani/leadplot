"""Local Excel projections. Database state is authoritative; never import formulas."""
import io, json, os, re, tempfile, time
from pathlib import Path
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from . import db, contacts
COLUMNS=['Business Name','Owner Name','Owner Email','Business Email','Owner or Business Email','Location','Google Map URL','Social Media URL (Facebook preferred)','Website Status','Lead Status','Owner Email Status','Business Email Status','Review Count','Rating','Source URLs','Lead ID']
def clean(value):
    if isinstance(value,(int,float,bool)) or value is None:return value
    return re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]','',str(value))[:32000]
def refine(l,policy):
    raw=json.loads(l['raw']);r=json.loads(l['research'])
    return [raw.get('title',''),r.get('decision_name',''),r.get('decision_email',''),r.get('email',''),'; '.join(e for _,e in contacts.pick(r,policy)),raw.get('address',''),raw.get('url',''),r.get('facebook_url') or raw.get('facebookUrl') or r.get('linkedin_url') or r.get('instagram_url') or '',r.get('website_status',''),l['status'],r.get('decision_email_status','not_found'),r.get('email_status','not_found'),raw.get('reviewsCount',0),raw.get('totalScore',0),'\n'.join(s.get('url','') for s in r.get('sources',[]) if isinstance(s,dict)),l['id']]
def workbook(run_id):
    # One transaction gives the workbook a consistent view across its tabs.
    with db.connect() as c:
        c.execute('BEGIN')
        run=c.execute('SELECT * FROM runs WHERE id=?',(run_id,)).fetchone()
        if not run:raise ValueError('Discovery not found')
        leads=[dict(x) for x in c.execute('SELECT * FROM leads WHERE run_id=? ORDER BY id',(run_id,))]
        emails=[dict(x) for x in c.execute('SELECT e.* FROM emails e JOIN leads l ON l.id=e.lead_id WHERE l.run_id=? ORDER BY e.id',(run_id,))]
        msgs=[dict(x) for x in c.execute('SELECT m.* FROM messages m JOIN emails e ON e.id=m.root_id JOIN leads l ON l.id=e.lead_id WHERE l.run_id=? ORDER BY m.created',(run_id,))]
    policy=db.setting('outreach',{}).get('recipient_policy','prefer_owner')
    wb=Workbook();wb.remove(wb.active)
    def sheet(name,columns,rows):
        ws=wb.create_sheet(name);ws.append(columns)
        for row in rows:
            ws.append([clean(v) for v in row])
            for cell in ws[ws.max_row]:
                if isinstance(cell.value,str):cell.data_type='s' # =,+,@ remain literal text, not formulas
                cell.alignment=Alignment(vertical='top',wrap_text=True)
        for c in ws[1]:c.font=Font(bold=True,color='FFFFFF');c.fill=PatternFill('solid',fgColor='185C48')
        ws.freeze_panes='A2';ws.auto_filter.ref=ws.dimensions;ws.row_dimensions[1].height=32
        for col in ws.columns:ws.column_dimensions[col[0].column_letter].width=min(48,max(19,len(str(col[0].value))+2))
    sheet('Initial',COLUMNS,[refine(l,policy) for l in leads])
    sheet('Refined',COLUMNS,[refine(l,policy) for l in leads if json.loads(l['research'])])
    sheet('Qualified',COLUMNS,[refine(l,policy) for l in leads if l['status']=='qualified'])
    sheet('Outreach',['Email ID','Lead ID','Recipient Type','Recipient','Subject','Message','Mode','Status','Sent Timestamp (UTC epoch)','Error'],[[e['id'],e['lead_id'],e['recipient_kind'],e['recipient'],e['subject'],e['body'],e['mode'],e['status'],e['sent_at'],e['error']] for e in emails])
    sheet('Conversations',['Conversation ID','Direction','From','To','Subject','Message','Status','Timestamp (UTC epoch)'],[[m['root_id'],m['direction'],m['sender'],m['recipient'],m['subject'],m['body'],m['status'],m['created']] for m in msgs])
    out=io.BytesIO();wb.save(out);return out.getvalue()
def mark(run_id):db.save_setting('export_dirty_'+str(run_id),True)
def save(run_id):
    folder=db.DB_PATH.parent/'exports';folder.mkdir(exist_ok=True)
    content=workbook(run_id);fd,name=tempfile.mkstemp(dir=folder,suffix='.xlsx.tmp')
    try:
        with os.fdopen(fd,'wb') as f:f.write(content)
        os.replace(name,folder/f'discovery-{run_id}.xlsx')
        db.execute("UPDATE runs SET export_error='',exported_at=? WHERE id=?",(time.time(),run_id))
        db.save_setting('export_dirty_'+str(run_id),False)
    except OSError:
        db.execute('UPDATE runs SET export_error=? WHERE id=?',('Excel file is open or not writable. Close it; export will retry.',run_id))
    finally:Path(name).unlink(missing_ok=True)
def flush():
    for row in db.all_rows("SELECT key FROM settings WHERE key LIKE 'export_dirty_%' AND value='true' LIMIT 2"):
        rid=int(row['key'].removeprefix('export_dirty_'))
        try:save(rid)
        except Exception:db.execute('UPDATE runs SET export_error=? WHERE id=?',('Excel export failed; use Download Excel to retry.',rid))
