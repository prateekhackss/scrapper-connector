"""
ConnectorOS Scout — Technical Verification Checks

Layer 2 verification: DNS, MX, email format, LinkedIn, name plausibility, etc.
All checks are Python-native — no external API calls needed.

Security:
  - DNS queries use dnspython (safe resolver, no shell commands)
  - HTTP checks use httpx with strict timeouts to prevent hanging
  - No user-supplied data is passed to shell or OS commands
"""

from __future__ import annotations

import re
import socket
from urllib.parse import urlparse

import httpx
import dns.resolver

from core.models import VerificationResult
from core.logger import get_logger

logger = get_logger("verification.technical")

_EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")
_LINKEDIN_PATTERN = re.compile(r"^https?://(www\.)?linkedin\.com/(in|company)/[\w\-]+/?$")
_PARKED_KEYWORDS = ["buy this domain", "parked", "for sale", "domain is for sale", "expired"]


def check_dns_resolution(domain: str) -> bool:
    """Check if a domain resolves via DNS (is the domain real?)."""
    try:
        socket.getaddrinfo(domain, 80, socket.AF_INET, socket.SOCK_STREAM)
        return True
    except (socket.gaierror, OSError):
        return False


def check_mx_records(domain: str) -> bool:
    """Check if a domain has MX records (can receive email?)."""
    try:
        answers = dns.resolver.resolve(domain, "MX")
        return len(answers) > 0
    except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN, dns.resolver.NoNameservers, Exception):
        return False


def check_email_format(email: str | None) -> bool:
    """Validate email format against RFC-compliant regex."""
    if not email:
        return False
    return bool(_EMAIL_REGEX.match(email.strip().lower()))


def check_linkedin_format(url: str | None) -> bool:
    """Check if a LinkedIn URL has a valid format."""
    if not url:
        return False
    return bool(_LINKEDIN_PATTERN.match(url.strip()))


async def check_linkedin_live(url: str | None) -> bool:
    """Check if a LinkedIn URL returns 200/302 (is the profile real?)."""
    if not url or not check_linkedin_format(url):
        return False

    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
            resp = await client.head(url, headers={
                "User-Agent": "Mozilla/5.0 (compatible; ConnectorOS/1.0)"
            })
            return resp.status_code in (200, 301, 302, 303, 307, 308)
    except Exception:
        return False


def check_name_plausibility(name: str | None) -> bool:
    """Check if a name looks like a real person's name."""
    if not name:
        return False

    name = name.strip()

    # Must have at least 2 parts
    parts = name.split()
    if len(parts) < 2:
        return False

    # Must not contain numbers
    if any(c.isdigit() for c in name):
        return False

    # First and last parts should start with uppercase
    if not parts[0][0].isupper() or not parts[-1][0].isupper():
        return False

    # Suspicious patterns
    suspicious = ["test", "admin", "info@", "noreply", "example", "null", "n/a"]
    name_lower = name.lower()
    if any(s in name_lower for s in suspicious):
        return False

    return True


async def check_website_live(domain: str) -> bool:
    """Check if a company's website returns 200."""
    for scheme in ("https", "http"):
        try:
            url = f"{scheme}://{domain}"
            async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
                resp = await client.head(url, headers={
                    "User-Agent": "Mozilla/5.0 (compatible; ConnectorOS/1.0)"
                })
                return resp.status_code == 200
        except Exception:
            continue
    return False


async def check_parked_domain(domain: str) -> bool:
    """Check if a domain appears to be parked/for-sale."""
    try:
        url = f"https://{domain}"
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            resp = await client.get(url, headers={
                "User-Agent": "Mozilla/5.0 (compatible; ConnectorOS/1.0)"
            })
            body = resp.text.lower()[:5000]  # Only check first 5KB
            return any(kw in body for kw in _PARKED_KEYWORDS)
    except Exception:
        return False


async def run_technical_checks(
    domain: str,
    email: str | None,
    linkedin_url: str | None,
    full_name: str | None,
    all_names_in_batch: list[str] | None = None,
) -> VerificationResult:
    """
    Run all Layer 2 technical verification checks.

    Args:
        domain: Company domain.
        email: Best email to verify.
        linkedin_url: LinkedIn URL to check.
        full_name: Contact full name.
        all_names_in_batch: All names in current batch (for duplicate detection).

    Returns:
        VerificationResult with technical check results.
    """
    result = VerificationResult()

    # DNS resolution
    result.domain_active = check_dns_resolution(domain)

    # MX records
    result.domain_has_mx = check_mx_records(domain)

    # Email format
    result.email_format_valid = check_email_format(email)

    # LinkedIn format and live check
    linkedin_format_ok = check_linkedin_format(linkedin_url)
    if linkedin_format_ok:
        result.linkedin_url_valid = await check_linkedin_live(linkedin_url)
    else:
        result.linkedin_url_valid = False

    # Name plausibility
    result.name_plausible = check_name_plausibility(full_name)

    # Duplicate detection
    if all_names_in_batch and full_name:
        occurrences = sum(1 for n in all_names_in_batch if n and n.lower() == full_name.lower())
        result.is_duplicate_contact = occurrences >= 3

    logger.info(
        "technical_checks_complete",
        domain=domain,
        dns=result.domain_active,
        mx=result.domain_has_mx,
        email_ok=result.email_format_valid,
        linkedin=result.linkedin_url_valid,
        name_ok=result.name_plausible,
    )

    return result
