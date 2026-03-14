"""
ConnectorOS Scout — Notifications API Routes
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from core.database import SessionLocal, NotificationRow
from core.logger import get_logger

logger = get_logger("api.notifications")
router = APIRouter()


@router.get("")
async def list_notifications(unread_only: bool = False, limit: int = 50):
    """List notifications."""
    db = SessionLocal()
    try:
        query = db.query(NotificationRow)
        if unread_only:
            query = query.filter_by(is_read=False, is_dismissed=False)
        else:
            query = query.filter_by(is_dismissed=False)

        rows = query.order_by(NotificationRow.created_at.desc()).limit(limit).all()

        return [
            {
                "id": n.id,
                "type": n.type,
                "severity": n.severity,
                "title": n.title,
                "message": n.message,
                "related_entity": n.related_entity,
                "is_read": n.is_read,
                "created_at": n.created_at.isoformat() if n.created_at else None,
            }
            for n in rows
        ]
    finally:
        db.close()


@router.get("/count")
async def unread_count():
    """Get unread notification count."""
    db = SessionLocal()
    try:
        count = db.query(NotificationRow).filter_by(is_read=False, is_dismissed=False).count()
        return {"unread": count}
    finally:
        db.close()


@router.patch("/{notif_id}/read")
async def mark_read(notif_id: int):
    """Mark a notification as read."""
    db = SessionLocal()
    try:
        notif = db.query(NotificationRow).filter_by(id=notif_id).first()
        if not notif:
            raise HTTPException(status_code=404, detail="Notification not found")
        notif.is_read = True
        db.commit()
        return {"status": "marked_read"}
    finally:
        db.close()


@router.patch("/{notif_id}/dismiss")
async def dismiss_notification(notif_id: int):
    """Dismiss a notification."""
    db = SessionLocal()
    try:
        notif = db.query(NotificationRow).filter_by(id=notif_id).first()
        if not notif:
            raise HTTPException(status_code=404, detail="Notification not found")
        notif.is_dismissed = True
        db.commit()
        return {"status": "dismissed"}
    finally:
        db.close()


@router.post("/mark-all-read")
async def mark_all_read():
    """Mark all notifications as read."""
    db = SessionLocal()
    try:
        db.query(NotificationRow).filter_by(is_read=False).update({"is_read": True})
        db.commit()
        return {"status": "all_marked_read"}
    finally:
        db.close()
