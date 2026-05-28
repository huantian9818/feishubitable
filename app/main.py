from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.db import SessionLocal, init_db

app = FastAPI(title="Feishu Bitable Monitor")

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def get_session():
    with SessionLocal() as session:
        yield session


init_db()
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

from app.web.routes import monitors, settings

app.include_router(settings.router)
app.include_router(monitors.router)


@app.get("/health")
def health():
    return {"status": "ok"}
