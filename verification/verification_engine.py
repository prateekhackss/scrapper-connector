"""
ConnectorOS Scout — Verification Engine (Orchestrator)

Runs OpenAI cross-check + technical checks → computes confidence → saves to DB.

Security:
  - Rate limited between verification calls
  - All DB operations use ORM (SQL injection safe)
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from core.database import SessionLocal, ContactRow, CompanyRow, get_setting
from core.models import VerificationResult
from core.logger import get_logger

from verification.openai_verifier import verify_contact_openai
from verification.technical_checks import run_technical_checks
from verification.confidence_scorer import calculate_confidence, assign_confidence_tier

logger = get_logger("verification.engine")


async def verify_single_contact(contact_id: int) -> int:
    """
    Verify a single contact (OpenAI + technical checks).

    Returns:
        Data confidence score (0-100).
    """
    db = SessionLocal()
    try:
        contact = db.query(ContactRow).filter_by(id=contact_id).first()
        if not contact:
            logger.warning("verify_contact_not_found", contact_id=contact_id)
            return 0

        company = db.query(CompanyRow).filter_by(id=contact.company_id).first()
        if not company:
            logger.warning("verify_company_not_found", company_id=contact.company_id)
            return 0

        # Layer 1: OpenAI cross-check (if contact was found)
        openai_result = VerificationResult()
        if contact.full_name and contact.title:
            try:
                openai_result = await verify_contact_openai(
                    person_name=contact.full_name,
                    person_title=contact.title,
                    company_name=company.company_name,
                    company_domain=company.company_domain,
                    linkedin_url=contact.linkedin_url,
                )
            except Exception as e:
                logger.warning("verify_openai_skip", contact_id=contact_id, error=str(e))

        # Layer 2: Technical checks
        tech_result = await run_technical_checks(
            domain=company.company_domain,
            email=contact.best_email,
            linkedin_url=contact.linkedin_url,
            full_name=contact.full_name,
        )

        # Merge results
        combined = VerificationResult(
            person_verified=openai_result.person_verified,
            person_detail=openai_result.person_detail,
            title_current=openai_result.title_current,
            current_title_if_different=openai_result.current_title_if_different,
            company_actively_hiring=openai_result.company_actively_hiring,
            domain_active=tech_result.domain_active,
            domain_has_mx=tech_result.domain_has_mx,
            linkedin_url_valid=tech_result.linkedin_url_valid or openai_result.linkedin_url_valid,
            name_plausible=tech_result.name_plausible,
            is_duplicate_contact=tech_result.is_duplicate_contact,
            email_format_valid=tech_result.email_format_valid,
            verification_sources=openai_result.verification_sources,
            overall_confidence=openai_result.overall_confidence,
        )

        # Layer 3: Calculate confidence score
        confidence = calculate_confidence(combined, contact.enrichment_source or "unknown")
        tier = assign_confidence_tier(confidence)

        # Save to DB
        contact.is_verified = True
        contact.verification_data = json.dumps(combined.model_dump())
        contact.person_verified = combined.person_verified
        contact.title_verified = combined.title_current
        contact.linkedin_verified = combined.linkedin_url_valid
        contact.domain_has_mx = combined.domain_has_mx
        contact.data_confidence = confidence
        contact.confidence_tier = tier.value
        if contact.proof_quality != "fallback_only":
            if contact.full_name and contact.title and combined.linkedin_url_valid and combined.person_verified:
                contact.proof_quality = "verified_named_contact"
            elif contact.full_name and contact.title and combined.linkedin_url_valid:
                contact.proof_quality = "source_backed_named_contact"
        contact.verified_at = datetime.now(timezone.utc)

        db.commit()

        logger.info(
            "verification_complete",
            contact=contact.full_name,
            company=company.company_domain,
            confidence=confidence,
            tier=tier.value,
        )

        return confidence

    except Exception as e:
        db.rollback()
        logger.error("verification_error", contact_id=contact_id, error=str(e))
        return 0
    finally:
        db.close()


async def run_verification(max_count: int | None = None) -> int:
    """
    Verify all unverified contacts.

    Returns:
        Number of contacts verified.
    """
    if max_count is None:
        max_count = int(get_setting("max_companies_per_run", "200"))

    delay = int(get_setting("enrichment_delay_seconds", "2"))

    db = SessionLocal()
    try:
        unverified = (
            db.query(ContactRow)
            .filter_by(is_current=True, is_verified=False)
            .limit(max_count)
            .all()
        )
        contact_ids = [c.id for c in unverified]
    finally:
        db.close()

    verified_count = 0
    logger.info("verification_batch_start", total=len(contact_ids))

    for i, contact_id in enumerate(contact_ids):
        try:
            score = await verify_single_contact(contact_id)
            if score > 0:
                verified_count += 1

            if i < len(contact_ids) - 1:
                await asyncio.sleep(delay)

        except Exception as e:
            logger.error("verification_batch_error", contact_id=contact_id, error=str(e))
            continue

    logger.info("verification_batch_complete", verified=verified_count, total=len(contact_ids))
    return verified_count
