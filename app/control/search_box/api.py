from pathlib import Path

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
)

from app.infra.db import get_db


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

    db: Session = Depends(
        get_db
    ),
):

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