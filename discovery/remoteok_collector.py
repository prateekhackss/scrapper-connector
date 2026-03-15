"""
ConnectorOS Scout — RemoteOK JSON API Collector

Fetches remote job listings from RemoteOK's public JSON endpoint.
5-second delay between requests (being polite to their API).

Security:
  - No API key required (public endpoint)
  - All data validated through Pydantic before storage
"""

from __future__ import annotations

import asyncio
from urllib.parse import urlparse

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from core.models import CompanyBase, JobPosting
from core.logger import get_logger
from core.roles import classify_role_family, role_focus_matches, normalize_role_focus

logger = get_logger("discovery.remoteok")

REMOTEOK_API_URL = "https://remoteok.com/api"
REQUEST_DELAY_SECONDS = 5
_AGGREGATOR_HOSTS = {"remoteok.com", "www.remoteok.com"}


def _extract_domain(company: str, url: str | None) -> str:
    """Extract domain from the company URL, or guess from name."""
    if url:
        parsed = urlparse(url.strip())
        host = parsed.netloc.lower().strip()
        if host.startswith("www."):
            host = host[4:]
        if host and host not in _AGGREGATOR_HOSTS:
            return host.rstrip("/")

    # Fallback: guess from company name
    clean = company.lower().strip()
    for suffix in (" inc", " inc.", " ltd", " ltd.", " llc", " corp", " co."):
        if clean.endswith(suffix):
            clean = clean[: -len(suffix)].strip()
    return clean.replace(" ", "") + ".com"


def _parse_seniority(title: str) -> str:
    """Infer seniority from title keywords."""
    title_lower = title.lower()
    if any(kw in title_lower for kw in ("vp", "vice president", "director", "head of")):
        return "vp"
    if any(kw in title_lower for kw in ("lead", "principal", "staff", "architect")):
        return "lead"
    if any(kw in title_lower for kw in ("senior", "sr.", "sr ")):
        return "senior"
    if any(kw in title_lower for kw in ("junior", "jr.", "jr ", "entry", "intern")):
        return "junior"
    return "mid"


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=3, max=30),
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.HTTPStatusError)),
)
async def _fetch_remoteok() -> list[dict]:
    """Fetch the RemoteOK jobs JSON feed."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            REMOTEOK_API_URL,
            headers={"User-Agent": "ConnectorOS-Scout/1.0"},
        )
        resp.raise_for_status()
        data = resp.json()
        # First element is metadata, skip it
        return data[1:] if len(data) > 1 else []


async def collect_from_remoteok(
    max_results: int = 100,
    role_focus: str | None = "engineering",
) -> tuple[list[CompanyBase], list[JobPosting]]:
    """
    Fetch remote jobs from RemoteOK and return companies + postings.

    Args:
        max_results: Maximum number of listings to process.

    Returns:
        Tuple of (companies, job_postings).
    """
    logger.info("remoteok_fetch_start")

    try:
        jobs = await _fetch_remoteok()
    except Exception as e:
        logger.error("remoteok_fetch_error", error=str(e))
        return [], []

    companies_map: dict[str, CompanyBase] = {}
    all_postings: list[JobPosting] = []

    selected_focus = normalize_role_focus(role_focus)

    for job in jobs[:max_results]:
        company_name = job.get("company", "").strip()
        if not company_name:
            continue

        role_family = classify_role_family(job.get("position", ""))
        if not role_focus_matches(role_family, selected_focus):
            continue

        company_url = (
            job.get("company_url")
            or job.get("company_website")
            or job.get("apply_url")
            or job.get("apply_url_string")
            or ""
        )
        domain = _extract_domain(company_name, company_url)

        # Company
        if domain not in companies_map:
            companies_map[domain] = CompanyBase(
                company_name=company_name,
                company_domain=domain,
                headquarters="Remote",
                tech_stack=job.get("tags", []),
                discovery_sources=["remoteok"],
                discovery_source_urls=[job.get("url", "")],
            )

        # Job posting
        posting = JobPosting(
            company_domain=domain,
            job_title=job.get("position", "Unknown"),
            role_family=role_family,
            job_url=job.get("url"),
            location=job.get("location", "Remote"),
            remote_policy="remote",
            seniority=_parse_seniority(job.get("position", "")),
            tech_stack=job.get("tags", []),
            salary_range=None,
            source="remoteok",
            source_id=str(job.get("id", "")),
            posted_date=job.get("date"),
            evidence_urls=[job.get("url", "")],
        )
        all_postings.append(posting)

    logger.info("remoteok_fetch_complete", companies=len(companies_map), postings=len(all_postings))

    # Polite delay before returning (rate limiting ourselves)
    await asyncio.sleep(REQUEST_DELAY_SECONDS)

    return list(companies_map.values()), all_postings
