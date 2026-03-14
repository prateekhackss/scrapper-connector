"""
ConnectorOS Scout — Fallback Email Generator

When no decision-maker is found, generates generic role-based emails.
No API calls — zero cost.

Security:
  - All generated emails pass regex validation
  - No external dependencies
"""

from __future__ import annotations

import re

from core.models import EmailEntry

_EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")

# Generic role-based prefixes (most likely to reach someone relevant)
_GENERIC_PREFIXES = [
    ("careers", "medium"),
    ("hr", "medium"),
    ("recruiting", "medium"),
    ("hiring", "low"),
    ("talent", "low"),
    ("jobs", "low"),
    ("info", "low"),
    ("hello", "low"),
]


def generate_fallback_emails(domain: str) -> list[EmailEntry]:
    """
    Generate generic role-based emails for a domain.

    Args:
        domain: Company domain (e.g. "stripe.com").

    Returns:
        List of EmailEntry objects with generic role-based addresses.
    """
    domain = domain.strip().lower()
    results = []

    for prefix, confidence in _GENERIC_PREFIXES:
        email = f"{prefix}@{domain}"
        if _EMAIL_REGEX.match(email):
            results.append(EmailEntry(email=email, confidence=confidence))

    return results


def is_generic_role_email(email: str | None) -> bool:
    """Return True when an email is a generic inbox like careers@ or hr@."""
    if not email or "@" not in email:
        return False

    local_part = email.strip().lower().split("@", 1)[0]
    return any(local_part == prefix for prefix, _ in _GENERIC_PREFIXES)
