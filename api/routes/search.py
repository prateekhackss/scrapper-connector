"""
ConnectorOS Scout — Search API Routes

Manual search interface: company lookup, contact finder, market scan.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from core.database import SessionLocal, SearchHistoryRow
from core.logger import get_logger

logger = get_logger("api.search")
router = APIRouter()


class CompanySearchRequest(BaseModel):
    domain: str


class ContactSearchRequest(BaseModel):
    domain: str
    title: Optional[str] = None


class MarketScanRequest(BaseModel):
    market: str
    max_results: int = 20


@router.post("/company")
async def search_company(request: CompanySearchRequest):
    """Manual company lookup via OpenAI."""
    from enrichment.openai_enricher import enrich_company_contact
    from enrichment.email_generator import generate_emails
    from enrichment.fallback_emails import generate_fallback_emails

    try:
        contact = await enrich_company_contact(request.domain, request.domain)

        emails = []
        if contact.found and contact.first_name and contact.last_name:
            emails = await generate_emails(contact.first_name, contact.last_name, request.domain)
        else:
            emails = generate_fallback_emails(request.domain)

        result = {
            "domain": request.domain,
            "contact": contact.model_dump(),
            "emails": [e.model_dump() for e in emails],
        }

        # Save to search history
        db = SessionLocal()
        try:
            db.add(SearchHistoryRow(
                query_type="company_search",
                query_params=json.dumps({"domain": request.domain}),
                results_count=1 if contact.found else 0,
                results_data=json.dumps(result),
            ))
            db.commit()
        finally:
            db.close()

        return result

    except Exception as e:
        logger.error("search_company_error", domain=request.domain, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/contact")
async def search_contact(request: ContactSearchRequest):
    """Manual contact finder."""
    from enrichment.openai_enricher import enrich_company_contact
    from enrichment.email_generator import generate_emails

    try:
        contact = await enrich_company_contact(request.domain, request.domain)

        emails = []
        if contact.found and contact.first_name and contact.last_name:
            emails = await generate_emails(contact.first_name, contact.last_name, request.domain)

        result = {
            "domain": request.domain,
            "contact": contact.model_dump(),
            "emails": [e.model_dump() for e in emails],
        }

        db = SessionLocal()
        try:
            db.add(SearchHistoryRow(
                query_type="contact_search",
                query_params=json.dumps({"domain": request.domain, "title": request.title}),
                results_count=1 if contact.found else 0,
                results_data=json.dumps(result),
            ))
            db.commit()
        finally:
            db.close()

        return result

    except Exception as e:
        logger.error("search_contact_error", domain=request.domain, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/market")
async def search_market(request: MarketScanRequest):
    """Manual market scan via OpenAI."""
    from discovery.openai_discovery import collect_from_openai

    try:
        companies, postings = await collect_from_openai(request.market)

        result = {
            "market": request.market,
            "companies": [c.model_dump() for c in companies[:request.max_results]],
            "total_found": len(companies),
        }

        db = SessionLocal()
        try:
            db.add(SearchHistoryRow(
                query_type="market_scan",
                query_params=json.dumps({"market": request.market, "max_results": request.max_results}),
                results_count=len(companies),
                results_data=json.dumps(result),
            ))
            db.commit()
        finally:
            db.close()

        return result

    except Exception as e:
        logger.error("search_market_error", market=request.market, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history")
async def search_history(limit: int = 20):
    """Get recent search history."""
    db = SessionLocal()
    try:
        rows = (
            db.query(SearchHistoryRow)
            .order_by(SearchHistoryRow.id.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "id": r.id,
                "type": r.query_type,
                "params": json.loads(r.query_params or "{}"),
                "results_count": r.results_count,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]
    finally:
        db.close()
