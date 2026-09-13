import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

from app.monitor.service import _job_view, _stage_health, collect_status


NOW = datetime(2026, 9, 12, 12, 0, tzinfo=timezone.utc)


def job(**overrides):
    values = {
        "id": 1,
        "type": "scrape",
        "payload": {"search_request_id": 4, "website_id": 2, "route_type": "domestic"},
        "status": "pending",
        "outcome": None,
        "attempts": 0,
        "max_attempts": 3,
        "locked_until": None,
        "deadline_at": None,
        "finished_at": None,
        "run_at": NOW,
        "created_at": NOW - timedelta(minutes=3),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class MonitorTests(unittest.TestCase):
    def test_expired_running_job_is_critical(self):
        result = _stage_health([
            job(status="running", locked_until=NOW - timedelta(seconds=1)),
        ], "scrape", NOW)
        self.assertEqual(result["state"], "critical")

    def test_old_ready_queue_warns_about_worker(self):
        result = _stage_health([
            job(run_at=NOW - timedelta(minutes=3)),
        ], "scrape", NOW)
        self.assertEqual(result["state"], "warning")
        self.assertEqual(result["ready"], 1)

    def test_running_job_wins_over_old_queue_and_recent_errors(self):
        result = _stage_health([
            job(
                status="running",
                locked_until=NOW + timedelta(minutes=5),
            ),
            job(id=2, run_at=NOW - timedelta(hours=1)),
            job(
                id=3,
                status="failed",
                outcome="error",
                finished_at=NOW - timedelta(minutes=5),
            ),
            job(
                id=4,
                status="failed",
                outcome="error",
                finished_at=NOW - timedelta(minutes=4),
            ),
            job(
                id=5,
                status="failed",
                outcome="error",
                finished_at=NOW - timedelta(minutes=3),
            ),
        ], "scrape", NOW)
        self.assertEqual(result["state"], "working")
        self.assertEqual(result["running"], 1)

    def test_success_after_recent_errors_clears_warning(self):
        jobs = [
            job(
                id=index,
                status="failed",
                outcome="error",
                finished_at=NOW - timedelta(minutes=10 - index),
            )
            for index in range(1, 4)
        ]
        jobs.append(job(
            id=4,
            status="completed",
            outcome="success",
            finished_at=NOW - timedelta(minutes=1),
        ))

        result = _stage_health(jobs, "scrape", NOW)

        self.assertEqual(result["state"], "idle")

    def test_monitor_does_not_expose_route_or_snapshot_payload(self):
        item = job()
        item.payload.update({
            "origin_airport_id": 10,
            "destination_airport_id": 20,
            "departure_date": "2026-09-20",
            "snapshot_id": "a" * 32,
        })
        view = _job_view(item, NOW)
        self.assertNotIn("origin_airport_id", view)
        self.assertNotIn("destination_airport_id", view)
        self.assertNotIn("departure_date", view)
        self.assertNotIn("snapshot_id", view)

    @patch("app.monitor.service._storage_snapshot")
    @patch("app.monitor.service._ollama_snapshot")
    @patch("app.monitor.service._database_snapshot")
    def test_component_warning_changes_overall_health(self, database, ollama, storage):
        database.return_value = ({"state": "ok", "message": "ok", "latency_ms": 1}, [])
        ollama.return_value = {
            "state": "warning", "message": "missing", "configured_model": "x",
            "installed_models": [], "loaded_models": [], "latency_ms": 1,
        }
        storage.return_value = {
            "state": "ok", "message": "ok", "path": "/data",
            "free_bytes": 1, "used_percent": 1,
        }
        self.assertEqual(collect_status()["overall"], "warning")

    @patch("app.monitor.service._storage_snapshot")
    @patch("app.monitor.service._ollama_snapshot")
    @patch("app.monitor.service._database_snapshot")
    def test_row_limit_only_limits_display_not_health_counts(
        self,
        database,
        ollama,
        storage,
    ):
        database.return_value = (
            {"state": "ok", "message": "ok", "latency_ms": 1},
            [
                job(
                    id=index,
                    status="running",
                    locked_until=NOW + timedelta(minutes=5),
                )
                for index in range(1, 9)
            ],
        )
        ollama.return_value = {
            "state": "ok", "message": "ok", "configured_model": "x",
            "installed_models": ["x"], "loaded_models": [], "latency_ms": 1,
        }
        storage.return_value = {
            "state": "ok", "message": "ok", "path": "/data",
            "free_bytes": 1, "used_percent": 1,
        }

        result = collect_status(row_limit=5, history_hours=6)

        self.assertEqual(result["counts"]["running"], 8)
        self.assertEqual(len(result["active_jobs"]), 5)
        self.assertEqual(result["settings"], {
            "row_limit": 5,
            "history_hours": 6,
        })


if __name__ == "__main__":
    unittest.main()
