import hashlib, json, re, math
from datetime import datetime, timezone
from urllib.parse import urlparse
DEFAULTS={'niche':'HVAC contractor','location':'Austin, Texas, USA','lead_count':10,
 'min_rating':2.0,'min_reviews':30,'active_days':30,'mode':'demo','sync_sheets':False,
 'research_prompt':'Prioritize public business contact details and check identity using address and phone.',
 'required_fields':['contact_email'],'model':'','manual_research':True}
TEMPLATE={'subject':'Website idea for {{BusinessName}}','body':'Hi {{FirstName}},\n\nI came across {{BusinessName}} in {{Location}}. I build websites and useful automations for local businesses.\n\nWould you be open to a short conversation?\n\nBest regards,\nYour name','fallback':'there','daily_limit':25,'delay_seconds':60,'batch_size':10,'recipient_policy':'prefer_owner'}

def config(data):
    x={**DEFAULTS,**{k:v for k,v in data.items() if k in DEFAULTS}}
    for k,lo,hi in [('lead_count',1,500),('min_reviews',0,1000000),('active_days',1,365),('min_rating',0,5)]:
        x[k]=float(x[k]) if k=='min_rating' else int(x[k])
        if not lo <= x[k] <= hi: raise ValueError(f'{k} must be between {lo} and {hi}')
    if x['mode'] not in ('demo','live'): raise ValueError('Invalid mode')
    for k in ['niche','location']:
        x[k]=str(x[k]).strip()
        if not x[k] or len(x[k])>250: raise ValueError(f'{k} is required (max 250 characters)')
    if not isinstance(x['manual_research'],bool): raise ValueError('manual_research must be boolean')
    if not isinstance(x['sync_sheets'],bool): raise ValueError('sync_sheets must be boolean')
    if not isinstance(x['required_fields'],list) or set(x['required_fields'])-{'email','contact_email','decision_name','phone','address'}: raise ValueError('Unsupported required_fields')
    x['research_prompt']=str(x['research_prompt'])[:5000]
    x['model']=str(x['model'])[:100]
    return x

def blank(v): return str(v or '').strip().lower() in ('','null','undefined','n/a','none')
def identity(raw):
    key=raw.get('placeId') or raw.get('cid') or raw.get('url')
    if not key: key='|'.join(str(raw.get(k,'')).strip().lower() for k in ['title','address','phone'])
    return hashlib.sha256(str(key).encode()).hexdigest()
def parse_date(value):
    if not value: return None
    try:
        d=datetime.fromisoformat(str(value).replace('Z','+00:00'))
        return d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d
    except (ValueError,TypeError): return None

def basic(raw,cfg,now=None):
    now=now or datetime.now(timezone.utc)
    if blank(raw.get('title')) or blank(raw.get('address')): return 'Missing business identity/address'
    if not blank(raw.get('website')): return 'Website listed'
    if any(raw.get(k) for k in ['permanentlyClosed','temporarilyClosed','closed']): return 'Business closed'
    try:
        if raw.get('totalScore') is None or raw.get('reviewsCount') is None: return 'Missing review/rating data'
        score=float(raw['totalScore']); count=float(raw['reviewsCount'])
        if not math.isfinite(score) or not 0<=score<=5 or not math.isfinite(count) or count<0 or not count.is_integer(): return 'Invalid review/rating data'
        if score<cfg['min_rating']: return 'Rating below minimum'
        if count<cfg['min_reviews']: return 'Review count below minimum'
    except (ValueError,TypeError,OverflowError): return 'Invalid review/rating data'
    dates=[parse_date(r.get('publishedAtDate') or r.get('publishAt') or r.get('publishedAt')) for r in (raw.get('reviews') or []) if isinstance(r,dict)]
    if not any(d and 0 <= (now-d).total_seconds() <= cfg['active_days']*86400 for d in dates): return 'No dated review within activity window'
    return ''
def valid_email(v):
    return isinstance(v,str) and len(v)<=254 and bool(re.fullmatch(r'[A-Za-z0-9.!#$%&\x27*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,}',v))
def sources(research):
    found=[]
    for s in research.get('sources',[]):
        if isinstance(s,dict) and urlparse(str(s.get('url',''))).scheme in ('http','https'): found.append(s)
    return found

def qualified(raw,research,cfg,reviewed=False):
    failure=basic(raw,cfg)
    if failure: return failure
    if not blank(research.get('website_url')): return 'Website URL conflicts with no-website finding'
    if research.get('website_status')!='no_website_found': return 'Website exists or status is uncertain'
    if not reviewed: return 'Evidence requires human review'
    domains={urlparse(s['url']).hostname for s in sources(research)}
    if len(domains)<2: return 'At least two independent source domains required'
    if research.get('identity_match') is not True: return 'Business identity not confirmed'
    if research.get('niche_match') is not True or research.get('location_match') is not True: return 'Niche/location match not confirmed'
    for field in cfg['required_fields']:
        if field=='contact_email':
            from .contacts import available
            if not available(research): return 'Verify at least one owner or business email'
            continue
        if blank(research.get(field) or raw.get(field)): return f'Missing required field: {field}'
    if 'email' in cfg['required_fields']:
        from .contacts import available
        if not any(kind=='business' for kind,email in available(research)):return 'Business email needs a verified source'
    if 'decision_name' in cfg['required_fields'] and research.get('decision_status')!='verified':return 'Decision-maker name requires verification'
    return ''

def personalize(raw,research,cfg,tpl):
    name=research.get('decision_name','') if research.get('decision_status')=='verified' else ''
    values={'FirstName':name.split()[0] if name else tpl['fallback'],'FullName':name or tpl['fallback'],
      'BusinessName':raw.get('title',''),'BusinessCategory':raw.get('categoryName',''),
      'Location':raw.get('address',cfg['location']),'WebsiteStatus':research.get('website_status','unknown'),
      'CustomResearchField':research.get('custom_research_field','')}
    def render(s):
        def replace(m):
            if m[1] not in values: raise ValueError('Unknown template variable: '+m[1])
            return str(values[m[1]])
        return re.sub(r'{{\s*(\w+)\s*}}',replace,s)
    subject=render(tpl['subject'])
    if '\r' in subject or '\n' in subject: raise ValueError('Subject must be one line')
    return subject,render(tpl['body'])
