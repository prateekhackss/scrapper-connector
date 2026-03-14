"""
ConnectorOS Scout — FastAPI Application

Main entry point for the backend API.

Security:
  - CORS restricted to known origins (localhost dev + configurable production)
  - All routes require no auth for MVP but middleware logs all requests
  - Database initialized on startup
  - Scheduler started on startup
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from core.config import HOST, PORT, EXPORTS_DIR, IS_VERCEL, CORS_ALLOWED_ORIGINS
from core.database import init_db
from core.logger import setup_logging, get_logger
from core.sse import set_main_loop
from pipeline.scheduler import start_scheduler, stop_scheduler

from api.routes import pipeline, leads, agencies, search, analytics, notifications, settings as settings_routes

logger = get_logger("api")
app_state: dict[str, Any] = {
    "startup_ok": False,
    "startup_error": None,
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    # Startup
    setup_logging()
    logger.info("app_starting")
    try:
        init_db()
        logger.info("database_initialized")
        # Capture the running event loop so SSE can deliver events thread-safely
        set_main_loop(asyncio.get_event_loop())
        if not IS_VERCEL:
            start_scheduler()
            logger.info("scheduler_started")
        else:
            logger.info("scheduler_skipped_serverless")
        app_state["startup_ok"] = True
        app_state["startup_error"] = None
    except Exception as exc:
        app_state["startup_ok"] = False
        app_state["startup_error"] = str(exc)
        logger.exception("app_startup_failed", error=str(exc))
    yield
    # Shutdown
    if app_state["startup_ok"] and not IS_VERCEL:
        stop_scheduler()
    logger.info("app_shutdown")


app = FastAPI(
    title="ConnectorOS Scout API",
    description="Lead generation pipeline for tech recruiting agencies",
    version="2.0.0",
    lifespan=lifespan,
)

# ── CORS (restrict to known origins) ────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["*"],
)

# ── Mount exports directory for file downloads ──────────────────
app.mount("/exports", StaticFiles(directory=str(EXPORTS_DIR)), name="exports")

# ── Register routers ────────────────────────────────────────────
app.include_router(pipeline.router, prefix="/api/pipeline", tags=["Pipeline"])
app.include_router(leads.router, prefix="/api/leads", tags=["Leads"])
app.include_router(agencies.router, prefix="/api/agencies", tags=["Agencies"])
app.include_router(search.router, prefix="/api/search", tags=["Search"])
app.include_router(analytics.router, prefix="/api/analytics", tags=["Analytics"])
app.include_router(notifications.router, prefix="/api/notifications", tags=["Notifications"])
app.include_router(settings_routes.router, prefix="/api/settings", tags=["Settings"])


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy" if app_state["startup_ok"] else "degraded",
        "version": "2.0.0",
        "startup_ok": app_state["startup_ok"],
        "startup_error": app_state["startup_error"],
    }
