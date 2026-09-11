import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from app.infra.config import settings
from app.infra.storage import extracted_path, learned_path, snapshot_directory, write_json_atomic
from app.orchestration.jobs import plan_followups
from app.orchestration.maintenance import cleanup_artifacts, plan_job_deletions


class RuntimeCleanupTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        root_patch = patch.object(settings, 'storage_root', str(self.root))
        root_patch.start()
        self.addCleanup(root_patch.stop)
        self.now = datetime.now(timezone.utc)
        self.old = self.now - timedelta(days=40)
        self.cutoff = self.now - timedelta(seconds=settings.job_retention_seconds)

    def job(self, job_id, kind='scrape', status='failed', source=1, website=1, route='domestic', recent=False):
        payload = {'search_request_id': source, 'website_id': website,
                   'route_type': route, 'snapshot_id': f'{source:032x}'}
        if kind != 'scrape':
            payload['source_job_id'] = source
        return {'id': job_id, 'type': kind, 'status': status, 'outcome': 'success', 'payload': payload,
                'finished_at': self.now if recent else self.old}

    def age(self, path):
        for child in path.rglob('*') if path.is_dir() else []:
            if not child.is_symlink():
                os.utime(child, (self.old.timestamp(), self.old.timestamp()))
        os.utime(path, (self.old.timestamp(), self.old.timestamp()))
        return path

    def raw(self, job):
        directory = snapshot_directory(job['payload'])
        directory.mkdir(parents=True, exist_ok=True)
        (directory / 'page.html').write_text('<article>ticket</article>')
        (directory / 'screenshot.png').write_bytes(b'screenshot')
        return self.age(directory)

    def cleanup(self, jobs):
        removable = plan_job_deletions(jobs, self.cutoff)
        return cleanup_artifacts(jobs, removable, self.now)

    def test_completed_chain_is_pruned_but_last_learning_watermark_is_retained(self):
        scrape = self.job(1)
        learn = self.job(2, 'learn')
        extractor = self.job(3, 'extractor')
        raw = self.raw(scrape)
        output = extracted_path(extractor['payload'])
        write_json_atomic(output, [{'price': 2000000}])
        self.age(output)
        template = learned_path(1, 'domestic')
        write_json_atomic(template, ['<article>ticket</article>'])
        self.age(template)
        removable, removed = self.cleanup([scrape, learn, extractor])
        self.assertEqual(removable, {1, 3})
        self.assertGreaterEqual(removed, 2)
        self.assertFalse(raw.exists())
        self.assertFalse(output.exists())
        self.assertTrue(template.exists())

    def test_old_input_is_preserved_during_hours_long_learning_and_pending_retry(self):
        for status in ['pending', 'running']:
            with self.subTest(status=status):
                scrape = self.job(1)
                learn = self.job(2, 'learn', status)
                raw = self.raw(scrape)
                removable, _ = self.cleanup([scrape, learn])
                self.assertEqual(removable, set())
                self.assertTrue(raw.exists())

    def test_old_input_is_preserved_during_long_scrape(self):
        scrape = self.job(1, status='running')
        raw = self.raw(scrape)
        self.assertEqual(self.cleanup([scrape])[0], set())
        self.assertTrue(raw.exists())

    def test_active_extraction_protects_input_and_output(self):
        scrape = self.job(1)
        extractor = self.job(2, 'extractor', 'running')
        raw = self.raw(scrape)
        output = extracted_path(extractor['payload'])
        write_json_atomic(output, [])
        self.age(output)
        self.cleanup([scrape, extractor])
        self.assertTrue(raw.exists())
        self.assertTrue(output.exists())

    def test_newly_finished_dependency_keeps_scrape_and_deduplication_records(self):
        scrape = self.job(1)
        extractor = self.job(2, 'extractor', recent=True)
        raw = self.raw(scrape)
        self.assertEqual(self.cleanup([scrape, extractor])[0], set())
        self.assertTrue(raw.exists())

    def test_extractor_history_survives_while_source_is_retained(self):
        scrape = self.job(1, recent=True)
        extractor = self.job(2, 'extractor')
        self.assertEqual(plan_job_deletions([scrape, extractor], self.cutoff), set())

    def test_retention_expires_snapshots_waiting_forever_for_first_learning(self):
        scrape = self.job(1)
        raw = self.raw(scrape)
        self.assertEqual(self.cleanup([scrape])[0], {1})
        self.assertFalse(raw.exists())

    def test_recent_file_blocks_metadata_deletion_too(self):
        scrape = self.job(1)
        extractor = self.job(2, 'extractor')
        raw = self.raw(scrape)
        os.utime(raw / 'page.html', None)
        self.assertEqual(self.cleanup([scrape, extractor])[0], set())
        self.assertTrue(raw.exists())

    def test_only_latest_learning_source_per_website_and_route_is_kept(self):
        jobs = [self.job(10, 'learn', source=1), self.job(11, 'learn', source=3),
                self.job(12, 'learn', source=2), self.job(13, 'learn', source=4, route='international'),
                self.job(14, 'learn', source=5, website=2)]
        self.assertEqual(plan_job_deletions(jobs, self.cutoff), {10, 12})

    def test_restart_after_cleanup_does_not_relearn_an_old_source(self):
        learn = self.job(10, 'learn', source=3)
        scrape = self.job(2, source=2, recent=True)
        self.raw(scrape)
        self.assertEqual(plan_followups([scrape, learn]), [])

    def test_successful_failed_status_still_advances_the_pipeline(self):
        scrape = self.job(1, recent=True)
        self.raw(scrape)
        self.assertEqual(plan_followups([scrape])[0][0], 'learn')
        scrape['outcome'] = 'error'
        self.assertEqual(plan_followups([scrape]), [])

    def test_orphan_snapshots_and_scratch_are_removed_but_active_scratch_is_protected(self):
        orphan = self.raw(self.job(90, source=90))
        temporary = self.root / 'temp'
        paths = []
        for name in ['job_1_1_abcd', 'job_2_1_abcd', 'learn_abcd']:
            path = temporary / name
            path.mkdir(parents=True)
            (path / 'input.js').write_text('data')
            paths.append(self.age(path))
        active = self.job(2, 'learn', 'running')
        self.cleanup([active])
        self.assertFalse(orphan.exists())
        self.assertFalse(paths[0].exists())
        self.assertTrue(paths[1].exists())
        self.assertTrue(paths[2].exists())
        self.cleanup([])
        self.assertFalse(paths[1].exists())
        self.assertFalse(paths[2].exists())

    def test_atomic_leftovers_are_removed_without_deleting_templates(self):
        template = learned_path(1, 'domestic')
        write_json_atomic(template, ['<article>ticket</article>'])
        leftover = template.parent / '.atomic-orphan.tmp'
        leftover.write_text('partial')
        self.age(leftover)
        active = self.job(2, 'learn', 'running')
        self.cleanup([active])
        self.assertTrue(leftover.exists())
        self.cleanup([])
        self.assertFalse(leftover.exists())
        self.assertTrue(template.exists())

    def test_symlink_cannot_delete_data_outside_owned_storage(self):
        with tempfile.TemporaryDirectory() as outside:
            target = Path(outside) / 'important.txt'
            target.write_text('keep')
            path = self.root / 'raw' / 'website_1'
            path.parent.mkdir(parents=True)
            path.symlink_to(outside, target_is_directory=True)
            self.cleanup([])
            self.assertEqual(target.read_text(), 'keep')
