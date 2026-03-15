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
from core.database import SessionLocal, PipelineRunRow, CompanyRow, ContactRow, JobPostingRow, LeadRow
from core.logger import get_logger
from core.sse import event_generator, publish_event
from pipeline.orchestrator import run_full_pipeline
from core.roles import get_role_focus_label

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


def _run_window(run: PipelineRunRow) -> tuple[datetime, datetime]:
    """Return a safe time window for reconstructing run activity."""
    started_at = _as_utc(run.started_at) or datetime.now(timezone.utc)
    ended_at = _as_utc(run.completed_at) or datetime.now(timezone.utc)
    if ended_at < started_at:
        ended_at = started_at
    return started_at, ended_at


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


@router.get("/runs/{run_id}/preview")
async def get_run_preview(run_id: int):
    """Return discovered companies and saved lead snapshots for a specific run."""
    db = SessionLocal()
    try:
        _reconcile_stale_serverless_runs(db)
        _reconcile_orphaned_runs(db)

        run = db.query(PipelineRunRow).filter_by(id=run_id).first()
        if not run:
            raise HTTPException(status_code=404, detail="Pipeline run not found")

        started_at, ended_at = _run_window(run)
        role_focus = run.target_role_family or "engineering"

        lead_rows = (
            db.query(LeadRow, CompanyRow, ContactRow)
            .join(CompanyRow, LeadRow.company_id == CompanyRow.id)
            .outerjoin(ContactRow, LeadRow.contact_id == ContactRow.id)
            .filter(LeadRow.pipeline_run_id == run_id)
            .order_by(LeadRow.hiring_intensity.desc(), LeadRow.data_confidence.desc(), LeadRow.id.desc())
            .all()
        )

        recent_postings = (
            db.query(JobPostingRow, CompanyRow)
            .join(CompanyRow, JobPostingRow.company_id == CompanyRow.id)
            .filter(
                JobPostingRow.is_active == True,
                JobPostingRow.last_scraped >= started_at,
                JobPostingRow.last_scraped <= ended_at,
            )
            .order_by(JobPostingRow.last_scraped.desc(), JobPostingRow.id.desc())
            .all()
        )

        discovered_map: dict[int, dict] = {}
        for posting, company in recent_postings:
            if role_focus != "all" and posting.role_family != role_focus:
                continue

            item = discovered_map.setdefault(company.id, {
                "company_id": company.id,
                "company_name": company.company_name,
                "company_domain": company.company_domain,
                "website_url": company.website_url,
                "industry": company.industry,
                "headquarters": company.headquarters,
                "times_seen": company.times_seen,
                "last_seen_at": company.last_seen_at.isoformat() if company.last_seen_at else None,
                "role_focus": role_focus,
                "role_count": 0,
                "top_roles": [],
                "sources": [],
                "source_urls": [],
            })

            item["role_count"] += 1
            if posting.job_title and posting.job_title not in item["top_roles"] and len(item["top_roles"]) < 5:
                item["top_roles"].append(posting.job_title)

            if posting.source and posting.source not in item["sources"]:
                item["sources"].append(posting.source)

            if posting.job_url and posting.job_url not in item["source_urls"] and len(item["source_urls"]) < 8:
                item["source_urls"].append(posting.job_url)

        current_contacts = {
            contact.company_id: contact
            for contact in db.query(ContactRow)
            .filter(ContactRow.company_id.in_(list(discovered_map.keys())), ContactRow.is_current == True)
            .all()
        } if discovered_map else {}

        for company_id, item in discovered_map.items():
            contact = current_contacts.get(company_id)
            item["contact_name"] = contact.full_name if contact else None
            item["contact_title"] = contact.title if contact else None
            item["best_email"] = contact.best_email if contact else None

        return {
            "run": {
                "id": run.id,
                "status": run.status,
                "target_role_family": role_focus,
                "target_role_label": get_role_focus_label(role_focus),
                "started_at": run.started_at.isoformat() if run.started_at else None,
                "completed_at": run.completed_at.isoformat() if run.completed_at else None,
                "companies_discovered": run.companies_discovered,
                "leads_generated": run.leads_generated,
            },
            "discovered_total": len(discovered_map),
            "leads_total": len(lead_rows),
            "discovered_companies": sorted(
                discovered_map.values(),
                key=lambda row: (-row["role_count"], row["company_name"].lower()),
            ),
            "leads": [
                {
                    "id": lead.id,
                    "company_name": company.company_name,
                    "company_domain": company.company_domain,
                    "role_focus": lead.role_focus,
                    "role_count": lead.role_count,
                    "top_roles": json.loads(lead.top_roles or "[]"),
                    "hiring_intensity": lead.hiring_intensity,
                    "hiring_label": lead.hiring_label,
                    "data_confidence": lead.data_confidence,
                    "confidence_tier": lead.confidence_tier,
                    "priority_tier": lead.priority_tier,
                    "contact_name": contact.full_name if contact else None,
                    "contact_title": contact.title if contact else None,
                    "buyer_ready": lead.buyer_ready,
                    "qa_status": lead.qa_status,
                    "proof_summary": lead.proof_summary,
                    "status": lead.status,
                    "created_at": lead.created_at.isoformat() if lead.created_at else None,
                }
                for lead, company, contact in lead_rows
            ],
        }
    finally:
        db.close()
