"""
ConnectorOS Scout — Priority Matrix & Velocity

Combines hiring intensity + data confidence into a 2×2 priority matrix.
Also calculates velocity labels for trend tracking.

Security: No external calls — pure computation.
"""

from __future__ import annotations

from core.models import PriorityTier, VelocityLabel
from core.logger import get_logger

logger = get_logger("scoring.priority")


def assign_priority(hiring_intensity: int, data_confidence: int) -> PriorityTier:
    """
    Assign priority tier from the 2×2 matrix.

    | | High Confidence | Low Confidence |
    |--|-----------------|----------------|
    | High Hiring | PRIORITY | REVIEW |
    | Low Hiring  | NURTURE  | ARCHIVE |
    """
    high_hiring = hiring_intensity >= 60
    high_confidence = data_confidence >= 60

    if high_hiring and high_confidence:
        return PriorityTier.PRIORITY
    elif high_hiring and not high_confidence:
        return PriorityTier.REVIEW
    elif not high_hiring and high_confidence:
        return PriorityTier.NURTURE
    else:
        return PriorityTier.ARCHIVE


def calculate_velocity(
    roles_last_week: int | None,
    roles_this_week: int,
) -> VelocityLabel:
    """Calculate hiring velocity label."""
    if roles_last_week is None or roles_last_week == 0:
        return VelocityLabel.NEW

    ratio = roles_this_week / roles_last_week

    if ratio > 1.3:
        return VelocityLabel.ACCELERATING
    elif ratio < 0.7:
        return VelocityLabel.DECLINING
    else:
        return VelocityLabel.STABLE
