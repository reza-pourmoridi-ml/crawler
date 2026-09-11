from pathlib import Path

from fastapi import (
    APIRouter,
    Depends,
    Form,
    HTTPException,
    Request,
    Response,
)

from fastapi.responses import (
    HTMLResponse,
    RedirectResponse,
)

from fastapi.templating import (
    Jinja2Templates,
)

from sqlalchemy.orm import Session

from app.control.websites import service

from app.control.websites.schemas import (
    WebsiteResponse,
    WebsiteWriteRequest,
)

from app.infra.db import get_db


router = APIRouter(
    prefix="/control/websites",
    tags=["Websites"],
)

templates = Jinja2Templates(
    directory=str(
        Path(__file__).resolve().parents[1]
        / "templates"
    )
)


def _website_or_404(
    db: Session,
    website_id: int,
):
    try:
        return service.get_website(
            db,
            website_id,
        )

    except service.WebsiteNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc


def _form(
    request: Request,
    website,
    *,
    error=None,
    status_code=200,
):
    return templates.TemplateResponse(
        request=request,
        name="website_form.html",
        context={
            "website": website,
            "error": error,
        },
        status_code=status_code,
    )


def _submitted_website(
    website_id,
    name,
    domestic_url_format,
    international_url_format,
    date_calendar,
    date_format,
):
    return {
        "id": website_id,
        "name": name,

        "domestic_url_format":
            domestic_url_format,

        "international_url_format":
            international_url_format,

        "date_calendar":
            date_calendar,

        "date_format":
            date_format,
    }


@router.get(
    "/page",
    response_class=HTMLResponse,
)
def websites_page(
    request: Request,
    db: Session = Depends(get_db),
):
    return templates.TemplateResponse(
        request=request,
        name="websites.html",
        context={
            "websites":
                service.get_websites(db)
        },
    )


@router.get(
    "/page/new",
    response_class=HTMLResponse,
)
def new_website_page(
    request: Request,
):
    return _form(
        request,
        _submitted_website(
            None,
            "",
            "",
            "",
            "jalali",
            "YYYY-MM-DD",
        ),
    )


@router.post(
    "/page/new",
    response_class=HTMLResponse,
)
def create_website_page(
    request: Request,

    name: str = Form(default=""),

    domestic_url_format: str = Form(
        default=""
    ),

    international_url_format: str = Form(
        default=""
    ),

    date_calendar: str = Form(
        default=""
    ),

    date_format: str = Form(
        default=""
    ),

    db: Session = Depends(get_db),
):
    try:
        website = service.create_website(
            db,
            name,
            domestic_url_format,
            international_url_format,
            date_calendar,
            date_format,
        )

    except (
        service.WebsiteAlreadyExistsError,
        ValueError,
    ) as exc:

        return _form(
            request,

            _submitted_website(
                None,
                name,
                domestic_url_format,
                international_url_format,
                date_calendar,
                date_format,
            ),

            error=str(exc),

            status_code=(
                409
                if isinstance(
                    exc,
                    service.WebsiteAlreadyExistsError,
                )
                else 422
            ),
        )

    return RedirectResponse(
        f"/control/websites/page/{website.id}",
        status_code=303,
    )


@router.get(
    "/page/{website_id}",
    response_class=HTMLResponse,
)
def website_detail_page(
    request: Request,
    website_id: int,
    db: Session = Depends(get_db),
):
    return templates.TemplateResponse(
        request=request,
        name="website_detail.html",
        context={
            "website":
                _website_or_404(
                    db,
                    website_id,
                )
        },
    )


@router.get(
    "/page/{website_id}/edit",
    response_class=HTMLResponse,
)
def edit_website_page(
    request: Request,
    website_id: int,
    db: Session = Depends(get_db),
):
    return _form(
        request,
        _website_or_404(
            db,
            website_id,
        ),
    )


@router.post(
    "/page/{website_id}/edit",
    response_class=HTMLResponse,
)
def update_website_page(
    request: Request,
    website_id: int,

    name: str = Form(default=""),

    domestic_url_format: str = Form(
        default=""
    ),

    international_url_format: str = Form(
        default=""
    ),

    date_calendar: str = Form(
        default=""
    ),

    date_format: str = Form(
        default=""
    ),

    db: Session = Depends(get_db),
):
    _website_or_404(
        db,
        website_id,
    )

    try:
        service.update_website(
            db,
            website_id,
            name,
            domestic_url_format,
            international_url_format,
            date_calendar,
            date_format,
        )

    except (
        service.WebsiteAlreadyExistsError,
        ValueError,
    ) as exc:

        return _form(
            request,

            _submitted_website(
                website_id,
                name,
                domestic_url_format,
                international_url_format,
                date_calendar,
                date_format,
            ),

            error=str(exc),

            status_code=(
                409
                if isinstance(
                    exc,
                    service.WebsiteAlreadyExistsError,
                )
                else 422
            ),
        )

    return RedirectResponse(
        f"/control/websites/page/{website_id}",
        status_code=303,
    )


@router.get(
    "/page/{website_id}/delete",
    response_class=HTMLResponse,
)
def delete_website_confirmation(
    request: Request,
    website_id: int,
    db: Session = Depends(get_db),
):
    return templates.TemplateResponse(
        request=request,
        name="website_delete.html",
        context={
            "website":
                _website_or_404(
                    db,
                    website_id,
                ),
            "error": None,
        },
    )


@router.post(
    "/page/{website_id}/delete",
    response_class=HTMLResponse,
)
def delete_website_page(
    request: Request,
    website_id: int,
    db: Session = Depends(get_db),
):
    website = _website_or_404(
        db,
        website_id,
    )

    try:
        service.delete_website(
            db,
            website_id,
        )

    except service.WebsiteInUseError as exc:
        return templates.TemplateResponse(
            request=request,
            name="website_delete.html",

            context={
                "website": website,
                "error": str(exc),
            },

            status_code=409,
        )

    return RedirectResponse(
        "/control/websites/page",
        status_code=303,
    )


@router.get(
    "",
    response_model=list[WebsiteResponse],
)
def get_websites(
    db: Session = Depends(get_db),
):
    return service.get_websites(
        db
    )


@router.post(
    "",
    response_model=WebsiteResponse,
    status_code=201,
)
def create_website(
    payload: WebsiteWriteRequest,
    db: Session = Depends(get_db),
):
    try:
        return service.create_website(
            db,
            **payload.model_dump(),
        )

    except service.WebsiteAlreadyExistsError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc


@router.get(
    "/{website_id}",
    response_model=WebsiteResponse,
)
def get_website(
    website_id: int,
    db: Session = Depends(get_db),
):
    return _website_or_404(
        db,
        website_id,
    )


@router.put(
    "/{website_id}",
    response_model=WebsiteResponse,
)
def update_website(
    website_id: int,
    payload: WebsiteWriteRequest,
    db: Session = Depends(get_db),
):
    _website_or_404(
        db,
        website_id,
    )

    try:
        return service.update_website(
            db,
            website_id,
            **payload.model_dump(),
        )

    except service.WebsiteAlreadyExistsError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc


@router.delete(
    "/{website_id}",
    status_code=204,
    response_class=Response,
)
def delete_website(
    website_id: int,
    db: Session = Depends(get_db),
):
    _website_or_404(
        db,
        website_id,
    )

    try:
        service.delete_website(
            db,
            website_id,
        )

    except service.WebsiteInUseError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc

    return Response(
        status_code=204
    )