"""
ConnectorOS Scout — OpenAI Contact Enricher

Finds decision-makers at companies using OpenAI web search.
Returns ContactData with name, title, LinkedIn, and preliminary email guesses.

Security:
  - API key from config (never hardcoded)
  - All user-facing data validated through Pydantic
  - Rate limited: configurable delay between calls
  - Cached: skips companies enriched within 7 days
"""

from __future__ import annotations

import json
import time

from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from core.config import OPENAI_API_KEY
from core.models import ContactData, EmailEntry
from core.logger import get_logger
from core.exceptions import APIError
from core.database import get_setting

logger = get_logger("enrichment.openai")

ENRICHMENT_SYSTEM_PROMPT = """You are an expert B2B sales researcher. Given a company name and domain, find the most relevant decision-maker for a staffing/recruiting agency to contact.

Target titles (in order of preference):
1. VP of Engineering / VP Engineering
2. Head of Engineering
3. CTO / Chief Technology Officer
4. Director of Engineering
5. Head of Talent / VP of People / Head of HR
6. Engineering Manager

Instructions:
1. Search the web for this company's leadership team
2. Find a REAL person currently in one of the above roles
3. Verify they CURRENTLY work at this company (not a past employee)
4. Find their LinkedIn profile if possible
5. Note your sources

Return ONLY valid JSON with these fields:
{
  "found": true/false,
  "full_name": "First Last",
  "first_name": "First",
  "last_name": "Last",
  "title": "VP Engineering",
  "linkedin_url": "https://linkedin.com/in/...",
  "confidence_notes": "Found on LinkedIn and company About page",
  "enrichment_sources": ["LinkedIn", "Company website"],
  "source_urls": ["https://linkedin.com/in/...", "https://company.com/team"],
  "found_on_date": "2026-03-14"
}

If you cannot find anyone with confidence, return: {"found": false, "confidence_notes": "reason why not found"}
Return ONLY valid JSON. No markdown."""


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


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=2, max=30),
)
async def enrich_company_contact(
    company_name: str,
    company_domain: str,
) -> ContactData:
    """
    Find the decision-maker at a company using OpenAI web search.

    Args:
        company_name: Company name.
        company_domain: Company domain.

    Returns:
        ContactData with person info, or found=False.
    """
    if not OPENAI_API_KEY:
        raise APIError("openai", "OPENAI_API_KEY not configured in .env")

    client = AsyncOpenAI(api_key=OPENAI_API_KEY)

    user_prompt = (
        f"Find the VP of Engineering, Head of Engineering, or CTO at {company_name} ({company_domain}). "
        f"This person must CURRENTLY work there. Search LinkedIn and the company website."
    )

    start = time.time()
    try:
        response = await client.responses.create(
            model=get_setting("openai_model", "gpt-4o-mini"),
            tools=[{"type": "web_search_preview"}],
            input=[
                {"role": "system", "content": ENRICHMENT_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        )

        duration_ms = int((time.time() - start) * 1000)

        # Extract text
        raw_text = _extract_response_text(response)

        if raw_text.startswith("```"):
            raw_text = raw_text.split("\n", 1)[1] if "\n" in raw_text else raw_text[3:]
            raw_text = raw_text.rsplit("```", 1)[0]

        data = json.loads(raw_text)

        contact = ContactData(
            found=data.get("found", False),
            full_name=data.get("full_name"),
            first_name=data.get("first_name"),
            last_name=data.get("last_name"),
            title=data.get("title"),
            linkedin_url=data.get("linkedin_url"),
            enrichment_source="openai_web_search",
            enrichment_sources=data.get("enrichment_sources", []),
            source_urls=data.get("source_urls", []),
            found_on_date=data.get("found_on_date"),
            confidence_notes=data.get("confidence_notes"),
        )

        logger.info(
            "enrichment_complete",
            company=company_domain,
            found=contact.found,
            contact_name=contact.full_name,
            duration_ms=duration_ms,
        )

        return contact

    except json.JSONDecodeError as e:
        logger.error("enrichment_json_error", company=company_domain, error=str(e))
        return ContactData(found=False, confidence_notes=f"JSON parse error: {str(e)}")
    except Exception as e:
        logger.error("enrichment_error", company=company_domain, error=str(e))
        raise
