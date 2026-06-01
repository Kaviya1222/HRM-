from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.router import api_router
from app.core.config import ROOT_DIR, settings
from app.db.base import Base
from app.db.database import (
    ensure_attendance_runtime_schema,
    ensure_leave_runtime_schema,
    ensure_notification_runtime_schema,
    ensure_payroll_runtime_schema,
    ensure_tracker_runtime_schema,
)
from app.db.session import SessionLocal, engine
from app.services.bootstrap_service import bootstrap_reference_data


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    ensure_attendance_runtime_schema(engine)
    ensure_leave_runtime_schema(engine)
    ensure_notification_runtime_schema(engine)
    ensure_payroll_runtime_schema(engine)
    ensure_tracker_runtime_schema(engine)
    if settings.auto_bootstrap:
        with SessionLocal() as db:
            bootstrap_reference_data(db)
    yield


app = FastAPI(title=settings.app_name, debug=settings.debug, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

media_root = ROOT_DIR / "backend" / "storage"
media_root.mkdir(parents=True, exist_ok=True)
app.include_router(api_router, prefix=settings.api_v1_prefix)
app.mount("/media", StaticFiles(directory=media_root), name="media")


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}
