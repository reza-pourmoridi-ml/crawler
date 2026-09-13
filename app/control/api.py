from pathlib import Path

from fastapi import (
    APIRouter,
    Depends,
    Form,
    HTTPException,
    Request,
)
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.control import service
from app.control.schemas import (
    AirlineCreateRequest,
    AirlineResponse,
    AirlineUpdateRequest,
)
from app.infra.db import get_db


router = APIRouter(
    prefix="/control",
    tags=["Control Panel"],
)


TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

templates = Jinja2Templates(
    directory=str(TEMPLATES_DIR)
)



@router.get(
    "/dashboard",
    response_class=HTMLResponse,
)
async def get_dashboard(
    request: Request,
):
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={},
    )


@router.get("/status")
async def get_api_status():
    return {
        "status": "ok",
        "service": "crawler-control",
    }



@router.get(
    "/airlines/page",
    response_class=HTMLResponse,
)
def airlines_page(
    request: Request,
    db: Session = Depends(get_db),
):
    airlines = service.get_airlines(db)

    return templates.TemplateResponse(
        request=request,
        name="airlines.html",
        context={
            "airlines": airlines,
        },
    )



@router.get(
    "/airlines",
    response_model=list[AirlineResponse],
)
def get_airlines(
    db: Session = Depends(get_db),
):
    return service.get_airlines(db)


@router.post("/airlines", response_model=AirlineResponse, status_code=201)
def create_airline(
    payload: AirlineCreateRequest,
    db: Session = Depends(get_db),
):
    try:
        return service.create_airline(
            db=db,
            official_name_fa=payload.official_name_fa,
            aliases=payload.aliases,
        )
    except service.AirlineAlreadyExistsError:
        raise HTTPException(
            status_code=409,
            detail="An airline with this name already exists.",
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get(
    "/airlines/{airline_id}",
    response_model=AirlineResponse,
)
def get_airline(
    airline_id: int,
    db: Session = Depends(get_db),
):
    try:
        return service.get_airline(
            db=db,
            airline_id=airline_id,
        )

    except service.AirlineNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="Airline not found",
        )


@router.put(
    "/airlines/{airline_id}",
    response_model=AirlineResponse,
)
def update_airline(
    airline_id: int,
    payload: AirlineUpdateRequest,
    db: Session = Depends(get_db),
):
    try:
        return service.update_airline(
            db=db,
            airline_id=airline_id,
            official_name_fa=payload.official_name_fa,
            aliases=payload.aliases,
        )

    except service.AirlineNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="Airline not found",
        )

    except service.AirlineAlreadyExistsError:
        raise HTTPException(
            status_code=409,
            detail="An airline with this name already exists.",
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        )



@router.get("/airlines/page/new", response_class=HTMLResponse)
def airline_create_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="airline_edit.html",
        context={
            "airline": {"official_name_fa": "", "aliases": []},
            "creating": True,
            "error": None,
        },
    )


@router.post("/airlines/page/new", response_class=HTMLResponse)
def create_airline_page(
    request: Request,
    official_name_fa: str = Form(default=""),
    aliases: list[str] = Form(default=[]),
    db: Session = Depends(get_db),
):
    try:
        service.create_airline(db, official_name_fa, aliases)
        return RedirectResponse(url="/control/airlines/page", status_code=303)
    except service.AirlineAlreadyExistsError:
        error = "ایرلاینی با این نام از قبل وجود دارد."
        status_code = 409
    except ValueError as exc:
        error = str(exc)
        status_code = 422

    return templates.TemplateResponse(
        request=request,
        name="airline_edit.html",
        context={
            "airline": {
                "official_name_fa": official_name_fa,
                "aliases": [{"alias_name": alias} for alias in aliases],
            },
            "creating": True,
            "error": error,
        },
        status_code=status_code,
    )


@router.get("/airlines/page/{airline_id}", response_class=HTMLResponse)
def airline_detail_page(
    request: Request,
    airline_id: int,
    db: Session = Depends(get_db),
):
    try:
        airline = service.get_airline(db, airline_id)
    except service.AirlineNotFoundError:
        raise HTTPException(status_code=404, detail="Airline not found")
    return templates.TemplateResponse(
        request=request,
        name="airline_detail.html",
        context={"airline": airline},
    )


@router.delete("/airlines/{airline_id}", status_code=204)
def delete_airline(
    airline_id: int,
    db: Session = Depends(get_db),
):
    try:
        service.delete_airline(db, airline_id)
    except service.AirlineNotFoundError:
        raise HTTPException(status_code=404, detail="Airline not found")
    return Response(status_code=204)


@router.get("/airlines/page/{airline_id}/delete", response_class=HTMLResponse)
def airline_delete_page(
    request: Request,
    airline_id: int,
    db: Session = Depends(get_db),
):
    try:
        airline = service.get_airline(db, airline_id)
    except service.AirlineNotFoundError:
        raise HTTPException(status_code=404, detail="Airline not found")
    return templates.TemplateResponse(
        request=request,
        name="airline_delete.html",
        context={"airline": airline},
    )


@router.post("/airlines/page/{airline_id}/delete")
def delete_airline_page(
    airline_id: int,
    db: Session = Depends(get_db),
):
    try:
        service.delete_airline(db, airline_id)
    except service.AirlineNotFoundError:
        raise HTTPException(status_code=404, detail="Airline not found")
    return RedirectResponse(url="/control/airlines/page", status_code=303)


@router.get(
    "/airlines/page/{airline_id}/edit",
    response_class=HTMLResponse,
)
def airline_edit_page(
    request: Request,
    airline_id: int,
    db: Session = Depends(get_db),
):
    try:
        airline = service.get_airline(
            db=db,
            airline_id=airline_id,
        )

    except service.AirlineNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="Airline not found",
        )

    return templates.TemplateResponse(
        request=request,
        name="airline_edit.html",
        context={
            "airline": airline,
            "error": None,
        },
    )


@router.post(
    "/airlines/page/{airline_id}/edit",
    response_class=HTMLResponse,
)
def update_airline_page(
    request: Request,
    airline_id: int,
    official_name_fa: str = Form(default=""),
    aliases: list[str] = Form(default=[]),
    db: Session = Depends(get_db),
):
    try:
        service.update_airline(
            db=db,
            airline_id=airline_id,
            official_name_fa=official_name_fa,
            aliases=aliases,
        )

        return RedirectResponse(
            url="/control/airlines/page",
            status_code=303,
        )

    except service.AirlineNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="Airline not found",
        )

    except service.AirlineAlreadyExistsError:
        error = "ایرلاینی با این نام از قبل وجود دارد."
        status_code = 409

    except ValueError as exc:
        error = str(exc)
        status_code = 422

    return templates.TemplateResponse(
        request=request,
        name="airline_edit.html",
        context={
            "airline": {
                "id": airline_id,
                "official_name_fa": official_name_fa,
                "aliases": [
                    {"alias_name": alias}
                    for alias in aliases
                ],
            },
            "error": error,
        },
        status_code=status_code,
    )
