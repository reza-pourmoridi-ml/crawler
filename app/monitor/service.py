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
    oldest_ready_age = max(
        (_age_seconds(job.run_at, now) or 0 for job in ready),
        default=0,
    )

    if expired:
        state, message = "critical", "قفل job در حال اجرا منقضی شده است"
    elif len(recent_errors) >= 3:
        state, message = "warning", "چند خطای نهایی در یک ساعت اخیر ثبت شده است"
    elif ready and not running and oldest_ready_age > 120:
        state, message = "warning", "صف آماده مانده؛ worker احتمالاً پاسخ‌گو نیست"
    elif running:
        state, message = "working", "در حال پردازش"
    elif ready:
        state, message = "queued", "job آمادهٔ دریافت است"
    elif scheduled:
        state, message = "queued", "retry زمان‌بندی‌شده دارد"
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


def _database_snapshot(now: datetime) -> tuple[dict, list[Job]]:
    started = time.monotonic()
    try:
        with SessionLocal() as db:
            jobs = list(db.scalars(select(Job).order_by(Job.id.desc()).limit(500)))
        return {
            "state": "ok",
            "message": "اتصال برقرار است",
            "latency_ms": round((time.monotonic() - started) * 1000),
        }, jobs
    except Exception as exc:
        return {
            "state": "critical",
            "message": f"اتصال ناموفق: {type(exc).__name__}",
            "latency_ms": None,
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


def collect_status() -> dict:
    now = datetime.now(timezone.utc)
    database, jobs = _database_snapshot(now)
    stages = [_stage_health(jobs, stage, now) for stage in STAGES]
    active = [job for job in jobs if job.status == "running"]
    ready = [job for job in jobs if job.status == "pending" and _utc(job.run_at) <= now]
    scheduled = [job for job in jobs if job.status == "pending" and _utc(job.run_at) > now]
    failures = [job for job in jobs if job.status == "failed" and job.outcome == "error"]
    successes = [job for job in jobs if job.outcome == "success"]

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
        "active_jobs": [_job_view(job, now) for job in active[:20]],
        "ready_jobs": [_job_view(job, now) for job in ready[:20]],
        "recent_failures": [_job_view(job, now) for job in failures[:10]],
        "recent_successes": [_job_view(job, now) for job in successes[:10]],
    }
