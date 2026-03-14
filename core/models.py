"""
ConnectorOS Scout — Pydantic Data Models (v2)

All data contracts for the system. Every piece of data flows through
these models for type safety and validation.

Security:
  - Email fields are validated via regex
  - Domain fields are normalized (lowercase, stripped)
  - Enum fields prevent injection of arbitrary status values
"""

from __future__ import annotations

import re
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


# =====================================================================
# Enums — restrict valid values to prevent arbitrary string injection
# =====================================================================

class HiringLabel(str, Enum):
    RED_HOT = "RED_HOT"       # 80-100
    WARM = "WARM"             # 60-79
    COOL = "COOL"             # 40-59
    COLD = "COLD"             # 0-39


class ConfidenceTier(str, Enum):
    VERIFIED = "VERIFIED"     # 80-100
    LIKELY = "LIKELY"         # 60-79
    UNCERTAIN = "UNCERTAIN"   # 40-59
    UNVERIFIED = "UNVERIFIED" # 0-39


class PriorityTier(str, Enum):
    PRIORITY = "PRIORITY"     # high hiring + high confidence
    REVIEW = "REVIEW"         # high hiring + low confidence
    NURTURE = "NURTURE"       # low hiring + high confidence
    ARCHIVE = "ARCHIVE"       # low hiring + low confidence


class VelocityLabel(str, Enum):
    ACCELERATING = "ACCELERATING"  # roles_this_week > roles_last_week * 1.3
    STABLE = "STABLE"              # within ±30%
    DECLINING = "DECLINING"        # roles_this_week < roles_last_week * 0.7
    NEW = "NEW"                    # first time seen


class LeadStatus(str, Enum):
    NEW = "new"
    DELIVERED = "delivered"
    REJECTED = "rejected"
    ARCHIVED = "archived"


class RunStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"


class NotificationType(str, Enum):
    PIPELINE_COMPLETE = "pipeline_complete"
    PIPELINE_FAILED = "pipeline_failed"
    HOT_LEAD_FOUND = "hot_lead_found"
    API_LIMIT_WARNING = "api_limit_warning"
    SERPAPI_LOW = "serpapi_low"
    DELIVERY_SENT = "delivery_sent"
    VERIFICATION_FAILURE_RATE = "verification_failure_rate"
    NEW_AGENCY_SIGNUP = "new_agency_signup"
    ERROR = "error"


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


# =====================================================================
# Data Models
# =====================================================================

# ── Email ────────────────────────────────────────────────────────

_EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")


class EmailEntry(BaseModel):
    email: str
    confidence: str = "medium"  # high | medium | low

    @field_validator("email")
    @classmethod
    def validate_email_format(cls, v: str) -> str:
        v = v.strip().lower()
        if not _EMAIL_REGEX.match(v):
            raise ValueError(f"Invalid email format: {v}")
        return v


# ── Company ──────────────────────────────────────────────────────

class CompanyBase(BaseModel):
    company_name: str
    company_domain: str
    website_url: Optional[str] = None
    industry: Optional[str] = None
    headquarters: Optional[str] = None
    employee_count: Optional[str] = None
    tech_stack: list[str] = []
    discovery_sources: list[str] = []
    discovery_source_urls: list[str] = []

    @field_validator("company_domain")
    @classmethod
    def normalize_domain(cls, v: str) -> str:
        """Lowercase, strip www. and trailing slash to avoid duplicates."""
        v = v.strip().lower()
        if v.startswith("http://"):
            v = v[7:]
        if v.startswith("https://"):
            v = v[8:]
        if v.startswith("www."):
            v = v[4:]
        return v.rstrip("/")


# ── Job Posting ──────────────────────────────────────────────────

class JobPosting(BaseModel):
    company_domain: Optional[str] = None
    job_title: str
    job_url: Optional[str] = None
    location: Optional[str] = None
    remote_policy: Optional[str] = None   # onsite | remote | hybrid
    seniority: Optional[str] = None       # junior | mid | senior | lead | vp
    tech_stack: list[str] = []
    salary_range: Optional[str] = None
    source: str                           # serpapi | remoteok | hn | wellfound | openai
    source_id: Optional[str] = None
    posted_date: Optional[str] = None
    evidence_urls: list[str] = []


# ── Contact ──────────────────────────────────────────────────────

class ContactData(BaseModel):
    found: bool = False
    full_name: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    title: Optional[str] = None
    linkedin_url: Optional[str] = None
    emails: list[EmailEntry] = []
    best_email: Optional[str] = None
    enrichment_source: str = "unknown"
    enrichment_sources: list[str] = []
    source_urls: list[str] = []
    found_on_date: Optional[str] = None
    proof_quality: Optional[str] = None
    confidence_notes: Optional[str] = None


# ── Verification ─────────────────────────────────────────────────

class VerificationResult(BaseModel):
    person_verified: Optional[bool] = None
    person_detail: Optional[str] = None
    title_current: Optional[bool] = None
    current_title_if_different: Optional[str] = None
    company_actively_hiring: Optional[bool] = None
    domain_active: Optional[bool] = None
    domain_has_mx: Optional[bool] = None
    linkedin_url_valid: Optional[bool] = None
    name_plausible: Optional[bool] = None
    is_duplicate_contact: Optional[bool] = None
    email_format_valid: Optional[bool] = None
    verification_sources: list[str] = []
    overall_confidence: Optional[str] = None


# ── Scoring ──────────────────────────────────────────────────────

class ScoreBreakdown(BaseModel):
    role_count_score: int = 0        # max 25
    velocity_score: int = 0          # max 20
    seniority_score: int = 0         # max 15
    multi_source_score: int = 0      # max 15
    role_age_score: int = 0          # max 15
    promoted_ads_score: int = 0      # max 10
    total: int = 0                   # max 100


# ── Lead (composite) ────────────────────────────────────────────

class Lead(BaseModel):
    company: CompanyBase
    contact: Optional[ContactData] = None
    verification: Optional[VerificationResult] = None

    job_postings: list[JobPosting] = []
    role_count: int = 0
    top_roles: list[str] = []

    hiring_intensity: int = 0
    hiring_label: Optional[HiringLabel] = None
    data_confidence: int = 0
    confidence_tier: Optional[ConfidenceTier] = None
    priority_tier: Optional[PriorityTier] = None

    score_breakdown: Optional[ScoreBreakdown] = None
    velocity_label: Optional[VelocityLabel] = None
    roles_last_week: Optional[int] = None
    roles_this_week: Optional[int] = None

    notes: Optional[str] = None


# ── Agency ───────────────────────────────────────────────────────

class AgencyICP(BaseModel):
    target_industries: list[str] = []
    target_locations: list[str] = []
    min_employee_count: Optional[int] = None
    max_employee_count: Optional[int] = None
    min_hiring_score: int = 50
    min_confidence: int = 40
    preferred_tech_stack: list[str] = []
    excluded_companies: list[str] = []


class Agency(BaseModel):
    id: Optional[int] = None
    name: str
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    icp_config: AgencyICP = AgencyICP()
    delivery_day: str = "monday"
    delivery_email: Optional[str] = None
    max_leads_per_week: int = 50
    monthly_rate: Optional[int] = None
    billing_status: str = "trial"
    status: str = "active"


# ── Pipeline Run ─────────────────────────────────────────────────

class PipelineRunStats(BaseModel):
    id: Optional[int] = None
    run_type: str = "full"
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    status: str = "running"

    companies_discovered: int = 0
    companies_enriched: int = 0
    companies_verified: int = 0
    leads_generated: int = 0
    leads_delivered: int = 0

    avg_hiring_score: Optional[float] = None
    avg_data_confidence: Optional[float] = None
    verified_count: int = 0
    unverified_count: int = 0

    openai_calls: int = 0
    openai_cost_usd: float = 0.0
    serpapi_calls: int = 0

    errors: list[str] = []
    error_count: int = 0
    duration_seconds: Optional[float] = None


# ── Notification ─────────────────────────────────────────────────

class NotificationData(BaseModel):
    id: Optional[int] = None
    type: str
    severity: str = "info"
    title: str
    message: str
    related_entity: Optional[str] = None
    is_read: bool = False
    is_dismissed: bool = False
    created_at: Optional[datetime] = None


# ── API Usage ────────────────────────────────────────────────────

class APIUsageEntry(BaseModel):
    api_name: str
    model: Optional[str] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    cost_usd: Optional[float] = None
    company_domain: Optional[str] = None
    request_type: Optional[str] = None
    success: bool = True
    error_message: Optional[str] = None
    response_time_ms: Optional[int] = None
