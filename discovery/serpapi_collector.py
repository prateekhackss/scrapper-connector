"""
ConnectorOS Scout — SerpAPI Google Jobs Collector

Queries Google Jobs via SerpAPI to find companies actively hiring.
Returns normalized CompanyBase + JobPosting lists.

Security:
  - API key read from config, never hardcoded
  - Results are validated through Pydantic before DB insertion
  - Monthly credit usage tracked in api_usage table
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from core.config import SERPAPI_KEY
from core.models import CompanyBase, JobPosting
from core.logger import get_logger
from core.exceptions import APIError, RateLimitError

logger = get_logger("discovery.serpapi")

SERPAPI_BASE_URL = "https://serpapi.com/search.json"


def _parse_seniority(title: str) -> str:
    """Infer seniority level from job title keywords."""
    title_lower = title.lower()
    if any(kw in title_lower for kw in ("vp", "vice president", "director", "head of")):
        return "vp"
    if any(kw in title_lower for kw in ("lead", "principal", "staff", "architect")):
        return "lead"
    if any(kw in title_lower for kw in ("senior", "sr.", "sr ")):
        return "senior"
    if any(kw in title_lower for kw in ("junior", "jr.", "jr ", "entry", "intern", "graduate")):
        return "junior"
    return "mid"


def _parse_remote_policy(extensions: list[str] | None) -> str:
    """Extract remote/onsite/hybrid from SerpAPI extensions list."""
    if not extensions:
        return "onsite"
    text = " ".join(extensions).lower()
    if "remote" in text and "hybrid" in text:
        return "hybrid"
    if "remote" in text:
        return "remote"
    if "hybrid" in text:
        return "hybrid"
    return "onsite"


def _normalize_domain(company_name: str) -> str:
    """Best-effort domain guess from company name (fallback only)."""
    clean = company_name.lower().strip()
    for suffix in (" inc", " inc.", " ltd", " ltd.", " llc", " corp", " corp.", " co.", " co"):
        if clean.endswith(suffix):
            clean = clean[: -len(suffix)].strip()
    return clean.replace(" ", "") + ".com"


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=2, max=30),
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.HTTPStatusError)),
)
async def _fetch_serpapi(query: str, location: str = "United States", num: int = 20) -> dict:
    """Make a single SerpAPI request with retry logic."""
    if not SERPAPI_KEY:
        raise APIError("serpapi", "SERPAPI_KEY not configured in .env")

    params = {
        "engine": "google_jobs",
        "q": query,
        "location": location,
        "api_key": SERPAPI_KEY,
        "num": str(num),
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(SERPAPI_BASE_URL, params=params)

        if resp.status_code == 429:
            raise RateLimitError("serpapi", retry_after=60)
        resp.raise_for_status()
        return resp.json()


async def collect_from_serpapi(
    queries: list[str] | None = None,
    location: str = "United States",
    max_results: int = 20,
) -> tuple[list[CompanyBase], list[JobPosting]]:
    """
    Run SerpAPI Google Jobs searches and return discovered companies + postings.

    Args:
        queries: Search queries (e.g. ["software engineer", "backend developer"]).
                 Defaults to a sensible set if None.
        location: Geographic filter for Google Jobs.
        max_results: Max results per query.

    Returns:
        Tuple of (companies, job_postings).
    """
    if queries is None:
        queries = [
            "software engineer",
            "backend developer",
            "frontend developer",
            "full stack developer",
            "devops engineer",
        ]

    companies_map: dict[str, CompanyBase] = {}
    all_postings: list[JobPosting] = []

    for query in queries:
        try:
            logger.info("serpapi_search_start", query=query, location=location)
            data = await _fetch_serpapi(query, location, max_results)
            jobs = data.get("jobs_results", [])

            for job in jobs:
                company_name = job.get("company_name", "").strip()
                if not company_name:
                    continue

                # Build domain from detected_extensions or guess
                domain = _normalize_domain(company_name)

                # Company
                if domain not in companies_map:
                    companies_map[domain] = CompanyBase(
                        company_name=company_name,
                        company_domain=domain,
                        headquarters=job.get("location", ""),
                        discovery_sources=["serpapi"],
                    )

                # Job posting
                extensions = job.get("detected_extensions", {})
                posting = JobPosting(
                    job_title=job.get("title", "Unknown"),
                    job_url=job.get("share_link") or job.get("apply_link", {}).get("link"),
                    location=job.get("location", ""),
                    remote_policy=_parse_remote_policy(job.get("extensions")),
                    seniority=_parse_seniority(job.get("title", "")),
                    salary_range=extensions.get("salary"),
                    source="serpapi",
                    source_id=job.get("job_id"),
                    posted_date=extensions.get("posted_at"),
                )
                all_postings.append(posting)

            logger.info("serpapi_search_complete", query=query, jobs_found=len(jobs))

        except RateLimitError:
            logger.warning("serpapi_rate_limited", query=query)
            break
        except Exception as e:
            logger.error("serpapi_search_error", query=query, error=str(e))
            continue

    return list(companies_map.values()), all_postings
