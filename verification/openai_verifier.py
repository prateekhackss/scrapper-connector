"""
ConnectorOS Scout — OpenAI Cross-Check Verifier

Independent second OpenAI web search to verify enrichment data.
Different prompt than enrichment — asks specifically "does this person currently work here?"

Security:
  - Separate verification prompt prevents confirmation bias
  - Uses web search to cross-reference real-time data
"""

from __future__ import annotations

import json
import time

from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from core.config import OPENAI_API_KEY
from core.models import VerificationResult
from core.logger import get_logger
from core.database import get_setting

logger = get_logger("verification.openai")

VERIFICATION_SYSTEM_PROMPT = """You are a data verification specialist. Your job is to INDEPENDENTLY verify whether a person currently works at a specific company in a specific role.

You are NOT confirming what someone told you. You are doing your OWN research to verify.

Instructions:
1. Search the web for this person at this company
2. Check LinkedIn, company website, press releases, recent articles
3. Verify: Does this person CURRENTLY work at this company?
4. Verify: Is their title current or has it changed?
5. Verify: Is the company still actively hiring?

Return ONLY valid JSON:
{
  "person_verified": true/false,
  "person_detail": "Found on LinkedIn, profile shows current role at company",
  "title_current": true/false,
  "current_title_if_different": null or "new title",
  "company_actively_hiring": true/false,
  "linkedin_url_valid": true/false,
  "verification_sources": ["LinkedIn profile", "Company website"],
  "overall_confidence": "high" / "medium" / "low"
}

Be SKEPTICAL. If you can't find evidence, say so. Don't guess.
Return ONLY valid JSON."""


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
async def verify_contact_openai(
    person_name: str,
    person_title: str,
    company_name: str,
    company_domain: str,
    linkedin_url: str | None = None,
) -> VerificationResult:
    """
    Cross-verify a contact using OpenAI web search.

    Returns:
        VerificationResult with verification findings.
    """
    if not OPENAI_API_KEY:
        return VerificationResult(overall_confidence="low")

    client = AsyncOpenAI(api_key=OPENAI_API_KEY)

    user_prompt = (
        f"Verify: Does {person_name} currently work as {person_title} at {company_name} ({company_domain})?"
    )
    if linkedin_url:
        user_prompt += f" Their LinkedIn is reportedly: {linkedin_url}"

    start = time.time()
    try:
        response = await client.responses.create(
            model=get_setting("openai_model", "gpt-4o-mini"),
            tools=[{"type": "web_search_preview"}],
            input=[
                {"role": "system", "content": VERIFICATION_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        )

        duration_ms = int((time.time() - start) * 1000)

        raw_text = _extract_response_text(response)

        if raw_text.startswith("```"):
            raw_text = raw_text.split("\n", 1)[1] if "\n" in raw_text else raw_text[3:]
            raw_text = raw_text.rsplit("```", 1)[0]

        data = json.loads(raw_text)

        result = VerificationResult(
            person_verified=data.get("person_verified"),
            person_detail=data.get("person_detail"),
            title_current=data.get("title_current"),
            current_title_if_different=data.get("current_title_if_different"),
            company_actively_hiring=data.get("company_actively_hiring"),
            linkedin_url_valid=data.get("linkedin_url_valid"),
            verification_sources=data.get("verification_sources", []),
            overall_confidence=data.get("overall_confidence", "low"),
        )

        logger.info(
            "verification_openai_complete",
            person=person_name,
            company=company_domain,
            verified=result.person_verified,
            duration_ms=duration_ms,
        )

        return result

    except json.JSONDecodeError as e:
        logger.error("verification_json_error", company=company_domain, error=str(e))
        return VerificationResult(overall_confidence="low")
    except Exception as e:
        logger.error("verification_openai_error", company=company_domain, error=str(e))
        raise
