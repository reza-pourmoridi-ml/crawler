"""Notebook fidelity and isolated workflow tests; no live DB, browser or LLM."""

import ast
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.control.airlines.models import Airline, AirlineAlias
from app.control.airports.models import Airport
from app.control.flight_paths.models import FlightPath
from app.control.search_box.models import SearchRequest
from app.control.websites.models import Website
from app.extractor.repo import get_airlines
from app.extractor.service import extract_tickets
from app.extractor.tickets import extract_ticket_item
from app.infra.config import settings
from app.infra.db import Base
from app.infra.storage import extracted_path, learned_path, read_tickets, snapshot_directory, write_json_atomic
from app.infra.worker_base import run_handler_in_process
from app.orchestration.jobs import create_scrape_jobs, plan_followups

ROOT = Path(__file__).resolve().parents[1]
CARD = '<article class="ticket"><div class="airline">Mahan Air</div><div class="route">تهران به مشهد</div><div class="time">۱۲:۳۰</div><div class="price">۲٬۵۰۰٬۰۰۰ تومان</div><button>انتخاب پرواز</button></article>'
PAGE = '<html><body><main>' + CARD + '</main></body></html>'


def process_write(payload):
    Path(payload['path']).write_text('done')


def process_fail(payload):
    raise ValueError('test failure')


def process_wait(payload):
    time.sleep(5)
    process_write(payload)


class NotebookFidelityTests(unittest.TestCase):
    def test_original_algorithm_functions_are_preserved(self):
        notebook = json.loads((ROOT / 'test-ollama.ipynb').read_text())
        pairs = [
            (5, 'app/learn/candidates.py', {'save_final_layers'}),
            (7, 'app/learn/validation.py', {'start_ollama_server', 'run_pipeline', 'process_file_validation'}),
            (9, 'app/extractor/matching.py', set()),
            (10, 'app/extractor/tickets.py', {'get_airline', 'extract_ticket_item', 'process_ticket_data'}),
        ]
        for cell, filename, excluded in pairs:
            original = ast.parse(''.join(notebook['cells'][cell]['source']))
            actual = ast.parse((ROOT / filename).read_text())
            functions = {node.name: node for node in actual.body if isinstance(node, ast.FunctionDef)}
            for node in original.body:
                if isinstance(node, ast.FunctionDef) and node.name not in excluded:
                    with self.subTest(file=filename, function=node.name):
                        self.assertEqual(ast.dump(node), ast.dump(functions[node.name]))

    def test_airline_adapter_matches_notebook_with_same_dictionary(self):
        source = json.loads((ROOT / 'test-ollama.ipynb').read_text())['cells'][10]['source']
        nodes = ast.parse(''.join(source)).body
        # Execute definitions and constants only, excluding the Kaggle batch call.
        nodes = [node for node in nodes if not (
            isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'results' for t in node.targets)
        )]
        namespace = {}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), '<notebook>', 'exec'), namespace)
        for html in [CARD, '<div>Iran Airtour 23:10 9,000,000</div>', '<div>unknown 0</div>']:
            self.assertEqual(extract_ticket_item(html, namespace['airlines']), namespace['extract_ticket_item'](html))


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        root_patch = patch.object(settings, 'storage_root', self.directory.name)
        root_patch.start()
        self.addCleanup(root_patch.stop)
        self.now = datetime.now(timezone.utc)

    def scrape(self, job_id=1, website_id=1, route_type='domestic', status='done'):
        payload = {
            'search_request_id': job_id, 'website_id': website_id,
            'route_type': route_type, 'snapshot_id': f'{job_id:032x}',
        }
        folder = snapshot_directory(payload)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / 'page.html').write_text(PAGE, encoding='utf-8')
        return {'id': job_id, 'type': 'scrape', 'status': status, 'payload': payload, 'run_at': self.now}

    def learned(self, website_id=1, route_type='domestic', age=0):
        path = learned_path(website_id, route_type)
        write_json_atomic(path, [CARD])
        timestamp = self.now.timestamp() - age
        os.utime(path, (timestamp, timestamp))
        return path

    def child(self, parent, kind='learn', status='running'):
        return {'id': 100, 'type': kind, 'status': status,
                'payload': {**parent['payload'], 'source_job_id': parent['id']}, 'run_at': self.now}

    def test_first_sample_learns_before_extracting(self):
        scrape = self.scrape()
        planned = plan_followups([scrape])
        self.assertEqual([kind for kind, _ in planned], ['learn'])
        self.assertEqual(planned[0][1]['source_job_id'], scrape['id'])

    def test_one_learn_per_site_and_route_uses_latest_sample(self):
        jobs = [self.scrape(1), self.scrape(2), self.scrape(3, route_type='international'), self.scrape(4, website_id=2)]
        planned = plan_followups(jobs)
        self.assertEqual([kind for kind, _ in planned], ['learn'] * 3)
        self.assertEqual({p['source_job_id'] for _, p in planned}, {2, 3, 4})

    def test_pending_running_learning_blocks_duplicates(self):
        scrape = self.scrape()
        for status in ['pending', 'running']:
            self.assertEqual(plan_followups([scrape, self.child(scrape, status=status)]), [])

    def test_existing_learning_extracts_each_snapshot_without_relearning(self):
        self.learned()
        scrapes = [self.scrape(1), self.scrape(2)]
        planned = plan_followups([*scrapes, self.child(scrapes[-1], status='done')])
        self.assertEqual([kind for kind, _ in planned], ['extractor', 'extractor'])

    def test_expired_learning_refreshes_once_and_remains_usable(self):
        self.learned(age=8 * 24 * 60 * 60)
        planned = plan_followups([self.scrape(1), self.scrape(2)])
        self.assertEqual([kind for kind, _ in planned], ['learn', 'extractor', 'extractor'])

    def test_refresh_in_progress_does_not_block_extraction(self):
        scrape = self.scrape()
        self.learned(age=8 * 24 * 60 * 60)
        planned = plan_followups([scrape, self.child(scrape)])
        self.assertEqual([kind for kind, _ in planned], ['extractor'])

    def test_restart_never_recreates_existing_extraction_even_after_failure(self):
        scrape = self.scrape()
        self.learned()
        for status in ['pending', 'running', 'done', 'failed']:
            self.assertEqual(plan_followups([scrape, self.child(scrape, 'extractor', status), self.child(scrape, status='done')]), [])

    def test_failed_learning_requires_new_snapshot(self):
        scrape = self.scrape()
        failed = self.child(scrape, status='failed')
        self.assertEqual(plan_followups([scrape, failed]), [])
        planned = plan_followups([scrape, failed, self.scrape(2)])
        self.assertEqual([kind for kind, _ in planned], ['learn'])
        self.assertEqual(planned[0][1]['source_job_id'], 2)

    def test_newest_snapshot_waits_for_active_learn_then_runs_immediately(self):
        original = self.scrape(1)
        newer = self.scrape(2)
        newest = self.scrape(3)
        self.learned()
        for status in ['pending', 'running']:
            planned = plan_followups([original, newer, newest, self.child(original, status=status)])
            self.assertEqual([kind for kind, _ in planned], ['extractor'] * 3)
        planned = plan_followups([original, newer, newest, self.child(original, status='done')])
        self.assertEqual([kind for kind, _ in planned], ['learn', 'extractor', 'extractor', 'extractor'])
        self.assertEqual(planned[0][1]['source_job_id'], 3)

    def test_old_template_without_new_scrape_does_not_trigger_learn(self):
        scrape = self.scrape()
        self.learned(age=30 * 24 * 60 * 60)
        planned = plan_followups([scrape, self.child(scrape, status='done')])
        self.assertEqual([kind for kind, _ in planned], ['extractor'])

    def test_last_source_uses_maximum_scrape_id_not_job_order(self):
        older = self.scrape(1)
        newer = self.scrape(2)
        latest_learn = self.child(newer, status='done')
        older_learn = self.child(older, status='failed')
        self.assertEqual(plan_followups([newer, latest_learn, older, older_learn]), [])

    def test_newer_unsuccessful_scrape_does_not_trigger_learn(self):
        original = self.scrape(1)
        for status in ['pending', 'running', 'failed']:
            planned = plan_followups([original, self.child(original, status='done'), self.scrape(2, status=status)])
            self.assertEqual(planned, [])

    def test_active_learning_is_independent_for_each_website_and_route(self):
        domestic = self.scrape(1)
        international = self.scrape(2, route_type='international')
        other_website = self.scrape(3, website_id=2)
        planned = plan_followups([domestic, international, other_website, self.child(domestic)])
        self.assertEqual([kind for kind, _ in planned], ['learn', 'learn'])
        self.assertEqual({payload['source_job_id'] for _, payload in planned}, {2, 3})

    def test_next_poll_does_not_duplicate_newly_planned_learn(self):
        scrape = self.scrape()
        planned = plan_followups([scrape])
        pending = {'type': planned[0][0], 'payload': planned[0][1], 'status': 'pending'}
        self.assertEqual(plan_followups([scrape, pending]), [])

    def test_missing_raw_or_unfinished_scrape_is_not_dispatched(self):
        scrape = self.scrape(status='running')
        self.assertEqual(plan_followups([scrape]), [])
        scrape['status'] = 'done'
        (snapshot_directory(scrape['payload']) / 'page.html').unlink()
        self.assertEqual(plan_followups([scrape]), [])

    def test_corrupt_template_relearns_without_dispatching_extraction(self):
        path = self.learned()
        path.write_text('{invalid')
        self.assertEqual([kind for kind, _ in plan_followups([self.scrape()])], ['learn'])

    def test_learning_then_real_matching_and_parsing(self):
        from app.learn.service import learn_website
        scrape = self.scrape()
        html_path = snapshot_directory(scrape['payload']) / 'page.html'
        with patch('app.learn.validation.final_validation', side_effect=lambda chunk: (chunk.startswith('<article'), .99)) as classifier:
            path = learn_website(html_path, 1, 'domestic', scrape['payload']['snapshot_id'])
        classifier.assert_called()
        self.assertEqual(read_tickets(path), [CARD])
        tickets = extract_tickets(html_path, path, {'ماهان': ['Mahan Air']})
        self.assertEqual(len(tickets), 1)
        self.assertEqual(tickets[0]['price'], 2500000)
        self.assertEqual(tickets[0]['time'], '12:30')
        self.assertEqual(tickets[0]['airline'], 'ماهان')
        self.assertEqual([kind for kind, _ in plan_followups([scrape, self.child(scrape, status='done')])], ['extractor'])

    def test_empty_learn_does_not_overwrite_previous_template(self):
        from app.learn.service import learn_website
        path = self.learned()
        original = path.read_bytes(), path.stat().st_mtime_ns
        scrape = self.scrape()
        with patch('app.learn.validation.final_validation', return_value=(False, 0)):
            with self.assertRaises(ValueError):
                learn_website(snapshot_directory(scrape['payload']) / 'page.html', 1, 'domestic', scrape['payload']['snapshot_id'])
        self.assertEqual((path.read_bytes(), path.stat().st_mtime_ns), original)

    def test_extractor_reads_database_aliases_each_job_and_writes_file(self):
        from app.extractor.worker import handle_extract
        engine = create_engine('sqlite+pysqlite:///:memory:')
        self.addCleanup(engine.dispose)
        Base.metadata.create_all(engine, tables=[Airline.__table__, AirlineAlias.__table__])
        with Session(engine) as db:
            db.add(Airline(official_name_fa='ماهان', aliases=[AirlineAlias(alias_name='Mahan Air')]))
            db.commit()
            self.assertEqual(get_airlines(db), {'ماهان': ['ماهان', 'Mahan Air']})
        scrape = self.scrape()
        payload = {**scrape['payload'], 'source_job_id': scrape['id']}
        self.learned()
        with patch('app.extractor.worker.SessionLocal', side_effect=lambda: Session(engine)), \
             patch('app.extractor.worker.save_provider_minimums') as save:
            handle_extract(payload)
        save.assert_called_once()
        self.assertEqual(save.call_args.args[1], payload)
        result = json.loads(extracted_path(payload).read_text())
        self.assertEqual(save.call_args.args[2], result)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['airline'], 'ماهان')
        self.assertEqual(result[0]['price'], 2500000)

    def test_fast_extractor_does_not_import_learn_or_requests(self):
        import subprocess
        result = subprocess.run([
            str(Path(os.sys.executable)), '-c',
            'import sys; import app.extractor.worker; '
            'assert "app.learn.validation" not in sys.modules; assert "requests" not in sys.modules',
        ], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


class WorkerProcessTests(unittest.TestCase):
    def test_process_completes_and_propagates_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / 'result')
            run_handler_in_process(process_write, {'path': path}, 10)
            self.assertEqual(Path(path).read_text(), 'done')
        with self.assertRaisesRegex(RuntimeError, 'ValueError: test failure'):
            run_handler_in_process(process_fail, {}, 10)

    def test_timeout_terminates_work_before_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / 'result')
            with self.assertRaises(TimeoutError):
                run_handler_in_process(process_wait, {'path': path}, .1)
            self.assertFalse(Path(path).exists())


class ScrapeDispatchTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite+pysqlite:///:memory:')
        self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(self.engine, tables=[
            Website.__table__, Airport.__table__, FlightPath.__table__, SearchRequest.__table__,
        ])
        with Session(self.engine) as db:
            db.add_all([
                Website(id=1, name='configured', domestic_url_format='https://example.test/{origin_path}/{destination_path}/{date}',
                        date_calendar='gregorian', date_format='YYYY-MM-DD'),
                Website(id=2, name='incomplete'),
                Airport(id=1, name_fa='تهران', category='domestic'),
                Airport(id=2, name_fa='مشهد', category='domestic'),
            ])
            db.flush()
            db.add_all([FlightPath(website_id=1, airport_id=1, code='THR'),
                        FlightPath(website_id=1, airport_id=2, code='MHD')])
            db.add(SearchRequest(id=1, route_type='domestic', origin_airport_id=1,
                                 destination_airport_id=2, departure_date=self.request_date()))
            db.commit()
        self.request = {'id': 1, 'route_type': 'domestic', 'origin_airport': {'id': 1},
                        'destination_airport': {'id': 2}, 'departure_date': '2026-09-20'}

    @staticmethod
    def request_date():
        from datetime import date
        return date(2026, 9, 20)

    def test_dispatch_has_worker_type_website_and_unique_snapshot(self):
        with patch('app.orchestration.jobs.SessionLocal', side_effect=lambda: Session(self.engine)), \
             patch('app.orchestration.jobs.get_pipeline_jobs', return_value=[]), \
             patch('app.orchestration.jobs.enqueue', return_value=1) as enqueue:
            create_scrape_jobs([self.request, self.request])
            enqueue.assert_called_once()
            kind, payload = enqueue.call_args.args
            self.assertEqual(kind, 'scrape')
            self.assertEqual(payload['website_id'], 1)
            self.assertEqual(payload['route_type'], 'domestic')
            self.assertEqual(len(payload['snapshot_id']), 32)

    def test_active_scrape_is_not_duplicated(self):
        existing = [{'type': 'scrape', 'status': 'pending', 'payload': {'search_request_id': 1, 'website_id': 1}}]
        with patch('app.orchestration.jobs.SessionLocal', side_effect=lambda: Session(self.engine)), \
             patch('app.orchestration.jobs.get_pipeline_jobs', return_value=existing), \
             patch('app.orchestration.jobs.enqueue') as enqueue:
            create_scrape_jobs([self.request])
            enqueue.assert_not_called()

    def test_scraper_writes_exact_snapshot_consumed_by_followups(self):
        from unittest.mock import AsyncMock
        from app.scraper.worker import handle_scrape
        payload = {'search_request_id': 1, 'website_id': 1, 'route_type': 'domestic', 'snapshot_id': 'a' * 32}
        with patch('app.scraper.worker.SessionLocal', side_effect=lambda: Session(self.engine)), \
             patch('app.scraper.worker.scrape_url', new_callable=AsyncMock, return_value={'status': 'success'}) as scrape:
            handle_scrape(payload)
        self.assertEqual(scrape.call_args.kwargs['output_dir'], snapshot_directory(payload))
        self.assertEqual(scrape.call_args.args[0], 'https://example.test/THR/MHD/2026-09-20')
