from .rules import valid_email
POLICIES={'prefer_owner','prefer_business','owner_only','business_only','both'}
def available(research):
    choices=[]
    for kind,field,status,source in [('owner','decision_email','decision_email_status','decision_email_source'),('business','email','email_status','email_source')]:
        email=str(research.get(field) or '').strip().lower()
        urls=[s.get('url') for s in research.get('sources',[]) if isinstance(s,dict) and isinstance(s.get('url'),str) and s['url'].startswith(('https://','http://'))]
        if valid_email(email) and research.get(status)=='verified' and bool(research.get(source)) and research.get(source) in urls:
            if email not in [x[1] for x in choices]:choices.append((kind,email))
    return choices

def pick(research,policy='prefer_owner'):
    if policy not in POLICIES:raise ValueError('Choose a valid recipient preference')
    choices=available(research)
    if policy=='both':return choices
    if policy.endswith('_only'):return [c for c in choices if c[0]==policy.split('_')[0]]
    order=['business','owner'] if policy=='prefer_business' else ['owner','business']
    for kind in order:
        matches=[c for c in choices if c[0]==kind]
        if matches:return matches[:1]
    return []
