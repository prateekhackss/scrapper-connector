"""
ConnectorOS Scout — Email Pattern Generator

Uses OpenAI (WITHOUT web search) to generate likely email patterns
for a given person + domain. Falls back to generic patterns.

Security:
  - No PII is stored unvalidated — all emails pass regex validation
  - Email patterns are probabilistic, not confirmed deliverable
"""

from __future__ import annotations

import json
import re

from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from core.config import OPENAI_API_KEY
from core.models import EmailEntry
from core.logger import get_logger
from core.database import get_setting

logger = get_logger("enrichment.email")

_EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")

EMAIL_GEN_SYSTEM_PROMPT = """You are an email pattern expert. Given a person's name and their company domain, generate the most likely professional email addresses.

Common patterns (in order of likelihood):
1. first.last@domain.com
2. first@domain.com
3. flast@domain.com (first initial + last name)
4. firstl@domain.com (first name + last initial)
5. first_last@domain.com

Return ONLY a JSON array of objects:
[
  {"email": "john.doe@example.com", "confidence": "high"},
  {"email": "jdoe@example.com", "confidence": "medium"},
  {"email": "john@example.com", "confidence": "medium"}
]

Generate 3-5 email patterns. Mark the most common pattern as "high" confidence.
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
    stop=stop_after_attempt(2),
    wait=wait_exponential(multiplier=1, min=1, max=10),
)
async def generate_emails(
    first_name: str,
    last_name: str,
    domain: str,
) -> list[EmailEntry]:
    """
    Generate likely email patterns for a person at a company.

    Args:
        first_name: Person's first name.
        last_name: Person's last name.
        domain: Company domain (e.g. "stripe.com").

    Returns:
        List of EmailEntry objects ranked by confidence.
    """
    if not OPENAI_API_KEY:
        # Fall back to pattern generation without AI
        return _generate_patterns_locally(first_name, last_name, domain)

    client = AsyncOpenAI(api_key=OPENAI_API_KEY)

    user_prompt = (
        f"Generate email patterns for {first_name} {last_name} at {domain}. "
        f"Return 3-5 patterns ordered by likelihood."
    )

    try:
        response = await client.responses.create(
            model=get_setting("openai_model", "gpt-4o-mini"),
            input=[
                {"role": "system", "content": EMAIL_GEN_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        )

        raw_text = _extract_response_text(response)

        if raw_text.startswith("```"):
            raw_text = raw_text.split("\n", 1)[1] if "\n" in raw_text else raw_text[3:]
            raw_text = raw_text.rsplit("```", 1)[0]

        emails_data = json.loads(raw_text)

        results = []
        for entry in emails_data:
            email = entry.get("email", "").strip().lower()
            if _EMAIL_REGEX.match(email):
                results.append(EmailEntry(
                    email=email,
                    confidence=entry.get("confidence", "medium"),
                ))

        logger.info("email_gen_complete", name=f"{first_name} {last_name}", domain=domain, count=len(results))
        return results if results else _generate_patterns_locally(first_name, last_name, domain)

    except Exception as e:
        logger.warning("email_gen_fallback", error=str(e))
        return _generate_patterns_locally(first_name, last_name, domain)


def _generate_patterns_locally(first_name: str, last_name: str, domain: str) -> list[EmailEntry]:
    """Generate email patterns without AI (pure logic)."""
    first = first_name.strip().lower()
    last = last_name.strip().lower()
    domain = domain.strip().lower()

    patterns = [
        (f"{first}.{last}@{domain}", "high"),
        (f"{first}@{domain}", "medium"),
        (f"{first[0]}{last}@{domain}", "medium"),
        (f"{first}{last[0]}@{domain}", "low"),
        (f"{first}_{last}@{domain}", "low"),
    ]

    return [
        EmailEntry(email=email, confidence=conf)
        for email, conf in patterns
        if _EMAIL_REGEX.match(email)
    ]
