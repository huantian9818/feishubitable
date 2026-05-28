from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.db import init_db

BASE_DIR = Path(__file__).resolve().parent


def create_app(*, init_database: bool = True) -> FastAPI:
    lifespan = None
    if init_database:

        @asynccontextmanager
        async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
            init_db()
            yield

    app = FastAPI(title="Feishu Bitable Monitor", lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

    from app.web.routes import monitors, settings

    app.include_router(settings.router)
    app.include_router(monitors.router)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app


app = create_app()
