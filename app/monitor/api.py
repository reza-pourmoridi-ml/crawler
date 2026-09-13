from pathlib import Path

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.monitor.service import collect_status


router = APIRouter(prefix="/control/monitor", tags=["Monitor"])
templates = Jinja2Templates(directory=[
    str(Path(__file__).resolve().parent / "templates"),
    str(Path(__file__).resolve().parents[1] / "control" / "templates"),
])


@router.get("/page", response_class=HTMLResponse)
def monitor_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="monitor.html",
        context={},
    )


@router.get("/status")
def monitor_status(
    row_limit: int = Query(default=20, ge=5, le=200),
    history_hours: int = Query(default=24, ge=1, le=168),
):
    return collect_status(
        row_limit=row_limit,
        history_hours=history_hours,
    )
