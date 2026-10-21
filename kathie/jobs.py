"""Durable, single-worker job queue; uncertain credit work is never replayed."""
from __future__ import annotations

import json
import logging
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from kathie.providers import ProviderError

LOG = logging.getLogger(__name__)


class JobQueue:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, kind TEXT NOT NULL, payload TEXT NOT NULL,
                dedupe_key TEXT NOT NULL UNIQUE, status TEXT NOT NULL,
                result TEXT, error TEXT, created_at REAL NOT NULL,
                notified INTEGER NOT NULL DEFAULT 0)''')
            db.execute("UPDATE jobs SET status='interrupted', error=? WHERE status='running'",
                ('Interrupted by restart. Review results before submitting this work again.',))

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def _row(row):
        if row is None:
            return None
        result = dict(row)
        result['payload'] = json.loads(result['payload'])
        result['result'] = json.loads(result['result']) if result['result'] else None
        return result

    def enqueue(self, kind, payload, dedupe_key):
        if not dedupe_key:
            raise ValueError('A stable submission ID is required.')
        with self.connect() as db:
            db.execute('INSERT OR IGNORE INTO jobs(id,kind,payload,dedupe_key,status,created_at) VALUES(?,?,?,?,?,?)',
                (uuid.uuid4().hex, kind, json.dumps(payload), dedupe_key, 'queued', time.time()))
            return db.execute('SELECT id FROM jobs WHERE dedupe_key=?', (dedupe_key,)).fetchone()['id']

    def get(self, job_id):
        with self.connect() as db:
            return self._row(db.execute('SELECT * FROM jobs WHERE id=?', (job_id,)).fetchone())

    def claim(self):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute("SELECT * FROM jobs WHERE status='queued' ORDER BY created_at,id LIMIT 1").fetchone()
            if row:
                db.execute("UPDATE jobs SET status='running' WHERE id=?", (row['id'],))
            return self._row(row)

    def run_one(self, handler):
        job = self.claim()
        if not job:
            return False
        try:
            result = handler(job['kind'], job['payload'])
            status, error = 'succeeded', None
        except Exception as exc:
            # Expected domain exceptions contain safe messages. Unknown exceptions
            # are classified without logging a possibly secret-bearing traceback.
            error = str(exc) if isinstance(exc, (ValueError, ProviderError)) else f'{type(exc).__name__}: job failed; review app configuration.'
            LOG.error('Job %s (%s) failed: %s', job['id'], job['kind'], error)
            result, status = None, 'failed'
        with self.connect() as db:
            db.execute('UPDATE jobs SET status=?,result=?,error=? WHERE id=?',
                (status, json.dumps(result) if result is not None else None, error, job['id']))
        return True

    def notifications(self):
        with self.connect() as db:
            return [self._row(row) for row in db.execute("SELECT * FROM jobs WHERE status IN ('succeeded','failed','interrupted') AND notified=0 ORDER BY created_at LIMIT 20")]

    def mark_notified(self, job_id):
        with self.connect() as db:
            db.execute('UPDATE jobs SET notified=1 WHERE id=?', (job_id,))
