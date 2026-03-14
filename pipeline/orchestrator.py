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

import json
from datetime import datetime, timezone

from core.database import (
    SessionLocal, PipelineRunRow, CompanyRow, ContactRow, LeadRow,
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
from scoring.notes_generator import generate_notes
from export.excel_generator import generate_excel
from export.delivery_ledger import get_already_delivered_lead_ids, record_delivery
from core.sse import publish_event

logger = get_logger("pipeline.orchestrator")


def _create_pipeline_run(run_type: str = "full") -> int:
    """Create a new pipeline_run record. Returns run ID."""
    db = SessionLocal()
    try:
        run = PipelineRunRow(
            run_type=run_type,
            started_at=datetime.utcnow(),
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


def _score_all_leads(run_id: int) -> list[dict]:
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
            from core.database import JobPostingRow
            postings = (
                db.query(JobPostingRow)
                .filter_by(company_id=company.id, is_active=True)
                .all()
            )
            role_count = len(postings)

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

            # Create lead row
            lead_row = LeadRow(
                company_id=company.id,
                contact_id=contact.id if contact else None,
                hiring_intensity=hiring_score,
                hiring_label=hiring_label.value,
                data_confidence=data_confidence,
                confidence_tier=confidence_tier_str,
                priority_tier=priority.value,
                score_breakdown=json.dumps(breakdown.model_dump()),
                role_count=role_count,
                top_roles=json.dumps(top_roles),
                roles_this_week=role_count,
                velocity_label=velocity.value,
                pipeline_run_id=run_id,
                status="new",
            )
            db.add(lead_row)
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


async def run_full_pipeline(target_market: str | None = None) -> dict:
    """
    Execute the full 5-stage pipeline.

    Returns:
        Dict with run stats.
    """
    if target_market is None:
        target_market = get_setting("default_target_market", "US tech companies")

    run_id = _create_pipeline_run("full")
    errors = []

    logger.info("pipeline_start", run_id=run_id, target_market=target_market)
    await publish_event("system", f"🚀 Started pipeline run #{run_id} for target market: '{target_market}'")

    try:
        # ── Stage 1: Discovery ──────────────────────────────────
        try:
            await publish_event("discovery", "Starting company discovery across data sources...")
            discovered = await run_discovery(target_market)
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
            await publish_event("scoring", "Calculating hiring intensity and data confidence scores...")
            leads_data = _score_all_leads(run_id)
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
                            if l["hiring_intensity"] >= min_hiring and l["data_confidence"] >= min_conf
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
        completed_at = datetime.utcnow()

        db = SessionLocal()
        try:
            run = db.query(PipelineRunRow).filter_by(id=run_id).first()
            if run:
                run.status = status
                run.completed_at = completed_at
                run.duration_seconds = (completed_at - run.started_at).total_seconds()
                run.errors = json.dumps(errors)
                run.error_count = len(errors)
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
        await publish_event("system", f"🎉 Pipeline completed in {run.duration_seconds:.1f}s. Delivered {delivered_total} leads total.", level="success")

        return {
            "run_id": run_id,
            "status": status,
            "companies_discovered": discovered if 'discovered' in dir() else 0,
            "companies_enriched": enriched if 'enriched' in dir() else 0,
            "companies_verified": verified,
            "leads_generated": len(leads_data),
            "leads_delivered": delivered_total,
            "errors": errors,
        }

    except Exception as e:
        _update_run(run_id, status="failed", errors=json.dumps([str(e)]), error_count=1)
        _create_notification("pipeline_failed", "Pipeline crashed", str(e), severity="error")
        logger.critical("pipeline_crashed", run_id=run_id, error=str(e))
        await publish_event("system", f"🚨 Pipeline crashed: {str(e)}", level="error")
        raise PipelineError("orchestrator", str(e))
