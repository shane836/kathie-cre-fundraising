import tempfile
import unittest
from pathlib import Path
from kathie.demo import prepare_demo, DemoHTTP
from kathie.http import ProviderError

class DemoTests(unittest.TestCase):
    def test_all_synthetic_cases_use_normal_screening(self):
        with tempfile.TemporaryDirectory() as folder:
            store, service, summary = prepare_demo(Path(folder)/'demo.sqlite', 'OWNER')
            self.assertTrue(store.demo_mode)
            self.assertEqual(len(summary['results']), 9)
            self.assertTrue(all(row['match'] for row in summary['results']))
            self.assertEqual(summary['counts'], {'eligible':2, 'blocked':5, 'held':2})
            self.assertEqual(len(store.screen_results()), 9)
            self.assertEqual(len(store.list_leads()), 9)
            service.handle('import', {'user_id':'OWNER','dataset_id':'demo','segment':'tech'})
            self.assertEqual(len(store.list_leads()), 9)

    def test_real_database_rejected(self):
        with self.assertRaises(ValueError):
            prepare_demo('/tmp/kathie.sqlite', 'OWNER')

    def test_does_not_reset_existing_edits(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'demo.sqlite'
            store, _, _ = prepare_demo(path, 'OWNER')
            store.save_snapshot('optouts',['acquired@example.com'],True)
            _, _, summary = prepare_demo(path, 'OWNER')
            acquired = next(row for row in summary['results'] if row['name']=='Alex Acquired')
            self.assertEqual(acquired['actual_status'], 'blocked')
            self.assertFalse(acquired['match'])

    def test_unknown_requests_fail_closed(self):
        with self.assertRaises(ProviderError):
            DemoHTTP([]).request('GET', 'https://unknown.example.com')
