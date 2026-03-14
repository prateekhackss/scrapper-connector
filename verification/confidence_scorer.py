"""
ConnectorOS Scout — Confidence Scorer

Combines OpenAI verification (Layer 1) and technical checks (Layer 2)
into a single 0-100 data confidence score with tier assignment.

Security:
  - No external calls — pure scoring logic
  - Score clamped to 0-100 to prevent overflow
"""

from __future__ import annotations

from core.models import VerificationResult, ConfidenceTier
from core.logger import get_logger

logger = get_logger("verification.confidence")


def calculate_confidence(verification: VerificationResult, enrichment_source: str) -> int:
    """
    Calculate data confidence score (0-100) from verification results.

    Scoring:
      - Person verified by OpenAI:       +25
      - High overall confidence:          +5
      - Domain active (DNS resolves):     +10
      - Domain has MX records:            +10
      - LinkedIn URL valid/live:          +15
      - Name plausible:                   +5
      - Email format valid:               +5
      - Duplicate contact (3+ companies): -20
      - Source bonus (web search):        +10
      - Source penalty (fallback):        -10

    Returns:
        Integer score clamped to 0-100.
    """
    score = 0

    # Layer 1: OpenAI verification
    if verification.person_verified:
        score += 25
    if verification.overall_confidence == "high":
        score += 5

    # Layer 2: Technical checks
    if verification.domain_active:
        score += 10
    if verification.domain_has_mx:
        score += 10
    if verification.linkedin_url_valid:
        score += 15
    if verification.name_plausible:
        score += 5
    if verification.email_format_valid:
        score += 5

    # Penalties
    if verification.is_duplicate_contact:
        score -= 20

    # Source bonus/penalty
    if enrichment_source == "openai_web_search":
        score += 10
    elif enrichment_source == "fallback":
        score -= 10

    # Clamp to 0-100
    final = max(0, min(100, score))

    logger.debug(
        "confidence_calculated",
        raw_score=score,
        final_score=final,
        enrichment_source=enrichment_source,
    )

    return final


def assign_confidence_tier(score: int) -> ConfidenceTier:
    """Assign confidence tier based on score."""
    if score >= 80:
        return ConfidenceTier.VERIFIED
    if score >= 60:
        return ConfidenceTier.LIKELY
    if score >= 40:
        return ConfidenceTier.UNCERTAIN
    return ConfidenceTier.UNVERIFIED
