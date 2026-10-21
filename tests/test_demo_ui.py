import unittest
from kathie.ui import home_view,form

class Store:
    demo_mode=False
    def screen_results(self): return []
    def list_leads(self): return []
    def list_experiments(self): return []

class DemoUITests(unittest.TestCase):
    def test_demo_has_prominent_badge_and_walkthrough(self):
        store=Store(); store.demo_mode=True
        view=home_view(store)
        self.assertIn('DEMO',view['blocks'][0]['text']['text'])
        self.assertIn('fictional contacts',str(view)); self.assertIn('simulated Hunter/Attio',str(view)); self.assertIn('no credits or outreach',str(view))
        self.assertIn('dataset ID: demo',str(view)); self.assertIn('example.com',str(view))
    def test_live_mode_has_no_demo_instructions(self):
        view=home_view(Store())
        self.assertNotIn('DEMO',str(view)); self.assertNotIn('dataset ID: demo',str(view))
    def test_default_sequence_still_three_drafts(self):
        modal=form('experiment')
        followups=next(x for x in modal['blocks'] if x.get('block_id')=='followups')
        self.assertEqual(len(followups['element']['initial_value'].split('\n---\n')),3)
        self.assertIn('Nothing sends',str(modal))
