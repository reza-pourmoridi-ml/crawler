"""Central scheduling: workers execute jobs; only the orchestrator dispatches stages."""

import logging
from datetime import date, datetime, timezone
from uuid import uuid4

from sqlalchemy import select

from app.control.websites.models import Website
from app.infra.config import settings
from app.infra.db import SessionLocal
from app.infra.queue import enqueue
from app.infra.storage import learned_path, snapshot_directory, usable_learning
from app.orchestration.models import Job
from app.scraper.url_builder import ScrapeUrlBuildError, build_scrape_url

logger = logging.getLogger(__name__)
ACTIVE_STATUSES = {"pending", "running"}
SCRAPE = "scrape"
LEARN = "learn"
EXTRACTOR = "extractor"


def get_pipeline_jobs() -> list[dict]:
    with SessionLocal() as db:
        rows = db.execute(
            select(Job.id, Job.type, Job.status, Job.payload, Job.run_at)
            .where(Job.type.in_([SCRAPE, LEARN, EXTRACTOR]))
            .order_by(Job.id)
        )
        return [dict(row._mapping) for row in rows]


def create_scrape_jobs(requests: list[dict]) -> None:
    active = {
        (job["payload"].get("search_request_id"), job["payload"].get("website_id"))
        for job in get_pipeline_jobs()
        if job["type"] == SCRAPE and job["status"] in ACTIVE_STATUSES
    }
    with SessionLocal() as db:
        website_ids = list(db.scalars(select(Website.id).order_by(Website.id)))
        for request in requests:
            for website_id in website_ids:
                key = (request["id"], website_id)
                if key in active:
                    continue
                payload = {
                    "search_request_id": request["id"],
                    "website_id": website_id,
                    "route_type": request["route_type"],
                    "origin_airport_id": request["origin_airport"]["id"],
                    "destination_airport_id": request["destination_airport"]["id"],
                    "departure_date": request["departure_date"],
                    "snapshot_id": uuid4().hex,
                }
                try:
                    # Incomplete website/path configuration must not create retrying jobs.
                    build_scrape_url(
                        db, website_id, payload["route_type"], payload["origin_airport_id"],
                        payload["destination_airport_id"], date.fromisoformat(payload["departure_date"]),
                    )
                except (ScrapeUrlBuildError, KeyError, ValueError) as exc:
                    logger.warning("Skipping request=%s website=%s: %s", *key, exc)
                    continue
                job_id = enqueue(SCRAPE, payload)
                active.add(key)
                logger.info("Created scrape job=%s request=%s website=%s", job_id, *key)


def plan_followups(jobs: list[dict], now: datetime) -> list[tuple[str, dict]]:
    """Plan from persistent queue state and published files, including after restart."""
    completed = [
        job for job in jobs
        if job["type"] == SCRAPE and job["status"] == "done"
        and job["payload"].get("snapshot_id")
    ]
    latest_samples = {}
    for job in completed:
        payload = job["payload"]
        key = (payload["website_id"], payload["route_type"])
        if key not in latest_samples or job["id"] > latest_samples[key]["id"]:
            latest_samples[key] = job

    active_learning = set()
    failed_learning = {}
    extracted_sources = set()
    for job in jobs:
        payload = job["payload"]
        if job["type"] == EXTRACTOR:
            # Includes terminal failures: the queue owns bounded retries.
            extracted_sources.add(payload.get("source_job_id"))
        elif job["type"] == LEARN:
            key = (payload["website_id"], payload["route_type"])
            if job["status"] in ACTIVE_STATUSES:
                active_learning.add(key)
            elif job["status"] == "failed":
                run_at = job["run_at"]
                if run_at.tzinfo is None:
                    run_at = run_at.replace(tzinfo=timezone.utc)
                failed_learning[key] = max(failed_learning.get(key, run_at), run_at)

    planned = []
    learned = {key: usable_learning(*key) for key in latest_samples}
    for key, job in latest_samples.items():
        if key in active_learning:
            continue
        if key in failed_learning and (now - failed_learning[key]).total_seconds() < settings.learn_retry_seconds:
            continue
        path = learned_path(*key)
        if learned[key] and now.timestamp() - path.stat().st_mtime < settings.learn_interval_seconds:
            continue
        if (snapshot_directory(job["payload"]) / "page.html").is_file():
            planned.append((LEARN, {**job["payload"], "source_job_id": job["id"]}))

    for job in completed:
        payload = job["payload"]
        key = (payload["website_id"], payload["route_type"])
        if job["id"] in extracted_sources or not learned[key]:
            continue
        # A stale but valid template remains usable while its refresh is running.
        if (snapshot_directory(payload) / "page.html").is_file():
            planned.append((EXTRACTOR, {**payload, "source_job_id": job["id"]}))
    return planned


def advance_pipeline() -> None:
    for job_type, payload in plan_followups(get_pipeline_jobs(), datetime.now(timezone.utc)):
        job_id = enqueue(job_type, payload)
        logger.info("Created %s job=%s from scrape=%s", job_type, job_id, payload["source_job_id"])
