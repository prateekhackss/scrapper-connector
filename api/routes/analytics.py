"""
ConnectorOS Scout — Analytics API Routes
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from sqlalchemy import func
from fastapi import APIRouter, Query

from core.database import SessionLocal, LeadRow, CompanyRow, PipelineRunRow, ContactRow, APIUsageRow
from core.logger import get_logger

logger = get_logger("api.analytics")
router = APIRouter()


@router.get("/overview")
async def analytics_overview():
    """Dashboard overview stats."""
    db = SessionLocal()
    try:
        total_companies = db.query(CompanyRow).filter_by(status="active").count()
        total_leads = db.query(LeadRow).count()
        total_contacts = db.query(ContactRow).filter_by(is_current=True).count()
        verified = db.query(ContactRow).filter_by(is_current=True, is_verified=True).count()

        total_cost = db.query(func.sum(APIUsageRow.cost_usd)).scalar() or 0
        today_cost = (
            db.query(func.sum(APIUsageRow.cost_usd))
            .filter(APIUsageRow.created_at >= datetime.now(timezone.utc).replace(hour=0, minute=0, second=0))
            .scalar() or 0
        )

        return {
            "total_companies": total_companies,
            "total_leads": total_leads,
            "total_contacts": total_contacts,
            "verified_contacts": verified,
            "total_cost_usd": round(float(total_cost), 2),
            "today_cost_usd": round(float(today_cost), 2),
        }
    finally:
        db.close()


@router.get("/trends")
async def analytics_trends(days: int = Query(30, ge=7, le=90)):
    """Weekly trend data for charts."""
    db = SessionLocal()
    try:
        runs = (
            db.query(PipelineRunRow)
            .filter(PipelineRunRow.started_at >= datetime.now(timezone.utc) - timedelta(days=days))
            .order_by(PipelineRunRow.started_at)
            .all()
        )

        return [
            {
                "date": r.started_at.isoformat() if r.started_at else None,
                "companies_discovered": r.companies_discovered,
                "leads_generated": r.leads_generated,
                "leads_delivered": r.leads_delivered,
                "avg_hiring_score": r.avg_hiring_score,
                "avg_data_confidence": r.avg_data_confidence,
                "cost_usd": r.openai_cost_usd,
            }
            for r in runs
        ]
    finally:
        db.close()


@router.get("/distributions")
async def analytics_distributions():
    """Score distributions for histograms."""
    db = SessionLocal()
    try:
        leads = db.query(LeadRow.hiring_intensity, LeadRow.data_confidence).all()

        hiring_dist = [0] * 10  # 0-9, 10-19, ..., 90-100
        confidence_dist = [0] * 10

        for lead in leads:
            h_bucket = min(lead.hiring_intensity // 10, 9)
            c_bucket = min(lead.data_confidence // 10, 9)
            hiring_dist[h_bucket] += 1
            confidence_dist[c_bucket] += 1

        return {
            "hiring_intensity": {
                "labels": [f"{i*10}-{i*10+9}" for i in range(10)],
                "values": hiring_dist,
            },
            "data_confidence": {
                "labels": [f"{i*10}-{i*10+9}" for i in range(10)],
                "values": confidence_dist,
            },
        }
    finally:
        db.close()


@router.get("/industries")
async def analytics_industries():
    """Top industries breakdown."""
    db = SessionLocal()
    try:
        companies = db.query(CompanyRow.industry).filter(CompanyRow.industry.isnot(None)).all()
        counts = {}
        for (ind,) in companies:
            if ind:
                counts[ind] = counts.get(ind, 0) + 1

        sorted_items = sorted(counts.items(), key=lambda x: x[1], reverse=True)[:10]
        return {"industries": [{"name": k, "count": v} for k, v in sorted_items]}
    finally:
        db.close()


@router.get("/cost-breakdown")
async def analytics_cost_breakdown(days: int = Query(30, ge=1, le=90)):
    """Cost breakdown by stage."""
    db = SessionLocal()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        usage = (
            db.query(APIUsageRow.request_type, func.sum(APIUsageRow.cost_usd))
            .filter(APIUsageRow.created_at >= cutoff)
            .group_by(APIUsageRow.request_type)
            .all()
        )

        total = sum(cost or 0 for _, cost in usage)
        return {
            "stages": [
                {
                    "name": req_type or "unknown",
                    "cost_usd": round(float(cost or 0), 4),
                    "percentage": round(float(cost or 0) / total * 100, 1) if total > 0 else 0,
                }
                for req_type, cost in usage
            ],
            "total_usd": round(float(total), 2),
        }
    finally:
        db.close()
