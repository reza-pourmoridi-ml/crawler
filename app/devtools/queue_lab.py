import sys
import time
import threading
import logging
from datetime import datetime, timezone

from sqlalchemy import text
from app.infra.db import SessionLocal
from app.infra.queue import enqueue, fetch_job, extend_lock, mark_done, mark_failed, sweep_stuck_jobs
from app.infra.worker_base import run_worker

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("queue_lab")


def reset():
    with SessionLocal() as db:
        db.execute(text("DELETE FROM jobs WHERE type LIKE 'test.%'"))
        db.commit()
    log.info("test jobs cleared")


def scenario_happy_path():
    reset()
    job_id = enqueue("test.echo", {"msg": "hello"})
    job = fetch_job(["test.echo"])
    assert job and job["id"] == job_id
    mark_done(job["id"])
    with SessionLocal() as db:
        status = db.execute(text("SELECT status FROM jobs WHERE id=:id"), {"id": job_id}).scalar()
    assert status == "failed"
    log.info("OK: happy path")


def scenario_concurrency():
    """چند 'ورکر' همزمان یه جاب رو می‌قاپن؛ باید فقط یکیشون موفق بشه (SKIP LOCKED)."""
    reset()
    enqueue("test.echo", {"msg": "race"})
    results, lock = [], threading.Lock()

    def worker():
        job = fetch_job(["test.echo"])
        with lock:
            results.append(job)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    [t.start() for t in threads]
    [t.join() for t in threads]

    picked = [r for r in results if r is not None]
    assert len(picked) == 1, f"باید فقط یک ورکر بگیره، گرفتن: {len(picked)}"
    mark_done(picked[0]["id"])
    log.info("OK: concurrency (فقط 1 از 10 ورکر جاب رو گرفت)")


def scenario_retry_backoff():
    reset()
    job_id = enqueue("test.fail", {}, max_attempts=2)

    job = fetch_job(["test.fail"])
    mark_failed(job["id"])
    with SessionLocal() as db:
        row = db.execute(text("SELECT status, run_at FROM jobs WHERE id=:id"), {"id": job_id}).fetchone()
    assert row.status == "pending"
    assert row.run_at > datetime.now(timezone.utc), "باید backoff داشته باشه"
    log.info("attempt 1 fail -> pending تا %s", row.run_at)

    with SessionLocal() as db:
        db.execute(text("UPDATE jobs SET run_at = NOW() WHERE id=:id"), {"id": job_id})
        db.commit()

    job = fetch_job(["test.fail"])
    mark_failed(job["id"])
    with SessionLocal() as db:
        status = db.execute(text("SELECT status FROM jobs WHERE id=:id"), {"id": job_id}).scalar()
    assert status == "failed"
    log.info("OK: retry/backoff تا failed نهایی")


def scenario_stuck_job_sweep():
    """شبیه‌سازی کرش ورکر: running ولی locked_until گذشته."""
    reset()
    job_id = enqueue("test.echo", {})
    fetch_job(["test.echo"])
    with SessionLocal() as db:
        db.execute(text("UPDATE jobs SET locked_until = NOW() - INTERVAL '1 minute' WHERE id=:id"), {"id": job_id})
        db.commit()

    sweep_stuck_jobs()
    with SessionLocal() as db:
        status = db.execute(text("SELECT status FROM jobs WHERE id=:id"), {"id": job_id}).scalar()
    assert status == "pending"
    log.info("OK: sweep_stuck_jobs جاب گیرکرده رو آزاد کرد")


def scenario_heartbeat():
    reset()
    job_id = enqueue("test.echo", {})
    fetch_job(["test.echo"], lock_seconds=2)
    with SessionLocal() as db:
        before = db.execute(text("SELECT locked_until FROM jobs WHERE id=:id"), {"id": job_id}).scalar()
    extend_lock(job_id, lock_seconds=120)
    with SessionLocal() as db:
        after = db.execute(text("SELECT locked_until FROM jobs WHERE id=:id"), {"id": job_id}).scalar()
    assert after > before
    log.info("OK: heartbeat/extend_lock قفل رو جلو برد (%s -> %s)", before, after)


def _hang_forever(payload):
    time.sleep(999)


def scenario_worker_timeout():
    reset()
    job_id = enqueue("test.hang", {})
    t = threading.Thread(
        target=run_worker,
        kwargs=dict(job_types=["test.hang"], handlers={"test.hang": _hang_forever}, timeouts={"test.hang": 3}),
        daemon=True,
    )
    t.start()
    time.sleep(6)

    with SessionLocal() as db:
        row = db.execute(text("SELECT status, attempts FROM jobs WHERE id=:id"), {"id": job_id}).fetchone()

    log.info("after timeout: status=%s attempts=%s", row.status, row.attempts)
    assert row.attempts >= 1, "جاب اصلاً fetch نشده — یعنی run_worker قبل از رسیدن به fetch_job کرش کرده (چک کن thread هنوز زنده‌ست)"
    assert row.status in ("pending", "failed"), "نباید بعد از timeout همچنان running بمونه"
    log.info("OK: timeout واقعاً کار کرد (جاب گرفته شد، بعد رها شد)")

SCENARIOS = {
    "reset": reset,
    "scenario_happy_path->happy": scenario_happy_path,
    "scenario_concurrency->concurrency": scenario_concurrency,
    "scenario_retry_backoff->retry": scenario_retry_backoff,
    "scenario_stuck_job_sweep->stuck": scenario_stuck_job_sweep,
    "scenario_heartbeat->heartbeat": scenario_heartbeat,
    "scenario_worker_timeout->timeout": scenario_worker_timeout,
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in {*SCENARIOS, "all"}:
        print(f"Usage: python -m app.devtools.queue_lab [{'|'.join(SCENARIOS)}|all]")
        return
    if sys.argv[1] == "all":
        for name, fn in SCENARIOS.items():
            print(f"{name}")
            print()
            if name == "reset":
                continue
            log.info("--- %s ---", name)
            fn()
    else:
        SCENARIOS[sys.argv[1]]()


if __name__ == "__main__":
    main()
