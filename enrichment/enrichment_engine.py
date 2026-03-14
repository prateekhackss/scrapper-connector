"""
ConnectorOS Scout — Enrichment Engine (Orchestrator)

For each company: check cache → OpenAI enrich → email gen → fallback → DB save.

Security:
  - Budget checked before each API call
  - Delay between calls prevents rate limiting
  - Old contacts marked is_current=False (never deleted)
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from core.database import SessionLocal, CompanyRow, ContactRow, get_setting
from core.models import ContactData, EmailEntry
from core.logger import get_logger

from enrichment.openai_enricher import enrich_company_contact
from enrichment.email_generator import generate_emails
from enrichment.fallback_emails import generate_fallback_emails, is_generic_role_email

logger = get_logger("enrichment.engine")


def _classify_contact_proof_quality(contact: ContactData) -> str:
    """Grade how defensible this contact is before verification runs."""
    if contact.enrichment_source == "fallback" or not contact.found:
        return "fallback_only"
    if contact.full_name and contact.title and contact.linkedin_url and contact.source_urls:
        return "source_backed_named_contact"
    if contact.full_name and contact.title and contact.linkedin_url:
        return "named_contact_with_linkedin"
    if contact.full_name and contact.title:
        return "named_contact_light_proof"
    return "weak_contact"


def _is_recently_enriched(db: Session, company_id: int, days: int = 7) -> bool:
    """Check if this company has a current contact enriched within N days."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    contact = (
        db.query(ContactRow)
        .filter_by(company_id=company_id, is_current=True)
        .filter(ContactRow.enriched_at > cutoff)
        .first()
    )
    return contact is not None


def _save_contact(db: Session, company_id: int, contact: ContactData, emails: list[EmailEntry]) -> int:
    """Save contact to DB. Returns contact row ID."""
    # Mark old contacts as not current
    db.query(ContactRow).filter_by(company_id=company_id, is_current=True).update({"is_current": False})

    best_email = None
    for e in emails:
        if e.confidence == "high":
            best_email = e.email
            break
    if not best_email and emails:
        best_email = emails[0].email

    proof_quality = contact.proof_quality or _classify_contact_proof_quality(contact)
    generic_email_only = is_generic_role_email(best_email) and not bool(contact.full_name and contact.title)

    row = ContactRow(
        company_id=company_id,
        full_name=contact.full_name,
        first_name=contact.first_name,
        last_name=contact.last_name,
        title=contact.title,
        linkedin_url=contact.linkedin_url,
        emails=json.dumps([e.model_dump() for e in emails]),
        best_email=best_email,
        enrichment_source=contact.enrichment_source,
        enrichment_sources=json.dumps(contact.enrichment_sources),
        source_urls=json.dumps([url for url in contact.source_urls if isinstance(url, str) and url.strip()]),
        found_on_date=contact.found_on_date,
        proof_quality=proof_quality,
        generic_email_only=generic_email_only,
        confidence_notes=contact.confidence_notes,
        is_current=True,
        enriched_at=datetime.now(timezone.utc),
    )
    db.add(row)
    db.flush()
    return row.id


async def enrich_single_company(company_id: int, company_name: str, company_domain: str) -> int | None:
    """
    Enrich a single company (find contact + generate emails).

    Returns:
        Contact row ID if enriched, None if skipped/failed.
    """
    db = SessionLocal()
    try:
        # Check cache
        if _is_recently_enriched(db, company_id, days=7):
            logger.info("enrichment_cached", company=company_domain)
            return None

        # Step 1: Find decision-maker
        contact = await enrich_company_contact(company_name, company_domain)

        # Step 2: Generate emails
        if contact.found and contact.first_name and contact.last_name:
            emails = await generate_emails(contact.first_name, contact.last_name, company_domain)
        else:
            emails = generate_fallback_emails(company_domain)
            contact.enrichment_source = "fallback"
            contact.proof_quality = "fallback_only"

        # Step 3: Save to DB
        contact_id = _save_contact(db, company_id, contact, emails)
        db.commit()

        logger.info(
            "enrichment_saved",
            company=company_domain,
            contact_found=contact.found,
            emails_count=len(emails),
        )
        return contact_id

    except Exception as e:
        db.rollback()
        logger.error("enrichment_failed", company=company_domain, error=str(e))
        return None
    finally:
        db.close()


async def run_enrichment(max_count: int | None = None) -> int:
    """
    Enrich all companies that need enrichment.

    Args:
        max_count: Maximum companies to enrich in this run.

    Returns:
        Number of companies enriched.
    """
    if max_count is None:
        max_count = int(get_setting("max_companies_per_run", "200"))

    delay = int(get_setting("enrichment_delay_seconds", "2"))

    db = SessionLocal()
    try:
        # Find companies without current contacts
        companies_needing_enrichment = (
            db.query(CompanyRow)
            .filter_by(status="active")
            .outerjoin(ContactRow, (ContactRow.company_id == CompanyRow.id) & (ContactRow.is_current == True))
            .filter(ContactRow.id == None)
            .limit(max_count)
            .all()
        )

        # Also include companies whose contacts are stale (>7 days old)
        stale_cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        stale_companies = (
            db.query(CompanyRow)
            .filter_by(status="active")
            .join(ContactRow, ContactRow.company_id == CompanyRow.id)
            .filter(ContactRow.is_current == True, ContactRow.enriched_at < stale_cutoff)
            .limit(max_count)
            .all()
        )

        all_targets = {c.id: c for c in companies_needing_enrichment}
        for c in stale_companies:
            if c.id not in all_targets:
                all_targets[c.id] = c

    finally:
        db.close()

    enriched_count = 0
    targets = list(all_targets.values())[:max_count]

    logger.info("enrichment_batch_start", total=len(targets))

    for i, company in enumerate(targets):
        try:
            result = await enrich_single_company(company.id, company.company_name, company.company_domain)
            if result:
                enriched_count += 1

            # Rate limiting delay
            if i < len(targets) - 1:
                await asyncio.sleep(delay)

        except Exception as e:
            logger.error("enrichment_batch_error", company=company.company_domain, error=str(e))
            continue

    logger.info("enrichment_batch_complete", enriched=enriched_count, total=len(targets))
    return enriched_count
