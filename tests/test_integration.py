import tempfile
import unittest
from pathlib import Path

from kathie.core import Store, SOURCES
from kathie.jobs import JobQueue
from kathie.service import Service
from kathie.providers import ProviderError


class FakeApify:
    def fetch_leads(self, dataset_id, segment):
        return [dict(first_name='New', last_name='Person', domain='example.com', profile_url='https://linkedin.com/in/new', email='', source='apify', source_id='dataset:1', segment=segment)]


class FakeHunter:
    def find_email(self, lead):
        return {'email': 'new@example.com', 'status': 'valid', 'sources': []}
    def verify(self, email):
        return 'valid'


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / 'app.sqlite')
        self.service = Service(self.store, owner='OWNER', apify=FakeApify(), hunter=FakeHunter(), attio_lookup=lambda email: False)

    def tearDown(self):
        self.temp.cleanup()

    def test_import_acquire_screen_and_preview_without_sending(self):
        queue = JobQueue(Path(self.temp.name) / 'app.sqlite')
        queue.enqueue('import', {'dataset_id': 'data1', 'segment': 'tech', 'user_id': 'OWNER'}, 'import1')
        queue.run_one(self.service.handle)
        lead = self.store.list_leads()[0]
        self.assertEqual(lead['email'], 'new@example.com')
        for source in SOURCES:
            self.service.handle('snapshot', {'source': source, 'emails': [], 'complete': True, 'user_id': 'OWNER'})
        result = self.service.handle('screen', {'user_id': 'OWNER'})
        self.assertEqual(result['counts']['eligible'], 1)
        experiment = self.service.handle('experiment', {'user_id': 'OWNER', 'data': dict(name='Test', segment='tech', subject='Storage', body='Shared body', hooks=['Opening A', 'Opening B'], followups=['Follow-up 1', 'Follow-up 2'], interval_business_days=2)})
        preview = self.store.preview_experiment(experiment['experiment_id'])
        self.assertEqual([step['after_business_days'] for step in preview['followups']], [2, 4])
        self.assertEqual(preview['experiment']['status'], 'draft')

    def test_unauthorized_job_cannot_modify_store(self):
        with self.assertRaises(PermissionError):
            self.service.handle('capture', {'user_id': 'OTHER', 'lead': dict(email='x@example.com', segment='tech', source='event')})
        self.assertEqual(self.store.list_leads(), [])

    def test_lookup_failure_preserves_captured_lead_and_visible_warning(self):
        class BrokenHunter(FakeHunter):
            def find_email(self, lead):
                raise ProviderError('Hunter: HTTP 429')
        self.service.hunter = BrokenHunter()
        result = self.service.handle('import', {'dataset_id': 'data1', 'segment': 'tech', 'user_id': 'OWNER'})
        self.assertEqual(len(self.store.list_leads()), 1)
        self.assertTrue(any('429' in warning for warning in result['warnings']))
        self.assertEqual(self.store.screen_leads()[0]['status'], 'held')

    def test_warm_capture_is_saved_for_automated_followup_later(self):
        result = self.service.handle('capture', {'user_id': 'OWNER', 'lead': dict(first_name='Known', email='known@example.com', segment='tech', source='event', relationship='warm')})
        self.assertEqual(self.store.get_lead(result['lead_id'])['relationship'], 'warm')
        self.assertIn('Warm follow-up', result['message'])

    def test_recapture_with_known_email_fills_existing_profile(self):
        self.service.hunter = None
        lead = dict(first_name='Known', last_name='Person', profile_url='https://linkedin.com/in/known', segment='tech', source='event', relationship='warm')
        first = self.service.handle('capture', {'user_id': 'OWNER', 'lead': lead})
        second = self.service.handle('capture', {'user_id': 'OWNER', 'lead': {**lead, 'email': 'known@example.com'}})
        self.assertEqual(first['lead_id'], second['lead_id'])
        self.assertEqual(self.store.get_lead(first['lead_id'])['email'], 'known@example.com')

    def test_ambient_capture_message_names_ambient_track(self):
        result = self.service.handle('capture', {'user_id': 'OWNER', 'lead': dict(first_name='Met', email='met@example.com', source='event', segment='tech', relationship='ambient', phone='555-0100', notes='Met at conference')})
        self.assertIn('Ambient follow-up', result['message'])
        self.assertEqual(self.store.get_lead(result['lead_id'])['phone'], '555-0100')


if __name__ == '__main__':
    unittest.main()
