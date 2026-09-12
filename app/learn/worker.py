import os
from contextlib import redirect_stderr, redirect_stdout

from app.infra.config import settings
from app.infra.storage import snapshot_directory
from app.infra.worker_base import run_worker
from app.learn.service import learn_website
from app.infra.logging_config import configure_logging

JOB_TYPE = "learn"


def handle_learn(payload: dict) -> None:
    # Notebook-fidelity functions print model output/HTML errors. Keep their
    # algorithm untouched, but prevent those payloads from entering Docker logs.
    with open(os.devnull, "w", encoding="utf-8") as sink:
        with redirect_stdout(sink), redirect_stderr(sink):
            learn_website(
                snapshot_directory(payload) / "page.html",
                int(payload["website_id"]),
                payload["route_type"],
                payload["snapshot_id"],
            )


def main() -> None:
    configure_logging("learn")
    run_worker([JOB_TYPE], {JOB_TYPE: handle_learn}, {JOB_TYPE: settings.learn_job_timeout},
               isolate_handlers=True)
