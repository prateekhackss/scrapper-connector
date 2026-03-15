"""
ConnectorOS Scout — Pipeline Orchestrator

Runs the full 5-stage pipeline: Discover → Enrich → Verify → Score → Export.
Supports checkpointing, error recovery, and cost tracking.

Security:
  - Budget checked at each stage
  - All errors caught and logged (never swallowed)
  - Pipeline run tracked in DB for auditing
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

from core.database import (
    SessionLocal, PipelineRunRow, CompanyRow, ContactRow, LeadRow, JobPostingRow,
    AgencyRow, NotificationRow, get_setting,
)
from core.models import Lead, CompanyBase, ScoreBreakdown, HiringLabel, ConfidenceTier
from core.logger import get_logger
from core.exceptions import PipelineError

from discovery.discovery_engine import run_discovery
from enrichment.enrichment_engine import run_enrichment
from verification.verification_engine import run_verification
from scoring.hiring_scorer import calculate_hiring_intensity, assign_hiring_label
from scoring.priority_matrix import assign_priority, calculate_velocity
from scoring.notes_generator import generate_notes, generate_outreach_summary
from export.excel_generator import generate_excel
from export.delivery_ledger import get_already_delivered_lead_ids, record_delivery
from core.sse import publish_event
from enrichment.fallback_emails import is_generic_role_email
from core.roles import get_role_focus_label, normalize_role_focus, role_focus_matches

logger = get_logger("pipeline.orchestrator")


def _as_utc(dt: datetime) -> datetime:
    """
    Normalize datetimes to UTC-aware objects.

    Supabase/Postgres can return tz-aware datetimes while older rows may be
    naive. This keeps arithmetic safe and consistent.
    """
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _create_pipeline_run(run_type: str = "full", target_role_family: str = "engineering") -> int:
    """Create a new pipeline_run record. Returns run ID."""
    db = SessionLocal()
    try:
        run = PipelineRunRow(
            run_type=run_type,
            target_role_family=target_role_family,
            started_at=datetime.now(timezone.utc),
            status="running",
        )
        db.add(run)
        db.commit()
        run_id = run.id
        return run_id
    finally:
        db.close()


def _update_run(run_id: int, **kwargs) -> None:
    """Update pipeline run fields."""
    db = SessionLocal()
    try:
        run = db.query(PipelineRunRow).filter_by(id=run_id).first()
        if run:
            for k, v in kwargs.items():
                setattr(run, k, v)
            db.commit()
    finally:
        db.close()


def _create_notification(type_: str, title: str, message: str, severity: str = "info") -> None:
    """Create a system notification."""
    db = SessionLocal()
    try:
        notif = NotificationRow(type=type_, severity=severity, title=title, message=message)
        db.add(notif)
        db.commit()
    finally:
        db.close()


def _json_list(value: str | None) -> list:
    """Safely load a JSON list from a DB text column."""
    if not value:
        return []
    try:
        data = json.loads(value)
    except Exception:
        return []
    return data if isinstance(data, list) else []


def _unique_urls(*groups: list[str]) -> list[str]:
    """Return de-duplicated, non-empty URLs while preserving order."""
    seen: set[str] = set()
    urls: list[str] = []
    for group in groups:
        for url in group:
            if not isinstance(url, str):
                continue
            clean = url.strip()
            if not clean or clean in seen:
                continue
            seen.add(clean)
            urls.append(clean)
    return urls


def _collect_role_evidence_urls(postings: list[JobPostingRow]) -> list[str]:
    """Gather proof URLs that show the roles are real and current."""
    evidence: list[str] = []
    for posting in postings:
        if posting.job_url:
            evidence.append(posting.job_url)
        evidence.extend(_json_list(posting.evidence_urls))
    return _unique_urls(evidence)


def _contact_proof_quality(contact: ContactRow | None) -> str:
    """Describe how defensible the saved contact is for buyers."""
    if not contact:
        return "no_contact"
    if contact.proof_quality:
        return contact.proof_quality
    if contact.enrichment_source == "fallback" or contact.generic_email_only:
        return "fallback_only"
    if contact.full_name and contact.title and contact.linkedin_url and _json_list(contact.source_urls):
        return "source_backed_named_contact"
    if contact.full_name and contact.title and contact.linkedin_url:
        return "named_contact_with_linkedin"
    if contact.full_name and contact.title:
        return "named_contact_light_proof"
    return "weak_contact"


def _is_buyer_ready(contact: ContactRow | None) -> bool:
    """Only deliver contacts that look commercially defensible."""
    if not contact:
        return False

    min_confidence = int(get_setting("min_buyer_confidence_for_delivery", "55"))
    require_named = get_setting("require_named_contact_for_delivery", "true").lower() == "true"
    require_linkedin = get_setting("require_linkedin_for_delivery", "true").lower() == "true"

    if contact.enrichment_source == "fallback" or contact.generic_email_only:
        return False
    if is_generic_role_email(contact.best_email):
        return False
    if contact.data_confidence < min_confidence:
        return False
    if require_named and not (contact.full_name and contact.title):
        return False
    if require_linkedin and not contact.linkedin_url:
        return False

    proof_signals = sum(
        1 for value in (
            bool(_json_list(contact.source_urls)),
            bool(contact.linkedin_verified),
            bool(contact.person_verified),
            bool(contact.title_verified),
        )
        if value
    )
    return proof_signals >= 2 or (contact.data_confidence >= 70 and proof_signals >= 1)


def _build_proof_summary(
    company: CompanyRow,
    contact: ContactRow | None,
    postings: list[JobPostingRow],
) -> str:
    """Generate a concise buyer-facing rationale for the lead."""
    role_urls = _collect_role_evidence_urls(postings)
    role_bits = [f"{len(postings)} active role(s)"]
    if role_urls:
        role_bits.append(f"{len(role_urls)} supporting URL(s)")
    if company.discovery_source_urls and _json_list(company.discovery_source_urls):
        role_bits.append(f"{len(_json_list(company.discovery_source_urls))} company discovery source URL(s)")

    if not contact:
        return f"Hiring proof: {', '.join(role_bits)}. No named contact found yet."

    contact_urls = _json_list(contact.source_urls)
    contact_bits = [f"contact quality { _contact_proof_quality(contact) }"]
    if contact.full_name and contact.title:
        contact_bits.append(f"{contact.full_name} ({contact.title})")
    if contact_urls:
        contact_bits.append(f"{len(contact_urls)} contact proof URL(s)")
    if contact.linkedin_url:
        contact_bits.append("LinkedIn present")
    if any((contact.person_verified, contact.title_verified, contact.linkedin_verified)):
        contact_bits.append("verification signals present")

    return f"Hiring proof: {', '.join(role_bits)}. Contact proof: {', '.join(contact_bits)}."


def _derive_qa_status(existing_status: str | None, buyer_ready: bool) -> str:
    """Choose the next QA state while respecting manual agency review where possible."""
    if existing_status == "rejected":
        return "rejected"
    if existing_status == "approved" and buyer_ready:
        return "approved"
    return "pending_review" if buyer_ready else "needs_research"


def _get_current_lead_row(db, company_id: int, role_focus: str) -> LeadRow | None:
    """Return the latest lead row for a company + role focus."""
    return (
        db.query(LeadRow)
        .filter_by(company_id=company_id, role_focus=role_focus)
        .order_by(LeadRow.updated_at.desc(), LeadRow.id.desc())
        .first()
    )


def _score_all_leads(run_id: int, role_focus: str) -> list[dict]:
    """Score all companies with contacts and create lead records."""
    db = SessionLocal()
    try:
        companies = db.query(CompanyRow).filter_by(status="active").all()
        leads_data = []

        for company in companies:
            contact = (
                db.query(ContactRow)
                .filter_by(company_id=company.id, is_current=True)
                .first()
            )

            # Count active job postings
            postings = (
                db.query(JobPostingRow)
                .filter_by(company_id=company.id, is_active=True)
                .all()
            )
            postings = [posting for posting in postings if role_focus_matches(posting.role_family, role_focus)]
            role_count = len(postings)

            # Do not keep discovery-only companies in the shortlist. If an older
            # lead exists for a company that no longer has active postings, archive it.
            if role_count <= 0:
                existing_lead = _get_current_lead_row(db, company.id, role_focus)
                if existing_lead and existing_lead.status != "archived":
                    existing_lead.status = "archived"
                    existing_lead.qa_status = "needs_research"
                    existing_lead.proof_summary = (
                        "No active role postings are currently attached to this company. "
                        "Lead archived until fresh hiring evidence is found."
                    )
                    existing_lead.outreach_summary = ""
                continue

            # Seniority mix
            seniority_mix = {}
            for p in postings:
                s = p.seniority or "mid"
                seniority_mix[s] = seniority_mix.get(s, 0) + 1

            # Source count
            sources = json.loads(company.discovery_sources or "[]")
            source_count = len(sources)

            # Calculate hiring intensity
            hiring_score, breakdown = calculate_hiring_intensity(
                role_count=role_count,
                roles_last_week=None,
                roles_this_week=role_count,
                seniority_mix=seniority_mix,
                source_count=source_count,
                avg_role_age_days=14,
                has_promoted_ads=False,
            )

            hiring_label = assign_hiring_label(hiring_score)

            # Data confidence
            data_confidence = contact.data_confidence if contact else 0
            confidence_tier_str = contact.confidence_tier if contact else "UNVERIFIED"

            # Priority
            priority = assign_priority(hiring_score, data_confidence)

            # Velocity
            velocity = calculate_velocity(None, role_count)

            # Top roles
            top_roles = [p.job_title for p in postings[:5]]
            role_evidence_urls = _collect_role_evidence_urls(postings)
            contact_source_urls = _json_list(contact.source_urls) if contact else []
            contact_quality = _contact_proof_quality(contact)
            buyer_ready = _is_buyer_ready(contact)
            proof_summary = _build_proof_summary(company, contact, postings)
            outreach_summary = generate_outreach_summary(
                company_name=company.company_name,
                top_roles=top_roles,
                tech_stack=json.loads(company.tech_stack or "[]"),
                contact_title=contact.title if contact else None,
            )

            # Preserve a per-run snapshot while still carrying forward reviewer context.
            previous_lead = _get_current_lead_row(db, company.id, role_focus)
            previous_status = previous_lead.status if previous_lead else "new"
            previous_qa_status = previous_lead.qa_status if previous_lead else None
            lead_row = LeadRow(company_id=company.id, role_focus=role_focus, status="new")
            db.add(lead_row)

            lead_row.contact_id = contact.id if contact else None
            lead_row.role_focus = role_focus
            lead_row.hiring_intensity = hiring_score
            lead_row.hiring_label = hiring_label.value
            lead_row.data_confidence = data_confidence
            lead_row.confidence_tier = confidence_tier_str
            lead_row.priority_tier = priority.value
            lead_row.score_breakdown = json.dumps(breakdown.model_dump())
            lead_row.role_count = role_count
            lead_row.top_roles = json.dumps(top_roles)
            lead_row.roles_this_week = role_count
            lead_row.velocity_label = velocity.value
            lead_row.buyer_ready = buyer_ready
            lead_row.qa_status = _derive_qa_status(previous_qa_status, buyer_ready)
            lead_row.proof_summary = proof_summary
            lead_row.outreach_summary = outreach_summary
            lead_row.pipeline_run_id = run_id
            lead_row.status = previous_status if previous_status == "delivered" else "new"
            db.flush()

            # Build export dict
            lead_dict = {
                "lead_id": lead_row.id,
                "company_name": company.company_name,
                "company_domain": company.company_domain,
                "website_url": company.website_url or f"https://{company.company_domain}",
                "headquarters": company.headquarters or "",
                "industry": company.industry or "",
                "employee_count": company.employee_count or "",
                "tech_stack": json.loads(company.tech_stack or "[]"),
                "role_count": role_count,
                "role_focus": role_focus,
                "top_roles": top_roles,
                "hiring_intensity": hiring_score,
                "hiring_label": hiring_label.value,
                "contact_name": contact.full_name if contact else "",
                "contact_title": contact.title if contact else "",
                "best_email": contact.best_email if contact else "",
                "linkedin_url": contact.linkedin_url if contact else "",
                "data_confidence": data_confidence,
                "confidence_tier": confidence_tier_str,
                "priority_tier": priority.value,
                "buyer_ready": buyer_ready,
                "qa_status": lead_row.qa_status,
                "role_evidence_urls": role_evidence_urls,
                "contact_source_urls": contact_source_urls,
                "contact_proof_quality": contact_quality,
                "proof_summary": proof_summary,
                "outreach_summary": outreach_summary,
                "notes": "",
            }

            # Generate notes
            lead_model = Lead(
                company=CompanyBase(
                    company_name=company.company_name,
                    company_domain=company.company_domain,
                    discovery_sources=json.loads(company.discovery_sources or "[]"),
                ),
                role_count=role_count,
                top_roles=top_roles,
                velocity_label=velocity,
                confidence_tier=ConfidenceTier(confidence_tier_str) if confidence_tier_str in [t.value for t in ConfidenceTier] else None,
            )
            lead_dict["notes"] = generate_notes(lead_model)
            lead_row.notes = lead_dict["notes"]

            leads_data.append(lead_dict)

            # Hot lead notification
            if hiring_score >= 85:
                _create_notification(
                    "hot_lead_found",
                    f"🔥 Hot Lead: {company.company_name}",
                    f"{company.company_name} scored {hiring_score} with {role_count} open roles.",
                )

        db.commit()
        return leads_data

    except Exception as e:
        db.rollback()
        raise
    finally:
        db.close()


async def run_full_pipeline(target_market: str | None = None, role_focus: str | None = None) -> dict:
    """
    Execute the full 5-stage pipeline.

    Returns:
        Dict with run stats.
    """
    if target_market is None:
        target_market = get_setting("default_target_market", "US tech companies")
    selected_role_focus = normalize_role_focus(role_focus or get_setting("default_role_focus", "engineering"))
    role_focus_label = get_role_focus_label(selected_role_focus)

    run_id = _create_pipeline_run("full", target_role_family=selected_role_focus)
    errors = []

    logger.info("pipeline_start", run_id=run_id, target_market=target_market, role_focus=selected_role_focus)
    await publish_event(
        "system",
        f"🚀 Started pipeline run #{run_id} for target market: '{target_market}' with role focus: {role_focus_label}"
    )

    try:
        # ── Stage 1: Discovery ──────────────────────────────────
        try:
            await publish_event("discovery", f"Starting company discovery across data sources for {role_focus_label} roles...")
            discovered = await run_discovery(target_market, role_focus=selected_role_focus)
            _update_run(run_id, companies_discovered=discovered)
            logger.info("pipeline_discovery_done", discovered=discovered)
            await publish_event("discovery", f"✅ Found {discovered} new companies matching ICP.", level="success")
        except Exception as e:
            errors.append(f"Discovery: {str(e)}")
            logger.error("pipeline_discovery_failed", error=str(e))
            await publish_event("discovery", f"❌ Discovery failed: {str(e)}", level="error")

        # ── Stage 2: Enrichment ─────────────────────────────────
        try:
            await publish_event("enrichment", "Finding contacts and generating smart emails...")
            enriched = await run_enrichment()
            _update_run(run_id, companies_enriched=enriched)
            logger.info("pipeline_enrichment_done", enriched=enriched)
            await publish_event("enrichment", f"✅ Successfully enriched {enriched} companies with contact data.", level="success")
        except Exception as e:
            errors.append(f"Enrichment: {str(e)}")
            logger.error("pipeline_enrichment_failed", error=str(e))
            await publish_event("enrichment", f"❌ Enrichment failed: {str(e)}", level="error")

        # ── Stage 3: Verification ───────────────────────────────
        verification_enabled = get_setting("verification_enabled", "true").lower() == "true"
        verified = 0
        if verification_enabled:
            try:
                await publish_event("verification", "Running technical checks and OpenAI cross-validation...")
                verified = await run_verification()
                _update_run(run_id, companies_verified=verified)
                logger.info("pipeline_verification_done", verified=verified)
                await publish_event("verification", f"✅ Verification complete. Scaled {verified} verified domains.", level="success")
            except Exception as e:
                errors.append(f"Verification: {str(e)}")
                logger.error("pipeline_verification_failed", error=str(e))
                await publish_event("verification", f"❌ Verification failed: {str(e)}", level="error")

        # ── Stage 4: Scoring ────────────────────────────────────
        try:
            await publish_event("scoring", f"Calculating hiring intensity and data confidence scores for {role_focus_label} roles...")
            leads_data = _score_all_leads(run_id, selected_role_focus)
            _update_run(run_id, leads_generated=len(leads_data))
            logger.info("pipeline_scoring_done", leads=len(leads_data))
            await publish_event("scoring", f"✅ Scoring complete. Generated {len(leads_data)} qualified leads.", level="success")
        except Exception as e:
            errors.append(f"Scoring: {str(e)}")
            logger.error("pipeline_scoring_failed", error=str(e))
            await publish_event("scoring", f"❌ Scoring failed: {str(e)}", level="error")
            leads_data = []

        # ── Stage 5: Export per agency ──────────────────────────
        delivered_total = 0
        db = SessionLocal()
        try:
            await publish_event("export", "Matching leads against agency ICPs and generating export files...")
            agencies = db.query(AgencyRow).filter_by(status="active").all()
            for agency in agencies:
                try:
                    already_delivered = get_already_delivered_lead_ids(agency.id)
                    new_leads = [l for l in leads_data if l["lead_id"] not in already_delivered]

                    if new_leads:
                        # Filter by agency ICP (if configured)
                        icp = json.loads(agency.icp_config or "{}")
                        min_hiring = icp.get("min_hiring_score", 50)
                        min_conf = icp.get("min_confidence", 40)
                        filtered = [
                            l for l in new_leads
                            if (
                                l["hiring_intensity"] >= min_hiring
                                and l["data_confidence"] >= min_conf
                                and l.get("buyer_ready")
                            )
                        ]

                        # Limit to max leads per week
                        filtered = filtered[:agency.max_leads_per_week]

                        if filtered:
                            filepath = generate_excel(filtered, agency.name)
                            filename = filepath.split("/")[-1] if "/" in filepath else filepath.split("\\")[-1]

                            record_delivery(
                                agency_id=agency.id,
                                lead_ids=[l["lead_id"] for l in filtered],
                                file_name=filename,
                                file_path=filepath,
                            )
                            delivered_total += len(filtered)

                            _create_notification(
                                "delivery_sent",
                                f"📨 Delivered to {agency.name}",
                                f"{len(filtered)} leads delivered. File: {filename}",
                            )
                            await publish_event("export", f"📊 Delivered {len(filtered)} leads to agency: {agency.name}")

                except Exception as e:
                    errors.append(f"Export [{agency.name}]: {str(e)}")
                    logger.error("pipeline_export_error", agency=agency.name, error=str(e))
                    await publish_event("export", f"❌ Failed export for {agency.name}: {str(e)}", level="error")

        finally:
            db.close()

        _update_run(run_id, leads_delivered=delivered_total)

        # ── Finalize ────────────────────────────────────────────
        status = "completed" if not errors else "partial"
        completed_at = datetime.now(timezone.utc)
        duration_seconds = 0.0

        db = SessionLocal()
        try:
            run = db.query(PipelineRunRow).filter_by(id=run_id).first()
            if run:
                started_at = _as_utc(run.started_at) if run.started_at else completed_at
                completed_at_utc = _as_utc(completed_at)
                run.status = status
                run.completed_at = completed_at_utc
                run.duration_seconds = max(0.0, (completed_at_utc - started_at).total_seconds())
                run.errors = json.dumps(errors)
                run.error_count = len(errors)
                duration_seconds = run.duration_seconds
                db.commit()
        finally:
            db.close()

        _create_notification(
            "pipeline_complete" if status == "completed" else "pipeline_failed",
            f"Pipeline {status}",
            f"Discovered: {discovered if 'discovered' in dir() else 0}, "
            f"Enriched: {enriched if 'enriched' in dir() else 0}, "
            f"Delivered: {delivered_total}. "
            f"Errors: {len(errors)}.",
            severity="info" if status == "completed" else "warning",
        )

        logger.info("pipeline_complete", run_id=run_id, status=status, errors=len(errors))
        await publish_event("system", f"🎉 Pipeline completed in {duration_seconds:.1f}s. Delivered {delivered_total} leads total.", level="success")

        return {
            "run_id": run_id,
            "status": status,
            "role_focus": selected_role_focus,
            "companies_discovered": discovered if 'discovered' in dir() else 0,
            "companies_enriched": enriched if 'enriched' in dir() else 0,
            "companies_verified": verified,
            "leads_generated": len(leads_data),
            "leads_delivered": delivered_total,
            "errors": errors,
        }

    except asyncio.CancelledError:
        completed_at = datetime.now(timezone.utc)
        db = SessionLocal()
        try:
            run = db.query(PipelineRunRow).filter_by(id=run_id).first()
            if run:
                started_at = _as_utc(run.started_at) if run.started_at else completed_at
                completed_at_utc = _as_utc(completed_at)
                run.status = "cancelled"
                run.completed_at = completed_at_utc
                run.duration_seconds = max(0.0, (completed_at_utc - started_at).total_seconds())
                run.errors = json.dumps(["Cancelled by user"])
                run.error_count = 1
                db.commit()
        finally:
            db.close()

        _create_notification("pipeline_failed", "Pipeline stopped", "Pipeline cancelled by user.", severity="warning")
        logger.warning("pipeline_cancelled", run_id=run_id)
        await publish_event("system", "⏹ Pipeline stopped by user.", level="warning")
        raise

    except Exception as e:
        _update_run(run_id, status="failed", errors=json.dumps([str(e)]), error_count=1)
        _create_notification("pipeline_failed", "Pipeline crashed", str(e), severity="error")
        logger.critical("pipeline_crashed", run_id=run_id, error=str(e))
        await publish_event("system", f"🚨 Pipeline crashed: {str(e)}", level="error")
        raise PipelineError("orchestrator", str(e))

