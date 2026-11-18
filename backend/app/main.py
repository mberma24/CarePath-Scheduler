from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import blocks, care_paths, patients, resources, schedule
from app.config import settings
from app.db.models import Base
from app.db.session import engine


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    Base.metadata.create_all(engine)  # startup: create missing tables
    yield
    # shutdown: nothing to clean up yet


def create_app() -> FastAPI:
    app = FastAPI(title="Care Path Scheduler API", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(patients.router)
    app.include_router(resources.router)
    app.include_router(care_paths.router)
    app.include_router(blocks.router)
    app.include_router(schedule.router)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/config")
    def config() -> dict[str, int | str]:
        """Scheduling settings the frontend needs, so it never hardcodes them."""
        return {
            "slot_minutes": settings.slot_minutes,
            "schedule_horizon_days": settings.schedule_horizon_days,
            "clinic_timezone": settings.clinic_timezone,
            "clinic_open_hour": settings.clinic_open_hour,
            "clinic_close_hour": settings.clinic_close_hour,
        }

    return app


app = create_app()
