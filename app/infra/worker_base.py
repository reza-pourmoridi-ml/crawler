# app/infra/worker_base.py
import logging
import signal
import threading
from app.infra.queue import fetch_job, extend_lock, mark_done, mark_failed, sweep_stuck_jobs

logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL = 60
IDLE_SLEEP = 5
SWEEP_INTERVAL = 300  # هر ۵ دقیقه جاب‌های گیرکرده رو آزاد کن


def run_worker(job_types: list[str], handlers: dict, timeouts: dict, default_timeout: int = 300):
    """
    لوپ اصلی ورکر. هر ماژول (extraction, learning, ...) این تابع رو با
    type ها و handler های خودش صدا می‌زنه.

    handlers: {"extraction.crawl_alibaba": handle_fn, ...}
    timeouts: {"extraction.crawl_alibaba": 3600, ...}   -> ثانیه، برای جاب سنگین بالا بگیر
    """
    stop = threading.Event()

    if threading.current_thread() is threading.main_thread():
        signal.signal(signal.SIGTERM, lambda *_: stop.set())
        signal.signal(signal.SIGINT, lambda *_: stop.set())
    else:
        logger.debug("run_worker is not in main thread; skipping SIGTERM/SIGINT handlers (expected in tests)")

    import time
    last_sweep_ts = time.time()

    logger.info("Worker started for types: %s", job_types)

    while not stop.is_set():
        if time.time() - last_sweep_ts > SWEEP_INTERVAL:
            try:
                sweep_stuck_jobs()
            except Exception as e:
                logger.warning("Sweep failed: %s", e)
            last_sweep_ts = time.time()

        job = fetch_job(job_types, lock_seconds=max(timeouts.values(), default=default_timeout) + 60)
        if job is None:
            stop.wait(IDLE_SLEEP)
            continue

        job_id, job_type = job["id"], job["type"]
        timeout = timeouts.get(job_type, default_timeout)
        hb_stop = threading.Event()

        def heartbeat():
            while not hb_stop.wait(HEARTBEAT_INTERVAL):
                try:
                    extend_lock(job_id, timeout + 60)
                except Exception as e:
                    logger.warning("Heartbeat failed for job %s: %s", job_id, e)

        hb_thread = threading.Thread(target=heartbeat, daemon=True)
        hb_thread.start()

        try:
            handler = handlers.get(job_type)
            if handler is None:
                raise ValueError(f"No handler for job type: {job_type}")

            result = [None]
            exc = [None]

            def target():
                try:
                    handler(job["payload"])
                except Exception as e:
                    exc[0] = e

            t = threading.Thread(target=target, daemon=True)
            t.start()
            t.join(timeout=timeout)
            if t.is_alive():
                raise TimeoutError(f"Handler exceeded {timeout}s for job {job_id}")
            if exc[0]:
                raise exc[0]

            mark_done(job_id)
            logger.info("Job %s (%s) done", job_id, job_type)
        except Exception as e:
            logger.error("Job %s (%s) failed: %s", job_id, job_type, e)
            mark_failed(job_id)
        finally:
            hb_stop.set()
            hb_thread.join()

    logger.info("Worker stopped")