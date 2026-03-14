"""
ConnectorOS Scout — Hiring Intensity Scorer

Calculates hiring intensity (0-100) based on:
- Role count, velocity, seniority mix, multi-source presence,
  role age, and promoted ads.

Security: No external calls — pure computation.
"""

from __future__ import annotations

from core.models import ScoreBreakdown, HiringLabel
from core.logger import get_logger

logger = get_logger("scoring.hiring")


def calculate_hiring_intensity(
    role_count: int,
    roles_last_week: int | None,
    roles_this_week: int,
    seniority_mix: dict[str, int],
    source_count: int,
    avg_role_age_days: float,
    has_promoted_ads: bool = False,
) -> tuple[int, ScoreBreakdown]:
    """
    Calculate hiring intensity score (0-100) with full breakdown.

    Returns:
        Tuple of (total_score, ScoreBreakdown).
    """
    breakdown = ScoreBreakdown()

    # 1. Role count (max 25)
    if role_count >= 10:
        breakdown.role_count_score = 25
    elif role_count >= 6:
        breakdown.role_count_score = 20
    elif role_count >= 3:
        breakdown.role_count_score = 12
    else:
        breakdown.role_count_score = 5

    # 2. Velocity (max 20)
    if roles_last_week is not None and roles_last_week > 0:
        change = (roles_this_week - roles_last_week) / roles_last_week
        if change > 0.5:
            breakdown.velocity_score = 20      # surging
        elif change > 0.1:
            breakdown.velocity_score = 12      # growing
        else:
            breakdown.velocity_score = 5       # stable
    else:
        breakdown.velocity_score = 10          # new company, assume moderate

    # 3. Seniority (max 15)
    senior_count = (
        seniority_mix.get("senior", 0)
        + seniority_mix.get("lead", 0)
        + seniority_mix.get("vp", 0)
    )
    total = sum(seniority_mix.values()) or 1
    senior_ratio = senior_count / total
    if senior_ratio > 0.5:
        breakdown.seniority_score = 15
    elif senior_ratio > 0.2:
        breakdown.seniority_score = 10
    else:
        breakdown.seniority_score = 3

    # 4. Multi-source (max 15)
    if source_count >= 3:
        breakdown.multi_source_score = 15
    elif source_count == 2:
        breakdown.multi_source_score = 8
    else:
        breakdown.multi_source_score = 3

    # 5. Role age (max 15)
    if avg_role_age_days > 28:
        breakdown.role_age_score = 15
    elif avg_role_age_days > 14:
        breakdown.role_age_score = 10
    else:
        breakdown.role_age_score = 5

    # 6. Promoted ads (max 10)
    breakdown.promoted_ads_score = 10 if has_promoted_ads else 0

    # Total
    breakdown.total = (
        breakdown.role_count_score
        + breakdown.velocity_score
        + breakdown.seniority_score
        + breakdown.multi_source_score
        + breakdown.role_age_score
        + breakdown.promoted_ads_score
    )

    return breakdown.total, breakdown


def assign_hiring_label(score: int) -> HiringLabel:
    """Assign hiring label based on score."""
    if score >= 80:
        return HiringLabel.RED_HOT
    if score >= 60:
        return HiringLabel.WARM
    if score >= 40:
        return HiringLabel.COOL
    return HiringLabel.COLD
