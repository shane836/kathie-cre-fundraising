import tempfile
import unittest
from pathlib import Path
from kathie.core import Store, SOURCES
from kathie.ui import result_text, form


class AudienceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / 'audience.sqlite')
        for source in SOURCES:
            self.store.save_snapshot(source, [])

    def tearDown(self):
        self.temp.cleanup()

    def capture(self, audience):
        lead = self.store.add_lead(dict(first_name='Test', email='test@example.com', source='apify', segment='tech', audience=audience))
        self.store.set_verification(lead, 'valid')
        return lead

    def test_unverified_audience_is_flagged_but_not_suppression_hold(self):
        self.capture({'status': 'unverified', 'missing': ['school'], 'checks': {'school': None}})
        result = self.store.screen_leads()[0]
        self.assertEqual(result['status'], 'eligible')
        self.assertEqual(result['audience']['missing'], ['school'])
        self.assertIn('Unverified', result_text(result))

    def test_known_audience_mismatch_is_excluded(self):
        self.capture({'status': 'excluded', 'missing': [], 'checks': {'location': False}})
        self.assertEqual(self.store.screen_leads()[0]['status'], 'blocked')

    def test_new_mismatch_cannot_disappear_in_duplicate(self):
        self.capture({'status': 'unverified', 'missing': ['location'], 'checks': {'location': None}})
        self.store.add_lead(dict(email='test@example.com', source='apify', segment='tech', audience={'status': 'excluded', 'missing': [], 'checks': {'location': False}}))
        self.assertEqual(self.store.screen_leads()[0]['status'], 'blocked')

    def test_new_messaging_form_has_three_editable_followups(self):
        view = form('experiment')
        field = next(block for block in view['blocks'] if block.get('block_id') == 'followups')
        self.assertEqual(len(field['element']['initial_value'].split('\n---\n')), 3)


if __name__ == '__main__':
    unittest.main()
