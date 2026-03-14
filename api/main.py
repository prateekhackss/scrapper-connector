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

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from core.config import HOST, PORT, EXPORTS_DIR
from core.database import init_db
from core.logger import setup_logging, get_logger
from core.sse import set_main_loop
from pipeline.scheduler import start_scheduler, stop_scheduler

from api.routes import pipeline, leads, agencies, search, analytics, notifications, settings as settings_routes

logger = get_logger("api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    # Startup
    setup_logging()
    logger.info("app_starting")
    init_db()
    logger.info("database_initialized")
    # Capture the running event loop so SSE can deliver events thread-safely
    set_main_loop(asyncio.get_event_loop())
    start_scheduler()
    logger.info("scheduler_started")
    yield
    # Shutdown
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
    allow_origins=[
        "http://localhost:5173",      # Vite dev server
        "http://localhost:3000",      # Alternative dev port
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ],
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
    return {"status": "healthy", "version": "2.0.0"}
