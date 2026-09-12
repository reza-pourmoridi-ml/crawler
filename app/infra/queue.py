from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select, update

from app.infra.config import settings
from app.infra.db import SessionLocal
from app.orchestration.models import Job

LOCK_GRACE_SECONDS = 60


def utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def job_timeout(job_type: str) -> int:
    return {
        'learn': settings.learn_hard_timeout,
        'scrape': settings.scrape_job_timeout,
        'scrap': settings.scrape_job_timeout,
        'extractor': settings.extractor_job_timeout,
    }.get(job_type, 300)


def enqueue(job_type: str, payload: dict, max_attempts: int = 3, run_at: datetime | None = None) -> int:
    if max_attempts < 1:
        raise ValueError('max_attempts must be positive')
    with SessionLocal() as db:
        job = Job(type=job_type, payload=payload, max_attempts=max_attempts,
                  run_at=run_at or datetime.now(timezone.utc))
        db.add(job)
        db.commit()
        db.refresh(job)
        return job.id


def fetch_job(job_types: list[str], lock_seconds: int = 300, timeouts: dict | None = None) -> dict | None:
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        job = db.scalar(
            select(Job)
            .where(Job.status == 'pending', Job.run_at <= now, Job.type.in_(job_types),
                   Job.attempts < Job.max_attempts,
                   Job.run_at > now - timedelta(seconds=settings.pending_job_timeout))
            .order_by(Job.run_at, Job.id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if job is None:
            return None
        timeout = (timeouts or {}).get(job.type, job_timeout(job.type))
        job.status = 'running'
        job.attempts += 1
        job.deadline_at = now + timedelta(seconds=timeout + LOCK_GRACE_SECONDS)
        job.locked_until = min(now + timedelta(seconds=lock_seconds), job.deadline_at)
        job.finished_at = None
        job.outcome = None
        result = {'id': job.id, 'type': job.type, 'payload': job.payload, 'attempts': job.attempts}
        db.commit()
        return result


def owned_attempt(job_id: int, attempt: int | None):
    conditions = [Job.id == job_id, Job.status == 'running']
    if attempt is not None:
        conditions.append(Job.attempts == attempt)
    return conditions


def extend_lock(job_id: int, lock_seconds: int = 300, attempt: int | None = None) -> bool:
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        job = db.scalar(select(Job).where(*owned_attempt(job_id, attempt)).with_for_update())
        if job is None or job.locked_until is None or utc(job.locked_until) <= now:
            return False
        deadline = utc(job.deadline_at) if job.deadline_at else now + timedelta(seconds=job_timeout(job.type) + LOCK_GRACE_SECONDS)
        if deadline <= now:
            return False
        job.deadline_at = deadline
        job.locked_until = min(now + timedelta(seconds=lock_seconds), deadline)
        db.commit()
        return True


def mark_done(job_id: int, attempt: int | None = None) -> bool:
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        result = db.execute(
            update(Job).where(*owned_attempt(job_id, attempt), Job.locked_until > now,
                              or_(Job.deadline_at.is_(None), Job.deadline_at > now))
            .values(status='failed', outcome='success', finished_at=now, locked_until=None, deadline_at=None)
        )
        db.commit()
        return bool(result.rowcount)


def fail_attempt(job: Job, now: datetime) -> None:
    job.locked_until = None
    job.deadline_at = None
    if job.attempts < job.max_attempts:
        job.status = 'pending'
        job.run_at = now + timedelta(seconds=min(2 ** min(job.attempts, 10) * 30, 3600))
        job.finished_at = None
        job.outcome = None
    else:
        job.status = 'failed'
        job.outcome = 'error'
        job.finished_at = now


def mark_failed(job_id: int, attempt: int | None = None) -> bool:
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        job = db.scalar(select(Job).where(*owned_attempt(job_id, attempt)).with_for_update())
        if job is None:
            return False
        fail_attempt(job, now)
        db.commit()
        return True


def sweep_stuck_jobs() -> int:
    now = datetime.now(timezone.utc)
    count = 0
    with SessionLocal() as db:
        running = db.scalars(
            select(Job).where(Job.status == 'running', or_(
                Job.locked_until <= now, Job.locked_until.is_(None),
                Job.deadline_at <= now, Job.deadline_at.is_(None),
            )).with_for_update(skip_locked=True)
        )
        for job in running:
            if job.deadline_at is None:
                job.deadline_at = now + timedelta(seconds=job_timeout(job.type) + LOCK_GRACE_SECONDS)
            if job.locked_until is None:
                job.locked_until = job.deadline_at
            if utc(job.locked_until) <= now or utc(job.deadline_at) <= now:
                fail_attempt(job, now)
                count += 1
        result = db.execute(
            update(Job).where(Job.status == 'pending', or_(
                Job.attempts >= Job.max_attempts,
                Job.run_at <= now - timedelta(seconds=settings.pending_job_timeout),
            )).values(status='failed', outcome='error', finished_at=now, locked_until=None, deadline_at=None)
        )
        count += result.rowcount
        db.commit()
    return count
