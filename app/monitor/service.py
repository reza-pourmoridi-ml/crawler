from __future__ import annotations

import json
import os
import shutil
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select

from app.infra.config import settings
from app.infra.db import SessionLocal
from app.infra.storage import storage_root
from app.orchestration.models import Job


STAGES = ("scrape", "learn", "extractor")
STAGE_LABELS = {
    "scrape": "اسکرپر",
    "learn": "لرن",
    "extractor": "استخراج‌گر",
}


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    normalized = _utc(value)
    return normalized.isoformat() if normalized else None


def _age_seconds(value: datetime | None, now: datetime) -> int | None:
    normalized = _utc(value)
    return max(0, int((now - normalized).total_seconds())) if normalized else None


def _job_view(job: Job, now: datetime) -> dict:
    payload = job.payload if isinstance(job.payload, dict) else {}
    return {
        "id": job.id,
        "type": job.type,
        "label": STAGE_LABELS.get(job.type, job.type),
        "status": job.status,
        "outcome": job.outcome,
        "attempt": job.attempts,
        "max_attempts": job.max_attempts,
        "search_request_id": payload.get("search_request_id"),
        "website_id": payload.get("website_id"),
        "route_type": payload.get("route_type"),
        "source_job_id": payload.get("source_job_id"),
        "created_at": _iso(job.created_at),
        "run_at": _iso(job.run_at),
        "deadline_at": _iso(job.deadline_at),
        "locked_until": _iso(job.locked_until),
        "finished_at": _iso(job.finished_at),
        "age_seconds": _age_seconds(job.created_at, now),
    }


def _stage_health(jobs: list[Job], stage: str, now: datetime) -> dict:
    stage_jobs = [job for job in jobs if job.type == stage]
    running = [job for job in stage_jobs if job.status == "running"]
    ready = [
        job for job in stage_jobs
        if job.status == "pending" and _utc(job.run_at) <= now
    ]
    scheduled = [
        job for job in stage_jobs
        if job.status == "pending" and _utc(job.run_at) > now
    ]
    expired = [
        job for job in running
        if job.locked_until is None or _utc(job.locked_until) <= now
    ]
    recent_errors = [
        job for job in stage_jobs
        if job.status == "failed" and job.outcome == "error"
        and job.finished_at is not None
        and _utc(job.finished_at) >= now - timedelta(hours=1)
    ]
    recent_success = [
        job for job in stage_jobs
        if job.outcome == "success" and job.finished_at is not None
    ]
    latest_error_at = max(
        (_utc(job.finished_at) for job in recent_errors),
        default=None,
    )
    latest_success_at = max(
        (_utc(job.finished_at) for job in recent_success),
        default=None,
    )
    oldest_ready_age = max(
        (_age_seconds(job.run_at, now) or 0 for job in ready),
        default=0,
    )

    if expired:
        state, message = "critical", "قفل job در حال اجرا منقضی شده است"
    elif running:
        state, message = "working", "در حال پردازش"
    elif ready and not running and oldest_ready_age > 120:
        state, message = "warning", "صف آماده مانده؛ worker احتمالاً پاسخ‌گو نیست"
    elif ready:
        state, message = "queued", "job آمادهٔ دریافت است"
    elif scheduled:
        state, message = "queued", "retry زمان‌بندی‌شده دارد"
    elif (
        len(recent_errors) >= 3
        and (
            latest_success_at is None
            or latest_error_at > latest_success_at
        )
    ):
        state, message = "warning", "چند خطای نهایی بازیابی‌نشده ثبت شده است"
    else:
        state, message = "idle", "صف خالی است؛ سلامت worker قابل استنباط نیست"

    return {
        "name": stage,
        "label": STAGE_LABELS[stage],
        "state": state,
        "message": message,
        "running": len(running),
        "ready": len(ready),
        "scheduled": len(scheduled),
        "recent_errors": len(recent_errors),
        "oldest_ready_seconds": oldest_ready_age or None,
        "last_success_at": _iso(max(
            (_utc(job.finished_at) for job in recent_success),
            default=None,
        )),
    }


def _database_snapshot(
    now: datetime,
    history_hours: int,
) -> tuple[dict, list[Job]]:
    started = time.monotonic()
    try:
        history_cutoff = now - timedelta(hours=history_hours)
        with SessionLocal() as db:
            active_jobs = list(db.scalars(
                select(Job)
                .where(Job.status.in_(("running", "pending")))
                .order_by(Job.id.desc())
            ))
            recent_jobs = list(db.scalars(
                select(Job)
                .where(Job.finished_at >= history_cutoff)
                .order_by(Job.id.desc())
            ))
            latest_successes = []
            for stage in STAGES:
                latest = db.scalar(
                    select(Job)
                    .where(
                        Job.type == stage,
                        Job.outcome == "success",
                        Job.finished_at.is_not(None),
                    )
                    .order_by(Job.finished_at.desc())
                    .limit(1)
                )
                if latest is not None:
                    latest_successes.append(latest)

        jobs_by_id = {
            job.id: job
            for job in (*active_jobs, *recent_jobs, *latest_successes)
        }
        jobs = list(jobs_by_id.values())
        return {
            "state": "ok",
            "message": "اتصال برقرار است",
            "latency_ms": round((time.monotonic() - started) * 1000),
            "observed_jobs": len(jobs),
        }, jobs
    except Exception as exc:
        return {
            "state": "critical",
            "message": f"اتصال ناموفق: {type(exc).__name__}",
            "latency_ms": None,
            "observed_jobs": 0,
        }, []


def _ollama_snapshot() -> dict:
    started = time.monotonic()
    base_url = settings.ollama_host.rstrip("/")
    try:
        with urllib.request.urlopen(f"{base_url}/api/tags", timeout=2) as response:
            tags = json.load(response)
        with urllib.request.urlopen(f"{base_url}/api/ps", timeout=2) as response:
            running = json.load(response)
        installed = [item.get("name") for item in tags.get("models", [])]
        loaded = [
            {
                "name": item.get("name"),
                "size": item.get("size"),
                "size_vram": item.get("size_vram"),
                "expires_at": item.get("expires_at"),
            }
            for item in running.get("models", [])
        ]
        configured = settings.ollama_model
        available = configured in installed
        return {
            "state": "ok" if available else "warning",
            "message": "مدل تنظیم‌شده موجود است" if available else "مدل تنظیم‌شده نصب نیست",
            "latency_ms": round((time.monotonic() - started) * 1000),
            "configured_model": configured,
            "installed_models": installed,
            "loaded_models": loaded,
        }
    except Exception as exc:
        return {
            "state": "critical",
            "message": f"Ollama پاسخ نمی‌دهد: {type(exc).__name__}",
            "latency_ms": None,
            "configured_model": settings.ollama_model,
            "installed_models": [],
            "loaded_models": [],
        }


def _storage_snapshot() -> dict:
    root = storage_root()
    try:
        usage = shutil.disk_usage(root)
        readable = root.is_dir() and os.access(root, os.R_OK)
        return {
            "state": "ok" if readable else "critical",
            "message": "در دسترس و قابل خواندن است" if readable else "قابل خواندن نیست",
            "path": str(root),
            "free_bytes": usage.free,
            "used_percent": round((usage.used / usage.total) * 100, 1),
        }
    except OSError as exc:
        return {
            "state": "critical",
            "message": f"Storage در دسترس نیست: {type(exc).__name__}",
            "path": str(root),
            "free_bytes": None,
            "used_percent": None,
        }


def collect_status(
    row_limit: int = 20,
    history_hours: int = 24,
) -> dict:
    row_limit = max(5, min(int(row_limit), 200))
    history_hours = max(1, min(int(history_hours), 168))
    now = datetime.now(timezone.utc)
    history_cutoff = now - timedelta(hours=history_hours)
    database, jobs = _database_snapshot(now, history_hours)
    stages = [_stage_health(jobs, stage, now) for stage in STAGES]
    active = [job for job in jobs if job.status == "running"]
    ready = [job for job in jobs if job.status == "pending" and _utc(job.run_at) <= now]
    scheduled = [job for job in jobs if job.status == "pending" and _utc(job.run_at) > now]
    failures = [
        job for job in jobs
        if job.status == "failed"
        and job.outcome == "error"
        and job.finished_at is not None
        and _utc(job.finished_at) >= history_cutoff
    ]
    successes = [
        job for job in jobs
        if job.outcome == "success"
        and job.finished_at is not None
        and _utc(job.finished_at) >= history_cutoff
    ]

    active.sort(key=lambda job: (_utc(job.created_at), job.id), reverse=True)
    ready.sort(key=lambda job: (_utc(job.run_at), job.id))
    failures.sort(key=lambda job: (_utc(job.finished_at), job.id), reverse=True)
    successes.sort(key=lambda job: (_utc(job.finished_at), job.id), reverse=True)

    ollama = _ollama_snapshot()
    storage = _storage_snapshot()
    component_states = [database["state"], ollama["state"], storage["state"]]
    stage_states = [stage["state"] for stage in stages]
    if "critical" in component_states or "critical" in stage_states:
        overall = "critical"
    elif "warning" in component_states or "warning" in stage_states:
        overall = "warning"
    else:
        overall = "ok"

    newest_job = max((_utc(job.created_at) for job in jobs), default=None)
    orchestrator = {
        "state": "ok" if newest_job and newest_job >= now - timedelta(minutes=10) else "unknown",
        "message": (
            "در ۱۰ دقیقهٔ اخیر فعالیت صف ثبت شده"
            if newest_job and newest_job >= now - timedelta(minutes=10)
            else "heartbeat مستقیم ندارد؛ از فعالیت صف استنباط می‌شود"
        ),
        "last_activity_at": _iso(newest_job),
    }

    return {
        "generated_at": now.isoformat(),
        "overall": overall,
        "settings": {
            "row_limit": row_limit,
            "history_hours": history_hours,
        },
        "components": {
            "database": database,
            "ollama": ollama,
            "storage": storage,
            "orchestrator": orchestrator,
        },
        "stages": stages,
        "counts": {
            "running": len(active),
            "ready": len(ready),
            "scheduled": len(scheduled),
            "final_errors": len(failures),
        },
        "active_jobs": [_job_view(job, now) for job in active[:row_limit]],
        "ready_jobs": [_job_view(job, now) for job in ready[:row_limit]],
        "recent_failures": [_job_view(job, now) for job in failures[:row_limit]],
        "recent_successes": [_job_view(job, now) for job in successes[:row_limit]],
    }
