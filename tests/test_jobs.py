import tempfile
import unittest
from pathlib import Path

from kathie.jobs import JobQueue


class JobTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'jobs.sqlite'
        self.queue = JobQueue(self.path)

    def tearDown(self):
        self.temp.cleanup()

    def test_replayed_submission_enqueues_once(self):
        first = self.queue.enqueue('capture', {'user_id': 'U1'}, 'view-1')
        second = self.queue.enqueue('capture', {'user_id': 'U1'}, 'view-1')
        self.assertEqual(first, second)
        seen = []
        self.assertTrue(self.queue.run_one(lambda kind, payload: seen.append(payload) or {'ok': True}))
        self.assertFalse(self.queue.run_one(lambda *args: self.fail('duplicate job')))
        self.assertEqual(len(seen), 1)

    def test_pending_jobs_survive_restart(self):
        job_id = self.queue.enqueue('screen', {}, 'screen1')
        restarted = JobQueue(self.path)
        restarted.run_one(lambda *args: {'count': 3})
        self.assertEqual(restarted.get(job_id)['status'], 'succeeded')
        self.assertEqual(restarted.get(job_id)['result']['count'], 3)

    def test_failed_job_is_visible_and_not_automatically_retried(self):
        job_id = self.queue.enqueue('import', {}, 'import1')
        def failing(*args):
            raise ValueError('Dataset mapping is missing')
        self.queue.run_one(failing)
        self.assertEqual(self.queue.get(job_id)['status'], 'failed')
        self.assertIn('Dataset mapping', self.queue.get(job_id)['error'])
        self.assertFalse(self.queue.run_one(lambda *args: self.fail('unsafe retry')))

    def test_notification_ack_is_separate_from_job_success(self):
        job_id = self.queue.enqueue('screen', {}, 'screen1')
        self.queue.run_one(lambda *args: {'message': 'done'})
        self.assertEqual([row['id'] for row in self.queue.notifications()], [job_id])
        self.queue.mark_notified(job_id)
        self.assertEqual(self.queue.notifications(), [])

    def test_interrupted_credit_work_is_not_replayed(self):
        job_id = self.queue.enqueue('import', {}, 'import1')
        self.queue.claim()
        restarted = JobQueue(self.path)
        self.assertEqual(restarted.get(job_id)['status'], 'interrupted')
        self.assertFalse(restarted.run_one(lambda *args: self.fail('uncertain work rerun')))


if __name__ == '__main__':
    unittest.main()
