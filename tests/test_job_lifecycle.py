import os
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy import create_engine, select, text, update
from sqlalchemy.orm import sessionmaker

from app.infra import queue
from app.infra.config import settings
from app.infra.progress import report_progress
from app.infra.storage import snapshot_directory
from app.orchestration.jobs import get_pipeline_jobs, plan_followups
from app.orchestration.maintenance import cleanup_runtime_data
from app.orchestration.models import Job
from app.infra.worker_base import run_handler_in_process


def leave_scratch_and_wait(payload):
    import subprocess
    import sys
    import tempfile
    work = Path(os.environ['CRAWLER_JOB_TEMP'])
    tempfile.NamedTemporaryFile(delete=False).close()
    (work / 'candidate.json').write_text('partial')
    subprocess.Popen([sys.executable, '-c',
                      'import time,pathlib,sys; time.sleep(2); pathlib.Path(sys.argv[1]).write_text("leaked")',
                      payload['marker']])
    Path(payload['started']).write_text(str(work))
    time.sleep(30)


def progress_then_finish(payload):
    deadline = time.monotonic() + payload['duration']
    while time.monotonic() < deadline:
        report_progress()
        time.sleep(payload['interval'])
    Path(payload['finished']).write_text('done')


def wait_without_progress(payload):
    time.sleep(payload['duration'])


class WorkerCleanupTests(unittest.TestCase):
    def test_timeout_removes_temporary_files_and_stops_descendants(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            marker = root / 'late-write'
            started = root / 'started'
            with patch.object(settings, 'storage_root', directory):
                with self.assertRaises(TimeoutError):
                    run_handler_in_process(leave_scratch_and_wait,
                                           {'marker': str(marker), 'started': str(started)}, 1)
            self.assertTrue(started.exists())
            self.assertFalse(Path(started.read_text()).exists())
            time.sleep(2)
            self.assertFalse(marker.exists())
            self.assertEqual(list((root / 'temp').iterdir()), [])

    def test_lost_lease_cancels_process(self):
        event = threading.Event()
        event.set()
        with tempfile.TemporaryDirectory() as directory, patch.object(settings, 'storage_root', directory):
            with self.assertRaisesRegex(RuntimeError, 'lease lost'):
                run_handler_in_process(leave_scratch_and_wait, {}, 60, cancel_events=(event,))
            self.assertEqual(list((Path(directory) / 'temp').iterdir()), [])

    def test_progress_allows_handler_to_run_past_idle_timeout(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(settings, 'storage_root', directory):
            finished = Path(directory) / 'finished'
            run_handler_in_process(
                progress_then_finish,
                {'duration': 2.5, 'interval': .1, 'finished': str(finished)},
                timeout=8,
                idle_timeout=2,
            )
            self.assertEqual(finished.read_text(), 'done')

    def test_missing_progress_triggers_idle_timeout(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(settings, 'storage_root', directory):
            with self.assertRaisesRegex(TimeoutError, 'no progress for 2s'):
                run_handler_in_process(
                    wait_without_progress,
                    {'duration': 10},
                    timeout=8,
                    idle_timeout=2,
                )

    def test_hard_timeout_wins_even_with_continuous_progress(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(settings, 'storage_root', directory):
            with self.assertRaisesRegex(TimeoutError, 'exceeded 2s'):
                run_handler_in_process(
                    progress_then_finish,
                    {'duration': 10, 'interval': .1, 'finished': str(Path(directory) / 'finished')},
                    timeout=2,
                    idle_timeout=4,
                )


@unittest.skipUnless(os.getenv('CRAWLER_TEST_DATABASE_URL'), 'Set CRAWLER_TEST_DATABASE_URL to an isolated PostgreSQL database')
class JobLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.admin = create_engine(os.environ['CRAWLER_TEST_DATABASE_URL'])
        self.schema = 'test_lifecycle_' + uuid4().hex
        with self.admin.begin() as db:
            db.execute(text(f'CREATE SCHEMA {self.schema}'))
        self.engine = create_engine(os.environ['CRAWLER_TEST_DATABASE_URL'],
                                    connect_args={'options': f'-csearch_path={self.schema}'})
        self.sessions = sessionmaker(bind=self.engine, expire_on_commit=False)
        Job.__table__.create(self.engine)
        self.addCleanup(self.cleanup_database)
        for module in ['app.infra.queue', 'app.orchestration.jobs', 'app.orchestration.maintenance']:
            setting_patch = patch(module + '.SessionLocal', self.sessions)
            setting_patch.start()
            self.addCleanup(setting_patch.stop)
        self.now = datetime.now(timezone.utc)

    def cleanup_database(self):
        self.engine.dispose()
        with self.admin.begin() as db:
            db.execute(text(f'DROP SCHEMA {self.schema} CASCADE'))
        self.admin.dispose()

    def get(self, job_id):
        with self.sessions() as db:
            return db.get(Job, job_id)

    def change(self, job_id, **values):
        with self.sessions.begin() as db:
            db.execute(update(Job).where(Job.id == job_id).values(**values))

    def test_success_is_terminal_failed_with_success_outcome(self):
        job_id = queue.enqueue('scrape', {})
        job = queue.fetch_job(['scrape'])
        self.assertTrue(queue.mark_done(job_id, attempt=job['attempts']))
        saved = self.get(job_id)
        self.assertEqual((saved.status, saved.outcome), ('failed', 'success'))
        self.assertIsNotNone(saved.finished_at)
        self.assertIsNone(queue.fetch_job(['scrape']))
        self.assertFalse(queue.mark_failed(job_id, attempt=1))
        self.assertEqual(self.get(job_id).outcome, 'success')

    def test_repeated_crashes_reach_final_failure_at_max_attempts(self):
        job_id = queue.enqueue('learn', {}, max_attempts=2)
        queue.fetch_job(['learn'])
        self.change(job_id, locked_until=self.now - timedelta(seconds=1))
        queue.sweep_stuck_jobs()
        saved = self.get(job_id)
        self.assertEqual(saved.status, 'pending')
        self.assertGreater(saved.run_at, self.now)
        self.change(job_id, run_at=self.now)
        job = queue.fetch_job(['learn'])
        self.assertEqual(job['attempts'], 2)
        self.change(job_id, locked_until=self.now - timedelta(seconds=1))
        queue.sweep_stuck_jobs()
        saved = self.get(job_id)
        self.assertEqual((saved.status, saved.outcome), ('failed', 'error'))
        self.assertIsNotNone(saved.finished_at)
        self.assertIsNone(queue.fetch_job(['learn']))

    def test_regular_failure_retries_then_finishes(self):
        job_id = queue.enqueue('scrape', {}, max_attempts=2)
        queue.fetch_job(['scrape'])
        self.assertTrue(queue.mark_failed(job_id, attempt=1))
        self.assertEqual(self.get(job_id).status, 'pending')
        self.change(job_id, run_at=self.now)
        queue.fetch_job(['scrape'])
        queue.mark_failed(job_id, attempt=2)
        self.assertEqual((self.get(job_id).status, self.get(job_id).outcome), ('failed', 'error'))

    def test_stale_worker_cannot_finish_fail_or_extend_new_attempt(self):
        job_id = queue.enqueue('learn', {})
        queue.fetch_job(['learn'])
        queue.mark_failed(job_id, attempt=1)
        self.change(job_id, run_at=self.now)
        queue.fetch_job(['learn'])
        self.assertFalse(queue.mark_done(job_id, attempt=1))
        self.assertFalse(queue.mark_failed(job_id, attempt=1))
        self.assertFalse(queue.extend_lock(job_id, attempt=1))
        self.assertEqual(self.get(job_id).status, 'running')
        self.assertTrue(queue.mark_done(job_id, attempt=2))

    def test_heartbeat_cannot_extend_hard_deadline(self):
        job_id = queue.enqueue('learn', {}, max_attempts=1)
        queue.fetch_job(['learn'], lock_seconds=60)
        deadline = self.now + timedelta(seconds=10)
        self.change(job_id, deadline_at=deadline)
        self.assertTrue(queue.extend_lock(job_id, lock_seconds=999999, attempt=1))
        self.assertEqual(self.get(job_id).locked_until, deadline)
        self.change(job_id, deadline_at=self.now - timedelta(seconds=1), locked_until=self.now + timedelta(hours=10))
        self.assertFalse(queue.extend_lock(job_id, attempt=1))
        queue.sweep_stuck_jobs()
        self.assertEqual(self.get(job_id).status, 'failed')

    def test_long_learn_and_scrape_with_valid_leases_are_not_reaped(self):
        for kind, remaining in [('learn', 3 * 60 * 60), ('scrape', 10 * 60)]:
            job_id = queue.enqueue(kind, {})
            queue.fetch_job([kind])
            self.change(job_id, created_at=self.now - timedelta(days=10),
                        locked_until=self.now + timedelta(seconds=remaining),
                        deadline_at=self.now + timedelta(seconds=remaining + 60))
            queue.sweep_stuck_jobs()
            self.assertEqual(self.get(job_id).status, 'running')

    def test_pending_without_worker_fails_but_future_scheduled_job_is_kept(self):
        old = queue.enqueue('unknown', {}, run_at=self.now - timedelta(seconds=settings.pending_job_timeout + 1))
        future = queue.enqueue('learn', {}, run_at=self.now + timedelta(days=30))
        self.assertIsNone(queue.fetch_job(['unknown']))
        queue.sweep_stuck_jobs()
        self.assertEqual((self.get(old).status, self.get(old).outcome), ('failed', 'error'))
        self.assertEqual(self.get(future).status, 'pending')

    def test_legacy_running_gets_bounded_deadline_without_interrupting_learning(self):
        job_id = queue.enqueue('learn', {})
        self.change(job_id, status='running', attempts=1, locked_until=None, deadline_at=None)
        queue.sweep_stuck_jobs()
        saved = self.get(job_id)
        self.assertEqual(saved.status, 'running')
        self.assertGreater(saved.deadline_at, self.now + timedelta(hours=29))

    def test_only_one_concurrent_worker_claims_a_job(self):
        queue.enqueue('scrape', {})
        with ThreadPoolExecutor(max_workers=8) as executor:
            jobs = list(executor.map(lambda _: queue.fetch_job(['scrape']), range(8)))
        self.assertEqual(sum(job is not None for job in jobs), 1)

    def test_cleanup_and_success_outcome_preserve_pipeline_progress(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(settings, 'storage_root', directory):
            payload = {'search_request_id': 1, 'website_id': 1, 'route_type': 'domestic', 'snapshot_id': 'a' * 32}
            source = queue.enqueue('scrape', payload)
            queue.fetch_job(['scrape'])
            raw = snapshot_directory(payload)
            raw.mkdir(parents=True)
            (raw / 'page.html').write_text('<article>ticket</article>')
            queue.mark_done(source, attempt=1)
            self.assertEqual(plan_followups(get_pipeline_jobs())[0][0], 'learn')
            learn = queue.enqueue('learn', {**payload, 'source_job_id': source})
            extract = queue.enqueue('extractor', {**payload, 'source_job_id': source})
            for kind in ['learn', 'extractor']:
                job = queue.fetch_job([kind])
                queue.mark_done(job['id'], attempt=job['attempts'])
            old = self.now - timedelta(days=40)
            for job_id in [source, learn, extract]:
                self.change(job_id, finished_at=old)
            os.utime(raw / 'page.html', (old.timestamp(), old.timestamp()))
            os.utime(raw, (old.timestamp(), old.timestamp()))
            result = cleanup_runtime_data(self.now)
            self.assertEqual(result['jobs_removed'], 2)
            self.assertIsNone(self.get(source))
            self.assertIsNone(self.get(extract))
            self.assertIsNotNone(self.get(learn))
            self.assertFalse(raw.exists())

    def test_migration_preserves_real_outcomes_and_can_be_reversed(self):
        import importlib.util
        from alembic.migration import MigrationContext
        from alembic.operations import Operations

        path = Path(__file__).resolve().parents[1] / 'migrations/versions/2026_09_11_job_lifecycle.py'
        spec = importlib.util.spec_from_file_location('job_lifecycle_migration', path)
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        with self.engine.begin() as db:
            for column in ['deadline_at', 'finished_at', 'outcome']:
                db.execute(text(f'ALTER TABLE jobs DROP COLUMN {column}'))
            db.execute(text("INSERT INTO jobs (id, type, payload, status, attempts, max_attempts) VALUES "
                            "(1, 'scrape', '{}', 'done', 1, 3), (2, 'learn', '{}', 'failed', 3, 3), "
                            "(3, 'learn', '{}', 'running', 1, 3)"))
            with Operations.context(MigrationContext.configure(db)):
                migration.upgrade()
            rows = db.execute(text('SELECT status, outcome, finished_at FROM jobs ORDER BY id')).all()
            self.assertEqual([(row.status, row.outcome) for row in rows],
                             [('failed', 'success'), ('failed', 'error'), ('running', None)])
            self.assertIsNotNone(rows[0].finished_at)
            self.assertIsNone(rows[2].finished_at)
            with Operations.context(MigrationContext.configure(db)):
                migration.downgrade()
            self.assertEqual(list(db.scalars(text('SELECT status FROM jobs ORDER BY id'))),
                             ['done', 'failed', 'running'])
