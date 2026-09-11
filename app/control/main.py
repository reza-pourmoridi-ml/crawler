from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.control.api import (
    router as control_router,
)

from app.control.websites.api import (
    router as websites_router,
)

from app.control.flight_paths.api import (
    router as flight_paths_router,
)

from app.control.search_box.api import (
    router as search_box_router,
)


app = FastAPI(
    title="Crawler Application"
)


STATIC_DIR = (
    Path(__file__).resolve().parent
    / "static"
)

if STATIC_DIR.is_dir():

    app.mount(
        "/static",
        StaticFiles(
            directory=str(STATIC_DIR)
        ),
        name="static",
    )


app.include_router(
    control_router
)

app.include_router(
    websites_router
)

app.include_router(
    flight_paths_router
)

app.include_router(
    search_box_router
)


@app.get("/")
def root():

    return {
        "message":
            "Crawler Root API"
    }