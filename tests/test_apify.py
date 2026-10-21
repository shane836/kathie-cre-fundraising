import unittest
from kathie.apify import ApifyClient
from kathie.http import ProviderError

class Fake:
    def __init__(self,*responses): self.responses=list(responses); self.calls=[]
    def request(self,*args,**kwargs):
        self.calls.append((args,kwargs)); return self.responses.pop(0)

class ApifyTests(unittest.TestCase):
    def test_unknown_is_not_verified(self):
        lead=ApifyClient('x',Fake([{'firstName':'Ada'}])).fetch_leads('data','tech')[0]
        self.assertEqual(lead['audience']['status'],'unverified')
        self.assertEqual(len(lead['audience']['missing']),4)
    def test_false_evidence_excludes(self):
        lead=ApifyClient('x',Fake([{'firstName':'Ada','audience':{'checks':{'location':False}}}])).fetch_leads('data','real_estate')[0]
        self.assertEqual(lead['audience']['status'],'excluded')
    def test_true_requires_all_checks(self):
        row={'firstName':'Ada','audience':{'checks':dict.fromkeys(['location','tech_employment','school','engagement'],True)}}
        self.assertEqual(ApifyClient('x',Fake([row])).fetch_leads('data','tech')[0]['audience']['status'],'verified')
    def test_pagination(self):
        client=ApifyClient('x',Fake([{'firstName':'Ada'}],[]),page_size=1)
        self.assertEqual(len(client.fetch_leads('data','tech')),1)
        self.assertIn('offset=1',client.http.calls[1][0][1])
    def test_task_requires_budget(self):
        with self.assertRaises(ProviderError): ApifyClient('x',Fake()).start_task('task',{},max_charge_usd=0)
    def test_task_start_and_pending(self):
        http=Fake({'data':{'id':'run','status':'RUNNING'}},{'data':{'id':'run','status':'SUCCEEDED','defaultDatasetId':'data'}},[{'firstName':'Ada'}])
        client=ApifyClient('x',http)
        self.assertEqual(client.start_task('task',{'configured':'input'},max_charge_usd=1)['id'],'run')
        self.assertEqual(len(client.fetch_task_leads('run','tech')),1)
        self.assertNotIn('token=',http.calls[0][0][1])
    def test_pending_no_empty_success(self):
        with self.assertRaises(ProviderError): ApifyClient('x',Fake({'data':{'status':'RUNNING'}})).fetch_task_leads('run','tech')
    def test_bad_evidence_fails(self):
        with self.assertRaises(ProviderError): ApifyClient('x',Fake([{'firstName':'Ada','audience':{'checks':{'location':'yes'}}}])).fetch_leads('data','tech')
