# app/infra/queue.py
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, update, text
from app.infra.db import SessionLocal
from app.orchestration.models import Job


def enqueue(job_type: str, payload: dict, max_attempts: int = 3, run_at: datetime | None = None) -> int:
    with SessionLocal() as db:
        job = Job(
            type=job_type,
            payload=payload,
            max_attempts=max_attempts,
            run_at=run_at or datetime.now(timezone.utc),
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        return job.id


def fetch_job(job_types: list[str], lock_seconds: int = 300) -> dict | None:
    """
    یک جاب pending از بین type های داده‌شده می‌گیره و قفل می‌کنه.
    هر ماژول فقط type های خودش رو پاس می‌ده، پس هیچ‌وقت جاب ماژول دیگه رو نمی‌قاپه.
    """
    with SessionLocal() as db:
        row = db.execute(text("""
            UPDATE jobs SET
                status = 'running',
                attempts = attempts + 1,
                locked_until = NOW() + make_interval(secs => :lock_seconds)
            WHERE id = (
                SELECT id FROM jobs
                WHERE status = 'pending' AND run_at <= NOW() AND type = ANY(:types)
                ORDER BY run_at
                FOR UPDATE SKIP LOCKED
                LIMIT 1
            )
            RETURNING id, type, payload, attempts
        """), {"lock_seconds": lock_seconds, "types": job_types}).fetchone()
        db.commit()

    if row is None:
        return None
    return {"id": row.id, "type": row.type, "payload": row.payload, "attempts": row.attempts}


def extend_lock(job_id: int, lock_seconds: int = 300):
    with SessionLocal() as db:
        db.execute(
            update(Job)
            .where(Job.id == job_id, Job.status == "running")
            .values(locked_until=datetime.now(timezone.utc) + timedelta(seconds=lock_seconds))
        )
        db.commit()


def mark_done(job_id: int):
    with SessionLocal() as db:
        db.execute(update(Job).where(Job.id == job_id).values(status="done", locked_until=None))
        db.commit()


def mark_failed(job_id: int):
    with SessionLocal() as db:
        db.execute(text("""
            UPDATE jobs SET
                status = CASE WHEN attempts < max_attempts THEN 'pending' ELSE 'failed' END,
                locked_until = NULL,
                run_at = CASE WHEN attempts < max_attempts
                              THEN NOW() + make_interval(secs => POWER(2, attempts) * 30)
                              ELSE run_at END
            WHERE id = :id
        """), {"id": job_id})
        db.commit()


def sweep_stuck_jobs():
    """جاب‌هایی که worker وسط کارش کرش کرده رو برمی‌گردونه به pending."""
    with SessionLocal() as db:
        db.execute(text("""
            UPDATE jobs SET status = 'pending', locked_until = NULL
            WHERE status = 'running' AND locked_until < NOW()
        """))
        db.commit()