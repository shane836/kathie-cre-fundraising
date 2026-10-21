import tempfile
import unittest
from pathlib import Path
from kathie.core import Store

SOURCES = ('asana','beehiiv','mailerlite','replies','sends','optouts','bounces','attio')

class CoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name)/'db.sqlite'
        self.store = Store(self.path)
    def tearDown(self): self.tmp.cleanup()
    def lead(self, **kw):
        return self.store.add_lead(dict(email='Person@Example.com',source='apify',segment='tech',**kw))
    def ready(self):
        for source in SOURCES: self.store.save_snapshot(source, [], now=1000)
    def test_identity_and_durable_context(self):
        lead = self.lead(notes='original')
        self.assertEqual(lead,self.store.add_lead({'email':'person@example.com','source':'apify','segment':'tech'}))
        self.assertEqual(Store(self.path).get_lead(lead)['notes'],'original')
        with self.assertRaises(ValueError): self.store.set_email(lead,'not an email')
    def test_eligible_requires_every_check(self):
        lead=self.lead(); self.ready(); self.store.set_verification(lead,'valid',1000)
        self.assertEqual(self.store.screen_leads(now=1001)[0]['status'],'eligible')
        result=self.store.screen_leads(now=100000)[0]
        self.assertEqual(result['status'],'held')
        self.assertTrue(any('asana' in r for r in result['reasons']))
    def test_historical_block_overrides_stale_and_empty(self):
        self.lead(); self.store.save_snapshot('optouts',['PERSON@example.com'],now=1000)
        self.store.save_snapshot('optouts',[],now=1001)
        result=self.store.screen_leads(now=100000)[0]
        self.assertEqual(result['status'],'blocked')
        self.assertIn('optouts match',result['reasons'])
    def test_invalid_snapshot_atomic_and_incomplete_held(self):
        self.lead(); self.ready()
        self.store.save_snapshot('asana',['person@example.com'],now=1000)
        with self.assertRaises(ValueError): self.store.save_snapshot('asana',['bad'],now=1001)
        self.assertEqual(self.store.screen_leads(now=1002)[0]['status'],'blocked')
    def test_provider_errors_visible_and_manual_blocked(self):
        lead=self.lead(); self.ready(); self.store.set_verification(lead,'valid',1000)
        def broken(email): raise RuntimeError('secret response')
        result=self.store.screen_leads(attio_lookup=broken,now=1001)[0]
        self.assertEqual(result['status'],'held')
        self.assertIn('attio lookup failed (RuntimeError)', result['reasons'])
        self.store.add_lead({'email':'warm@example.com','source':'event','segment':'tech'})
        self.assertEqual(self.store.screen_leads(now=1001)[1]['status'],'blocked')
    def test_profile_dedupe_and_email_collision(self):
        a=self.store.add_lead({'profile_url':'https://linkedin.com/in/person/','source':'apify','segment':'tech'})
        self.assertEqual(a,self.store.add_lead({'profile_url':'https://linkedin.com/in/person','email':'x@example.com','source':'apify','segment':'tech'}))
        b=self.lead()
        with self.assertRaises(ValueError): self.store.set_email(a,'person@example.com')
    def test_versioning_and_finite_preview(self):
        data=dict(name='test',segment='tech',subject='Hello',body='Shared',hooks=['One','Two'],followups=['Again','Final'],interval_business_days=2)
        first=self.store.save_experiment(data,'owner'); data['body']='Revised'
        second=self.store.save_experiment(data,'owner',first['id'])
        self.assertEqual(second['version'],2)
        self.assertEqual(self.store.preview_experiment(first['id'])['variants'][0]['initial'],'One\n\nRevised')
        self.assertEqual([x['after_business_days'] for x in self.store.preview_experiment(first['id'])['followups']],[2,4])
        self.assertEqual(len(self.store.list_experiments()),1)
        with self.assertRaises(ValueError): self.store.save_experiment({**data,'interval_business_days':3},'owner')
        with self.assertRaises(ValueError): self.store.save_experiment({**data,'body':'Bad—copy'},'owner')

if __name__=='__main__': unittest.main()

class RecaptureTests(unittest.TestCase):
    def test_manual_recapture_marks_original_cold_lead_warm(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'db.sqlite')
            original=store.add_lead({'email':'x@example.com','source':'apify','segment':'tech','notes':'original'})
            duplicate=store.add_lead({'email':'X@example.com','source':'event','segment':'tech'})
            self.assertEqual(original,duplicate)
            self.assertEqual(store.get_lead(original)['notes'],'original')
            self.assertEqual(store.screen_leads()[0]['status'],'blocked')

class RoutingTests(unittest.TestCase):
    def test_explicit_cold_event_requires_and_can_pass_all_checks(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'db.sqlite')
            lead=store.add_lead({'email':'cold@example.com','source':'event','segment':'tech','relationship':'cold'})
            for source in SOURCES: store.save_snapshot(source, [], now=1000)
            store.set_verification(lead,'valid',1000)
            self.assertEqual(store.get_lead(lead)['relationship'],'cold')
            self.assertEqual(store.screen_leads(now=1001)[0]['status'],'eligible')
            store.save_snapshot('asana',['cold@example.com'],now=1000)
            self.assertEqual(store.screen_leads(now=1001)[0]['status'],'blocked')
    def test_warm_apify_cannot_be_downgraded_by_duplicate(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'db.sqlite')
            lead=store.add_lead({'email':'warm@example.com','source':'apify','segment':'tech','relationship':'warm'})
            store.add_lead({'email':'warm@example.com','source':'apify','segment':'tech','relationship':'cold'})
            self.assertEqual(store.get_lead(lead)['relationship'],'warm')
            self.assertIn('Warm contact: use warm follow-up track',store.screen_leads()[0]['reasons'])
            with self.assertRaises(ValueError): store.add_lead({'source':'event','segment':'tech','relationship':'bad'})
    def test_any_finite_followup_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'db.sqlite')
            data=dict(name='long',segment='tech',subject='Hello',body='Shared',hooks=['One','Two'],followups=['Follow']*12)
            exp=store.save_experiment(data,'owner')
            self.assertEqual(len(store.preview_experiment(exp['id'])['followups']),12)

class EvidenceFreshnessTests(unittest.TestCase):
    def test_result_relationship_and_snapshot_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'db.sqlite')
            store.add_lead({'email':'w@example.com','source':'apify','segment':'tech','relationship':'warm'})
            self.assertEqual(store.screen_leads()[0]['relationship'],'warm')
            self.assertIsNone(store.snapshot('asana'))
            store.save_snapshot('asana',['X@example.com'],complete=False,now=123)
            self.assertEqual(store.snapshot('asana'),{'emails':['x@example.com'],'complete':False,'updated_at':123})
    def test_verification_and_snapshot_invalidate_current_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'db.sqlite')
            lead=store.add_lead({'email':'x@example.com','source':'apify','segment':'tech'})
            store.screen_leads()
            store.set_verification(lead,'valid')
            self.assertEqual(store.screen_results(),[])
            store.screen_leads()
            store.save_snapshot('asana',[])
            self.assertEqual(store.screen_results(),[])
    def test_old_results_no_longer_display_as_eligible(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'db.sqlite')
            lead=store.add_lead({'email':'x@example.com','source':'apify','segment':'tech'})
            for source in SOURCES: store.save_snapshot(source,[],now=1000)
            store.set_verification(lead,'valid',1000)
            self.assertEqual(store.screen_leads(now=1001)[0]['status'],'eligible')
            self.assertEqual(store.screen_results()[0]['status'],'held')

class AmbientTests(unittest.TestCase):
    def test_ambient_track_and_phone_capture(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'db.sqlite')
            lead=store.add_lead({'email':'a@example.com','source':'event','segment':'tech','relationship':'ambient','phone':'+1 555 0100'})
            self.assertEqual(store.get_lead(lead)['phone'],'+1 555 0100')
            result=store.screen_leads()[0]
            self.assertEqual(result['relationship'],'ambient')
            self.assertEqual(result['track'],'ambient')
            self.assertEqual(result['status'],'blocked')
            self.assertIn('Ambient contact: use ambient follow-up track',result['reasons'])
    def test_recapture_preserves_strongest_relationship(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'db.sqlite')
            data={'email':'a@example.com','source':'apify','segment':'tech'}
            lead=store.add_lead(data)
            store.add_lead({**data,'relationship':'ambient'})
            store.add_lead({**data,'relationship':'cold'})
            self.assertEqual(store.get_lead(lead)['relationship'],'ambient')
            store.add_lead({**data,'relationship':'warm'})
            store.add_lead({**data,'relationship':'ambient'})
            self.assertEqual(store.get_lead(lead)['relationship'],'warm')
            self.assertEqual(store.screen_leads()[0]['track'],'warm')
            with self.assertRaises(ValueError): store.add_lead({**data,'phone':123})
