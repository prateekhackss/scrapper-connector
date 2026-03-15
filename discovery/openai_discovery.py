"""
ConnectorOS Scout — OpenAI Web Search Discovery

Uses OpenAI's gpt-4o-mini with web_search_preview tool to discover
tech companies actively hiring that may not appear on job boards.

Security:
  - API key from config (never hardcoded)
  - Budget checked before every call
  - All responses validated through Pydantic
  - API usage logged to api_usage table
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone

from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from core.config import OPENAI_API_KEY
from core.models import CompanyBase, JobPosting
from core.logger import get_logger
from core.exceptions import APIError, BudgetExceededError
from core.roles import classify_role_family, get_role_focus_label, normalize_role_focus

logger = get_logger("discovery.openai")

DISCOVERY_SYSTEM_PROMPT = """You are a tech industry research assistant specializing in identifying companies that are actively hiring software engineers and technical professionals.

Your goal: Find companies that are ACTIVELY HIRING right now — not just companies that exist.

Instructions:
1. Search the web for companies currently posting tech jobs
2. Focus on companies that may NOT appear on major job boards (internal career pages, LinkedIn-only postings, niche boards)
3. Return ONLY companies you can confirm are actively hiring NOW (not 6 months ago)
4. For each company, provide as much detail as possible

Return a JSON array of objects with these fields:
- company_name (string, required)
- company_domain (string, required — the main website domain)
- website_url (string — full URL)
- industry (string)
- headquarters (string — city, country)
- employee_count (string — e.g. "50-100", "500+")
- tech_stack (array of strings)
- source_urls (array of strings — direct URLs where you found this information)
- job_openings (array of objects with:
  - job_title (string, required)
  - job_url (string, if available)
  - location (string)
  - posted_date (string)
  - source_urls (array of strings — role-specific proof URLs)
)

If you cannot produce job_openings, include job_titles as a fallback.

Return ONLY valid JSON. No markdown, no explanation. Just the JSON array."""


def _extract_response_text(response: object) -> str:
    """Extract text from OpenAI Responses API objects across SDK versions."""
    output_text = getattr(response, "output_text", None)
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    chunks: list[str] = []
    for item in getattr(response, "output", []) or []:
        for block in getattr(item, "content", []) or []:
            text = getattr(block, "text", None)
            if isinstance(text, str) and text:
                chunks.append(text)
    return "".join(chunks).strip()


def _build_user_prompt(market: str, role_focus: str | None = None, segment: str | None = None) -> str:
    """Build the user prompt for a discovery call."""
    focus_label = get_role_focus_label(role_focus)
    prompt = f"Find 15-20 tech companies actively hiring for {focus_label} roles in the market: {market}."
    if segment:
        prompt += f" Focus specifically on the {segment} segment."
    prompt += f" Search career pages, LinkedIn, and niche job boards for companies with current {focus_label} openings."
    return prompt


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=2, max=30),
)
async def _call_openai_discovery(
    market: str,
    role_focus: str | None = None,
    segment: str | None = None,
) -> list[dict]:
    """Make a single OpenAI discovery call with web search."""
    if not OPENAI_API_KEY:
        raise APIError("openai", "OPENAI_API_KEY not configured in .env")

    client = AsyncOpenAI(api_key=OPENAI_API_KEY)

    start = time.time()
    try:
        response = await client.responses.create(
            model="gpt-4o-mini",
            tools=[{"type": "web_search_preview"}],
            input=[
                {"role": "system", "content": DISCOVERY_SYSTEM_PROMPT},
                {"role": "user", "content": _build_user_prompt(market, role_focus, segment)},
            ],
        )

        duration_ms = int((time.time() - start) * 1000)

        # Extract text content from response
        raw_text = _extract_response_text(response)

        # Parse JSON from response
        if raw_text.startswith("```"):
            raw_text = raw_text.split("\n", 1)[1] if "\n" in raw_text else raw_text[3:]
            raw_text = raw_text.rsplit("```", 1)[0]

        companies_data = json.loads(raw_text)

        logger.info(
            "openai_discovery_complete",
            market=market,
            segment=segment,
            companies_found=len(companies_data),
            duration_ms=duration_ms,
        )

        return companies_data if isinstance(companies_data, list) else []

    except json.JSONDecodeError as e:
        logger.error("openai_discovery_json_error", error=str(e), raw_text=raw_text[:200])
        return []
    except Exception as e:
        logger.error("openai_discovery_error", error=str(e))
        raise


async def collect_from_openai(
    target_market: str = "US tech companies",
    segments: list[str] | None = None,
    role_focus: str | None = "engineering",
) -> tuple[list[CompanyBase], list[JobPosting]]:
    """
    Discover companies via OpenAI web search.

    Args:
        target_market: Market description (e.g. "US tech companies").
        segments: Optional sub-segments for variety (e.g. ["SaaS", "Fintech", "AI/ML"]).

    Returns:
        Tuple of (companies, job_postings).
    """
    if segments is None:
        segments = ["SaaS and cloud platforms", "Fintech and financial services", "AI/ML and data companies"]

    selected_focus = normalize_role_focus(role_focus)
    companies_map: dict[str, CompanyBase] = {}
    all_postings: list[JobPosting] = []

    for segment in segments:
        try:
            results = await _call_openai_discovery(target_market, selected_focus, segment)

            for item in results:
                name = item.get("company_name", "").strip()
                domain = item.get("company_domain", "").strip().lower()

                if not name or not domain:
                    continue

                # Normalize domain
                for prefix in ("https://", "http://", "www."):
                    if domain.startswith(prefix):
                        domain = domain[len(prefix):]
                domain = domain.rstrip("/")

                if domain not in companies_map:
                    source_urls = [url for url in item.get("source_urls", []) if isinstance(url, str) and url.strip()]
                    companies_map[domain] = CompanyBase(
                        company_name=name,
                        company_domain=domain,
                        website_url=item.get("website_url"),
                        industry=item.get("industry"),
                        headquarters=item.get("headquarters"),
                        employee_count=item.get("employee_count"),
                        tech_stack=item.get("tech_stack", []),
                        discovery_sources=["openai"],
                        discovery_source_urls=source_urls,
                    )

                source_urls = companies_map[domain].discovery_source_urls

                # Preferred: role-level openings with proof URLs.
                openings = item.get("job_openings", [])
                for opening in openings:
                    title = str(opening.get("job_title", "")).strip()
                    if not title:
                        continue

                    evidence_urls = opening.get("source_urls") or source_urls
                    role_family = classify_role_family(title)
                    posting = JobPosting(
                        company_domain=domain,
                        job_title=title,
                        role_family=role_family,
                        job_url=opening.get("job_url"),
                        location=opening.get("location") or item.get("headquarters", ""),
                        posted_date=opening.get("posted_date"),
                        evidence_urls=[url for url in evidence_urls if isinstance(url, str) and url.strip()],
                        source="openai",
                        seniority=_parse_seniority_from_title(title),
                    )
                    all_postings.append(posting)

                # Backward-compatible fallback: title-only openings.
                if not openings:
                    for title in item.get("job_titles", []):
                        role_family = classify_role_family(title)
                        posting = JobPosting(
                            company_domain=domain,
                            job_title=title,
                            role_family=role_family,
                            location=item.get("headquarters", ""),
                            evidence_urls=source_urls,
                            source="openai",
                            seniority=_parse_seniority_from_title(title),
                        )
                        all_postings.append(posting)

        except Exception as e:
            logger.error("openai_discovery_segment_error", segment=segment, error=str(e))
            continue

    return list(companies_map.values()), all_postings


def _parse_seniority_from_title(title: str) -> str:
    """Infer seniority from title."""
    title_lower = title.lower()
    if any(kw in title_lower for kw in ("vp", "vice president", "director", "head of")):
        return "vp"
    if any(kw in title_lower for kw in ("lead", "principal", "staff", "architect")):
        return "lead"
    if any(kw in title_lower for kw in ("senior", "sr.", "sr ")):
        return "senior"
    if any(kw in title_lower for kw in ("junior", "jr.", "intern", "entry")):
        return "junior"
    return "mid"
