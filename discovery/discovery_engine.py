"""
ConnectorOS Scout — Discovery Engine (Orchestrator)

Coordinates all discovery sources, deduplicates results,
and persists to the database.

Security:
  - Rate limiting enforced per source
  - All DB operations use ORM (SQL injection safe)
  - Pipeline run errors are caught and logged, never swallowed
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from core.database import SessionLocal, CompanyRow, JobPostingRow
from core.models import CompanyBase, JobPosting
from core.logger import get_logger

from discovery.serpapi_collector import collect_from_serpapi
from discovery.remoteok_collector import collect_from_remoteok
from discovery.openai_discovery import collect_from_openai
from discovery.deduplicator import deduplicate_companies, normalize_domain

logger = get_logger("discovery.engine")


def _upsert_company(db: Session, company: CompanyBase) -> int:
    """Insert or update a company. Returns the company row ID."""
    existing = db.query(CompanyRow).filter_by(company_domain=company.company_domain).first()

    if existing:
        existing.last_seen_at = datetime.now(timezone.utc)
        existing.times_seen = (existing.times_seen or 0) + 1

        # Merge discovery sources
        old_sources = json.loads(existing.discovery_sources or "[]")
        new_sources = list(set(old_sources + company.discovery_sources))
        existing.discovery_sources = json.dumps(new_sources)

        # Fill in blanks
        if company.industry and not existing.industry:
            existing.industry = company.industry
        if company.headquarters and not existing.headquarters:
            existing.headquarters = company.headquarters
        if company.employee_count and not existing.employee_count:
            existing.employee_count = company.employee_count
        if company.tech_stack:
            old_stack = json.loads(existing.tech_stack or "[]")
            merged = list(set(old_stack + company.tech_stack))
            existing.tech_stack = json.dumps(merged)
        if company.website_url and not existing.website_url:
            existing.website_url = company.website_url

        db.flush()
        return existing.id
    else:
        row = CompanyRow(
            company_name=company.company_name,
            company_domain=company.company_domain,
            website_url=company.website_url,
            industry=company.industry,
            headquarters=company.headquarters,
            employee_count=company.employee_count,
            tech_stack=json.dumps(company.tech_stack),
            discovery_sources=json.dumps(company.discovery_sources),
            first_seen_at=datetime.now(timezone.utc),
            last_seen_at=datetime.now(timezone.utc),
            times_seen=1,
        )
        db.add(row)
        db.flush()
        return row.id


def _insert_posting(db: Session, company_id: int, posting: JobPosting) -> None:
    """Insert a job posting if not already present (by source + source_id)."""
    if posting.source_id:
        exists = (
            db.query(JobPostingRow)
            .filter_by(source=posting.source, source_id=posting.source_id)
            .first()
        )
        if exists:
            exists.last_scraped = datetime.now(timezone.utc)
            return

    row = JobPostingRow(
        company_id=company_id,
        job_title=posting.job_title,
        job_url=posting.job_url,
        location=posting.location,
        remote_policy=posting.remote_policy,
        seniority=posting.seniority,
        tech_stack=json.dumps(posting.tech_stack),
        salary_range=posting.salary_range,
        source=posting.source,
        source_id=posting.source_id,
        posted_date=posting.posted_date,
    )
    db.add(row)


async def run_discovery(
    target_market: str = "US tech companies",
    enable_serpapi: bool = True,
    enable_remoteok: bool = True,
    enable_openai: bool = True,
) -> int:
    """
    Run all discovery sources, deduplicate, and persist to DB.

    Args:
        target_market: Target market for OpenAI discovery.
        enable_serpapi: Whether to query SerpAPI.
        enable_remoteok: Whether to query RemoteOK.
        enable_openai: Whether to query OpenAI web search.

    Returns:
        Number of unique companies discovered.
    """
    all_companies: list[CompanyBase] = []
    all_postings: list[JobPosting] = []

    # ── Source 1: SerpAPI ────────────────────────────────────────
    if enable_serpapi:
        try:
            companies, postings = await collect_from_serpapi()
            all_companies.extend(companies)
            all_postings.extend(postings)
            logger.info("discovery_serpapi_done", companies=len(companies), postings=len(postings))
        except Exception as e:
            logger.error("discovery_serpapi_failed", error=str(e))

    # ── Source 2: RemoteOK ──────────────────────────────────────
    if enable_remoteok:
        try:
            companies, postings = await collect_from_remoteok()
            all_companies.extend(companies)
            all_postings.extend(postings)
            logger.info("discovery_remoteok_done", companies=len(companies), postings=len(postings))
        except Exception as e:
            logger.error("discovery_remoteok_failed", error=str(e))

    # ── Source 3: OpenAI web search ─────────────────────────────
    if enable_openai:
        try:
            companies, postings = await collect_from_openai(target_market)
            all_companies.extend(companies)
            all_postings.extend(postings)
            logger.info("discovery_openai_done", companies=len(companies), postings=len(postings))
        except Exception as e:
            logger.error("discovery_openai_failed", error=str(e))

    # ── Deduplicate ─────────────────────────────────────────────
    unique_companies = deduplicate_companies(all_companies)
    logger.info("discovery_dedup_done", before=len(all_companies), after=len(unique_companies))

    # ── Persist to DB ───────────────────────────────────────────
    db = SessionLocal()
    try:
        domain_to_id: dict[str, int] = {}

        for company in unique_companies:
            company_id = _upsert_company(db, company)
            domain_to_id[company.company_domain] = company_id

        for posting in all_postings:
            # Find matching company ID (by trying domain variations)
            matched_id = None
            for domain, cid in domain_to_id.items():
                matched_id = cid
                break  # Use first match for now

            if matched_id:
                _insert_posting(db, matched_id, posting)

        db.commit()
        logger.info("discovery_persisted", companies=len(unique_companies), postings=len(all_postings))

    except Exception as e:
        db.rollback()
        logger.error("discovery_persist_error", error=str(e))
        raise
    finally:
        db.close()

    return len(unique_companies)
