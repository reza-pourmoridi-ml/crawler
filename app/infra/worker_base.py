# app/infra/worker_base.py
import logging
import multiprocessing
import os
import tempfile
import time
import signal
import threading
from app.infra.queue import fetch_job, extend_lock, mark_done, mark_failed, sweep_stuck_jobs
from app.infra.storage import storage_root
from app.infra.logging_config import configure_logging

logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL = 60
IDLE_SLEEP = 5
SWEEP_INTERVAL = 300  # هر ۵ دقیقه جاب‌های گیرکرده رو آزاد کن


def _process_target(handler, payload, connection, directory, parent_pid):
    configure_logging(os.getenv("SERVICE_NAME", "worker"))
    if os.name == "posix":
        os.setsid()
    os.environ["CRAWLER_JOB_TEMP"] = directory
    os.environ["TMPDIR"] = directory
    tempfile.tempdir = directory

    def watch_parent():
        while os.getppid() == parent_pid:
            time.sleep(1)
        if os.name == "posix":
            os.killpg(os.getpgrp(), signal.SIGKILL)
        os._exit(1)

    threading.Thread(target=watch_parent, daemon=True).start()
    try:
        handler(payload)
        connection.send(None)
    except BaseException as exc:
        connection.send(f"{type(exc).__name__}: {exc}"[:2000])
    finally:
        connection.close()


def stop_process(process) -> None:
    if process.pid is None:
        return
    if os.name == "posix":
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    if process.is_alive():
        process.terminate()
    process.join(5)
    if os.name == "posix":
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    if process.is_alive():
        process.kill()
        process.join()
    process.close()


def run_handler_in_process(handler, payload: dict, timeout: int, *, job_id: int = 0,
                           attempt: int = 0, cancel_events=()) -> None:
    context = multiprocessing.get_context("spawn")
    root = storage_root() / "temp"
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f"job_{job_id}_{attempt}_", dir=root) as directory:
        receiver, sender = context.Pipe(duplex=False)
        process = context.Process(target=_process_target,
                                  args=(handler, payload, sender, directory, os.getpid()))
        try:
            process.start()
            sender.close()
            deadline = time.monotonic() + timeout
            while process.is_alive():
                if any(event.is_set() for event in cancel_events):
                    raise RuntimeError("Worker stopped or job lease lost")
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError(f"Handler exceeded {timeout}s")
                process.join(min(remaining, 0.5))
            if process.exitcode != 0:
                raise RuntimeError(f"Handler process exited with code {process.exitcode}")
            if not receiver.poll():
                raise RuntimeError("Handler process exited without a result")
            error = receiver.recv()
            if error is not None:
                raise RuntimeError(error)
        finally:
            stop_process(process)
            sender.close()
            receiver.close()


def run_worker(job_types: list[str], handlers: dict, timeouts: dict, default_timeout: int = 300,
               *, isolate_handlers: bool = True):
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

    last_sweep_ts = 0

    logger.info("Worker started for types: %s", job_types)

    while not stop.is_set():
        if time.time() - last_sweep_ts > SWEEP_INTERVAL:
            try:
                sweep_stuck_jobs()
            except Exception as e:
                logger.warning("Sweep failed: %s", e)
            last_sweep_ts = time.time()

        try:
            job = fetch_job(job_types, lock_seconds=max(timeouts.values(), default=default_timeout) + 60,
                            timeouts={kind: timeouts.get(kind, default_timeout) for kind in job_types})
        except Exception:
            logger.exception("Could not fetch job")
            stop.wait(IDLE_SLEEP)
            continue
        if job is None:
            stop.wait(IDLE_SLEEP)
            continue

        job_id, job_type = job["id"], job["type"]
        timeout = timeouts.get(job_type, default_timeout)
        hb_stop = threading.Event()
        lease_lost = threading.Event()
        attempt = job["attempts"]

        def heartbeat():
            while not hb_stop.wait(HEARTBEAT_INTERVAL):
                try:
                    if not extend_lock(job_id, timeout + 60, attempt=attempt):
                        lease_lost.set()
                        return
                except Exception as e:
                    logger.warning("Heartbeat failed for job %s: %s", job_id, e)
                    lease_lost.set()
                    return

        hb_thread = threading.Thread(target=heartbeat, daemon=True)
        hb_thread.start()

        try:
            handler = handlers.get(job_type)
            if handler is None:
                raise ValueError(f"No handler for job type: {job_type}")

            if isolate_handlers:
                run_handler_in_process(handler, job["payload"], timeout, job_id=job_id, attempt=attempt,
                                       cancel_events=(stop, lease_lost))
            else:
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

            if not mark_done(job_id, attempt=attempt):
                raise RuntimeError("Job lease expired before completion")
            logger.info("Job %s (%s) completed: outcome=success", job_id, job_type)
        except Exception as e:
            logger.error("Job %s (%s) failed: %s", job_id, job_type, e)
            try:
                mark_failed(job_id, attempt=attempt)
            except Exception:
                logger.exception("Could not record failure for job %s; sweeper will recover it", job_id)
        finally:
            hb_stop.set()
            hb_thread.join()

    logger.info("Worker stopped")
