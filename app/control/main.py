from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from app.control.api import router as control_router

app = FastAPI(title="Crawler Application")

# Mount static files if needed
STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Include the control router
app.include_router(control_router)

@app.get("/")
def root():
    return {"message": "Crawler Root API"}
