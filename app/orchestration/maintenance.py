import logging
import re
import shutil
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import delete, select

from app.infra.config import settings
from app.infra.db import SessionLocal
from app.infra.queue import sweep_stuck_jobs, utc
from app.infra.storage import extracted_path, snapshot_directory, storage_root
from app.orchestration.models import Job

logger = logging.getLogger(__name__)
ACTIVE = {'pending', 'running'}
TERMINAL = {'done', 'failed'}
_last_cleanup = None


def source_directory(payload: dict) -> Path | None:
    if payload.get('snapshot_id'):
        return snapshot_directory(payload)
    if 'search_request_id' in payload and 'website_id' in payload:
        return (Path(__file__).resolve().parents[2] / 'scraper_raw_data'
                / f"request_{int(payload['search_request_id'])}" / f"website_{int(payload['website_id'])}")
    return None


def expired_job(job: dict, cutoff: datetime) -> bool:
    return (job['status'] in TERMINAL and job.get('finished_at') is not None
            and utc(job['finished_at']) <= cutoff)


def plan_job_deletions(jobs: list[dict], cutoff: datetime) -> set[int]:
    by_id = {job['id']: job for job in jobs}
    children = {}
    latest_learns = {}
    for job in jobs:
        payload = job['payload']
        source_id = payload.get('source_job_id')
        if source_id is not None:
            children.setdefault(source_id, []).append(job)
        if job['type'] == 'learn':
            key = (payload['website_id'], payload['route_type'])
            current = latest_learns.get(key)
            if current is None or (source_id, job['id']) > (current['payload']['source_job_id'], current['id']):
                latest_learns[key] = job
    keep_learns = {job['id'] for job in latest_learns.values()}
    removable_sources = {
        job['id'] for job in jobs
        if job['type'] in {'scrape', 'scrap'} and expired_job(job, cutoff)
        and all(expired_job(child, cutoff) for child in children.get(job['id'], []))
    }
    removable = set(removable_sources)
    for job in jobs:
        if not expired_job(job, cutoff) or job['id'] in keep_learns:
            continue
        source_id = job['payload'].get('source_job_id')
        if source_id is not None:
            if source_id not in by_id or source_id in removable_sources:
                removable.add(job['id'])
        elif job['type'] not in {'scrape', 'scrap'}:
            removable.add(job['id'])
    return removable


def owned_path(path: Path, root: Path) -> bool:
    try:
        relative = path.relative_to(root)
    except ValueError:
        return False
    if not relative.parts or root.is_symlink():
        return False
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            return False
    return True


def old_path(path: Path, cutoff: datetime) -> bool:
    if not path.exists():
        return True
    if path.is_symlink() or path.stat().st_mtime > cutoff.timestamp():
        return False
    if path.is_dir():
        return all(old_path(child, cutoff) for child in path.iterdir() if not child.is_symlink())
    return True


def remove_old_path(path: Path, root: Path, cutoff: datetime) -> bool:
    if not path.exists():
        return False
    if not owned_path(path, root) or not old_path(path, cutoff):
        return False
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()
    parent = path.parent
    while parent != root and owned_path(parent, root):
        try:
            parent.rmdir()
        except OSError:
            break
        parent = parent.parent
    return True


def cleanup_artifacts(jobs: list[dict], removable: set[int], now: datetime) -> tuple[set[int], int]:
    root = storage_root()
    legacy_root = Path(__file__).resolve().parents[2] / 'scraper_raw_data'
    artifact_cutoff = now - timedelta(seconds=settings.artifact_retention_seconds)
    temporary_cutoff = now - timedelta(seconds=settings.temporary_retention_seconds)
    blocked_sources = set()
    for job in jobs:
        if job['id'] in removable and job['type'] in {'scrape', 'scrap'}:
            path = source_directory(job['payload'])
            owner = legacy_root if not job['payload'].get('snapshot_id') else root
            if path is not None and path.exists() and (not owned_path(path, owner) or not old_path(path, artifact_cutoff)):
                blocked_sources.add(job['id'])
    removable = {
        job_id for job_id in removable if job_id not in blocked_sources
    }
    removable.difference_update(
        job['id'] for job in jobs if job['payload'].get('source_job_id') in blocked_sources
    )
    protected_raw = set()
    protected_extracted = set()
    active_ids = set()
    active_keys = set()
    active_learn = False
    for job in jobs:
        payload = job['payload']
        if job['status'] in ACTIVE:
            active_ids.add(job['id'])
            active_learn = active_learn or job['type'] == 'learn'
            if 'website_id' in payload and 'route_type' in payload:
                active_keys.add((int(payload['website_id']), payload['route_type']))
            if job['type'] == 'extractor':
                protected_extracted.add(extracted_path(payload))
        if job['status'] in ACTIVE or (job['type'] in {'scrape', 'scrap'} and job['id'] not in removable):
            path = source_directory(payload)
            if path is not None:
                protected_raw.add(path)

    removed = 0
    for owner, pattern in [
        (root, 'raw/website_*/*/request_*/*'),
        (legacy_root, 'request_*/website_*'),
    ]:
        for path in list(owner.glob(pattern)):
            if owner == root and not re.fullmatch(r'[0-9a-f]{32}', path.name):
                continue
            if path not in protected_raw:
                removed += remove_old_path(path, owner, artifact_cutoff)
    for path in list(root.glob('extracted/website_*/*/scrape_*.json')):
        if path not in protected_extracted:
            removed += remove_old_path(path, root, artifact_cutoff)

    for path in list((root / 'temp').glob('*')):
        match = re.fullmatch(r'job_(\d+)_\d+_.+', path.name)
        if match:
            if int(match.group(1)) in active_ids:
                continue
        elif not path.name.startswith('learn_') or active_learn:
            continue
        removed += remove_old_path(path, root, temporary_cutoff)

    for area in ('learned', 'extracted'):
        for pattern in ('.atomic-*.tmp', 'tmp????????'):
            for path in list(root.glob(f'{area}/website_*/*/{pattern}')):
                website = path.parent.parent.name.removeprefix('website_')
                if not website.isdigit() or (int(website), path.parent.name) in active_keys:
                    continue
                removed += remove_old_path(path, root, temporary_cutoff)
    return removable, removed


def cleanup_runtime_data(now: datetime | None = None) -> dict[str, int]:
    now = now or datetime.now(timezone.utc)
    with SessionLocal() as db:
        records = list(db.scalars(select(Job).with_for_update()))
        jobs = [
            {'id': job.id, 'type': job.type, 'payload': job.payload, 'status': job.status,
             'outcome': job.outcome, 'finished_at': job.finished_at}
            for job in records
        ]
        removable = plan_job_deletions(jobs, now - timedelta(seconds=settings.job_retention_seconds))
        removable, files = cleanup_artifacts(jobs, removable, now)
        if removable:
            db.execute(delete(Job).where(Job.id.in_(removable)))
        db.commit()
    result = {'jobs_removed': len(removable), 'artifact_paths_removed': files}
    logger.info('Runtime cleanup: %s', result)
    return result


def maintain_pipeline() -> None:
    global _last_cleanup
    sweep_stuck_jobs()
    now = time.monotonic()
    if _last_cleanup is None or now - _last_cleanup >= settings.cleanup_interval_seconds:
        cleanup_runtime_data()
        _last_cleanup = now
