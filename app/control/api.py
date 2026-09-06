from pathlib import Path
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter(prefix="/control", tags=["Control Panel"])

# Locate the templates directory relative to this file
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


# 1. Server-Rendered HTML Route
@router.get("/dashboard", response_class=HTMLResponse)
async def get_dashboard(request: Request):
    # Dummy data to test rendering (replace with calls to service.py/repo.py)
    sample_tasks = [
        {"id": "task-101", "domain": "example.com", "state": "Running"},
        {"id": "task-102", "domain": "python.org", "state": "Idle"},
    ]

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "message": "Crawler Control Panel",
            "status": "Online",
            "tasks": sample_tasks,
        },
    )


# 2. Existing / New JSON API Routes can live side-by-side:
@router.get("/status")
async def get_api_status():
    return {"status": "ok", "service": "crawler-control"}
