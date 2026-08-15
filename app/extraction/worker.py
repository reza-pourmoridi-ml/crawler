# app/extraction/worker.py
import asyncio
import logging
from app.infra.worker_base import run_worker
from app.extraction.service import extract_alibaba_data

logger = logging.getLogger(__name__)


def handle_crawl_alibaba(payload: dict):
    url = payload["url"]
    headless = payload.get("headless", True)
    result = asyncio.run(extract_alibaba_data(url, headless_mode=headless))
    if result.get("status") not in ("success",):
        raise RuntimeError(f"Crawl failed with status={result.get('status')}")
    logger.info("Crawl result: %s", result)


HANDLERS = {
    "extraction.crawl_alibaba": handle_crawl_alibaba,
}

TIMEOUTS = {
    "extraction.crawl_alibaba": 240,  # این جاب معمولاً سریعه؛ اگه چیزی تا ۱ ساعت طول می‌کشه اینجا 3600 بذار
}


def main():
    logging.basicConfig(level=logging.INFO)
    run_worker(job_types=list(HANDLERS.keys()), handlers=HANDLERS, timeouts=TIMEOUTS)


if __name__ == "__main__":
    main()