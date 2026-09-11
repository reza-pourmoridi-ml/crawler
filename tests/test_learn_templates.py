import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from pydantic import ValidationError

from app.extractor.service import extract_tickets
from app.infra.config import Settings, settings
from app.infra.storage import learned_path, read_templates, read_tickets, write_json_atomic
from app.learn.service import learn_website, merge_templates
from app.learn.worker import handle_learn


class LearnTemplateTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        for name, value in [
            ('storage_root', directory.name),
            ('learn_max_new_templates', 20),
            ('learn_max_templates', 250),
        ]:
            setting_patch = patch.object(settings, name, value)
            setting_patch.start()
            self.addCleanup(setting_patch.stop)
        self.start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.snapshot_id = 'a' * 32

    def template(self, number):
        return {
            'html': f'<article>ticket {number}</article>',
            'learned_at': (self.start + timedelta(seconds=number)).isoformat(),
            'source_snapshot_id': f'{number:032x}',
        }

    def run_learn(self, tickets, website_id=1, route_type='domestic'):
        validation_path = self.root / 'validated.json'
        write_json_atomic(validation_path, tickets)
        with patch('app.learn.service.fast_safe_extraction', return_value={'output_file': 'candidates.json'}), \
             patch('app.learn.service.process_file_validation', return_value={'output_path': str(validation_path)}):
            return learn_website(self.root / 'page.html', website_id, route_type, self.snapshot_id)

    def test_merge_retains_previous_templates_and_adds_metadata(self):
        existing = self.template(1)
        write_json_atomic(learned_path(1, 'domestic'), [existing])
        before = datetime.now(timezone.utc)
        path = self.run_learn(['<article>new ticket</article>'])
        saved = json.loads(path.read_text())
        self.assertEqual(saved[0], existing)
        self.assertEqual(saved[1]['html'], '<article>new ticket</article>')
        self.assertEqual(saved[1]['source_snapshot_id'], self.snapshot_id)
        self.assertGreaterEqual(datetime.fromisoformat(saved[1]['learned_at']), before)
        self.assertLessEqual(datetime.fromisoformat(saved[1]['learned_at']), datetime.now(timezone.utc))

    def test_default_limit_is_twenty_new_templates_per_run(self):
        existing = [self.template(index) for index in range(10)]
        write_json_atomic(learned_path(1, 'domestic'), existing)
        tickets = [self.template(index)['html'] for index in range(10, 60)]
        saved = read_templates(self.run_learn(tickets))
        self.assertEqual(len(saved), 30)
        self.assertEqual(saved[:10], existing)
        self.assertEqual([template['html'] for template in saved[10:]], tickets[:20])

    def test_default_total_limit_is_250_and_removes_oldest_by_timestamp(self):
        existing = [self.template(index) for index in range(250)]
        write_json_atomic(learned_path(1, 'domestic'), list(reversed(existing)))
        tickets = [self.template(index)['html'] for index in range(250, 270)]
        saved = read_templates(self.run_learn(tickets))
        self.assertEqual(len(saved), 250)
        self.assertEqual(saved[:230], existing[20:])
        self.assertEqual([template['html'] for template in saved[-20:]], tickets)

    def test_limits_are_configurable(self):
        existing = [self.template(index) for index in range(3)]
        tickets = [self.template(index)['html'] for index in range(3, 10)]
        with patch.object(settings, 'learn_max_new_templates', 2), \
             patch.object(settings, 'learn_max_templates', 3):
            saved = merge_templates(existing, tickets, self.snapshot_id)
        self.assertEqual([template['html'] for template in saved], [existing[2]['html'], *tickets[:2]])

    def test_duplicates_do_not_consume_new_quota_or_refresh_metadata(self):
        existing = self.template(1)
        tickets = [existing['html'], '<b>new</b>', '<b>new</b>', existing['html'], '<b>other</b>', '<b>extra</b>']
        with patch.object(settings, 'learn_max_new_templates', 2):
            saved = merge_templates([existing], tickets, self.snapshot_id)
        self.assertEqual(saved[0], existing)
        self.assertEqual([template['html'] for template in saved], [existing['html'], '<b>new</b>', '<b>other</b>'])

    def test_duplicate_only_run_preserves_original_provenance(self):
        existing = self.template(1)
        self.assertEqual(merge_templates([existing], [existing['html']] * 30, self.snapshot_id), [existing])

    def test_total_limit_can_be_smaller_than_per_run_limit(self):
        tickets = [self.template(index)['html'] for index in range(10)]
        with patch.object(settings, 'learn_max_templates', 3):
            saved = merge_templates([], tickets, self.snapshot_id)
        self.assertEqual([template['html'] for template in saved], tickets[-3:])

    def test_lowered_total_limit_prunes_existing_templates_even_without_new_ones(self):
        existing = [self.template(index) for index in range(10)]
        with patch.object(settings, 'learn_max_templates', 3):
            saved = merge_templates(existing, [existing[0]['html']], self.snapshot_id)
        self.assertEqual(saved, existing[-3:])

    def test_timestamp_offsets_are_compared_chronologically(self):
        earlier = {**self.template(1), 'learned_at': '2026-01-01T12:00:00+03:30'}
        later = {**self.template(2), 'learned_at': '2026-01-01T09:00:00+00:00'}
        with patch.object(settings, 'learn_max_templates', 1):
            saved = merge_templates([later, earlier], [], self.snapshot_id)
        self.assertEqual(saved, [later])

    def test_legacy_html_list_is_readable_and_upgraded_on_merge(self):
        path = learned_path(1, 'domestic')
        legacy = ['<article>legacy</article>']
        write_json_atomic(path, legacy)
        os.utime(path, (self.start.timestamp(), self.start.timestamp()))
        self.assertEqual(read_tickets(path), legacy)
        self.run_learn(['<article>new</article>'])
        saved = json.loads(path.read_text())
        self.assertEqual(saved[0], {
            'html': legacy[0], 'learned_at': self.start.isoformat(), 'source_snapshot_id': None,
        })
        self.assertEqual(saved[1]['source_snapshot_id'], self.snapshot_id)

    def test_empty_validation_preserves_existing_file(self):
        path = learned_path(1, 'domestic')
        write_json_atomic(path, [self.template(1)])
        before = path.read_bytes(), path.stat().st_mtime_ns
        with self.assertRaises(ValueError):
            self.run_learn([])
        self.assertEqual((path.read_bytes(), path.stat().st_mtime_ns), before)

    def test_invalid_existing_data_is_not_silently_replaced(self):
        path = learned_path(1, 'domestic')
        path.parent.mkdir(parents=True)
        path.write_text('{invalid')
        with self.assertRaises(ValueError):
            self.run_learn(['<article>new</article>'])
        self.assertEqual(path.read_text(), '{invalid')

    def test_each_site_and_route_keeps_its_own_templates(self):
        first = self.run_learn(['<article>domestic</article>'])
        second = self.run_learn(['<article>international</article>'], route_type='international')
        third = self.run_learn(['<article>other website</article>'], website_id=2)
        self.assertEqual(read_tickets(first), ['<article>domestic</article>'])
        self.assertEqual(read_tickets(second), ['<article>international</article>'])
        self.assertEqual(read_tickets(third), ['<article>other website</article>'])

    def test_extractor_matches_only_html_from_metadata_records(self):
        html = '<article class="ticket"><span>Mahan Air</span><span>12:30</span><span>2,500,000</span></article>'
        path = learned_path(1, 'domestic')
        write_json_atomic(path, [{**self.template(1), 'html': html}])
        page = self.root / 'page.html'
        page.write_text('<html><body>' + html + '</body></html>')
        result = extract_tickets(page, path, {'ماهان': ['Mahan Air']})
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['time'], '12:30')
        self.assertEqual(result[0]['price'], 2500000)
        self.assertEqual(result[0]['airline'], 'ماهان')
        self.assertEqual(set(result[0]), {'time', 'price', 'airline', 'text'})

    def test_worker_passes_snapshot_id_to_learning(self):
        payload = {'website_id': 1, 'route_type': 'domestic', 'search_request_id': 1, 'snapshot_id': self.snapshot_id}
        with patch('app.learn.worker.learn_website') as learn:
            handle_learn(payload)
        self.assertEqual(learn.call_args.args[1:], (1, 'domestic', self.snapshot_id))

    def test_nonpositive_limits_are_rejected(self):
        for field in ['learn_max_new_templates', 'learn_max_templates']:
            for value in [0, -1]:
                with self.subTest(field=field, value=value), self.assertRaises(ValidationError):
                    Settings(_env_file=None, **{field: value})
