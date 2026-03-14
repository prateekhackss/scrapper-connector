"""
ConnectorOS Scout — Settings API Routes

Security:
  - API keys are masked when returned (only last 4 chars visible)
  - Settings values are validated before storage
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from core.database import SessionLocal, SettingRow, get_setting, update_setting
from core.config import mask_value
from core.logger import get_logger

logger = get_logger("api.settings")
router = APIRouter()


class SettingUpdate(BaseModel):
    key: str
    value: str


@router.get("")
async def list_settings():
    """List all settings (sensitive values masked)."""
    db = SessionLocal()
    try:
        rows = db.query(SettingRow).all()
        return [
            {
                "key": r.key,
                "value": mask_value(r.key, r.value) if "key" in r.key.lower() or "secret" in r.key.lower() else r.value,
                "description": r.description,
            }
            for r in rows
        ]
    finally:
        db.close()


@router.patch("")
async def update_settings(updates: list[SettingUpdate]):
    """Update one or more settings."""
    for update in updates:
        update_setting(update.key, update.value)
        logger.info("setting_updated", key=update.key)
    return {"status": "updated", "count": len(updates)}


@router.post("/test-api-key")
async def test_api_key(api_name: str, api_key: str):
    """Test if an API key is valid."""
    if api_name == "openai":
        from openai import AsyncOpenAI
        try:
            client = AsyncOpenAI(api_key=api_key)
            # Simple model list call to verify key
            await client.models.list()
            return {"valid": True, "message": "OpenAI API key is valid."}
        except Exception as e:
            return {"valid": False, "message": f"OpenAI key test failed: {str(e)}"}

    elif api_name == "serpapi":
        import httpx
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    "https://serpapi.com/account.json",
                    params={"api_key": api_key},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return {
                        "valid": True,
                        "message": f"SerpAPI key valid. Credits remaining: {data.get('total_searches_left', 'unknown')}",
                    }
                return {"valid": False, "message": f"SerpAPI returned status {resp.status_code}"}
        except Exception as e:
            return {"valid": False, "message": f"SerpAPI test failed: {str(e)}"}

    raise HTTPException(status_code=400, detail=f"Unknown API: {api_name}")
