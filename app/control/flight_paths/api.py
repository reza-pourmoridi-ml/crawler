from pathlib import Path

from fastapi import (
    APIRouter,
    Depends,
    Form,
    HTTPException,
    Query,
    Request,
)

from fastapi.responses import (
    HTMLResponse,
    RedirectResponse,
    Response,
)

from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.control.flight_paths import service
from app.control.flight_paths.schemas import (
    FlightPathRequest,
    FlightPathResponse,
)

from app.infra.db import get_db


router = APIRouter(
    prefix="/control/flight-paths",
    tags=["Airport codes"],
)

templates = Jinja2Templates(
    directory=str(
        Path(__file__).resolve().parents[1]
        / "templates"
    )
)


PAGE_CATEGORIES = {
    "domestic": {
        "db_category": "domestic",
        "title": "فرودگاه‌های داخلی",
        "description": (
            "کد هر فرودگاه داخلی را برای هر وب‌سایت "
            "در همان خانهٔ جدول وارد یا ویرایش کنید."
        ),
    },

    "foreign": {
        "db_category": "international",
        "title": "فرودگاه‌های خارجی",
        "description": (
            "کد هر فرودگاه خارجی را برای هر وب‌سایت "
            "در همان خانهٔ جدول وارد یا ویرایش کنید."
        ),
    },
}


def _page_config(
    page_category: str,
) -> dict:
    config = PAGE_CATEGORIES.get(
        page_category
    )

    if config is None:
        raise HTTPException(
            status_code=404,
            detail="دستهٔ فرودگاه پیدا نشد.",
        )

    return config


def _render_matrix(
    request: Request,
    db: Session,
    page_category: str,
    *,
    error: str | None = None,
    status_code: int = 200,
    submitted_airport_id: int | None = None,
    submitted_website_id: int | None = None,
    submitted_code: str | None = None,
    saved: bool = False,
):
    config = _page_config(
        page_category
    )

    airports, websites, matrix = (
        service.get_airport_matrix(
            db,
            config["db_category"],
        )
    )

    return templates.TemplateResponse(
        request=request,
        name="flight_paths.html",
        context={
            "page_category": page_category,
            "page_title": config["title"],
            "page_description": config[
                "description"
            ],

            "airports": airports,
            "websites": websites,
            "matrix": matrix,

            "error": error,
            "saved": saved,

            "submitted_airport_id":
                submitted_airport_id,

            "submitted_website_id":
                submitted_website_id,

            "submitted_code":
                submitted_code,
        },
        status_code=status_code,
    )


# =========================================================
# HTML pages
# =========================================================


@router.get("/page")
def flight_paths_page_redirect():
    return RedirectResponse(
        url=(
            "/control/flight-paths/"
            "page/domestic"
        ),
        status_code=307,
    )


@router.get(
    "/page/{page_category}",
    response_class=HTMLResponse,
)
def flight_paths_page(
    request: Request,
    page_category: str,
    saved: int = Query(default=0),
    db: Session = Depends(get_db),
):
    return _render_matrix(
        request,
        db,
        page_category,
        saved=(saved == 1),
    )


@router.post(
    "/page/{page_category}/code",
    response_class=HTMLResponse,
)
def save_airport_code_page(
    request: Request,
    page_category: str,

    airport_id: int = Form(...),
    website_id: int = Form(...),
    code: str = Form(default=""),

    db: Session = Depends(get_db),
):
    config = _page_config(
        page_category
    )

    try:
        airport = service.require_airport(
            db,
            airport_id,
        )

        if (
            airport.category
            != config["db_category"]
        ):
            raise ValueError(
                "این فرودگاه متعلق به این صفحه نیست."
            )

        service.set_airport_code(
            db=db,
            airport_id=airport_id,
            website_id=website_id,
            code=code,
        )

    except (
        service.FlightPathAlreadyExistsError
    ) as exc:
        return _render_matrix(
            request,
            db,
            page_category,
            error=str(exc),
            status_code=409,

            submitted_airport_id=airport_id,
            submitted_website_id=website_id,
            submitted_code=code,
        )

    except ValueError as exc:
        return _render_matrix(
            request,
            db,
            page_category,
            error=str(exc),
            status_code=422,

            submitted_airport_id=airport_id,
            submitted_website_id=website_id,
            submitted_code=code,
        )

    return RedirectResponse(
        url=(
            f"/control/flight-paths/"
            f"page/{page_category}"
            "?saved=1"
        ),
        status_code=303,
    )


# =========================================================
# JSON API
# =========================================================


@router.get(
    "",
    response_model=list[FlightPathResponse],
)
def get_flight_paths(
    website_id: int | None = Query(
        default=None,
        gt=0,
    ),
    db: Session = Depends(get_db),
):
    try:
        return service.get_flight_paths(
            db,
            website_id,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc


@router.post(
    "",
    response_model=FlightPathResponse,
    status_code=201,
)
def create_flight_path(
    payload: FlightPathRequest,
    db: Session = Depends(get_db),
):
    try:
        return service.create_flight_path(
            db,
            **payload.model_dump(),
        )

    except (
        service.FlightPathAlreadyExistsError
    ) as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc

    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc


@router.get(
    "/{flight_path_id}",
    response_model=FlightPathResponse,
)
def get_flight_path(
    flight_path_id: int,
    db: Session = Depends(get_db),
):
    try:
        return service.get_flight_path(
            db,
            flight_path_id,
        )

    except service.FlightPathNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc


@router.put(
    "/{flight_path_id}",
    response_model=FlightPathResponse,
)
def update_flight_path(
    flight_path_id: int,
    payload: FlightPathRequest,
    db: Session = Depends(get_db),
):
    try:
        return service.update_flight_path(
            db,
            flight_path_id,
            **payload.model_dump(),
        )

    except service.FlightPathNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc

    except (
        service.FlightPathAlreadyExistsError
    ) as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc

    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc


@router.delete(
    "/{flight_path_id}",
    status_code=204,
)
def delete_flight_path(
    flight_path_id: int,
    db: Session = Depends(get_db),
):
    try:
        service.delete_flight_path(
            db,
            flight_path_id,
        )

    except service.FlightPathNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc

    return Response(
        status_code=204
    )