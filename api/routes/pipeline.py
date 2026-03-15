"""
ConnectorOS Scout — Pipeline API Routes

Endpoints for starting, monitoring, and viewing pipeline runs.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from core.config import IS_VERCEL
from core.database import SessionLocal, PipelineRunRow
from core.logger import get_logger
from core.sse import event_generator, publish_event
from pipeline.orchestrator import run_full_pipeline

logger = get_logger("api.pipeline")
router = APIRouter()

_pipeline_running = False
_pipeline_task: asyncio.Task | None = None
_VERCEL_STALE_RUN_TIMEOUT = timedelta(minutes=10)


class StartPipelineRequest(BaseModel):
    target_market: str | None = None
    role_focus: str | None = None


def _as_utc(dt: datetime | None) -> datetime | None:
    """Normalize timestamps for safe comparisons."""
    if dt is None:
        return None
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _reconcile_stale_serverless_runs(db) -> None:
    """
    Mark hanging `running` rows as failed on Vercel.

    Background tasks created inside a serverless request are not durable. If a
    row has been left in `running` for several minutes, it is more honest to
    mark it failed than to show it as actively executing forever.
    """
    if not IS_VERCEL:
        return

    now = datetime.now(timezone.utc)
    cutoff = now - _VERCEL_STALE_RUN_TIMEOUT
    stale_runs = (
        db.query(PipelineRunRow)
        .filter(PipelineRunRow.status == "running")
        .all()
    )

    mutated = False
    for run in stale_runs:
        started_at = _as_utc(run.started_at)
        if started_at is None or started_at > cutoff:
            continue

        existing_errors = []
        try:
            existing_errors = json.loads(run.errors or "[]")
        except Exception:
            existing_errors = []

        timeout_message = (
            "Run was marked failed because Vercel serverless cannot keep long-running "
            "background pipeline jobs alive. Run the pipeline locally or on a persistent worker."
        )
        if timeout_message not in existing_errors:
            existing_errors.append(timeout_message)

        run.status = "failed"
        run.completed_at = now
        run.duration_seconds = max(0.0, (now - started_at).total_seconds())
        run.errors = json.dumps(existing_errors)
        run.error_count = len(existing_errors)
        mutated = True

    if mutated:
        db.commit()


def _reconcile_orphaned_runs(db) -> None:
    """
    Mark running rows as failed when the current process has no active task.

    This handles crashes, restarts, or deploys that leave DB rows stuck in
    `running` forever even though no in-memory pipeline task survived.
    """
    if _pipeline_running and _pipeline_task is not None and not _pipeline_task.done():
        return

    orphaned_runs = db.query(PipelineRunRow).filter(PipelineRunRow.status == "running").all()
    if not orphaned_runs:
        return

    now = datetime.now(timezone.utc)
    mutated = False
    for run in orphaned_runs:
        started_at = _as_utc(run.started_at) or now
        existing_errors = []
        try:
            existing_errors = json.loads(run.errors or "[]")
        except Exception:
            existing_errors = []

        message = (
            "Run was marked failed because the backend no longer has an active pipeline task. "
            "This usually means the worker restarted or the process crashed mid-run."
        )
        if message not in existing_errors:
            existing_errors.append(message)

        run.status = "failed"
        run.completed_at = now
        run.duration_seconds = max(0.0, (now - started_at).total_seconds())
        run.errors = json.dumps(existing_errors)
        run.error_count = len(existing_errors)
        mutated = True

    if mutated:
        db.commit()


@router.post("/start")
async def start_pipeline(
    payload: StartPipelineRequest | None = None,
    target_market: str | None = Query(default=None),
):
    """Start a full pipeline run in the background."""
    global _pipeline_running, _pipeline_task

    if IS_VERCEL:
        raise HTTPException(
            status_code=409,
            detail=(
                "Manual pipeline runs are disabled on Vercel serverless because long-running "
                "background jobs do not complete reliably there. Run the backend locally or "
                "move it to a persistent worker host like Render, Railway, or Fly.io."
            ),
        )

    if _pipeline_running:
        raise HTTPException(status_code=409, detail="Pipeline is already running.")

    resolved_market = (payload.target_market if payload else None) or target_market
    resolved_role_focus = payload.role_focus if payload else None

    _pipeline_running = True

    async def _run():
        global _pipeline_running, _pipeline_task
        try:
            await run_full_pipeline(resolved_market, resolved_role_focus)
        except Exception as exc:
            logger.exception("pipeline_background_task_failed", error=str(exc))
            await publish_event("system", f"Pipeline failed to start: {str(exc)}", level="error")
        finally:
            _pipeline_running = False
            _pipeline_task = None

    # Run on the SAME event loop as FastAPI so SSE queues are accessible
    _pipeline_task = asyncio.create_task(_run())

    return {
        "status": "started",
        "message": "Pipeline started in background.",
        "role_focus": resolved_role_focus or "engineering",
    }


@router.post("/stop")
async def stop_pipeline():
    """Stop the currently running pipeline task."""
    global _pipeline_task

    if not _pipeline_running or _pipeline_task is None or _pipeline_task.done():
        raise HTTPException(status_code=409, detail="No pipeline is currently running.")

    _pipeline_task.cancel()
    await publish_event("system", "Stop requested. Waiting for pipeline to halt...", level="warning")
    return {"status": "stopping", "message": "Pipeline stop requested."}


@router.get("/stream")
async def stream_pipeline_logs():
    """Stream real-time SSE logs to the client."""
    return StreamingResponse(event_generator(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no"
    })


@router.get("/status")
async def pipeline_status():
    """Get current pipeline status."""
    db = SessionLocal()
    try:
        _reconcile_stale_serverless_runs(db)
        _reconcile_orphaned_runs(db)
        latest = db.query(PipelineRunRow).order_by(PipelineRunRow.id.desc()).first()
        if not latest:
            return {
                "running": _pipeline_running,
                "can_stop": _pipeline_running and _pipeline_task is not None and not _pipeline_task.done(),
                "supports_background_jobs": not IS_VERCEL,
                "deployment_mode": "serverless" if IS_VERCEL else "persistent",
                "warning": (
                    "Manual pipeline runs are disabled on Vercel serverless. Use a persistent worker host or run locally."
                    if IS_VERCEL else None
                ),
                "last_run": None,
            }

        return {
            "running": _pipeline_running,
            "can_stop": _pipeline_running and _pipeline_task is not None and not _pipeline_task.done(),
            "supports_background_jobs": not IS_VERCEL,
            "deployment_mode": "serverless" if IS_VERCEL else "persistent",
            "warning": (
                "Manual pipeline runs are disabled on Vercel serverless. Use a persistent worker host or run locally."
                if IS_VERCEL else None
            ),
            "last_run": {
                "id": latest.id,
                "status": latest.status,
                "run_type": latest.run_type,
                "target_role_family": latest.target_role_family,
                "started_at": latest.started_at.isoformat() if latest.started_at else None,
                "completed_at": latest.completed_at.isoformat() if latest.completed_at else None,
                "duration_seconds": latest.duration_seconds,
                "companies_discovered": latest.companies_discovered,
                "companies_enriched": latest.companies_enriched,
                "companies_verified": latest.companies_verified,
                "leads_generated": latest.leads_generated,
                "leads_delivered": latest.leads_delivered,
                "openai_cost_usd": latest.openai_cost_usd,
                "errors": json.loads(latest.errors or "[]"),
                "error_count": latest.error_count,
            },
        }
    finally:
        db.close()


@router.get("/runs")
async def list_pipeline_runs(limit: int = 20):
    """List recent pipeline runs."""
    db = SessionLocal()
    try:
        _reconcile_stale_serverless_runs(db)
        _reconcile_orphaned_runs(db)
        runs = (
            db.query(PipelineRunRow)
            .order_by(PipelineRunRow.id.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "id": r.id,
                "run_type": r.run_type,
                "status": r.status,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "target_role_family": r.target_role_family,
                "completed_at": r.completed_at.isoformat() if r.completed_at else None,
                "duration_seconds": r.duration_seconds,
                "companies_discovered": r.companies_discovered,
                "leads_generated": r.leads_generated,
                "leads_delivered": r.leads_delivered,
                "openai_cost_usd": r.openai_cost_usd,
                "error_count": r.error_count,
            }
            for r in runs
        ]
    finally:
        db.close()
