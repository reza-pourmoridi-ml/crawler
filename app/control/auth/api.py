import json
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import APIRouter, File, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.infra.config import settings
from app.infra.storage import write_json_atomic


router = APIRouter(prefix="/control/auth", tags=["Auth"])
templates = Jinja2Templates(
    directory=str(Path(__file__).resolve().parents[1] / "templates")
)


def _auth_path() -> Path:
    return Path(settings.auth_state_file)


def _validate_storage_state(data) -> dict:
    if not isinstance(data, dict):
        raise ValueError("فایل باید ساختار Playwright storage state داشته باشد.")
    if not isinstance(data.get("cookies"), list) or not isinstance(data.get("origins"), list):
        raise ValueError("کلیدهای cookies و origins باید آرایه باشند.")
    return data


def _render_page(
    request: Request,
    *,
    error: str | None = None,
    saved: bool = False,
    status_code: int = 200,
):
    path = _auth_path()
    exists = path.is_file()
    updated_at = None
    if exists:
        updated_at = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).astimezone(
            ZoneInfo("Asia/Tehran")
        )
    return templates.TemplateResponse(
        request=request,
        name="auth.html",
        context={
            "auth_exists": exists,
            "auth_updated_at": updated_at,
            "error": error,
            "saved": saved,
        },
        status_code=status_code,
    )


@router.get("/page", response_class=HTMLResponse)
def auth_page(request: Request, saved: int = 0):
    return _render_page(request, saved=saved == 1)


@router.post("/page", response_class=HTMLResponse)
async def upload_auth_page(
    request: Request,
    auth_file: UploadFile = File(...),
):
    try:
        data = _validate_storage_state(json.loads(await auth_file.read()))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return _render_page(
            request,
            error="فایل انتخاب‌شده JSON معتبر نیست.",
            status_code=422,
        )
    except ValueError as exc:
        return _render_page(request, error=str(exc), status_code=422)
    finally:
        await auth_file.close()

    write_json_atomic(_auth_path(), data)
    return RedirectResponse(url="/control/auth/page?saved=1", status_code=303)
