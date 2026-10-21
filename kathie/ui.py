"""Plain language Slack views. Stored copy is never truncated."""
import re
import time
from datetime import datetime, timezone

def escape(value):
    return str(value).replace('&','&amp;').replace('<','&lt;').replace('>','&gt;')

def section(value):
    # Single display sections are bounded; full copy uses chunks below.
    first=chunks(str(value),3000)[0]
    return {'type':'section','text':{'type':'mrkdwn','text':escape(first)}}

def chunks(value, size=2800):
    parts=[]; current=[]; used=0
    for char in str(value):
        cost=len(escape(char))
        if used+cost>size:
            parts.append(''.join(current)); current=[]; used=0
        current.append(char); used+=cost
    if current: parts.append(''.join(current))
    return parts or ['(empty)']

def preview_blocks(preview):
    exp=preview['experiment']; blocks=[section(part) for part in chunks(f"Draft: {exp['name']} · version {exp['version']}")]+[section(part) for part in chunks('Subject: '+exp['subject'])]
    for variant in preview['variants']:
        blocks.append(section('Opening '+variant['label']))
        blocks.extend(section(part) for part in chunks(variant['initial']))
    for step in preview['followups']:
        blocks.append(section(f"Message {step['step']} · 2 business days after the previous message · business day {step['after_business_days']} from the initial message"))
        blocks.extend(section(part) for part in chunks(step['body']))
    return blocks

def input_block(key,label,value='',multiline=False,optional=False):
    element={'type':'plain_text_input','action_id':'value','multiline':multiline,'max_length':3000}
    if value: element['initial_value']=value
    return {'type':'input','block_id':key,'optional':optional,'label':{'type':'plain_text','text':label},'element':element}

def select(key,label,options,value=None):
    opts=[{'text':{'type':'plain_text','text':label},'value':val} for val,label in options]
    element={'type':'static_select','action_id':'value','options':opts}
    if value: element['initial_option']=next(x for x in opts if x['value']==value)
    return {'type':'input','block_id':key,'label':{'type':'plain_text','text':label},'element':element}

SEGMENTS=[('tech','Tech-company employees'),('real_estate','Real estate or construction')]
SOURCES=['asana','attio','beehiiv','mailerlite','replies','sends','optouts','bounces']

def form(kind,existing=None):
    existing=existing or {}; fields=[]
    if kind=='experiment' and not existing:
        existing={'name':'Osage opening-line test','subject':'Self-storage question',
            'body':'Would you like me to send information about our Los Angeles self-storage raise?',
            'hooks':['Interested in self-storage?','Looking at real estate beyond public markets?','Open to learning about a Los Angeles self-storage project?'],
            'followups':['Following up on my note. Would you like the information?',
                'Checking back in. Happy to send more details if you are interested.',
                'Last follow-up from me. Let me know if you would like the information.']}
    if kind=='capture':
        fields=[input_block('first_name','First name'),input_block('last_name','Last name',optional=True),input_block('email','Email address',optional=True),input_block('phone','Phone number',optional=True),input_block('domain','Company website domain, for finding an email',optional=True),input_block('profile_url','Profile link',optional=True),select('source','Contact source', [('event','Event'),('rolodex','My contacts')]),select('relationship','How do you know this person?', [('warm','Warm: I know them personally'),('ambient','Ambient: we met, but I do not know them personally'),('cold','Cold: we have never met')],'warm'),select('segment','Audience',SEGMENTS),input_block('notes','Where you met / relationship notes',multiline=True,optional=True),section('Warm and Ambient follow-up stay separate from cold tests. Automated follow-up comes later. The first Ambient message should refer to where you met.')]
    elif kind=='import': fields=[input_block('dataset_id','Completed Apify dataset ID'),select('segment','Audience',SEGMENTS)]
    elif kind=='snapshot':
        fields=[select('source','List to check',[(x,x.title()) for x in SOURCES]),input_block('emails','Email addresses, one per line',multiline=True,optional=True),section('This form accepts up to 3,000 characters. Supply the complete list; do not split it across submissions, because each save replaces the current list.'),select('complete','Is this the complete list?', [('yes','Yes, this is the complete list'),('no','No, this list is incomplete')])]
    elif kind=='experiment':
        fields=[input_block('name','Test name',existing.get('name','')),select('segment','Audience',SEGMENTS,existing.get('segment')),input_block('subject','Subject',existing.get('subject','')),input_block('body','Shared initial message',existing.get('body',''),True),input_block('hooks','Opening lines, one per line','\n'.join(existing.get('hooks',[])),True),input_block('followups','Follow-ups, separated by a line containing ---','\n---\n'.join(existing.get('followups',[])),True),section('Finite list. Each follow-up is 2 business days after the previous message. Nothing sends in this prototype.')]
    return {'type':'modal','callback_id':'kathie_'+kind,'private_metadata':existing.get('id',''),'title':{'type':'plain_text','text':{'capture':'Capture lead','import':'Import leads','snapshot':'Screening lists','experiment':'Draft messaging test'}[kind]},'submit':{'type':'plain_text','text':'Save draft' if kind=='experiment' else 'Save'},'close':{'type':'plain_text','text':'Cancel'},'blocks':fields}

def extract(view):
    return {key:item['value'].get('value') or (item['value'].get('selected_option') or {}).get('value','') for key,item in view['state']['values'].items()}

def parse_submission(kind,values):
    values={key:str(value or '').strip() for key,value in values.items()}
    if any(len(value)>3000 for value in values.values()):
        raise ValueError('Each form field can contain up to 3,000 characters. Shorten the field and try again.')
    if kind in ['capture','import','experiment'] and values.get('segment') not in ['tech','real_estate']:
        raise ValueError('Choose an audience.')
    if kind=='capture' and values.get('source') not in ['event','rolodex']:
        raise ValueError('Choose where you met this person.')
    if kind=='snapshot' and values.get('source') not in SOURCES:
        raise ValueError('Choose a screening list.')
    if kind=='capture':
        if not values.get('first_name'): raise ValueError('First name is required.')
        if values.get('email') and not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',values['email']): raise ValueError('Enter a valid email address.')
        if values.get('relationship','warm') not in ['warm','ambient','cold']: raise ValueError('Choose Warm, Ambient, or Cold.')
        values.setdefault('relationship','warm')
        if values.get('domain') and not re.fullmatch(r'[A-Za-z0-9.-]+\.[A-Za-z]{2,}',values['domain']): raise ValueError('Enter a company domain, such as example.com.')
        if not values.get('email') and not values.get('profile_url') and not (values.get('last_name') and values.get('domain')): raise ValueError('Enter an email, profile link, or last name and company domain.')
        return {'lead':values}
    if kind=='import':
        if not re.fullmatch(r'[A-Za-z0-9_-]+',values.get('dataset_id','')): raise ValueError('Enter the completed dataset ID.')
        return values
    if kind=='snapshot':
        if values.get('complete')!='yes': raise ValueError('Confirm this list is complete before saving.')
        emails=[x.strip().lower() for x in values.get('emails','').splitlines() if x.strip()]
        if any(not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',x) for x in emails): raise ValueError('Enter one valid email address per line.')
        return {'source':values['source'],'emails':emails,'complete':True}
    if kind=='experiment':
        data={**values,'hooks':[x.strip() for x in values.get('hooks','').splitlines() if x.strip()], 'followups':[x.strip() for x in re.split(r'(?m)^\s*---\s*$',values.get('followups',''))], 'interval_business_days':2}
        if any(not data.get(x) for x in ['name','subject','body']) or not 2<=len(data['hooks'])<=5 or not data['followups'] or any(not x for x in data['followups']): raise ValueError('Enter a name, subject, body, 2–5 opening lines, and a finite list of follow-ups.')
        if any('—' in x for x in [data['subject'],data['body'],*data['hooks'],*data['followups']]): raise ValueError('Replace em dashes in the message copy.')
        return {'data':data}
    raise ValueError('Unknown form.')

def home_view(store):
    results=store.screen_results(); counts={s:sum(r['status']==s for r in results) for s in ['eligible','blocked','held']}
    blocks=[section('Kathie · lead research and draft messaging'),section(f"Captured: {len(store.list_leads())} · Eligible: {counts['eligible']} · Blocked from cold outreach: {counts['blocked']} · Needs review: {counts['held']}"),section('Nothing sends here. Use /kathie capture, import, suppressions, screen, results, or experiment.'),{'type':'actions','elements':[{'type':'button','text':{'type':'plain_text','text':label},'action_id':'kathie_'+kind} for kind,label in [('capture','Capture lead'),('import','Import leads'),('snapshot','Screening lists'),('experiment','Draft messaging'),('screen','Check leads')]]}]
    if getattr(store,'demo_mode',False):
        blocks.insert(0,section('DEMO — fictional contacts; simulated Hunter/Attio; no credits or outreach'))
        blocks.insert(1,section('Try Import leads with dataset ID: demo, then Check leads. For manual capture, use a fictional name and an email such as alex@example.com. Draft messaging lets you edit and preview a test; nothing sends.'))
    if callable(getattr(store,'snapshot',None)):
        readiness=[]
        for source in SOURCES:
            saved=store.snapshot(source)
            if saved is None: state='missing'
            elif not saved.get('complete'): state='incomplete'
            elif time.time()-saved.get('updated_at',0)>86400: state='stale'
            else: state='complete and recent'
            readiness.append(readable_reason(f'{source} check {state}') if state!='complete and recent' else f'{source.title()}: complete and recent')
        blocks.append(section('Screening lists\n'+'\n'.join(readiness)))
        blocks.append(section('Lists must be complete and refreshed within 24 hours. Attio may also be checked directly when connected.'))
    if results:
        for row in results[:15]:
            blocks.append(section(result_text(row)[:2800]))
        blocks.append({'type':'actions','elements':[{'type':'button','text':{'type':'plain_text','text':'Review all leads'},'action_id':'kathie_results'}]})
        if len(results)>15: blocks.append(section('Showing the first 15 leads. Use Review all leads for the complete list.'))
    else: blocks.append(section('Required lists have not been checked yet. Run screening to see missing or incomplete checks.'))
    for exp in store.list_experiments()[:10]:
        blocks.append(section(f"Draft: {exp['name']} · version {exp['version']} · {exp['segment']}"))
        blocks.append({'type':'actions','elements':[{'type':'button','text':{'type':'plain_text','text':'Edit draft'},'action_id':'kathie_edit','value':exp['id']},{'type':'button','text':{'type':'plain_text','text':'Preview full sequence'},'action_id':'kathie_preview','value':exp['id']}]})
    return {'type':'home','blocks':blocks}

def result_text(row):
    if row.get('relationship')=='ambient' or row.get('track')=='ambient': track='Ambient follow-up'
    elif row.get('relationship')=='warm' or row.get('track')=='warm': track='Warm follow-up'
    else: track='Cold outreach'
    status={'eligible':'Ready for review','blocked':'Blocked from cold outreach','held':'Needs review'}[row['status']]
    reasons='; '.join(readable_reason(reason) for reason in row['reasons']) or 'All required checks passed.'
    checked=row.get('checked_at')
    stamp=datetime.fromtimestamp(checked,timezone.utc).strftime('%Y-%m-%d %H:%M UTC') if checked is not None else 'Not checked'
    freshness='Refresh checks before use' if checked is None or time.time()-checked>86400 else 'Checked within 24 hours'
    source={'apify':'Apify research','event':'Event','rolodex':'My contacts'}.get(row.get('source'),'Unknown source')
    audience=row.get('audience') or {'status':'unverified','missing':['Audience details not supplied']}
    audience_label={'verified':'Audience criteria verified','unverified':'Audience Unverified: '+', '.join(audience.get('missing',[])),'excluded':'Excluded: known audience mismatch'}[audience['status']]
    return f"{row['name']} · {row.get('email') or 'Email missing'}\n{source} · {track} · {status}\n{audience_label}\nChecked: {stamp} · {freshness}\n{reasons}"

def results_view(rows,page=0):
    total=max(1,(len(rows)+14)//15); page=max(0,min(page,total-1))
    blocks=[]
    for row in rows[page*15:(page+1)*15]:
        blocks.extend(section(part) for part in chunks(result_text(row)))
    if not blocks: blocks=[section('No screening results yet. Use Check leads to start.')]
    elements=[]
    if page: elements.append({'type':'button','text':{'type':'plain_text','text':'Previous page'},'action_id':'kathie_results_previous','value':str(page-1)})
    if page+1<total: elements.append({'type':'button','text':{'type':'plain_text','text':'Next page'},'action_id':'kathie_results_next','value':str(page+1)})
    if elements: blocks.append({'type':'actions','elements':elements})
    return {'type':'modal','title':{'type':'plain_text','text':f'Lead review {page+1}/{total}'},'close':{'type':'plain_text','text':'Close'},'blocks':blocks}

def readable_reason(reason):
    labels={'asana':'Asana investor pipeline','attio':'Attio investor pipeline','beehiiv':'beehiiv subscribers','mailerlite':'MailerLite subscribers','replies':'Prior replies','sends':'Prior sends','optouts':'Opt-outs','bounces':'Hard bounces'}
    for source,label in labels.items():
        if reason==f'{source} match': return f'Found in {label}'
        prefix=f'{source} check '
        if reason.startswith(prefix):
            state=reason[len(prefix):]
            wording={'missing':'has not been supplied','stale':'needs a fresh complete list','incomplete':'is incomplete','failed':'could not be checked'}.get(state,'needs review')
            return f'{label}: {wording}'
        if reason.startswith(f'{source} lookup failed'): return f'{label}: could not be checked'
    if reason.startswith('email verification failed'): return 'Email address: verification could not be completed'
    return reason
