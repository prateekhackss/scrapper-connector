"""
ConnectorOS Scout — Auto Notes Generator

Generates human-readable summary notes for each lead.

Security: No external calls — pure string formatting.
"""

from __future__ import annotations

from core.models import Lead, VelocityLabel, ConfidenceTier
from core.logger import get_logger

logger = get_logger("scoring.notes")


def generate_notes(lead: Lead) -> str:
    """
    Generate a human-readable summary note for a lead.

    Example: "12 open roles. Hiring accelerating. 3 senior positions.
    Posted on 3 boards. Data verified."
    """
    parts: list[str] = []

    # Role count
    if lead.role_count:
        parts.append(f"{lead.role_count} open roles")

    # Velocity
    if lead.velocity_label == VelocityLabel.ACCELERATING:
        parts.append("hiring accelerating")
    elif lead.velocity_label == VelocityLabel.DECLINING:
        parts.append("hiring declining")

    # Senior roles
    senior_keywords = ("senior", "lead", "principal", "staff", "vp", "director")
    senior_roles = [
        r for r in lead.top_roles
        if any(kw in r.lower() for kw in senior_keywords)
    ]
    if senior_roles:
        parts.append(f"{len(senior_roles)} senior positions")

    # Multi-source presence
    source_count = len(lead.company.discovery_sources) if lead.company.discovery_sources else 1
    if source_count >= 3:
        parts.append(f"posted on {source_count} boards")

    # Data confidence
    if lead.confidence_tier == ConfidenceTier.VERIFIED:
        parts.append("data verified")
    elif lead.confidence_tier == ConfidenceTier.UNVERIFIED:
        parts.append("data unverified — review recommended")

    return ". ".join(parts) + "." if parts else "No additional notes."
