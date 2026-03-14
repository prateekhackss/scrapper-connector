"""
ConnectorOS Scout — CSV Generator

Simple CSV export with UTF-8 BOM for Excel compatibility.

Security:
  - Filenames sanitized to prevent directory traversal
  - CSV injection mitigated: values starting with =, +, -, @ are prefixed with apostrophe
"""

from __future__ import annotations

import csv
import re
from datetime import datetime, timezone
from pathlib import Path

from core.config import EXPORTS_DIR
from core.logger import get_logger

logger = get_logger("export.csv")

_CSV_COLUMNS = [
    "Company", "Website", "Location", "Industry", "Employees",
    "Open Roles", "Top Roles", "Tech Stack", "Hiring Score",
    "Hiring Label", "Contact Name", "Contact Title", "Best Email",
    "LinkedIn", "Data Confidence", "Confidence Tier", "Notes",
]

# Characters that could trigger formula injection in spreadsheets
_INJECTION_CHARS = ("=", "+", "-", "@", "\t", "\r", "\n")


def _sanitize_csv_value(value: str) -> str:
    """Prevent CSV injection by prefixing dangerous characters."""
    if isinstance(value, str) and value and value[0] in _INJECTION_CHARS:
        return "'" + value
    return value


def _sanitize_filename(name: str) -> str:
    """Remove unsafe characters from filenames."""
    return re.sub(r"[^\w\s\-.]", "", name).strip()


def generate_csv(
    leads: list[dict],
    agency_name: str = "Default",
) -> str:
    """
    Generate a CSV file of leads.

    Args:
        leads: List of lead dicts.
        agency_name: Agency name (used in filename).

    Returns:
        Absolute path to the generated CSV file.
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    safe_name = _sanitize_filename(agency_name)
    filename = f"ConnectorOS_{safe_name}_{today}.csv"
    filepath = EXPORTS_DIR / filename

    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(_CSV_COLUMNS)

        for lead in leads:
            row = [
                _sanitize_csv_value(str(lead.get("company_name", ""))),
                _sanitize_csv_value(str(lead.get("website_url", ""))),
                _sanitize_csv_value(str(lead.get("headquarters", ""))),
                _sanitize_csv_value(str(lead.get("industry", ""))),
                str(lead.get("employee_count", "")),
                str(lead.get("role_count", 0)),
                _sanitize_csv_value(", ".join(lead.get("top_roles", []))),
                _sanitize_csv_value(", ".join(lead.get("tech_stack", []))),
                str(lead.get("hiring_intensity", 0)),
                str(lead.get("hiring_label", "")),
                _sanitize_csv_value(str(lead.get("contact_name", ""))),
                _sanitize_csv_value(str(lead.get("contact_title", ""))),
                _sanitize_csv_value(str(lead.get("best_email", ""))),
                _sanitize_csv_value(str(lead.get("linkedin_url", ""))),
                str(lead.get("data_confidence", 0)),
                str(lead.get("confidence_tier", "")),
                _sanitize_csv_value(str(lead.get("notes", ""))),
            ]
            writer.writerow(row)

    logger.info("csv_generated", file=str(filepath), rows=len(leads))
    return str(filepath)
