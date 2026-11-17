from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import blocks, kpasses, patients, resources, schedule
from app.config import settings
from app.db.models import Base
from app.db.session import engine


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    Base.metadata.create_all(engine)  # startup: create missing tables
    yield
    # shutdown: nothing to clean up yet


def create_app() -> FastAPI:
    app = FastAPI(title="KPass Scheduler API", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(patients.router)
    app.include_router(resources.router)
    app.include_router(kpasses.router)
    app.include_router(blocks.router)
    app.include_router(schedule.router)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
