import unittest
from kathie.ui import escape, parse_submission, preview_blocks
from kathie.slack_app import build_app

class FakeApp:
    def __init__(self, **kwargs): self.handlers={}; self.client=None
    def command(self,key): return self.register('command',key)
    def event(self,key): return self.register('event',key)
    def action(self,key): return self.register('action',key)
    def view(self,key): return self.register('view',key)
    def register(self,kind,key):
        def wrap(fn): self.handlers[(kind,key)]=fn; return fn
        return wrap
class SlackTests(unittest.TestCase):
    def test_mentions_escaped(self): self.assertEqual(escape('<@U>&'), '&lt;@U&gt;&amp;')
    def test_owner_required(self):
        with self.assertRaises(ValueError): build_app(None,None,'','',app_factory=FakeApp)
    def test_unauthorized_command_never_enqueues(self):
        jobs=[]; app=build_app(None,lambda *x:jobs.append(x),'OWNER','',app_factory=FakeApp)
        responses=[]; app.handlers['command','/kathie'](ack=lambda **x:None,body={'user_id':'OTHER','text':'screen'},respond=responses.append,client=None)
        self.assertFalse(jobs); self.assertIn('Shane',responses[0])
    def test_followups_preserved_and_fixed_interval(self):
        values={'name':'test','segment':'tech','subject':'subject','body':'body','hooks':'one\ntwo','followups':'first\n---\nsecond'}
        data=parse_submission('experiment',values)
        self.assertEqual(data['data']['followups'],['first','second']); self.assertEqual(data['data']['interval_business_days'],2)
    def test_snapshot_requires_attestation(self):
        with self.assertRaises(ValueError): parse_submission('snapshot',{'source':'asana','emails':'a@example.com'})
    def test_full_preview_escapes_copy(self):
        blocks=preview_blocks({'experiment':{'name':'X','version':1,'subject':'Hi'},'variants':[{'label':'A','initial':'<@U>'}], 'followups':[{'step':2,'after_business_days':2,'body':'next'}]})
        self.assertIn('&lt;@U&gt;',str(blocks)); self.assertIn('2 business days',str(blocks))

class SubmissionTests(unittest.TestCase):
    def test_unauthorized_submission_never_enqueues(self):
        jobs=[]; app=build_app(None,lambda *x:jobs.append(x),'OWNER','',app_factory=FakeApp)
        responses=[]
        view={'blocks':[{'block_id':'first_name'}]}
        app.handlers['view','kathie_capture'](ack=lambda **x:responses.append(x),body={'user':{'id':'OTHER'}},view=view)
        self.assertFalse(jobs); self.assertEqual(responses[0]['response_action'],'errors')
    def test_submission_dedupes_by_view_and_hash(self):
        jobs=[]; app=build_app(None,lambda *x:jobs.append(x),'OWNER','',app_factory=FakeApp)
        view={'id':'V1','hash':'H1','blocks':[{'block_id':'first_name'}],'state':{'values':{k:{'value':{'value':v}} for k,v in {'first_name':'Ada','email':'ada@example.com','source':'event','segment':'tech'}.items()}}}
        app.handlers['view','kathie_capture'](ack=lambda **x:None,body={'user':{'id':'OWNER'}},view=view)
        self.assertEqual(jobs[0][2],'view:V1:H1'); self.assertEqual(jobs[0][1]['user_id'],'OWNER')
    def test_unknown_segment_rejected(self):
        with self.assertRaises(ValueError): parse_submission('import',{'dataset_id':'test','segment':'unknown'})

class RoutingTests(unittest.TestCase):
    def test_domain_identity_capture(self):
        parsed=parse_submission('capture',{'first_name':'Ada','last_name':'Lovelace','domain':'example.com','source':'event','segment':'tech','relationship':'cold'})
        self.assertEqual(parsed['lead']['relationship'],'cold')
    def test_more_than_ten_finite_followups(self):
        data=parse_submission('experiment',{'name':'x','segment':'tech','subject':'x','body':'x','hooks':'a\nb','followups':'\n---\n'.join(['next']*11)})
        self.assertEqual(len(data['data']['followups']),11)
    def test_preview_cumulative_days(self):
        blocks=preview_blocks({'experiment':{'name':'X','version':1,'subject':'Hi'},'variants':[], 'followups':[{'step':3,'after_business_days':4,'body':'next'}]})
        self.assertIn('2 business days after the previous',str(blocks)); self.assertIn('day 4',str(blocks))

class LengthTests(unittest.TestCase):
    def test_escaped_preview_blocks_fit(self):
        blocks=preview_blocks({'experiment':{'name':'X','version':1,'subject':'Hi'},'variants':[{'label':'A','initial':'&'*5000+'<@U>'}], 'followups':[{'step':2,'after_business_days':2,'body':'&'*10000}]})
        self.assertTrue(all(len(b['text']['text'])<=3000 for b in blocks))
        self.assertEqual(sum(b['text']['text'].count('&amp;') for b in blocks),15000)
        self.assertIn('&lt;@U&gt;',str(blocks))
    def test_oversize_form_copy_rejected(self):
        with self.assertRaises(ValueError): parse_submission('experiment',{'name':'x','segment':'tech','subject':'x','body':'x','hooks':'a\nb','followups':'x'*3001})

class EvidenceTests(unittest.TestCase):
    def test_identity_and_timestamp_visible(self):
        from kathie.ui import result_text
        text=result_text({'name':'Ada','email':'ada@example.com','source':'event','checked_at':1,'status':'held','reasons':['Missing email']})
        self.assertIn('ada@example.com',text); self.assertIn('Event',text); self.assertIn('UTC',text); self.assertIn('Refresh',text)
    def test_all_results_paginated(self):
        from kathie.ui import results_view
        rows=[{'name':f'Person {i}','email':f'p{i}@example.com','source':'apify','checked_at':1,'status':'held','reasons':['Missing email']} for i in range(20)]
        first=results_view(rows,0); last=results_view(rows,1)
        self.assertIn('kathie_results_next',str(first)); self.assertIn('Person 19',str(last))

class AmbientTests(unittest.TestCase):
    def test_ambient_capture_with_phone(self):
        data=parse_submission('capture',{'first_name':'Ada','email':'ada@example.com','phone':'555-123-4567','source':'event','segment':'tech','relationship':'ambient'})
        self.assertEqual(data['lead']['relationship'],'ambient'); self.assertEqual(data['lead']['phone'],'555-123-4567')
    def test_ambient_review_label(self):
        from kathie.ui import result_text
        self.assertIn('Ambient follow-up',result_text({'name':'Ada','email':'ada@example.com','source':'event','relationship':'ambient','status':'blocked','reasons':[],'checked_at':1}))
