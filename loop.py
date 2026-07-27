import asyncio
import json
import random
from datetime import datetime, timezone
from pathlib import Path

# ایمپورت متد اصلی از get_page_data
from get_page_data import extract_alibaba_data

RESULTS_FILE = Path("daily_test_results.jsonl")
STATE_FILE = Path("daily_test_state.json")

URLS = [
    "https://www.alibaba.ir/flights/THR-MHD?adult=1&child=0&infant=0&departing=1405-05-09",
    # "https://www.alibaba.ir/international/IKA-ISTALL?adult=1&child=0&infant=0&departing=1405-05-15&flightClass=economy",
    "https://www.snapptrip.ir/flights/THR_city/MHD_city?adultCount=1&childCount=0&infantCount=0&departureDate=2026-08-5&source=searchBox&dateType=jalali",
    "https://www.snapptrip.ir/inter-flights/THR_city/IST_city?adultCount=1&childCount=0&infantCount=0&departureDate=2026-08-5&source=searchBox&dateType=jalali&cabinType=ECONOMY",
    "https://www.flytoday.ir/flight/search?departure=thr,1&arrival=mhd,1&departureDate=2026-08-05&adt=1&chd=0&inf=0&cabin=1&isDomestic=true&isAnyWhere=false",
    "https://www.flytoday.ir/flight/search?departure=thr,1&arrival=ist,1&departureDate=2026-08-05&adt=1&chd=0&inf=0&cabin=1&isAnyWhere=false",
    "https://mrbilit.com/flights/THR-MHD?departureDate=1405-05-15",
    "https://mrbilit.com/flights/IKA-ISTALL?departureDate=1405-05-15&cabinClass=/P",
    "https://ghasedak24.com/flights/THR-MHD?departure-date=1405-05-15&adult-count=1&child-count=0&infant-count=0",
    "https://ghasedak24.com/flights/IKA-ISTALL?departure-date=1405-05-15&adult-count=1&child-count=0&infant-count=0&cabin=Y",
]

# مدت کل تست (۲۴ ساعت)
RUN_FOR_SECONDS = 24 * 60 * 60

# تایم اوت قطعی هر اجرا (حداکثر ۴ دقیقه)
JOB_TIMEOUT_SECONDS = 240

# تاخیر تصادفی بین درخواست‌های موفق
MIN_SLEEP_BETWEEN_RUNS = 20
MAX_SLEEP_BETWEEN_RUNS = 30

# تاخیر بیشتر در صورت مواجهه با بلاک/کپچا برای از بین رفتن اثر حساسیت آی‌پی
BACKOFF_ON_FAILURE_MIN = 120
BACKOFF_ON_FAILURE_MAX = 300


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


async def run_one_iteration(target_url: str) -> dict:
    # ما در حالت Headless روی سرور تست را انجام می‌دهیم (می‌توانید به False تغییر دهید)
    return await extract_alibaba_data(target_url, headless_mode=True)


async def main():
    state = load_state()
    started = asyncio.get_running_loop().time()
    end_time = started + RUN_FOR_SECONDS

    print(f"[*] Daily test started/resumed at {state.get('started_at')}")
    print(f"[*] Total run window: {RUN_FOR_SECONDS/3600:.1f} hours")
    print(f"[*] Hard Timeout per run: {JOB_TIMEOUT_SECONDS}s")
    print(f"[*] Target URLs: {len(URLS)}")

    while True:
        now = asyncio.get_running_loop().time()
        if now >= end_time:
            print("[*] Daily test window finished.")
            break

        idx = state["index"] % len(URLS)
        target_url = URLS[idx]

        print(f"\n[*] Iteration #{state['runs'] + 1}")
        print(f"[*] Current URL [{idx}]: {target_url}")

        run_started = utc_now()
        status = "unknown"
        error = None
        result_payload = None

        try:
            # اعمال تایم اوت سخت روی کل اجرای متد
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
            error = f"Job hit the hard timeout limit of {JOB_TIMEOUT_SECONDS} seconds."
        except Exception as e:
            status = "exception"
            error = repr(e)

        duration_sec = round(asyncio.get_running_loop().time() - now, 2)

        # آپدیت وضعیت
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

        # منطق فاصله زمانی تا چرخه بعدی بر اساس نتیجه
        if status in {"captcha_detected", "captcha_timeout", "auth_required", "blocked", "job_timeout", "exception"}:
            sleep_s = random.randint(BACKOFF_ON_FAILURE_MIN, BACKOFF_ON_FAILURE_MAX)
            print(f"[!] Backing off due to status '{status}'. Waiting {sleep_s}s...")
        else:
            sleep_s = random.randint(MIN_SLEEP_BETWEEN_RUNS, MAX_SLEEP_BETWEEN_RUNS)
            print(f"[*] Step successful. Next in {sleep_s}s...")

        remaining = end_time - asyncio.get_running_loop().time()
        if remaining <= 0:
            break

        sleep_s = min(sleep_s, max(1, int(remaining)))
        await asyncio.sleep(sleep_s)

    print("\n[*] Daily test completed.")
    print(f"[*] Total iterations run: {state['runs']}")
    print(f"[*] Successful extractions: {state['success']}")
    print(f"[*] Failed extractions: {state['failure']}")
    print(f"[*] Detailed results appended to: {RESULTS_FILE}")
    print(f"[*] Final state saved to: {STATE_FILE}")


if __name__ == "__main__":
    asyncio.run(main())
