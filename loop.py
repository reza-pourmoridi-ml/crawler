import asyncio
import json
import random
from datetime import datetime, timezone
from pathlib import Path

# فرض: این تابع را از فایل اصلی‌ات import می‌کنی
# from alibaba_extractor import extract_alibaba_data_for_url
#
# بهتر است تابع اصلی‌ات به‌جای TARGET_URL ثابت، URL را به‌عنوان آرگومان بگیرد.
#
# مثال:
# async def extract_alibaba_data_for_url(target_url: str) -> dict:
#     ...
#     return {"status": "...", "target_url": target_url, ...}

RESULTS_FILE = Path("daily_test_results.jsonl")
STATE_FILE = Path("daily_test_state.json")

URLS = [
    "https://www.alibaba.ir/international/IKA-ISTALL?adult=1&child=0&infant=0&departing=1405-05-02&flightClass=economy",
    "https://www.flytoday.ir/flight/search?departure=thr,1&arrival=mhd,1&departureDate=2026-07-24&adt=1&chd=0&inf=0&cabin=1&isDomestic=true&isAnyWhere=false",
    "https://www.flytoday.ir/flight/search?departure=thr,1&arrival=ist,1&departureDate=2026-07-24&adt=1&chd=0&inf=0&cabin=1&isAnyWhere=false",
    "https://www.snapptrip.ir/flights/THR_city/MHD_city?adultCount=1&childCount=0&infantCount=0&departureDate=2026-07-24&source=searchBox&dateType=jalali",
    "https://www.snapptrip.ir/inter-flights/THR_city/IST_city?adultCount=1&childCount=0&infantCount=0&departureDate=2026-07-24&source=searchBox&dateType=jalali&cabinType=ECONOMY",
    "https://mrbilit.com/flights/THR-MHD?departureDate=1405-05-02",
    "https://mrbilit.com/flights/IKA-ISTALL?departureDate=1405-05-02&cabinClass=/P",
    "https://ghasedak24.com/flights/THR-MHD?departure-date=1405-05-02&adult-count=1&child-count=0&infant-count=0",
    "https://ghasedak24.com/flights/IKA-ISTALL?departure-date=1405-05-02&adult-count=1&child-count=0&infant-count=0&cabin=Y",
]

# 1 روز کامل
RUN_FOR_SECONDS = 24 * 60 * 60

# timeout کل هر job
JOB_TIMEOUT_SECONDS = 240

# timeout برای فاصله بین runها
MIN_SLEEP_BETWEEN_RUNS = 20
MAX_SLEEP_BETWEEN_RUNS = 90

# اگر خواستی نرخ را کمتر/بیشتر کنی
BACKOFF_ON_FAILURE_MIN = 60
BACKOFF_ON_FAILURE_MAX = 240


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "index": 0,
        "runs": 0,
        "success": 0,
        "failure": 0,
        "last_status": None,
        "last_url": None,
        "started_at": utc_now(),
    }


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def append_result(result: dict):
    with RESULTS_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(result, ensure_ascii=False) + "\n")


async def run_one_iteration(target_url: str):
    """
    اینجا باید تابع اصلی‌ات را صدا بزنی.
    بهتر است extract_alibaba_data با آرگومان url بازنویسی شود.
    """
    # نمونه:
    # result = await extract_alibaba_data_for_url(target_url)
    # return result

    raise NotImplementedError("Replace this with your real extractor call.")


async def main():
    state = load_state()
    started = asyncio.get_running_loop().time()
    end_time = started + RUN_FOR_SECONDS

    print(f"[*] Daily test started at {state.get('started_at')}")
    print(f"[*] Will run for {RUN_FOR_SECONDS/3600:.1f} hours")
    print(f"[*] Job timeout per iteration: {JOB_TIMEOUT_SECONDS}s")
    print(f"[*] URLs available: {len(URLS)}")

    while True:
        now = asyncio.get_running_loop().time()
        if now >= end_time:
            print("[*] Daily test time window finished.")
            break

        idx = state["index"] % len(URLS)
        target_url = URLS[idx]

        print(f"\n[*] Iteration #{state['runs'] + 1}")
        print(f"[*] Using URL index {idx}: {target_url}")

        run_started = utc_now()
        status = "unknown"
        error = None
        result_payload = None
        duration_sec = None

        try:
            result_payload = await asyncio.wait_for(
                run_one_iteration(target_url),
                timeout=JOB_TIMEOUT_SECONDS,
            )

            if isinstance(result_payload, dict):
                status = result_payload.get("status", "success")
            else:
                status = "success"

        except asyncio.TimeoutError:
            status = "job_timeout"
            error = f"Job exceeded {JOB_TIMEOUT_SECONDS} seconds"

        except Exception as e:
            status = "exception"
            error = repr(e)

        duration_sec = round(asyncio.get_running_loop().time() - now, 2)

        state["runs"] += 1
        state["index"] += 1
        state["last_status"] = status
        state["last_url"] = target_url
        if status == "success":
            state["success"] += 1
        else:
            state["failure"] += 1

        save_state(state)

        result = {
            "timestamp_utc": run_started,
            "url": target_url,
            "iteration": state["runs"],
            "status": status,
            "error": error,
            "duration_sec": duration_sec,
            "payload": result_payload,
        }
        append_result(result)

        print(f"[*] Status: {status} | Duration: {duration_sec}s")
        if error:
            print(f"[!] Error: {error}")

        if status in {"captcha_detected", "captcha_timeout", "auth_required", "blocked", "job_timeout", "exception"}:
            sleep_s = random.randint(BACKOFF_ON_FAILURE_MIN, BACKOFF_ON_FAILURE_MAX)
        else:
            sleep_s = random.randint(MIN_SLEEP_BETWEEN_RUNS, MAX_SLEEP_BETWEEN_RUNS)

        remaining = end_time - asyncio.get_running_loop().time()
        if remaining <= 0:
            break

        sleep_s = min(sleep_s, max(1, int(remaining)))
        print(f"[*] Sleeping {sleep_s}s before next run...")
        await asyncio.sleep(sleep_s)

    print("\n[*] Daily test finished.")
    print(f"[*] Total runs: {state['runs']}")
    print(f"[*] Success: {state['success']}")
    print(f"[*] Failure: {state['failure']}")
    print(f"[*] Results file: {RESULTS_FILE}")
    print(f"[*] State file: {STATE_FILE}")


if __name__ == "__main__":
    asyncio.run(main())
