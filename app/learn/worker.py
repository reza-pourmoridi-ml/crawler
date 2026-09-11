import logging

from app.infra.config import settings
from app.infra.storage import snapshot_directory
from app.infra.worker_base import run_worker
from app.learn.service import learn_website

JOB_TYPE = "learn"


def handle_learn(payload: dict) -> None:
    learn_website(
        snapshot_directory(payload) / "page.html",
        int(payload["website_id"]),
        payload["route_type"],
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    run_worker([JOB_TYPE], {JOB_TYPE: handle_learn}, {JOB_TYPE: settings.learn_job_timeout},
               isolate_handlers=True)
