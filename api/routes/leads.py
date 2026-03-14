"""
ConnectorOS Scout — Leads API Routes

Endpoints for browsing, filtering, and managing leads.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func
from pydantic import BaseModel
from core.database import SessionLocal, LeadRow, CompanyRow, ContactRow, JobPostingRow
from core.logger import get_logger

logger = get_logger("api.leads")
router = APIRouter()


class LeadUpdateRequest(BaseModel):
    status: str | None = None
    notes: str | None = None
    qa_status: str | None = None


def _age_in_days(dt):
    if not dt:
        return None
    now = datetime.now(timezone.utc)
    current = dt if getattr(dt, "tzinfo", None) else dt.replace(tzinfo=timezone.utc)
    return max(0, int((now - current).total_seconds() // 86400))


@router.get("")
async def list_leads(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    min_hiring: int = Query(0, ge=0, le=100),
    min_confidence: int = Query(0, ge=0, le=100),
    priority_tier: str | None = None,
    hiring_label: str | None = None,
    status: str | None = None,
    search: str | None = None,
    buyer_ready_only: bool = False,
    qa_status: str | None = None,
):
    """List leads with filtering and pagination."""
    db = SessionLocal()
    try:
        latest_ids = (
            db.query(func.max(LeadRow.id).label("lead_id"))
            .group_by(LeadRow.company_id)
            .subquery()
        )

        query = (
            db.query(LeadRow, CompanyRow, ContactRow)
            .join(latest_ids, LeadRow.id == latest_ids.c.lead_id)
            .join(CompanyRow, LeadRow.company_id == CompanyRow.id)
            .outerjoin(ContactRow, LeadRow.contact_id == ContactRow.id)
        )

        if min_hiring > 0:
            query = query.filter(LeadRow.hiring_intensity >= min_hiring)
        if min_confidence > 0:
            query = query.filter(LeadRow.data_confidence >= min_confidence)
        if priority_tier:
            query = query.filter(LeadRow.priority_tier == priority_tier)
        if hiring_label:
            query = query.filter(LeadRow.hiring_label == hiring_label)
        if status:
            query = query.filter(LeadRow.status == status)
        else:
            query = query.filter(LeadRow.status != "archived")
        if search:
            query = query.filter(CompanyRow.company_name.ilike(f"%{search}%"))
        if buyer_ready_only:
            query = query.filter(LeadRow.buyer_ready == True)
        if qa_status:
            query = query.filter(LeadRow.qa_status == qa_status)

        total = query.count()
        offset = (page - 1) * per_page
        rows = (
            query
            .order_by(LeadRow.buyer_ready.desc(), LeadRow.hiring_intensity.desc(), LeadRow.data_confidence.desc())
            .offset(offset)
            .limit(per_page)
            .all()
        )

        company_ids = [company.id for _, company, _ in rows]
        postings_by_company: dict[int, list[JobPostingRow]] = {}
        if company_ids:
            postings = (
                db.query(JobPostingRow)
                .filter(JobPostingRow.company_id.in_(company_ids), JobPostingRow.is_active == True)
                .all()
            )
            for posting in postings:
                postings_by_company.setdefault(posting.company_id, []).append(posting)

        leads = []
        for lead, company, contact in rows:
            role_evidence_urls = []
            seen_urls = set()
            for posting in postings_by_company.get(company.id, [])[:5]:
                for url in ([posting.job_url] if posting.job_url else []) + json.loads(posting.evidence_urls or "[]"):
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        role_evidence_urls.append(url)
            leads.append({
                "id": lead.id,
                "company_name": company.company_name,
                "company_domain": company.company_domain,
                "website_url": company.website_url,
                "industry": company.industry,
                "headquarters": company.headquarters,
                "employee_count": company.employee_count,
                "tech_stack": json.loads(company.tech_stack or "[]"),
                "role_count": lead.role_count,
                "top_roles": json.loads(lead.top_roles or "[]"),
                "hiring_intensity": lead.hiring_intensity,
                "hiring_label": lead.hiring_label,
                "data_confidence": lead.data_confidence,
                "confidence_tier": lead.confidence_tier,
                "priority_tier": lead.priority_tier,
                "velocity_label": lead.velocity_label,
                "contact_name": contact.full_name if contact else None,
                "contact_title": contact.title if contact else None,
                "best_email": contact.best_email if contact else None,
                "linkedin_url": contact.linkedin_url if contact else None,
                "buyer_ready": lead.buyer_ready,
                "qa_status": lead.qa_status,
                "proof_summary": lead.proof_summary,
                "outreach_summary": lead.outreach_summary,
                "contact_proof_quality": contact.proof_quality if contact else None,
                "contact_source_urls": json.loads(contact.source_urls or "[]") if contact else [],
                "role_evidence_urls": role_evidence_urls,
                "last_company_seen_at": company.last_seen_at.isoformat() if company.last_seen_at else None,
                "freshness_days": _age_in_days(company.last_seen_at),
                "contact_verified_at": contact.verified_at.isoformat() if contact and contact.verified_at else None,
                "notes": lead.notes,
                "status": lead.status,
                "score_breakdown": json.loads(lead.score_breakdown or "{}"),
                "created_at": lead.created_at.isoformat() if lead.created_at else None,
            })

        return {
            "leads": leads,
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": (total + per_page - 1) // per_page,
        }

    finally:
        db.close()


@router.get("/stats")
async def lead_stats():
    """Get lead statistics for the dashboard."""
    db = SessionLocal()
    try:
        total = db.query(LeadRow).count()
        by_priority = {}
        for tier in ("PRIORITY", "REVIEW", "NURTURE", "ARCHIVE"):
            by_priority[tier] = db.query(LeadRow).filter_by(priority_tier=tier).count()

        by_label = {}
        for label in ("RED_HOT", "WARM", "COOL", "COLD"):
            by_label[label] = db.query(LeadRow).filter_by(hiring_label=label).count()

        by_confidence = {}
        for tier in ("VERIFIED", "LIKELY", "UNCERTAIN", "UNVERIFIED"):
            by_confidence[tier] = db.query(LeadRow).filter_by(confidence_tier=tier).count()

        from sqlalchemy import func
        avg_hiring = db.query(func.avg(LeadRow.hiring_intensity)).scalar() or 0
        avg_conf = db.query(func.avg(LeadRow.data_confidence)).scalar() or 0

        return {
            "total": total,
            "by_priority": by_priority,
            "by_hiring_label": by_label,
            "by_confidence": by_confidence,
            "avg_hiring_score": round(float(avg_hiring), 1),
            "avg_data_confidence": round(float(avg_conf), 1),
        }

    finally:
        db.close()


@router.get("/{lead_id}")
async def get_lead(lead_id: int):
    """Get a single lead with full details."""
    db = SessionLocal()
    try:
        lead = db.query(LeadRow).filter_by(id=lead_id).first()
        if not lead:
            raise HTTPException(status_code=404, detail="Lead not found")

        company = db.query(CompanyRow).filter_by(id=lead.company_id).first()
        contact = db.query(ContactRow).filter_by(id=lead.contact_id).first() if lead.contact_id else None
        postings = db.query(JobPostingRow).filter_by(company_id=lead.company_id, is_active=True).all()

        return {
            "id": lead.id,
            "company": {
                "name": company.company_name,
                "domain": company.company_domain,
                "website": company.website_url,
                "industry": company.industry,
                "headquarters": company.headquarters,
                "employee_count": company.employee_count,
                "tech_stack": json.loads(company.tech_stack or "[]"),
                "first_seen": company.first_seen_at.isoformat() if company.first_seen_at else None,
                "last_seen": company.last_seen_at.isoformat() if company.last_seen_at else None,
                "times_seen": company.times_seen,
                "sources": json.loads(company.discovery_sources or "[]"),
                "source_urls": json.loads(company.discovery_source_urls or "[]"),
            },
            "contact": {
                "name": contact.full_name,
                "title": contact.title,
                "email": contact.best_email,
                "linkedin": contact.linkedin_url,
                "emails": json.loads(contact.emails or "[]"),
                "source_urls": json.loads(contact.source_urls or "[]"),
                "found_on_date": contact.found_on_date,
                "proof_quality": contact.proof_quality,
                "generic_email_only": contact.generic_email_only,
                "confidence": contact.data_confidence,
                "tier": contact.confidence_tier,
                "verified": contact.is_verified,
                "verified_at": contact.verified_at.isoformat() if contact.verified_at else None,
                "verification": json.loads(contact.verification_data or "{}"),
            } if contact else None,
            "job_postings": [
                {
                    "title": posting.job_title,
                    "job_url": posting.job_url,
                    "location": posting.location,
                    "posted_date": posting.posted_date,
                    "source": posting.source,
                    "evidence_urls": json.loads(posting.evidence_urls or "[]"),
                }
                for posting in postings
            ],
            "scoring": {
                "hiring_intensity": lead.hiring_intensity,
                "hiring_label": lead.hiring_label,
                "data_confidence": lead.data_confidence,
                "confidence_tier": lead.confidence_tier,
                "priority_tier": lead.priority_tier,
                "velocity_label": lead.velocity_label,
                "role_count": lead.role_count,
                "top_roles": json.loads(lead.top_roles or "[]"),
                "breakdown": json.loads(lead.score_breakdown or "{}"),
                "buyer_ready": lead.buyer_ready,
                "qa_status": lead.qa_status,
                "proof_summary": lead.proof_summary,
                "outreach_summary": lead.outreach_summary,
                "freshness_days": _age_in_days(company.last_seen_at),
            },
            "notes": lead.notes,
            "status": lead.status,
        }
    finally:
        db.close()


@router.patch("/{lead_id}")
async def update_lead(lead_id: int, data: LeadUpdateRequest):
    """Update a lead's status or notes."""
    valid_statuses = {"new", "delivered", "rejected", "archived"}
    valid_qa_statuses = {"pending_review", "approved", "rejected", "needs_research"}
    if data.status and data.status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {valid_statuses}")
    if data.qa_status and data.qa_status not in valid_qa_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid qa_status. Must be one of: {valid_qa_statuses}")

    db = SessionLocal()
    try:
        lead = db.query(LeadRow).filter_by(id=lead_id).first()
        if not lead:
            raise HTTPException(status_code=404, detail="Lead not found")

        if data.status:
            lead.status = data.status
        if data.notes is not None:
            lead.notes = data.notes
        if data.qa_status:
            lead.qa_status = data.qa_status

        db.commit()
        return {"id": lead.id, "status": lead.status, "notes": lead.notes, "qa_status": lead.qa_status}
    finally:
        db.close()
