"""Synthetic adapters use fixture data only; no network or environment access."""
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .core import SOURCES, Store
from .service import Service
from .providers import ApifyClient, HunterClient, AttioClient, ProviderError


class DemoHTTP:
    def __init__(self, rows):
        self.rows = rows
        self.by_email = {row['fixture_email']: row for row in rows if row.get('fixture_email')}

    def request(self, method, url, *, headers=None, body=None):
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        if method == 'GET' and parsed.hostname == 'api.apify.com' and parsed.path == '/v2/datasets/demo/items':
            offset = int(query.get('offset', ['0'])[0])
            limit = int(query.get('limit', ['1000'])[0])
            return self.rows[offset:offset+limit]
        if method == 'GET' and parsed.hostname == 'api.hunter.io':
            if parsed.path == '/v2/email-finder':
                first = query.get('first_name', [''])[0]
                handle = query.get('linkedin_handle', [''])[0]
                row = next((r for r in self.rows if (first and r['firstName']==first) or (handle and r.get('fixture_handle')==handle)), None)
                if row is None:
                    raise ProviderError('Demo Hunter: unknown fixture identity.')
                return {'data': {'email': row.get('fixture_email') or None,
                    'verification': {'status':row['fixture_verification']}, 'sources':[]}}
            if parsed.path == '/v2/email-verifier':
                email = query.get('email', [''])[0]
                row = self.by_email.get(email)
                if row is None:
                    raise ProviderError('Demo Hunter: unknown fixture email; held for review.')
                return {'data': {'email':email,'status':row['fixture_verification']}}
        if method == 'POST' and parsed.hostname == 'api.attio.com' and parsed.path == '/v2/objects/people/records/query':
            value = (body or {}).get('filter', {}).get('email_addresses')
            # The real adapter uses an exact-email filter; accept its documented nested form.
            if isinstance(value,dict):
                value = value.get('$eq') or value.get('email_address',{}).get('$eq')
            row = self.by_email.get(value)
            if row is None:
                raise ProviderError('Demo Attio: unknown fixture email; screening is incomplete.')
            data = [{'values':{'email_addresses':[{'email_address':value}]}}] if row.get('fixture_attio') else []
            return {'data':data}
        raise ProviderError('Demo: unexpected provider request; network is disabled.')


def prepare_demo(db_path, owner):
    path = Path(db_path)
    if 'demo' not in path.name.lower() or path.name.lower() == 'kathie.sqlite':
        raise ValueError('Synthetic demo requires a database filename containing demo.')
    rows = json.loads((Path(__file__).resolve().parent.parent/'demo-leads.json').read_text())
    store = Store(path)
    store.demo_mode = True
    http = DemoHTTP(rows)
    service = Service(store,owner,apify=ApifyClient('synthetic-demo',http=http),
        hunter=HunterClient('synthetic-demo',http=http),attio_lookup=AttioClient('synthetic-demo',http=http).contains)
    if not store.list_leads():
        service.handle('import', {'user_id':owner,'dataset_id':'demo','segment':'tech'})
        # Preserve capture relationship choices in the same Store API used by Slack.
        for row in rows:
            if row.get('fixture_relationship'):
                service.handle('capture',{'user_id':owner,'lead':{
                    'first_name':row['firstName'],'last_name':row['lastName'],
                    'email':row['fixture_email'],'source':'event','segment':'tech',
                    'relationship':row['fixture_relationship'],'notes':'Synthetic demo event'}})
        for source in SOURCES:
            store.save_snapshot(source,['asana@example.com'] if source=='asana' else [],complete=True)
    screened = service.handle('screen', {'user_id':owner})
    expected = {' '.join((row['firstName'],row['lastName'])):row['expected_status'] for row in rows}
    results = [{'name':row['name'],'expected_status':expected.get(row['name']),
        'actual_status':row['status'],'match':row['status']==expected.get(row['name'])}
        for row in store.screen_results()]
    return store,service,{'results':results,'counts':screened['counts'],
        'synthetic':True,'all_match':all(row['match'] for row in results)}
