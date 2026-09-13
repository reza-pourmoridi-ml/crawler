from pathlib import Path
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from fastapi import (
    APIRouter,
    Depends,
    Form,
    HTTPException,
    Request,
)

from fastapi.responses import (
    HTMLResponse,
    RedirectResponse,
)

from fastapi.templating import (
    Jinja2Templates,
)

from sqlalchemy.orm import Session

from app.control.search_box import (
    service,
)

from app.control.search_box.schemas import (
    SearchRequestCreate,
    SearchRequestResponse,
    SearchResultResponse,
)
from app.control.search_box.jalali import gregorian_to_jalali

from app.infra.db import get_db
from app.orchestration.results import (
    SearchResultNotFoundError,
    get_provider_airline_prices,
    get_search_result,
    get_search_results,
)


router = APIRouter(
    prefix="/control/search-box",
    tags=["Search Box"],
)


templates = Jinja2Templates(
    directory=str(
        Path(
            __file__
        ).resolve().parents[1]
        / "templates"
    )
)


JALALI_MONTHS = (
    "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
    "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند",
)


def _jalali_form_context(value: str) -> dict:
    today = datetime.now(ZoneInfo("Asia/Tehran")).date()
    selected_year, selected_month, selected_day = gregorian_to_jalali(today)
    if value:
        try:
            parts = value.strip().replace("/", "-").split("-")
            selected_year, selected_month, selected_day = (int(part) for part in parts)
        except (TypeError, ValueError):
            pass
    first_year = gregorian_to_jalali(today)[0]
    years = list(range(first_year, first_year + 4))
    if selected_year not in years:
        years.append(selected_year)
        years.sort()
    return {
        "jalali_years": years,
        "jalali_months": list(enumerate(JALALI_MONTHS, start=1)),
        "submitted_departure_year": selected_year,
        "submitted_departure_month": selected_month,
        "submitted_departure_day": selected_day,
    }


def _tehran_time(value):
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(ZoneInfo("Asia/Tehran"))


def _render_page(
    request: Request,
    db: Session,
    *,
    error: str | None = None,
    status_code: int = 200,
    saved: bool = False,
    route_type: str = "domestic",
    origin_airport_id:
        int | None = None,
    destination_airport_id:
        int | None = None,
    departure_date_jalali:
        str = "",
):

    (
        airports,
        domestic_requests,
        international_requests,
    ) = service.get_page_data(
        db
    )

    # برای JavaScript خام صفحه.
    # هیچ package سمت frontend نداریم.
    airport_options = [
        {
            "id":
                airport.id,

            "name":
                airport.name_fa,

            "category":
                airport.category,
        }

        for airport in airports
    ]

    search_results = get_search_results(
        db,
        [
            item.id
            for item in [
                *domestic_requests,
                *international_requests,
            ]
        ],
    )
    update_times = [
        result["updated_at"]
        for result in search_results.values()
        if result["updated_at"] is not None
    ]
    last_results_updated_at = max(update_times) if update_times else None
    last_results_updated_at = _tehran_time(last_results_updated_at)

    return templates.TemplateResponse(
        request=request,

        name="search_box.html",

        context={
            "airports":
                airports,

            "airport_options":
                airport_options,

            "domestic_requests":
                domestic_requests,

            "international_requests":
                international_requests,

            "search_results":
                search_results,

            "last_results_updated_at":
                last_results_updated_at,

            "error":
                error,

            "saved":
                saved,

            "submitted_route_type":
                route_type,

            "submitted_origin_airport_id":
                origin_airport_id,

            "submitted_destination_airport_id":
                destination_airport_id,

            "submitted_departure_date_jalali":
                departure_date_jalali,

            **_jalali_form_context(departure_date_jalali),
        },

        status_code=status_code,
    )


# =========================================================
# HTML
# =========================================================


@router.get(
    "/page",
    response_class=HTMLResponse,
)
def search_box_page(
    request: Request,

    saved: int = 0,

    db: Session = Depends(
        get_db
    ),
):

    return _render_page(
        request,
        db,

        saved=(
            saved == 1
        ),
    )


@router.post(
    "/page",
    response_class=HTMLResponse,
)
def create_search_request_page(
    request: Request,

    route_type: str = Form(...),

    origin_airport_id:
        int = Form(...),

    destination_airport_id:
        int = Form(...),

    departure_date_jalali:
        str = Form(
            default=""
        ),

    departure_year: int | None = Form(default=None),
    departure_month: int | None = Form(default=None),
    departure_day: int | None = Form(default=None),

    db: Session = Depends(
        get_db
    ),
):

    date_parts = (departure_year, departure_month, departure_day)
    if any(part is not None for part in date_parts):
        if any(part is None for part in date_parts):
            departure_date_jalali = ""
        else:
            departure_date_jalali = (
                f"{departure_year:04d}-{departure_month:02d}-{departure_day:02d}"
            )

    try:

        service.create_search_request(
            db=db,

            route_type=
                route_type,

            origin_airport_id=
                origin_airport_id,

            destination_airport_id=
                destination_airport_id,

            departure_date_jalali=
                departure_date_jalali,
        )

    except ValueError as exc:

        return _render_page(
            request,
            db,

            error=str(exc),

            status_code=422,

            route_type=
                route_type,

            origin_airport_id=
                origin_airport_id,

            destination_airport_id=
                destination_airport_id,

            departure_date_jalali=
                departure_date_jalali,
        )

    return RedirectResponse(
        url=(
            "/control/search-box/page"
            "?saved=1"
        ),

        status_code=303,
    )


@router.get(
    "/page/{search_request_id}/results",
    response_class=HTMLResponse,
)
def search_results_page(
    request: Request,
    search_request_id: int,
    db: Session = Depends(get_db),
):
    search_request = service.get_search_request(db, search_request_id)
    if search_request is None:
        raise HTTPException(status_code=404, detail="درخواست جستجو پیدا نشد.")
    result = get_search_result(db, search_request_id)
    result["updated_at_tehran"] = _tehran_time(result["updated_at"])
    for provider in result["providers"]:
        provider["updated_at_tehran"] = _tehran_time(provider["updated_at"])
    airline_rows = {}
    for offer in get_provider_airline_prices(db, search_request_id):
        row = airline_rows.setdefault(
            offer["airline"],
            {"airline": offer["airline"], "providers": {}},
        )
        row["providers"][offer["website_id"]] = offer
    return templates.TemplateResponse(
        request=request,
        name="search_results.html",
        context={
            "search_request": search_request,
            "result": result,
            "airline_rows": sorted(airline_rows.values(), key=lambda row: row["airline"]),
        },
    )


# =========================================================
# JSON API
# =========================================================


@router.get(
    "",
    response_model=list[
        SearchRequestResponse
    ],
)
def get_search_requests(
    db: Session = Depends(
        get_db
    ),
):

    return (
        service.get_search_requests(
            db
        )
    )


@router.get(
    "/{search_request_id}/results",
    response_model=SearchResultResponse,
)
def search_request_results(
    search_request_id: int,
    db: Session = Depends(get_db),
):
    try:
        return get_search_result(db, search_request_id)
    except SearchResultNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "",
    response_model=
        SearchRequestResponse,

    status_code=201,
)
def create_search_request(
    payload: SearchRequestCreate,

    db: Session = Depends(
        get_db
    ),
):

    try:

        return (
            service.create_search_request(
                db=db,

                **payload.model_dump(),
            )
        )

    except ValueError as exc:

        raise HTTPException(
            status_code=422,

            detail=str(exc),
        ) from exc
