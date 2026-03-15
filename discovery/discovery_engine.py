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
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from core.database import SessionLocal, CompanyRow, JobPostingRow, get_setting
from core.models import CompanyBase, JobPosting
from core.logger import get_logger
from core.roles import normalize_role_focus

from discovery.serpapi_collector import collect_from_serpapi
from discovery.remoteok_collector import collect_from_remoteok
from discovery.openai_discovery import collect_from_openai
from discovery.deduplicator import deduplicate_companies, normalize_domain

logger = get_logger("discovery.engine")

_AGGREGATOR_DOMAINS = {"remoteok.com", "wellfound.com", "angel.co", "greenhouse.io", "lever.co"}


def _looks_like_aggregator_domain(domain: str | None) -> bool:
    """Return True when the stored company domain is clearly an aggregator host."""
    if not domain:
        return False
    clean = normalize_domain(domain)
    return any(clean == agg or clean.endswith(f".{agg}") for agg in _AGGREGATOR_DOMAINS)


def _upsert_company(db: Session, company: CompanyBase) -> int:
    """Insert or update a company. Returns the company row ID."""
    existing = db.query(CompanyRow).filter_by(company_domain=company.company_domain).first()
    if not existing:
        # Repair old rows created with aggregator domains by matching on company name.
        name_match = db.query(CompanyRow).filter_by(company_name=company.company_name).first()
        if name_match and _looks_like_aggregator_domain(name_match.company_domain):
            name_match.company_domain = company.company_domain
            name_match.website_url = company.website_url or name_match.website_url
            existing = name_match

    if existing:
        existing.last_seen_at = datetime.now(timezone.utc)
        existing.times_seen = (existing.times_seen or 0) + 1

        # Merge discovery sources
        old_sources = json.loads(existing.discovery_sources or "[]")
        new_sources = list(set(old_sources + company.discovery_sources))
        existing.discovery_sources = json.dumps(new_sources)

        old_source_urls = json.loads(existing.discovery_source_urls or "[]")
        merged_source_urls = sorted({
            url for url in old_source_urls + company.discovery_source_urls
            if isinstance(url, str) and url.strip()
        })
        existing.discovery_source_urls = json.dumps(merged_source_urls)

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
            discovery_source_urls=json.dumps([
                url for url in company.discovery_source_urls
                if isinstance(url, str) and url.strip()
            ]),
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
            if posting.role_family and not exists.role_family:
                exists.role_family = posting.role_family
            return
    else:
        exists = (
            db.query(JobPostingRow)
            .filter_by(
                company_id=company_id,
                source=posting.source,
                job_title=posting.job_title,
                job_url=posting.job_url,
            )
            .first()
        )
        if exists:
            exists.last_scraped = datetime.now(timezone.utc)
            if posting.role_family and not exists.role_family:
                exists.role_family = posting.role_family
            return

    row = JobPostingRow(
        company_id=company_id,
        job_title=posting.job_title,
        role_family=posting.role_family,
        job_url=posting.job_url,
        location=posting.location,
        remote_policy=posting.remote_policy,
        seniority=posting.seniority,
        tech_stack=json.dumps(posting.tech_stack),
        salary_range=posting.salary_range,
        source=posting.source,
        source_id=posting.source_id,
        posted_date=posting.posted_date,
        evidence_urls=json.dumps([
            url for url in posting.evidence_urls
            if isinstance(url, str) and url.strip()
        ]),
    )
    db.add(row)


def _infer_posting_domain(posting: JobPosting) -> str | None:
    """Match a posting back to its company domain as reliably as possible."""
    if posting.company_domain:
        return normalize_domain(posting.company_domain)

    if posting.job_url:
        parsed = urlparse(posting.job_url)
        if parsed.netloc:
            return normalize_domain(parsed.netloc)

    for url in posting.evidence_urls:
        parsed = urlparse(url)
        if parsed.netloc:
            return normalize_domain(parsed.netloc)

    return None


def _has_recent_cached_openai_postings(db: Session, role_focus: str) -> bool:
    """Reuse recent role-specific OpenAI discovery for one week to save tokens."""
    if role_focus == "all":
        return False

    cache_days = int(get_setting("openai_discovery_cache_days", "7"))
    min_postings = int(get_setting("openai_discovery_cache_min_postings", "15"))
    cutoff = datetime.now(timezone.utc) - timedelta(days=cache_days)
    count = (
        db.query(JobPostingRow)
        .filter(
            JobPostingRow.source == "openai",
            JobPostingRow.role_family == role_focus,
            JobPostingRow.last_scraped >= cutoff,
            JobPostingRow.is_active == True,
        )
        .count()
    )
    return count >= min_postings


async def run_discovery(
    target_market: str = "US tech companies",
    role_focus: str | None = "engineering",
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
    selected_focus = normalize_role_focus(role_focus)
    all_companies: list[CompanyBase] = []
    all_postings: list[JobPosting] = []

    # ── Source 1: SerpAPI ────────────────────────────────────────
    if enable_serpapi:
        try:
            companies, postings = await collect_from_serpapi(role_focus=selected_focus)
            all_companies.extend(companies)
            all_postings.extend(postings)
            logger.info("discovery_serpapi_done", companies=len(companies), postings=len(postings))
        except Exception as e:
            logger.error("discovery_serpapi_failed", error=str(e))

    # ── Source 2: RemoteOK ──────────────────────────────────────
    if enable_remoteok:
        try:
            companies, postings = await collect_from_remoteok(role_focus=selected_focus)
            all_companies.extend(companies)
            all_postings.extend(postings)
            logger.info("discovery_remoteok_done", companies=len(companies), postings=len(postings))
        except Exception as e:
            logger.error("discovery_remoteok_failed", error=str(e))

    # ── Source 3: OpenAI web search ─────────────────────────────
    if enable_openai:
        try:
            db = SessionLocal()
            try:
                use_cache = _has_recent_cached_openai_postings(db, selected_focus)
            finally:
                db.close()

            if use_cache:
                logger.info("discovery_openai_cache_hit", role_focus=selected_focus)
            else:
                companies, postings = await collect_from_openai(target_market, role_focus=selected_focus)
                all_companies.extend(companies)
                all_postings.extend(postings)
                logger.info(
                    "discovery_openai_done",
                    companies=len(companies),
                    postings=len(postings),
                    role_focus=selected_focus,
                )
        except Exception as e:
            logger.error("discovery_openai_failed", error=str(e))

    # ── Deduplicate ─────────────────────────────────────────────
    unique_companies = deduplicate_companies(all_companies)

    # Only keep companies that have at least one posting we can map back.
    posting_domains = {
        posting_domain
        for posting in all_postings
        for posting_domain in [_infer_posting_domain(posting)]
        if posting_domain
    }
    unique_companies = [
        company for company in unique_companies
        if normalize_domain(company.company_domain) in posting_domains
    ]
    logger.info("discovery_dedup_done", before=len(all_companies), after=len(unique_companies))

    # ── Persist to DB ───────────────────────────────────────────
    db = SessionLocal()
    try:
        domain_to_id: dict[str, int] = {}

        for company in unique_companies:
            company_id = _upsert_company(db, company)
            domain_to_id[company.company_domain] = company_id

        for posting in all_postings:
            matched_id = None
            posting_domain = _infer_posting_domain(posting)
            if posting_domain:
                matched_id = domain_to_id.get(posting_domain)

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
