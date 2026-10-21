"""Durable capture, conservative screening, and immutable message drafts."""
import json
import re
import sqlite3
import time
import uuid
from pathlib import Path
from contextlib import contextmanager

SOURCES = ('asana', 'beehiiv', 'mailerlite', 'replies', 'sends', 'optouts', 'bounces', 'attio')
HISTORICAL = ('replies', 'sends', 'optouts', 'bounces')
FIELDS = ('first_name','last_name','email','domain','profile_url','source','source_id','segment','notes','relationship','phone','audience')
TTL = 86400


def normalize_email(email):
    if not isinstance(email, str):
        raise ValueError('Email must be text')
    email = email.strip().lower()
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email):
        raise ValueError('Provide a valid email address')
    return email


class Store:
    def __init__(self, path):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS leads (id TEXT PRIMARY KEY, data TEXT NOT NULL, email TEXT UNIQUE, profile TEXT UNIQUE);
            CREATE TABLE IF NOT EXISTS verifications (lead_id TEXT PRIMARY KEY, status TEXT NOT NULL, checked_at REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS snapshots (source TEXT PRIMARY KEY, emails TEXT NOT NULL, complete INTEGER NOT NULL, checked_at REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS history (source TEXT NOT NULL, email TEXT NOT NULL, PRIMARY KEY(source,email));
            CREATE TABLE IF NOT EXISTS screenings (lead_id TEXT PRIMARY KEY, result TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS screening_history (id INTEGER PRIMARY KEY, lead_id TEXT NOT NULL, result TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS experiments (id TEXT NOT NULL, version INTEGER NOT NULL, data TEXT NOT NULL, PRIMARY KEY(id,version));
            ''')

    @contextmanager
    def _db(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def add_lead(self, data):
        lead = {key: data.get(key, '') for key in FIELDS}
        lead['audience'] = data.get('audience') or {'status':'unverified','missing':['Audience details not supplied'],'checks':{}}
        if not isinstance(lead['audience'],dict) or lead['audience'].get('status') not in ('verified','unverified','excluded'):
            raise ValueError('Audience evidence requires verified, unverified, or excluded status')
        if lead['source'] not in ('apify','event','rolodex'):
            raise ValueError('Source must be apify, event, or rolodex')
        if lead['segment'] not in ('tech','real_estate'):
            raise ValueError('Segment must be tech or real_estate')
        lead['relationship'] = data.get('relationship', 'cold' if lead['source'] == 'apify' else 'warm')
        if lead['relationship'] not in ('warm','ambient','cold'):
            raise ValueError('Relationship must be warm, ambient, or cold')
        if lead['phone'] is None: lead['phone'] = ''
        if not isinstance(lead['phone'],str): raise ValueError('Phone must be text')
        lead['email'] = normalize_email(lead['email']) if lead['email'] else ''
        lead['profile_url'] = (lead['profile_url'] or '').strip().rstrip('/')
        with self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            matches = db.execute('SELECT id FROM leads WHERE (email IS NOT NULL AND email=?) OR (profile IS NOT NULL AND profile=?)', (lead['email'] or None, lead['profile_url'] or None)).fetchall()
            ids = {row['id'] for row in matches}
            if len(ids) > 1:
                raise ValueError('Email and profile identify different leads; resolve identity collision')
            if ids:
                existing_id = ids.pop()
                if lead['audience']['status'] == 'excluded':
                    current = json.loads(db.execute('SELECT data FROM leads WHERE id=?',(existing_id,)).fetchone()['data'])
                    current['audience'] = lead['audience']
                    db.execute('UPDATE leads SET data=? WHERE id=?',(json.dumps(current),existing_id))
                    db.execute('DELETE FROM screenings WHERE lead_id=?',(existing_id,))
                if lead['relationship'] in ('warm','ambient'):
                    existing = json.loads(db.execute('SELECT data FROM leads WHERE id=?',(existing_id,)).fetchone()['data'])
                    previous = existing.get('relationship', 'cold' if existing['source'] == 'apify' else 'warm')
                    if existing.get('warm_sources'): previous = 'warm'
                    existing['relationship_history'] = sorted(set(existing.get('relationship_history', [])) | {previous,lead['relationship']})
                    existing['relationship'] = 'warm' if 'warm' in existing['relationship_history'] else 'ambient'
                    if lead['relationship'] == 'warm':
                        existing['warm_sources'] = sorted(set(existing.get('warm_sources', [])) | {lead['source']})
                    db.execute('UPDATE leads SET data=? WHERE id=?',(json.dumps(existing),existing_id))
                    db.execute('DELETE FROM screenings WHERE lead_id=?',(existing_id,))
                return existing_id
            lead['id'] = str(uuid.uuid4())
            db.execute('INSERT INTO leads VALUES (?,?,?,?)', (lead['id'],json.dumps(lead),lead['email'] or None,lead['profile_url'] or None))
        return lead['id']

    def list_leads(self):
        with self._db() as db:
            return [json.loads(row['data']) for row in db.execute('SELECT data FROM leads ORDER BY rowid')]

    def get_lead(self, lead_id):
        with self._db() as db:
            row = db.execute('SELECT data FROM leads WHERE id=?',(lead_id,)).fetchone()
        if row is None: raise ValueError('Unknown lead')
        return json.loads(row['data'])

    def set_email(self, lead_id, email):
        email = normalize_email(email)
        with self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT data FROM leads WHERE id=?',(lead_id,)).fetchone()
            if row is None: raise ValueError('Unknown lead')
            existing = db.execute('SELECT id FROM leads WHERE email=? AND id<>?',(email,lead_id)).fetchone()
            if existing: raise ValueError('Email already belongs to another lead')
            data = json.loads(row['data'])
            if data['email'] != email:
                db.execute('DELETE FROM verifications WHERE lead_id=?',(lead_id,))
                db.execute('DELETE FROM screenings WHERE lead_id=?',(lead_id,))
            data['email'] = email
            db.execute('UPDATE leads SET email=?, data=? WHERE id=?',(email,json.dumps(data),lead_id))

    def set_verification(self, lead_id, status, checked_at=None):
        self.get_lead(lead_id)
        if status not in ('valid','invalid','unknown'): raise ValueError('Invalid verification status')
        with self._db() as db:
            db.execute('INSERT OR REPLACE INTO verifications VALUES (?,?,?)',(lead_id,status,time.time() if checked_at is None else checked_at))
            db.execute('DELETE FROM screenings WHERE lead_id=?',(lead_id,))

    def save_snapshot(self, source, emails, complete=True, now=None):
        if source not in SOURCES: raise ValueError('Unknown suppression source')
        emails = sorted({normalize_email(email) for email in emails})
        if not isinstance(complete,bool): raise ValueError('Completeness must be true or false')
        with self._db() as db:
            db.execute('INSERT OR REPLACE INTO snapshots VALUES (?,?,?,?)',(source,json.dumps(emails),int(complete),time.time() if now is None else now))
            db.execute('DELETE FROM screenings')
            if source in HISTORICAL:
                db.executemany('INSERT OR IGNORE INTO history VALUES (?,?)',[(source,email) for email in emails])

    def snapshot(self, source):
        if source not in SOURCES: raise ValueError('Unknown suppression source')
        with self._db() as db:
            row = db.execute('SELECT * FROM snapshots WHERE source=?',(source,)).fetchone()
        if row is None: return None
        return {'emails':json.loads(row['emails']),'complete':bool(row['complete']),'updated_at':row['checked_at']}

    def screen_leads(self, attio_lookup=None, verifier=None, now=None):
        now = time.time() if now is None else now
        with self._db() as db:
            snapshots = {r['source']:dict(r) for r in db.execute('SELECT * FROM snapshots')}
            history = {(r['source'],r['email']) for r in db.execute('SELECT * FROM history')}
            verifications = {r['lead_id']:dict(r) for r in db.execute('SELECT * FROM verifications')}
        results = []
        for lead in self.list_leads():
            reasons, checks = [], {}
            blocked = False
            relationship = lead.get('relationship', 'cold' if lead['source'] == 'apify' else 'warm')
            if lead.get('warm_sources'): relationship = 'warm'
            if relationship == 'warm' or lead.get('warm_sources'):
                blocked = True; reasons.append('Warm contact: use warm follow-up track')
            elif relationship == 'ambient':
                blocked = True; reasons.append('Ambient contact: use ambient follow-up track')
            audience = lead.get('audience') or {'status':'unverified','missing':['Audience details not supplied'],'checks':{}}
            if audience['status'] == 'excluded':
                blocked = True
                mismatches = [key for key,value in audience.get('checks',{}).items() if value is False]
                reasons.append('Audience mismatch: '+', '.join(mismatches or ['source evidence']))
            email = lead['email']
            if not email: reasons.append('Missing email')
            for source in SOURCES:
                if source == 'attio' and attio_lookup is not None and email:
                    try:
                        match = attio_lookup(email)
                        if not isinstance(match,bool): raise ValueError('Invalid lookup result')
                        checks[source] = {'status':'match' if match else 'clear','checked_at':now}
                        if match: blocked = True; reasons.append('attio match')
                    except Exception as exc:
                        checks[source] = {'status':'failed','error_type':type(exc).__name__}
                        reasons.append(f'attio lookup failed ({type(exc).__name__})')
                    continue
                snapshot = snapshots.get(source)
                match = bool(email and ((source,email) in history or (snapshot and email in json.loads(snapshot['emails']))))
                if match: blocked = True; reasons.append(f'{source} match')
                state = 'missing' if snapshot is None else 'incomplete' if not snapshot['complete'] else 'stale' if not 0 <= now-snapshot['checked_at'] <= TTL else 'clear'
                checks[source] = {'status':'match' if match else state,'checked_at':snapshot['checked_at'] if snapshot else None}
                if state != 'clear': reasons.append(f'{source} check {state}')
            if verifier is not None and email:
                try:
                    status = verifier(email)
                    self.set_verification(lead['id'],status,now)
                    verification = {'status':status,'checked_at':now}
                except Exception as exc:
                    verification = None
                    reasons.append(f'email verification failed ({type(exc).__name__})')
                    checks['verification'] = {'status':'failed','error_type':type(exc).__name__}
            else: verification = verifications.get(lead['id'])
            if verification is not None:
                status = verification['status']
                fresh = 0 <= now-verification['checked_at'] <= TTL
                checks['verification'] = {'status':status,'checked_at':verification['checked_at'],'fresh':fresh}
                if status == 'invalid': blocked = True; reasons.append('Email verification invalid')
                elif not fresh: reasons.append('Email verification stale')
                elif status != 'valid': reasons.append('Email verification unknown')
            elif 'verification' not in checks:
                checks['verification'] = {'status':'missing'}; reasons.append('Email verification missing')
            result = dict(lead_id=lead['id'],name=' '.join(filter(None,(lead['first_name'],lead['last_name']))),email=email,segment=lead['segment'],source=lead['source'],relationship=relationship,track=relationship,audience=audience,status='blocked' if blocked else 'held' if reasons else 'eligible',reasons=reasons,checks=checks,checked_at=now)
            with self._db() as db:
                encoded = json.dumps(result)
                db.execute('INSERT OR REPLACE INTO screenings VALUES (?,?)',(lead['id'],encoded))
                db.execute('INSERT INTO screening_history (lead_id,result) VALUES (?,?)',(lead['id'],encoded))
            results.append(result)
        return results

    def screen_results(self):
        with self._db() as db:
            results = [json.loads(r['result']) for r in db.execute('SELECT result FROM screenings ORDER BY rowid')]
        now = time.time()
        for result in results:
            evidence_times = [result['checked_at']] + [check['checked_at'] for check in result['checks'].values() if check.get('checked_at') is not None]
            if result['status'] != 'blocked' and any(not 0 <= now-stamp <= TTL for stamp in evidence_times):
                result['status'] = 'held'
                result['reasons'].append('Screening evidence expired; screen again')
        return results

    def save_experiment(self, data, user_id, experiment_id=None):
        required = ('name','subject','body')
        for field in required:
            if not isinstance(data.get(field),str) or not data[field].strip(): raise ValueError(f'{field} is required')
        if data.get('segment') not in ('tech','real_estate'): raise ValueError('Invalid segment')
        for field,low,high in (('hooks',2,5),('followups',1,None)):
            values = data.get(field)
            if not isinstance(values,list) or len(values) < low or (high is not None and len(values) > high) or any(not isinstance(x,str) or not x.strip() for x in values):
                limit = f'{low}–{high}' if high is not None else f'at least {low}'
                raise ValueError(f'{field} requires {limit} nonempty messages')
        if data.get('interval_business_days',2) != 2: raise ValueError('Follow-ups must be two business days apart')
        if any('—' in text for text in [*(data[k] for k in required),*data['hooks'],*data['followups']]): raise ValueError('Remove em dashes from copy')
        if not user_id: raise ValueError('User ID required')
        with self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            if experiment_id is not None:
                row = db.execute('SELECT MAX(version) AS version FROM experiments WHERE id=?',(experiment_id,)).fetchone()
                if row['version'] is None: raise ValueError('Unknown experiment')
                version = row['version']+1
            else: experiment_id,version = str(uuid.uuid4()),1
            result = {key:data[key] for key in (*required,'segment','hooks','followups')}
            result.update(id=experiment_id,version=version,interval_business_days=2,status='draft',created_by=user_id)
            db.execute('INSERT INTO experiments VALUES (?,?,?)',(experiment_id,version,json.dumps(result)))
        return result

    def list_experiments(self):
        with self._db() as db:
            return [json.loads(r['data']) for r in db.execute('SELECT e.data FROM experiments e WHERE version=(SELECT MAX(version) FROM experiments WHERE id=e.id) ORDER BY rowid')]

    def get_experiment(self, experiment_id):
        with self._db() as db:
            row = db.execute('SELECT data FROM experiments WHERE id=? ORDER BY version DESC LIMIT 1',(experiment_id,)).fetchone()
        if row is None: raise ValueError('Unknown experiment')
        return json.loads(row['data'])

    def preview_experiment(self, experiment_id):
        experiment = self.get_experiment(experiment_id)
        return {'experiment':experiment,'variants':[{'label':chr(65+i),'initial':hook+'\n\n'+experiment['body']} for i,hook in enumerate(experiment['hooks'])], 'followups':[{'step':i+2,'after_business_days':2*(i+1),'body':body} for i,body in enumerate(experiment['followups'])]}
