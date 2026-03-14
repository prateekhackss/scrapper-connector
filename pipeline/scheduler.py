"""
ConnectorOS Scout — Task Scheduler (APScheduler)

Manages automated pipeline runs, health checks, and data cleanup.

Security:
  - Scheduler runs in background thread (non-blocking)
  - No shell commands — all jobs are Python functions
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from core.database import SessionLocal, get_setting, JobPostingRow, LeadRow, APIUsageRow, NotificationRow, SearchHistoryRow
from core.logger import get_logger

logger = get_logger("pipeline.scheduler")

_scheduler: BackgroundScheduler | None = None


def _run_pipeline_sync():
    """Wrapper to run async pipeline in sync context."""
    from pipeline.orchestrator import run_full_pipeline
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(run_full_pipeline())
        logger.info("scheduled_pipeline_complete", result=result)
    except Exception as e:
        logger.error("scheduled_pipeline_error", error=str(e))
    finally:
        loop.close()


def _run_data_cleanup():
    """Weekly data cleanup job."""
    retention_days = int(get_setting("data_retention_days", "180"))
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)

    db = SessionLocal()
    try:
        # Archive old leads
        db.query(LeadRow).filter(
            LeadRow.created_at < cutoff,
            LeadRow.status == "new",
        ).update({"status": "archived"})

        # Delete old API usage logs
        db.query(APIUsageRow).filter(APIUsageRow.created_at < cutoff).delete()

        # Delete dismissed notifications
        db.query(NotificationRow).filter(
            NotificationRow.created_at < cutoff,
            NotificationRow.is_dismissed == True,
        ).delete()

        # Delete old search history
        db.query(SearchHistoryRow).filter(SearchHistoryRow.created_at < cutoff).delete()

        # Mark stale job postings as inactive
        stale_cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        db.query(JobPostingRow).filter(
            JobPostingRow.last_scraped < stale_cutoff,
        ).update({"is_active": False})

        db.commit()
        logger.info("data_cleanup_complete", retention_days=retention_days)
    except Exception as e:
        db.rollback()
        logger.error("data_cleanup_error", error=str(e))
    finally:
        db.close()


def start_scheduler() -> BackgroundScheduler:
    """Initialize and start the background scheduler."""
    global _scheduler

    if _scheduler and _scheduler.running:
        logger.info("scheduler_already_running")
        return _scheduler

    _scheduler = BackgroundScheduler()

    # Main pipeline — weekly (default: Monday 6 AM)
    cron_expr = get_setting("pipeline_schedule", "0 6 * * 1")
    try:
        _scheduler.add_job(
            _run_pipeline_sync,
            CronTrigger.from_crontab(cron_expr),
            id="main_pipeline",
            name="Weekly Pipeline Run",
            replace_existing=True,
        )
    except Exception as e:
        logger.error("scheduler_pipeline_job_error", error=str(e))

    # Weekly cleanup — Sunday 3 AM
    _scheduler.add_job(
        _run_data_cleanup,
        CronTrigger(day_of_week="sun", hour=3),
        id="cleanup",
        name="Weekly Data Cleanup",
        replace_existing=True,
    )

    _scheduler.start()
    logger.info("scheduler_started")

    return _scheduler


def stop_scheduler() -> None:
    """Stop the background scheduler."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("scheduler_stopped")
