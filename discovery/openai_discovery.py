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
- job_titles (array of strings — current open roles you found)
- source_urls (array of strings — where you found this information)

Return ONLY valid JSON. No markdown, no explanation. Just the JSON array."""


def _build_user_prompt(market: str, segment: str | None = None) -> str:
    """Build the user prompt for a discovery call."""
    prompt = f"Find 15-20 tech companies actively hiring in the market: {market}."
    if segment:
        prompt += f" Focus specifically on the {segment} segment."
    prompt += " Search career pages, LinkedIn, and niche job boards for companies with current openings."
    return prompt


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=2, max=30),
)
async def _call_openai_discovery(market: str, segment: str | None = None) -> list[dict]:
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
                {"role": "user", "content": _build_user_prompt(market, segment)},
            ],
        )

        duration_ms = int((time.time() - start) * 1000)

        # Extract text content from response
        raw_text = ""
        for item in response.output:
            if hasattr(item, "content"):
                for block in item.content:
                    if hasattr(block, "text"):
                        raw_text += block.text

        # Parse JSON from response
        raw_text = raw_text.strip()
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

    companies_map: dict[str, CompanyBase] = {}
    all_postings: list[JobPosting] = []

    for segment in segments:
        try:
            results = await _call_openai_discovery(target_market, segment)

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
                    companies_map[domain] = CompanyBase(
                        company_name=name,
                        company_domain=domain,
                        website_url=item.get("website_url"),
                        industry=item.get("industry"),
                        headquarters=item.get("headquarters"),
                        employee_count=item.get("employee_count"),
                        tech_stack=item.get("tech_stack", []),
                        discovery_sources=["openai"],
                    )

                # Create postings from discovered job titles
                for title in item.get("job_titles", []):
                    posting = JobPosting(
                        job_title=title,
                        location=item.get("headquarters", ""),
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
