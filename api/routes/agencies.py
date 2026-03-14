"""
ConnectorOS Scout — Agency API Routes

CRUD for agencies including ICP configuration and delivery history.
"""

from __future__ import annotations

import json
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from core.database import SessionLocal, AgencyRow, DeliveryRow
from core.logger import get_logger

logger = get_logger("api.agencies")
router = APIRouter()


class AgencyCreate(BaseModel):
    name: str
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    icp_config: Optional[dict] = None
    delivery_day: str = "monday"
    delivery_email: Optional[str] = None
    max_leads_per_week: int = 50
    monthly_rate: Optional[int] = None
    billing_status: str = "trial"


class AgencyUpdate(BaseModel):
    name: Optional[str] = None
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    icp_config: Optional[dict] = None
    delivery_day: Optional[str] = None
    delivery_email: Optional[str] = None
    max_leads_per_week: Optional[int] = None
    monthly_rate: Optional[int] = None
    billing_status: Optional[str] = None
    status: Optional[str] = None


@router.get("")
async def list_agencies():
    """List all agencies."""
    db = SessionLocal()
    try:
        agencies = db.query(AgencyRow).all()
        result = []
        for a in agencies:
            delivered_count = db.query(DeliveryRow).filter_by(agency_id=a.id).count()
            last_delivery = (
                db.query(DeliveryRow)
                .filter_by(agency_id=a.id)
                .order_by(DeliveryRow.delivered_at.desc())
                .first()
            )
            result.append({
                "id": a.id,
                "name": a.name,
                "contact_name": a.contact_name,
                "contact_email": a.contact_email,
                "icp_config": json.loads(a.icp_config or "{}"),
                "delivery_day": a.delivery_day,
                "delivery_email": a.delivery_email,
                "max_leads_per_week": a.max_leads_per_week,
                "monthly_rate": a.monthly_rate,
                "billing_status": a.billing_status,
                "status": a.status,
                "total_leads_sent": delivered_count,
                "last_delivery": last_delivery.delivered_at.isoformat() if last_delivery and last_delivery.delivered_at else None,
            })
        return result
    finally:
        db.close()


@router.post("")
async def create_agency(data: AgencyCreate):
    """Create a new agency."""
    db = SessionLocal()
    try:
        agency = AgencyRow(
            name=data.name,
            contact_name=data.contact_name,
            contact_email=data.contact_email,
            icp_config=json.dumps(data.icp_config or {}),
            delivery_day=data.delivery_day,
            delivery_email=data.delivery_email,
            max_leads_per_week=data.max_leads_per_week,
            monthly_rate=data.monthly_rate,
            billing_status=data.billing_status,
        )
        db.add(agency)
        db.commit()
        return {"id": agency.id, "name": agency.name, "status": "created"}
    finally:
        db.close()


@router.get("/{agency_id}")
async def get_agency(agency_id: int):
    """Get agency details with delivery history."""
    db = SessionLocal()
    try:
        agency = db.query(AgencyRow).filter_by(id=agency_id).first()
        if not agency:
            raise HTTPException(status_code=404, detail="Agency not found")

        deliveries = (
            db.query(DeliveryRow)
            .filter_by(agency_id=agency_id)
            .order_by(DeliveryRow.delivered_at.desc())
            .limit(20)
            .all()
        )

        return {
            "id": agency.id,
            "name": agency.name,
            "contact_name": agency.contact_name,
            "contact_email": agency.contact_email,
            "icp_config": json.loads(agency.icp_config or "{}"),
            "delivery_day": agency.delivery_day,
            "delivery_email": agency.delivery_email,
            "max_leads_per_week": agency.max_leads_per_week,
            "monthly_rate": agency.monthly_rate,
            "billing_status": agency.billing_status,
            "status": agency.status,
            "deliveries": [
                {
                    "id": d.id,
                    "delivered_at": d.delivered_at.isoformat() if d.delivered_at else None,
                    "batch_id": d.batch_id,
                    "file_name": d.file_name,
                    "feedback": d.feedback,
                }
                for d in deliveries
            ],
        }
    finally:
        db.close()


@router.patch("/{agency_id}")
async def update_agency(agency_id: int, data: AgencyUpdate):
    """Update agency details."""
    db = SessionLocal()
    try:
        agency = db.query(AgencyRow).filter_by(id=agency_id).first()
        if not agency:
            raise HTTPException(status_code=404, detail="Agency not found")

        if data.name is not None:
            agency.name = data.name
        if data.contact_name is not None:
            agency.contact_name = data.contact_name
        if data.contact_email is not None:
            agency.contact_email = data.contact_email
        if data.icp_config is not None:
            agency.icp_config = json.dumps(data.icp_config)
        if data.delivery_day is not None:
            agency.delivery_day = data.delivery_day
        if data.delivery_email is not None:
            agency.delivery_email = data.delivery_email
        if data.max_leads_per_week is not None:
            agency.max_leads_per_week = data.max_leads_per_week
        if data.monthly_rate is not None:
            agency.monthly_rate = data.monthly_rate
        if data.billing_status is not None:
            agency.billing_status = data.billing_status
        if data.status is not None:
            agency.status = data.status

        db.commit()
        return {"id": agency.id, "status": "updated"}
    finally:
        db.close()


@router.delete("/{agency_id}")
async def delete_agency(agency_id: int):
    """Delete an agency."""
    db = SessionLocal()
    try:
        agency = db.query(AgencyRow).filter_by(id=agency_id).first()
        if not agency:
            raise HTTPException(status_code=404, detail="Agency not found")
        db.delete(agency)
        db.commit()
        return {"status": "deleted"}
    finally:
        db.close()
