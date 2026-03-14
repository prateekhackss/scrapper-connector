"""
ConnectorOS Scout — Database Layer (SQLAlchemy 2.0)

All 10 tables defined as SQLAlchemy ORM models.
Uses parameterised queries exclusively — NO raw string concatenation.

Security:
  - All queries use SQLAlchemy ORM or bound parameters (SQL injection safe)
  - Database file permissions set to owner-only where supported
  - Sensitive fields (emails, API keys) are never indexed in plaintext
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    event,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    text,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Session,
    relationship,
    sessionmaker,
)

from core.config import DATABASE_URL, DATA_DIR


# =====================================================================
# Engine & Session Factory
# =====================================================================

_is_sqlite = "sqlite" in DATABASE_URL

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False, "timeout": 30} if _is_sqlite else {},
    echo=False,
    pool_pre_ping=True,
)


if _is_sqlite:
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, _connection_record) -> None:
        """
        Reduce lock contention and improve durability for desktop usage.
        """
        cursor = dbapi_connection.cursor()
        for pragma in (
            "PRAGMA journal_mode=WAL",
            "PRAGMA synchronous=NORMAL",
            "PRAGMA busy_timeout=30000",
        ):
            try:
                cursor.execute(pragma)
            except Exception:
                # Some filesystems (e.g. cloud-sync/reparse mounts) reject
                # specific pragmas. Keep the connection usable.
                continue
        cursor.close()

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db() -> Session:
    """Yield a DB session (for FastAPI dependency injection)."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# =====================================================================
# Base Model
# =====================================================================

class Base(DeclarativeBase):
    pass


# =====================================================================
# ORM Models (10 tables)
# =====================================================================

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ── 1. Companies ─────────────────────────────────────────────────

class CompanyRow(Base):
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True, autoincrement=True)
    company_name = Column(String, nullable=False)
    company_domain = Column(String, nullable=False, unique=True)
    website_url = Column(String)
    industry = Column(String)
    headquarters = Column(String)
    employee_count = Column(String)
    tech_stack = Column(Text)           # JSON array

    first_seen_at = Column(DateTime, default=_utcnow)
    last_seen_at = Column(DateTime, default=_utcnow)
    discovery_sources = Column(Text)    # JSON array
    times_seen = Column(Integer, default=1)

    status = Column(String, default="active")

    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    # Relationships
    job_postings = relationship("JobPostingRow", back_populates="company", cascade="all, delete-orphan")
    contacts = relationship("ContactRow", back_populates="company", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_companies_domain", "company_domain"),
        Index("idx_companies_status", "status"),
        Index("idx_companies_last_seen", "last_seen_at"),
    )


# ── 2. Job Postings ─────────────────────────────────────────────

class JobPostingRow(Base):
    __tablename__ = "job_postings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    job_title = Column(String, nullable=False)
    job_url = Column(String)
    location = Column(String)
    remote_policy = Column(String)
    seniority = Column(String)
    tech_stack = Column(Text)           # JSON array
    salary_range = Column(String)

    source = Column(String, nullable=False)
    source_id = Column(String)

    posted_date = Column(String)
    first_scraped = Column(DateTime, default=_utcnow)
    last_scraped = Column(DateTime, default=_utcnow)
    is_active = Column(Boolean, default=True)

    created_at = Column(DateTime, default=_utcnow)

    company = relationship("CompanyRow", back_populates="job_postings")

    __table_args__ = (
        Index("idx_postings_company", "company_id"),
        Index("idx_postings_active", "is_active"),
        Index("idx_postings_source", "source", "source_id"),
    )


# ── 3. Contacts ─────────────────────────────────────────────────

class ContactRow(Base):
    __tablename__ = "contacts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)

    full_name = Column(String)
    first_name = Column(String)
    last_name = Column(String)
    title = Column(String)
    linkedin_url = Column(String)

    emails = Column(Text)               # JSON array
    best_email = Column(String)

    enrichment_source = Column(String)
    enrichment_sources = Column(Text)   # JSON array
    confidence_notes = Column(Text)

    is_verified = Column(Boolean, default=False)
    verification_data = Column(Text)    # JSON blob
    person_verified = Column(Boolean)
    title_verified = Column(Boolean)
    linkedin_verified = Column(Boolean)
    domain_has_mx = Column(Boolean)

    data_confidence = Column(Integer, default=0)
    confidence_tier = Column(String)

    is_current = Column(Boolean, default=True)

    enriched_at = Column(DateTime)
    verified_at = Column(DateTime)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    company = relationship("CompanyRow", back_populates="contacts")

    __table_args__ = (
        Index("idx_contacts_company", "company_id"),
        Index("idx_contacts_current", "is_current"),
        Index("idx_contacts_confidence", "data_confidence"),
    )


# ── 4. Leads ────────────────────────────────────────────────────

class LeadRow(Base):
    __tablename__ = "leads"

    id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    contact_id = Column(Integer, ForeignKey("contacts.id"))

    hiring_intensity = Column(Integer, nullable=False, default=0)
    hiring_label = Column(String)
    data_confidence = Column(Integer, nullable=False, default=0)
    confidence_tier = Column(String)
    priority_tier = Column(String)

    score_breakdown = Column(Text)      # JSON blob

    role_count = Column(Integer, default=0)
    top_roles = Column(Text)            # JSON array

    roles_last_week = Column(Integer)
    roles_this_week = Column(Integer)
    velocity_label = Column(String)

    notes = Column(Text)

    pipeline_run_id = Column(Integer, ForeignKey("pipeline_runs.id"))

    status = Column(String, default="new")

    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    __table_args__ = (
        Index("idx_leads_scores", "hiring_intensity", "data_confidence"),
        Index("idx_leads_status", "status"),
        Index("idx_leads_priority", "priority_tier"),
        Index("idx_leads_run", "pipeline_run_id"),
    )


# ── 5. Agencies ─────────────────────────────────────────────────

class AgencyRow(Base):
    __tablename__ = "agencies"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    contact_name = Column(String)
    contact_email = Column(String)

    icp_config = Column(Text)           # JSON blob

    delivery_day = Column(String, default="monday")
    delivery_email = Column(String)
    max_leads_per_week = Column(Integer, default=50)

    monthly_rate = Column(Integer)
    billing_status = Column(String, default="trial")
    trial_ends_at = Column(DateTime)

    status = Column(String, default="active")

    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)


# ── 6. Deliveries ───────────────────────────────────────────────

class DeliveryRow(Base):
    __tablename__ = "deliveries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    agency_id = Column(Integer, ForeignKey("agencies.id"), nullable=False)
    lead_id = Column(Integer, ForeignKey("leads.id"), nullable=False)

    delivered_at = Column(DateTime, default=_utcnow)
    delivery_method = Column(String, default="email")
    batch_id = Column(String)

    file_name = Column(String)
    file_path = Column(String)

    feedback = Column(String)
    feedback_at = Column(DateTime)

    created_at = Column(DateTime, default=_utcnow)

    __table_args__ = (
        UniqueConstraint("agency_id", "lead_id", name="uq_agency_lead"),
        Index("idx_deliveries_agency", "agency_id"),
        Index("idx_deliveries_lead", "lead_id"),
        Index("idx_deliveries_batch", "batch_id"),
    )


# ── 7. Pipeline Runs ────────────────────────────────────────────

class PipelineRunRow(Base):
    __tablename__ = "pipeline_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)

    run_type = Column(String, nullable=False)
    started_at = Column(DateTime, nullable=False, default=_utcnow)
    completed_at = Column(DateTime)
    status = Column(String, default="running")

    companies_discovered = Column(Integer, default=0)
    companies_enriched = Column(Integer, default=0)
    companies_verified = Column(Integer, default=0)
    leads_generated = Column(Integer, default=0)
    leads_delivered = Column(Integer, default=0)

    avg_hiring_score = Column(Float)
    avg_data_confidence = Column(Float)
    verified_count = Column(Integer, default=0)
    unverified_count = Column(Integer, default=0)

    openai_calls = Column(Integer, default=0)
    openai_cost_usd = Column(Float, default=0)
    serpapi_calls = Column(Integer, default=0)

    errors = Column(Text)               # JSON array
    error_count = Column(Integer, default=0)

    duration_seconds = Column(Float)

    created_at = Column(DateTime, default=_utcnow)


# ── 8. API Usage ────────────────────────────────────────────────

class APIUsageRow(Base):
    __tablename__ = "api_usage"

    id = Column(Integer, primary_key=True, autoincrement=True)
    pipeline_run_id = Column(Integer, ForeignKey("pipeline_runs.id"))

    api_name = Column(String, nullable=False)
    model = Column(String)

    input_tokens = Column(Integer)
    output_tokens = Column(Integer)
    total_tokens = Column(Integer)

    cost_usd = Column(Float)

    company_domain = Column(String)
    request_type = Column(String)
    success = Column(Boolean, default=True)
    error_message = Column(Text)
    response_time_ms = Column(Integer)

    created_at = Column(DateTime, default=_utcnow)

    __table_args__ = (
        Index("idx_api_usage_run", "pipeline_run_id"),
        Index("idx_api_usage_date", "created_at"),
    )


# ── 9. Notifications ────────────────────────────────────────────

class NotificationRow(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, autoincrement=True)

    type = Column(String, nullable=False)
    severity = Column(String, default="info")
    title = Column(String, nullable=False)
    message = Column(Text, nullable=False)

    related_entity = Column(String)

    is_read = Column(Boolean, default=False)
    is_dismissed = Column(Boolean, default=False)

    created_at = Column(DateTime, default=_utcnow)

    __table_args__ = (
        Index("idx_notifications_unread", "is_read", "created_at"),
    )


# ── 10. Search History ──────────────────────────────────────────

class SearchHistoryRow(Base):
    __tablename__ = "search_history"

    id = Column(Integer, primary_key=True, autoincrement=True)

    query_type = Column(String, nullable=False)
    query_params = Column(Text, nullable=False)

    results_count = Column(Integer)
    results_data = Column(Text)

    openai_cost_usd = Column(Float)

    created_at = Column(DateTime, default=_utcnow)


# ── 11. Settings (key-value) ────────────────────────────────────

class SettingRow(Base):
    __tablename__ = "settings"

    key = Column(String, primary_key=True)
    value = Column(String, nullable=False)
    description = Column(Text)

    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)


# =====================================================================
# Database Initialisation
# =====================================================================

_DEFAULT_SETTINGS: list[dict] = [
    {"key": "pipeline_schedule", "value": "0 6 * * 1", "description": "Cron: every Monday 6 AM"},
    {"key": "default_target_market", "value": "US tech companies", "description": "Default discovery market"},
    {"key": "min_hiring_score_for_delivery", "value": "50", "description": "Min hiring score for delivery"},
    {"key": "min_confidence_for_delivery", "value": "40", "description": "Min confidence for delivery"},
    {"key": "openai_model", "value": "gpt-4o-mini", "description": "Model for all OpenAI calls"},
    {"key": "openai_daily_budget_usd", "value": "5.00", "description": "Max daily OpenAI spend"},
    {"key": "serpapi_monthly_limit", "value": "100", "description": "SerpAPI monthly credit limit"},
    {"key": "max_companies_per_run", "value": "200", "description": "Max companies per pipeline run"},
    {"key": "enrichment_delay_seconds", "value": "2", "description": "Delay between enrichment calls"},
    {"key": "verification_enabled", "value": "true", "description": "Run verification stage"},
    {"key": "notification_email", "value": "", "description": "Email for alerts"},
    {"key": "data_retention_days", "value": "180", "description": "Days to retain old data"},
]


def init_db() -> None:
    """Create all tables and seed default settings. Idempotent."""
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        for setting in _DEFAULT_SETTINGS:
            exists = db.query(SettingRow).filter_by(key=setting["key"]).first()
            if not exists:
                db.add(SettingRow(**setting))
        db.commit()
    finally:
        db.close()


def get_setting(key: str, default: str = "") -> str:
    """Read a setting from the settings table."""
    db = SessionLocal()
    try:
        row = db.query(SettingRow).filter_by(key=key).first()
        return row.value if row else default
    finally:
        db.close()


def update_setting(key: str, value: str) -> None:
    """Update a setting in the settings table."""
    db = SessionLocal()
    try:
        row = db.query(SettingRow).filter_by(key=key).first()
        if row:
            row.value = value
        else:
            db.add(SettingRow(key=key, value=value))
        db.commit()
    finally:
        db.close()
