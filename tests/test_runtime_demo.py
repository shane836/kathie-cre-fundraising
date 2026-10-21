import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from kathie import __main__ as cli


class RuntimeDemoTests(unittest.TestCase):
    def test_demo_flag_routes_to_demo_runtime(self):
        with patch('sys.argv', ['kathie', 'run', '--demo-data']), patch.object(cli, 'run') as run:
            cli.main()
        run.assert_called_once_with(demo_data=True)

    def test_regular_command_keeps_live_runtime(self):
        with patch('sys.argv', ['kathie', 'run']), patch.object(cli, 'run') as run:
            cli.main()
        run.assert_called_once_with(demo_data=False)

    def test_demo_ignores_real_database_and_provider_configuration(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            primary = base / 'real.sqlite'
            with patch.dict(os.environ, {'KATHIE_DB_PATH': str(primary), 'APIFY_FIELD_MAP': 'invalid-json', 'APIFY_TOKEN': 'must-not-use', 'HUNTER_API_KEY': 'must-not-use', 'ATTIO_TOKEN': 'must-not-use'}):
                with patch.object(cli, 'ApifyClient', side_effect=AssertionError('real Apify')), patch.object(cli, 'HunterClient', side_effect=AssertionError('real Hunter')), patch.object(cli, 'AttioClient', side_effect=AssertionError('real Attio')):
                    store, service, path = cli.build_runtime('OWNER', demo_data=True, base_dir=base)
            self.assertTrue(store.demo_mode)
            self.assertEqual(path, base / '.local/kathie-demo.sqlite')
            self.assertFalse(primary.exists())
            self.assertEqual(len(store.list_leads()), 9)

    def test_offline_demo_outputs_nine_cases_without_network(self):
        from contextlib import redirect_stdout
        from io import StringIO
        output = StringIO()
        with patch('kathie.http.urlopen', side_effect=AssertionError('network forbidden')), redirect_stdout(output):
            cli.demo()
        self.assertIn('2 eligible', output.getvalue())
        self.assertIn('5 blocked', output.getvalue())
        self.assertIn('2 held', output.getvalue())
        self.assertIn('Alex Acquired', output.getvalue())


if __name__ == '__main__':
    unittest.main()
