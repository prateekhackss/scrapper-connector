"""
ConnectorOS Scout — Delivery Ledger

Tracks which leads have been sent to which agencies.
Prevents duplicate deliveries via unique constraint.

Security:
  - Unique index (agency_id, lead_id) prevents double-delivery
  - All DB operations use ORM (SQL injection safe)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from core.database import SessionLocal, DeliveryRow, LeadRow
from core.logger import get_logger

logger = get_logger("export.delivery")


def get_already_delivered_lead_ids(agency_id: int) -> set[int]:
    """Return set of lead IDs already delivered to this agency."""
    db = SessionLocal()
    try:
        rows = db.query(DeliveryRow.lead_id).filter_by(agency_id=agency_id).all()
        return {r.lead_id for r in rows}
    finally:
        db.close()


def record_delivery(
    agency_id: int,
    lead_ids: list[int],
    file_name: str,
    file_path: str,
    delivery_method: str = "dashboard_download",
) -> str:
    """
    Record a batch delivery to the deliveries table.

    Args:
        agency_id: Target agency ID.
        lead_ids: List of lead IDs being delivered.
        file_name: Generated file name.
        file_path: Generated file path.
        delivery_method: How the delivery was made.

    Returns:
        Batch ID for this delivery.
    """
    batch_id = str(uuid.uuid4())[:8]
    now = datetime.now(timezone.utc)

    db = SessionLocal()
    try:
        for lead_id in lead_ids:
            # Check if already delivered (extra safety beyond DB constraint)
            exists = db.query(DeliveryRow).filter_by(
                agency_id=agency_id, lead_id=lead_id
            ).first()

            if exists:
                logger.warning("delivery_duplicate_skipped", agency_id=agency_id, lead_id=lead_id)
                continue

            row = DeliveryRow(
                agency_id=agency_id,
                lead_id=lead_id,
                delivered_at=now,
                delivery_method=delivery_method,
                batch_id=batch_id,
                file_name=file_name,
                file_path=file_path,
            )
            db.add(row)

            # Update lead status
            lead = db.query(LeadRow).filter_by(id=lead_id).first()
            if lead:
                lead.status = "delivered"

        db.commit()
        logger.info("delivery_recorded", agency_id=agency_id, batch_id=batch_id, count=len(lead_ids))

    except Exception as e:
        db.rollback()
        logger.error("delivery_record_error", error=str(e))
        raise
    finally:
        db.close()

    return batch_id
