import logging

from app.extractor.repo import get_airlines
from app.extractor.service import extract_tickets
from app.infra.config import settings
from app.infra.db import SessionLocal
from app.infra.storage import extracted_path, learned_path, snapshot_directory, write_json_atomic
from app.infra.worker_base import run_worker

JOB_TYPE = "extractor"


def handle_extract(payload: dict) -> None:
    with SessionLocal() as db:
        airlines = get_airlines(db)
    results = extract_tickets(
        snapshot_directory(payload) / "page.html",
        learned_path(int(payload["website_id"]), payload["route_type"]),
        airlines,
    )
    write_json_atomic(extracted_path(payload), results)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    run_worker([JOB_TYPE], {JOB_TYPE: handle_extract}, {JOB_TYPE: settings.extractor_job_timeout},
               isolate_handlers=True)
