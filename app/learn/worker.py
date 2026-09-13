import os
from contextlib import redirect_stderr, redirect_stdout
from functools import wraps

from app.infra.config import settings
from app.infra.progress import report_progress
from app.infra.storage import snapshot_directory
from app.infra.worker_base import run_worker
from app.learn import candidates, validation
from app.learn.service import learn_website
from app.infra.logging_config import configure_logging

JOB_TYPE = "learn"


def _report_after(function):
    @wraps(function)
    def tracked(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        finally:
            report_progress()

    return tracked


def handle_learn(payload: dict) -> None:
    original_hot_validate = candidates.hot_validate_html
    original_final_validation = validation.final_validation
    candidates.hot_validate_html = _report_after(original_hot_validate)
    validation.final_validation = _report_after(original_final_validation)
    report_progress()
    try:
        with open(os.devnull, "w", encoding="utf-8") as sink:
            with redirect_stdout(sink), redirect_stderr(sink):
                learn_website(
                    snapshot_directory(payload) / "page.html",
                    int(payload["website_id"]),
                    payload["route_type"],
                    payload["snapshot_id"],
                )
    finally:
        candidates.hot_validate_html = original_hot_validate
        validation.final_validation = original_final_validation


def main() -> None:
    configure_logging("learn")
    run_worker(
        [JOB_TYPE],
        {JOB_TYPE: handle_learn},
        {JOB_TYPE: settings.learn_hard_timeout},
        isolate_handlers=True,
        idle_timeouts={JOB_TYPE: settings.learn_job_timeout},
    )
