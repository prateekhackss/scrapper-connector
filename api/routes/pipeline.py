"""
ConnectorOS Scout — Pipeline API Routes

Endpoints for starting, monitoring, and viewing pipeline runs.
"""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from core.database import SessionLocal, PipelineRunRow
from core.logger import get_logger
from core.sse import event_generator, publish_event
from pipeline.orchestrator import run_full_pipeline

logger = get_logger("api.pipeline")
router = APIRouter()

_pipeline_running = False


class StartPipelineRequest(BaseModel):
    target_market: str | None = None


@router.post("/start")
async def start_pipeline(
    payload: StartPipelineRequest | None = None,
    target_market: str | None = Query(default=None),
):
    """Start a full pipeline run in the background."""
    global _pipeline_running

    if _pipeline_running:
        raise HTTPException(status_code=409, detail="Pipeline is already running.")

    resolved_market = (payload.target_market if payload else None) or target_market

    _pipeline_running = True

    async def _run():
        global _pipeline_running
        try:
            await run_full_pipeline(resolved_market)
        except Exception as exc:
            logger.exception("pipeline_background_task_failed", error=str(exc))
            await publish_event("system", f"Pipeline failed to start: {str(exc)}", level="error")
        finally:
            _pipeline_running = False

    # Run on the SAME event loop as FastAPI so SSE queues are accessible
    asyncio.ensure_future(_run())

    return {"status": "started", "message": "Pipeline started in background."}


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
        latest = db.query(PipelineRunRow).order_by(PipelineRunRow.id.desc()).first()
        if not latest:
            return {"running": _pipeline_running, "last_run": None}

        return {
            "running": _pipeline_running,
            "last_run": {
                "id": latest.id,
                "status": latest.status,
                "run_type": latest.run_type,
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
