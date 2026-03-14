# ConnectorOS Scout — Complete Technical Specification v2.0

> **This document contains EVERYTHING you need to build the entire system.**
> Every database table, every API call, every dashboard page, every edge case.
> If it's not in this doc, you don't need it for the MVP.

---

## Table of Contents

1. [System Overview & Architecture](#1-system-overview)
2. [Database Schema (Complete)](#2-database-schema)
3. [Pydantic Models (Complete)](#3-pydantic-models)
4. [Stage 1: Discovery Engine](#4-stage-1-discovery)
5. [Stage 2: Enrichment Engine](#5-stage-2-enrichment)
6. [Stage 3: Verification Engine](#6-stage-3-verification)
7. [Stage 4: Scoring Engine](#7-stage-4-scoring)
8. [Stage 5: Export Engine](#8-stage-5-export)
9. [Stage 6: Dashboard (Complete Wireframes)](#9-stage-6-dashboard)
10. [Manual Search Interface](#10-manual-search)
11. [Automation & Scheduling](#11-automation)
12. [Agency Management System](#12-agency-management)
13. [Notification System](#13-notifications)
14. [Rate Limiting & Queue Management](#14-rate-limiting)
15. [Logging Architecture](#15-logging)
16. [Error Recovery & Retry](#16-error-recovery)
17. [Data Retention & Cleanup](#17-data-retention)
18. [Settings & Configuration](#18-settings)
19. [All OpenAI Prompts (Final)](#19-prompts)
20. [Complete File Structure](#20-file-structure)
21. [Dependencies & Requirements](#21-dependencies)
22. [Build Order (Day by Day)](#22-build-order)
23. [Cost Breakdown (Final)](#23-costs)

---

## 1. System Overview

### What ConnectorOS Scout Does
Automatically discovers tech companies that are actively hiring, finds the right decision-maker at each company, verifies every data point, scores leads by urgency and data quality, exports agency-ready Excel files, and provides a real-time dashboard for monitoring everything.

### Architecture Principle
**OpenAI is the brain. Your code is the memory and the muscles.**
- OpenAI (with web search) = finds companies, finds contacts, verifies data
- Your Python code = stores everything in a database, tracks changes over time, deduplicates, scores, exports, schedules
- The database = your moat. It accumulates value every week. After 6 months you have intelligence that no single ChatGPT session can replicate.

### Tech Stack
| Component | Tool | Why |
|-----------|------|-----|
| Language | Python 3.11+ | You know it, it works |
| Web Framework | FastAPI | Your API layer (already built) |
| Dashboard | Streamlit | Fastest to build, Python-native |
| Database | SQLite (MVP) → PostgreSQL (scale) | Zero config to start |
| ORM | SQLAlchemy 2.0 | Type-safe, migration support |
| AI | OpenAI API (gpt-4o-mini + web_search_preview) | One API key for everything |
| Job Boards | SerpAPI (Google Jobs) | Already integrated |
| Excel Export | openpyxl | Multi-sheet, formatted Excel |
| Scheduling | APScheduler | Python-native cron |
| Validation | Pydantic v2 | Data integrity everywhere |
| HTTP Client | httpx | Async support, timeouts, retries |
| DNS Checks | dnspython | MX record verification |
| Logging | structlog | JSON structured logs |
| Charts | Plotly (via Streamlit) | Interactive, beautiful |

---

## 2. Database Schema (Complete)

### Table: `companies`
The core table. One row per unique company domain.

```sql
CREATE TABLE companies (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    company_name    TEXT NOT NULL,
    company_domain  TEXT NOT NULL UNIQUE,  -- normalized: lowercase, no www, no trailing slash
    website_url     TEXT,                   -- full URL with https://
    industry        TEXT,
    headquarters    TEXT,
    employee_count  TEXT,                   -- "50-100", "100-500", etc.
    tech_stack      TEXT,                   -- JSON array: ["Python", "Go", "AWS"]
    
    -- Discovery metadata
    first_seen_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_seen_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    discovery_sources TEXT,                 -- JSON array: ["serpapi", "remoteok", "openai"]
    times_seen      INTEGER DEFAULT 1,     -- incremented each time we re-discover this company
    
    -- Status
    status          TEXT DEFAULT 'active',  -- active | archived | blacklisted
    
    -- Timestamps
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_companies_domain ON companies(company_domain);
CREATE INDEX idx_companies_status ON companies(status);
CREATE INDEX idx_companies_last_seen ON companies(last_seen_at);
```

### Table: `job_postings`
Every job posting we've ever discovered. Linked to companies.

```sql
CREATE TABLE job_postings (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id      INTEGER NOT NULL REFERENCES companies(id),
    job_title       TEXT NOT NULL,
    job_url         TEXT,
    location        TEXT,
    remote_policy   TEXT,                   -- onsite | remote | hybrid
    seniority       TEXT,                   -- junior | mid | senior | lead | vp
    tech_stack      TEXT,                   -- JSON array specific to this role
    salary_range    TEXT,
    
    -- Source tracking
    source          TEXT NOT NULL,           -- serpapi | remoteok | hn | wellfound | openai
    source_id       TEXT,                    -- external ID from the source (for dedup)
    
    -- Timing
    posted_date     DATE,                    -- when the job was posted (from source)
    first_scraped   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_scraped    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active       BOOLEAN DEFAULT TRUE,    -- set to FALSE if posting disappears
    
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_postings_company ON job_postings(company_id);
CREATE INDEX idx_postings_active ON job_postings(is_active);
CREATE INDEX idx_postings_source ON job_postings(source, source_id);
```

### Table: `contacts`
Decision-makers found via enrichment. One company can have multiple contacts over time.

```sql
CREATE TABLE contacts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id      INTEGER NOT NULL REFERENCES companies(id),
    
    -- Person data
    full_name       TEXT,
    first_name      TEXT,
    last_name       TEXT,
    title           TEXT,
    linkedin_url    TEXT,
    
    -- Email data
    emails          TEXT,                    -- JSON array: [{"email": "...", "confidence": "high"}]
    best_email      TEXT,                    -- the highest confidence email
    
    -- Enrichment metadata
    enrichment_source   TEXT,               -- "openai_web_search" | "manual" | "apollo" | "fallback"
    enrichment_sources  TEXT,               -- JSON array of source URLs/descriptions
    confidence_notes    TEXT,               -- OpenAI's self-assessment
    
    -- Verification status
    is_verified         BOOLEAN DEFAULT FALSE,
    verification_data   TEXT,               -- JSON blob with all verification results
    person_verified     BOOLEAN,
    title_verified      BOOLEAN,
    linkedin_verified   BOOLEAN,
    domain_has_mx       BOOLEAN,
    
    -- Confidence
    data_confidence     INTEGER DEFAULT 0,   -- 0-100 composite score
    confidence_tier     TEXT,                -- VERIFIED | LIKELY | UNCERTAIN | UNVERIFIED
    
    -- Status
    is_current          BOOLEAN DEFAULT TRUE, -- FALSE when person leaves company
    
    -- Timestamps
    enriched_at         TIMESTAMP,
    verified_at         TIMESTAMP,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_contacts_company ON contacts(company_id);
CREATE INDEX idx_contacts_current ON contacts(is_current);
CREATE INDEX idx_contacts_confidence ON contacts(data_confidence);
```

### Table: `leads`
A lead = company + contact + scores. This is the "product" table — what gets exported.

```sql
CREATE TABLE leads (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id          INTEGER NOT NULL REFERENCES companies(id),
    contact_id          INTEGER REFERENCES contacts(id),  -- can be NULL if no contact found
    
    -- Scores
    hiring_intensity    INTEGER NOT NULL DEFAULT 0,   -- 0-100
    hiring_label        TEXT,                          -- RED_HOT | WARM | COOL | COLD
    data_confidence     INTEGER NOT NULL DEFAULT 0,    -- 0-100
    confidence_tier     TEXT,                          -- VERIFIED | LIKELY | UNCERTAIN | UNVERIFIED
    priority_tier       TEXT,                          -- PRIORITY | REVIEW | NURTURE | ARCHIVE
    
    -- Scoring breakdown (for transparency)
    score_breakdown     TEXT,                          -- JSON: {"role_count": 25, "velocity": 20, ...}
    
    -- Computed fields for quick access
    role_count          INTEGER DEFAULT 0,
    top_roles           TEXT,                          -- JSON array of top 3 role titles
    
    -- Velocity tracking
    roles_last_week     INTEGER,
    roles_this_week     INTEGER,
    velocity_label      TEXT,                          -- ACCELERATING | STABLE | DECLINING | NEW
    
    -- Auto-generated summary
    notes               TEXT,                          -- "12 senior roles, 3+ weeks, on 3 boards"
    
    -- Pipeline tracking
    pipeline_run_id     INTEGER REFERENCES pipeline_runs(id),
    
    -- Status
    status              TEXT DEFAULT 'new',            -- new | delivered | rejected | archived
    
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_leads_scores ON leads(hiring_intensity, data_confidence);
CREATE INDEX idx_leads_status ON leads(status);
CREATE INDEX idx_leads_priority ON leads(priority_tier);
CREATE INDEX idx_leads_run ON leads(pipeline_run_id);
```

### Table: `agencies`
Your clients. Each agency gets customized lead filters and delivery tracking.

```sql
CREATE TABLE agencies (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    contact_name    TEXT,                    -- your contact at the agency
    contact_email   TEXT,
    
    -- ICP Configuration (what kind of leads they want)
    icp_config      TEXT,                    -- JSON blob:
    -- {
    --   "target_industries": ["SaaS", "Fintech"],
    --   "target_locations": ["US", "UK", "UAE"],
    --   "min_employee_count": 20,
    --   "max_employee_count": 500,
    --   "min_hiring_score": 50,
    --   "min_confidence": 60,
    --   "preferred_tech_stack": ["React", "Python", "Go"],
    --   "excluded_companies": ["google.com", "meta.com"]  -- they already have these as clients
    -- }
    
    -- Delivery settings
    delivery_day    TEXT DEFAULT 'monday',   -- day of week for auto-delivery
    delivery_email  TEXT,                    -- where to send the Excel
    max_leads_per_week INTEGER DEFAULT 50,
    
    -- Billing
    monthly_rate    INTEGER,                 -- in INR
    billing_status  TEXT DEFAULT 'trial',    -- trial | active | paused | cancelled
    trial_ends_at   TIMESTAMP,
    
    -- Status
    status          TEXT DEFAULT 'active',
    
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Table: `deliveries`
Tracks every lead sheet sent to every agency. Critical for deduplication.

```sql
CREATE TABLE deliveries (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    agency_id       INTEGER NOT NULL REFERENCES agencies(id),
    lead_id         INTEGER NOT NULL REFERENCES leads(id),
    
    -- Delivery details
    delivered_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    delivery_method TEXT DEFAULT 'email',    -- email | dashboard_download | manual
    batch_id        TEXT,                    -- groups leads sent in the same delivery
    
    -- File tracking
    file_name       TEXT,                    -- "ConnectorOS_AgencyX_2026-03-14.xlsx"
    file_path       TEXT,
    
    -- Feedback (optional — agency can mark leads)
    feedback        TEXT,                    -- useful | not_useful | converted | null
    feedback_at     TIMESTAMP,
    
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_deliveries_agency ON deliveries(agency_id);
CREATE INDEX idx_deliveries_lead ON deliveries(lead_id);
CREATE INDEX idx_deliveries_batch ON deliveries(batch_id);
CREATE UNIQUE INDEX idx_deliveries_unique ON deliveries(agency_id, lead_id);
-- ^ Prevents sending the same lead to the same agency twice
```

### Table: `pipeline_runs`
Every time the pipeline executes, it creates a run record.

```sql
CREATE TABLE pipeline_runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    
    -- Run metadata
    run_type        TEXT NOT NULL,           -- full | discovery_only | enrichment_only | manual
    started_at      TIMESTAMP NOT NULL,
    completed_at    TIMESTAMP,
    status          TEXT DEFAULT 'running',  -- running | completed | failed | partial
    
    -- Stage-by-stage stats
    companies_discovered    INTEGER DEFAULT 0,
    companies_enriched      INTEGER DEFAULT 0,
    companies_verified      INTEGER DEFAULT 0,
    leads_generated         INTEGER DEFAULT 0,
    leads_delivered         INTEGER DEFAULT 0,
    
    -- Quality stats
    avg_hiring_score        REAL,
    avg_data_confidence     REAL,
    verified_count          INTEGER DEFAULT 0,
    unverified_count        INTEGER DEFAULT 0,
    
    -- Cost tracking
    openai_calls            INTEGER DEFAULT 0,
    openai_cost_usd         REAL DEFAULT 0,
    serpapi_calls            INTEGER DEFAULT 0,
    
    -- Error tracking
    errors                  TEXT,             -- JSON array of error messages
    error_count             INTEGER DEFAULT 0,
    
    -- Duration
    duration_seconds        REAL,
    
    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Table: `api_usage`
Tracks every external API call for cost monitoring.

```sql
CREATE TABLE api_usage (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    pipeline_run_id INTEGER REFERENCES pipeline_runs(id),
    
    api_name        TEXT NOT NULL,           -- openai_discovery | openai_enrichment | openai_verification | openai_email | serpapi
    model           TEXT,                    -- gpt-4o-mini
    
    -- Token usage
    input_tokens    INTEGER,
    output_tokens   INTEGER,
    total_tokens    INTEGER,
    
    -- Cost
    cost_usd        REAL,
    
    -- Request details
    company_domain  TEXT,                    -- which company this call was for
    request_type    TEXT,                    -- discovery | enrichment | email_gen | verification
    success         BOOLEAN DEFAULT TRUE,
    error_message   TEXT,
    response_time_ms INTEGER,
    
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_api_usage_run ON api_usage(pipeline_run_id);
CREATE INDEX idx_api_usage_date ON api_usage(created_at);
```

### Table: `notifications`
System alerts and notifications.

```sql
CREATE TABLE notifications (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    
    type            TEXT NOT NULL,           -- pipeline_complete | pipeline_failed | hot_lead_found | 
                                            -- api_limit_warning | delivery_sent | error
    severity        TEXT DEFAULT 'info',     -- info | warning | error | critical
    title           TEXT NOT NULL,
    message         TEXT NOT NULL,
    
    -- Context
    related_entity  TEXT,                    -- "pipeline_run:42" | "lead:156" | "agency:3"
    
    -- Status
    is_read         BOOLEAN DEFAULT FALSE,
    is_dismissed    BOOLEAN DEFAULT FALSE,
    
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_notifications_unread ON notifications(is_read, created_at);
```

### Table: `search_history`
Tracks manual searches from the dashboard.

```sql
CREATE TABLE search_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    
    query_type      TEXT NOT NULL,           -- company_search | contact_search | market_scan
    query_params    TEXT NOT NULL,           -- JSON blob of search parameters
    
    results_count   INTEGER,
    results_data    TEXT,                    -- JSON blob of results (cached)
    
    openai_cost_usd REAL,
    
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Table: `settings`
Key-value store for system configuration.

```sql
CREATE TABLE settings (
    key             TEXT PRIMARY KEY,
    value           TEXT NOT NULL,
    description     TEXT,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Default settings
INSERT INTO settings (key, value, description) VALUES
('pipeline_schedule', '0 6 * * 1', 'Cron expression: every Monday at 6 AM'),
('default_target_market', 'US tech companies', 'Default market for discovery'),
('min_hiring_score_for_delivery', '50', 'Minimum hiring score to include in deliveries'),
('min_confidence_for_delivery', '40', 'Minimum data confidence to include'),
('openai_model', 'gpt-4o-mini', 'Model for all OpenAI calls'),
('openai_daily_budget_usd', '5.00', 'Max daily spend on OpenAI'),
('serpapi_monthly_limit', '100', 'SerpAPI monthly credit limit'),
('max_companies_per_run', '200', 'Maximum companies to process in one pipeline run'),
('enrichment_delay_seconds', '2', 'Delay between enrichment API calls'),
('verification_enabled', 'true', 'Whether to run verification stage'),
('notification_email', '', 'Email for pipeline notifications'),
('data_retention_days', '180', 'Days to keep old data before cleanup');
```

---

## 3. Pydantic Models (Complete)

These are your data contracts. Every piece of data in the system flows through these models.

### Core Models

```python
from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import datetime
from enum import Enum

# === Enums ===

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

# === Data Models ===

class EmailEntry(BaseModel):
    email: str
    confidence: str  # high | medium | low

class CompanyBase(BaseModel):
    company_name: str
    company_domain: str
    website_url: Optional[str] = None
    industry: Optional[str] = None
    headquarters: Optional[str] = None
    employee_count: Optional[str] = None
    tech_stack: list[str] = []

class JobPosting(BaseModel):
    job_title: str
    job_url: Optional[str] = None
    location: Optional[str] = None
    remote_policy: Optional[str] = None
    seniority: Optional[str] = None
    tech_stack: list[str] = []
    salary_range: Optional[str] = None
    source: str
    posted_date: Optional[str] = None

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
    confidence_notes: Optional[str] = None

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

class ScoreBreakdown(BaseModel):
    role_count_score: int = 0        # max 25
    velocity_score: int = 0          # max 20
    seniority_score: int = 0         # max 15
    multi_source_score: int = 0      # max 15
    role_age_score: int = 0          # max 15
    promoted_ads_score: int = 0      # max 10
    total: int = 0                   # max 100

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
    
    notes: Optional[str] = None  # auto-generated summary

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
```

---

## 4. Stage 1: Discovery Engine

### Architecture

```
                    ┌─────────────────────┐
                    │   Discovery Engine   │
                    └─────────┬───────────┘
                              │
              ┌───────────────┼───────────────┐
              │               │               │
     ┌────────▼──────┐ ┌─────▼──────┐ ┌──────▼───────┐
     │  Job Board    │ │  OpenAI    │ │  Historical  │
     │  Scrapers     │ │  Web Search│ │  Re-check    │
     │  (SerpAPI,    │ │  (discover │ │  (re-scan    │
     │  RemoteOK,    │ │  companies │ │  existing    │
     │  HN, etc)     │ │  not on    │ │  companies)  │
     └────────┬──────┘ │  boards)   │ └──────┬───────┘
              │        └─────┬──────┘        │
              │              │               │
              └──────────────┼───────────────┘
                             │
                    ┌────────▼────────┐
                    │  Deduplicator   │
                    │  (merge by      │
                    │  domain)        │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │  companies +    │
                    │  job_postings   │
                    │  tables updated │
                    └─────────────────┘
```

### Discovery Flow (detailed)

**Step 1: Run Job Board Scrapers**
- Call SerpAPI for Google Jobs (query: "software engineer" + target market)
- Call RemoteOK JSON API
- Parse HN "Who's Hiring" thread (if it's the right time of month)
- Each scraper outputs a list of `CompanyBase` + `JobPosting` objects

**Step 2: Run OpenAI Discovery Search**
- Use the discovery prompt (see Section 19) with web_search_preview tool
- Target: find companies NOT on standard boards (internal career pages, LinkedIn-only, niche boards)
- Run 2-3 discovery calls with different market segments for variety

**Step 3: Historical Re-check**
- Query database for companies seen in previous runs
- For each company last seen > 7 days ago, check if they're still hiring
- This is a lightweight OpenAI call: "Is {company} still actively hiring? Quick yes/no with current role count."
- Update `last_seen_at` and `is_active` status on job postings

**Step 4: Deduplication**
- Normalize all domains: lowercase, strip www., strip trailing /
- Match by domain (primary) — if domain matches, merge records
- Fuzzy match by name (secondary) — Levenshtein ≥ 85% after stripping Inc/Ltd/LLC
- When merging: union job_titles, sum role_count, union sources, keep earliest first_seen

**Step 5: Database Update**
- INSERT new companies (ON CONFLICT DO UPDATE for existing domains)
- INSERT new job postings (check source_id to avoid duplicates)
- Update `last_seen_at`, `times_seen`, `discovery_sources` on existing companies

### Rate Limiting for Discovery
- SerpAPI: respect monthly limit (track in `api_usage` table)
- OpenAI: 2-second delay between discovery calls
- RemoteOK: 5-second delay between requests
- HN API: no rate limit, but be polite (1 req/sec)

---

## 5. Stage 2: Enrichment Engine

### Architecture

```
     ┌──────────────────────┐
     │  Company from Stage 1│
     │  (company_name +     │
     │   company_domain)    │
     └──────────┬───────────┘
                │
     ┌──────────▼───────────┐
     │  OpenAI Web Search   │
     │  "Find VP Eng at X"  │
     │  (web_search_preview)│
     └──────────┬───────────┘
                │
          ┌─────┴─────┐
          │           │
     found=true   found=false
          │           │
     ┌────▼────┐  ┌───▼──────────┐
     │ OpenAI  │  │ Fallback     │
     │ Email   │  │ Generic      │
     │ Gen     │  │ Emails       │
     │ (no web │  │ (careers@,   │
     │ search) │  │  hr@, etc)   │
     └────┬────┘  └───┬──────────┘
          │           │
          └─────┬─────┘
                │
     ┌──────────▼───────────┐
     │  contacts table      │
     │  updated             │
     └──────────────────────┘
```

### Enrichment Flow (detailed)

**Step 1: Check if already enriched recently**
- Query `contacts` table for this company_id where `is_current = TRUE` and `enriched_at > 7 days ago`
- If found, skip enrichment (use cached data)
- This saves API credits for companies already enriched recently

**Step 2: Call OpenAI with web search**
- Use enrichment prompt (see Section 19)
- Parse JSON response
- If `found=true`: extract person data, save to `contacts` table
- If `found=false`: log it, move to fallback

**Step 3: Generate emails**
- If person found: call OpenAI (WITHOUT web search) to generate email patterns
- If person NOT found: generate generic role emails (careers@, hr@, recruiting@, hiring@, talent@)
- Set `best_email` to highest confidence email

**Step 4: Save to database**
- INSERT into `contacts` table
- Set `is_current = FALSE` on any previous contacts for this company (if person changed)
- Log API usage to `api_usage` table

### Enrichment Configuration
```yaml
enrichment:
  skip_if_enriched_within_days: 7      # don't re-enrich recently enriched companies
  delay_between_calls_seconds: 2        # rate limiting
  max_retries: 3                        # retry on failure
  timeout_seconds: 30                   # per API call
  batch_size: 50                        # process 50 companies per run
  prioritize_by: "hiring_intensity"     # enrich highest-scoring companies first
```

---

## 6. Stage 3: Verification Engine

### Three Verification Layers

**Layer 1: OpenAI Cross-Check (API call)**
- Independent second OpenAI web search to verify the enrichment data
- Different prompt — asks specifically "does this person currently work here?"
- Catches: people who left, title changes, companies that stopped hiring

**Layer 2: Technical Checks (Python, no API)**

| Check | Implementation | Points |
|-------|---------------|--------|
| DNS resolution | `socket.getaddrinfo(domain, 80)` — catches fake/dead domains | +10 if passes |
| MX records | `dns.resolver.resolve(domain, 'MX')` — domain can receive email | +10 if passes |
| Email format | Regex: `^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$` | +5 if passes |
| LinkedIn URL format | Starts with `linkedin.com/in/` or `linkedin.com/company/` | +5 if valid format |
| LinkedIn URL live | HEAD request to URL, check for 200/302 status | +15 if live |
| Name plausibility | Has 2+ parts, starts uppercase, no numbers, not suspicious | +5 if passes |
| Duplicate detection | Same name appears for 3+ companies in this batch | -20 if duplicate |
| Website live | HEAD request to company domain, check 200 status | +10 if live |
| Parked domain check | If website body contains "buy this domain", "parked", "for sale" | -15 if parked |
| Historical consistency | Same person as previous enrichment for this company | +5 if consistent |

**Layer 3: Confidence Score Calculation**

```python
def calculate_confidence(verification: VerificationResult, enrichment_source: str) -> int:
    score = 0
    
    # OpenAI verification (Layer 1)
    if verification.person_verified:
        score += 25
    if verification.overall_confidence == "high":
        score += 5
    
    # Technical checks (Layer 2)
    if verification.domain_active:
        score += 10
    if verification.domain_has_mx:
        score += 10
    if verification.linkedin_url_valid:
        score += 15
    if verification.name_plausible:
        score += 5
    if verification.email_format_valid:
        score += 5
    if verification.is_duplicate_contact:
        score -= 20
    
    # Source bonus
    if enrichment_source == "openai_web_search":
        score += 10
    elif enrichment_source == "fallback":
        score -= 10
    
    # Clamp to 0-100
    return max(0, min(100, score))
```

### Confidence Tier Assignment
```python
def assign_confidence_tier(score: int) -> ConfidenceTier:
    if score >= 80: return ConfidenceTier.VERIFIED
    if score >= 60: return ConfidenceTier.LIKELY
    if score >= 40: return ConfidenceTier.UNCERTAIN
    return ConfidenceTier.UNVERIFIED
```

---

## 7. Stage 4: Scoring Engine

### Hiring Intensity Score (0-100)

```python
def calculate_hiring_intensity(
    role_count: int,
    roles_last_week: int | None,
    roles_this_week: int,
    seniority_mix: dict,          # {"junior": 2, "mid": 3, "senior": 5}
    source_count: int,             # how many job boards it appeared on
    avg_role_age_days: float,      # average days since posting
    has_promoted_ads: bool
) -> tuple[int, ScoreBreakdown]:
    
    breakdown = ScoreBreakdown()
    
    # 1. Role count (max 25)
    if role_count >= 10: breakdown.role_count_score = 25
    elif role_count >= 6: breakdown.role_count_score = 20
    elif role_count >= 3: breakdown.role_count_score = 12
    else: breakdown.role_count_score = 5
    
    # 2. Velocity (max 20)
    if roles_last_week is not None and roles_last_week > 0:
        change = (roles_this_week - roles_last_week) / roles_last_week
        if change > 0.5: breakdown.velocity_score = 20    # surging
        elif change > 0.1: breakdown.velocity_score = 12   # growing
        else: breakdown.velocity_score = 5                  # stable
    else:
        breakdown.velocity_score = 10  # new company, assume moderate
    
    # 3. Seniority (max 15)
    senior_count = seniority_mix.get("senior", 0) + seniority_mix.get("lead", 0) + seniority_mix.get("vp", 0)
    total = sum(seniority_mix.values()) or 1
    senior_ratio = senior_count / total
    if senior_ratio > 0.5: breakdown.seniority_score = 15
    elif senior_ratio > 0.2: breakdown.seniority_score = 10
    else: breakdown.seniority_score = 3
    
    # 4. Multi-source (max 15)
    if source_count >= 3: breakdown.multi_source_score = 15
    elif source_count == 2: breakdown.multi_source_score = 8
    else: breakdown.multi_source_score = 3
    
    # 5. Role age (max 15)
    if avg_role_age_days > 28: breakdown.role_age_score = 15
    elif avg_role_age_days > 14: breakdown.role_age_score = 10
    else: breakdown.role_age_score = 5
    
    # 6. Promoted ads (max 10)
    breakdown.promoted_ads_score = 10 if has_promoted_ads else 0
    
    breakdown.total = (
        breakdown.role_count_score + breakdown.velocity_score +
        breakdown.seniority_score + breakdown.multi_source_score +
        breakdown.role_age_score + breakdown.promoted_ads_score
    )
    
    return breakdown.total, breakdown
```

### Priority Matrix

```python
def assign_priority(hiring_intensity: int, data_confidence: int) -> PriorityTier:
    high_hiring = hiring_intensity >= 60
    high_confidence = data_confidence >= 60
    
    if high_hiring and high_confidence:
        return PriorityTier.PRIORITY
    elif high_hiring and not high_confidence:
        return PriorityTier.REVIEW
    elif not high_hiring and high_confidence:
        return PriorityTier.NURTURE
    else:
        return PriorityTier.ARCHIVE
```

### Auto-Generated Notes

```python
def generate_notes(lead: Lead) -> str:
    parts = []
    
    if lead.role_count:
        parts.append(f"{lead.role_count} open roles")
    
    if lead.velocity_label == VelocityLabel.ACCELERATING:
        parts.append("hiring accelerating")
    
    senior_roles = [r for r in lead.top_roles if any(
        kw in r.lower() for kw in ["senior", "lead", "principal", "staff", "vp", "director"]
    )]
    if senior_roles:
        parts.append(f"{len(senior_roles)} senior positions")
    
    source_count = len(lead.company.discovery_sources) if hasattr(lead.company, 'discovery_sources') else 1
    if source_count >= 3:
        parts.append(f"posted on {source_count} boards")
    
    if lead.confidence_tier == ConfidenceTier.VERIFIED:
        parts.append("data verified")
    
    return ". ".join(parts) + "." if parts else "No additional notes."
```

---

## 8. Stage 5: Export Engine

### Excel Generation (openpyxl)

**File naming:** `ConnectorOS_{agency_name}_{YYYY-MM-DD}.xlsx`

**Sheet 1: Priority Leads**
- Filter: `priority_tier IN ('PRIORITY', 'REVIEW')` AND not already delivered to this agency
- Sort: `hiring_intensity DESC`
- Limit: `agency.max_leads_per_week`
- Columns: Company, Website, Location, Industry, Employees, Open Roles, Top Roles, Tech Stack, Hiring Score, Hiring Label, Contact Name, Contact Title, Best Email, LinkedIn, Job URL, Data Confidence, Confidence Tier, Notes

**Formatting:**
- Header row: bold, dark blue background, white text, frozen row
- Hiring Label column: conditional formatting (RED_HOT=red fill, WARM=orange, COOL=blue)
- Confidence Tier: conditional formatting (VERIFIED=green, LIKELY=blue, UNCERTAIN=yellow, UNVERIFIED=red)
- Auto-width columns
- Hyperlinks on Website, LinkedIn, Job URL columns
- Data validation dropdown on a "Feedback" column (useful / not_useful / converted)

**Sheet 2: Summary Stats**
- Total leads in this delivery
- Breakdown by Hiring Label (count + percentage)
- Breakdown by Confidence Tier
- Top 5 industries
- Top 5 tech stacks
- Average hiring score
- Average data confidence
- Week-over-week comparison (if previous delivery exists)

**Sheet 3: Needs Review**
- Filter: `hiring_intensity >= 60 AND data_confidence < 60`
- These are hot leads with shaky data
- Same columns as Sheet 1 but with an extra "Review Notes" column explaining what failed verification

**Sheet 4: Nurture List**
- Filter: `hiring_intensity < 60 AND data_confidence >= 60`
- Companies not urgently hiring but with good data
- Useful for the agency to keep in their CRM for future outreach

### CSV Export (simpler alternative)
- Same data as Sheet 1
- UTF-8 encoded with BOM (for Excel compatibility)
- Pipe-delimited for fields that might contain commas

### Delivery Tracking
After export:
1. INSERT into `deliveries` table for each lead in the batch
2. UPDATE `leads.status` to 'delivered'
3. CREATE notification: "Delivered {count} leads to {agency_name}"
4. Log delivery to `pipeline_runs` stats

---

## 9. Stage 6: Dashboard (Complete Wireframes)

### Dashboard Tech: Streamlit

Entry point: `streamlit run dashboard/app.py`

### Page 1: Pipeline Overview (Home)

```
┌─────────────────────────────────────────────────────┐
│ ConnectorOS Scout — Dashboard                        │
├─────────────────────────────────────────────────────┤
│                                                     │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌──────────┐ │
│  │ 247     │ │ 189     │ │ 142     │ │ 98       │ │
│  │Companies│ │Enriched │ │Verified │ │Delivered │ │
│  │Found    │ │         │ │         │ │This Week │ │
│  └─────────┘ └─────────┘ └─────────┘ └──────────┘ │
│                                                     │
│  Pipeline Status: ✅ Completed (Mon 6:12 AM)        │
│  Next Run: Monday March 21, 6:00 AM                 │
│  Duration: 4m 23s | Cost: $0.38                     │
│                                                     │
│  ┌─── Funnel Chart ───────────────────────────────┐ │
│  │ Discovered: ████████████████████████████ 247    │ │
│  │ Enriched:   ████████████████████████     189    │ │
│  │ Verified:   ██████████████████           142    │ │
│  │ Delivered:  ████████████                  98    │ │
│  └────────────────────────────────────────────────┘ │
│                                                     │
│  ┌─── Source Breakdown (Pie) ─────────────────────┐ │
│  │  SerpAPI: 45%  RemoteOK: 22%  OpenAI: 18%     │ │
│  │  HN: 10%  Wellfound: 5%                       │ │
│  └────────────────────────────────────────────────┘ │
│                                                     │
│  ┌─── Recent Runs (Table) ────────────────────────┐ │
│  │ Date       | Status | Found | Delivered | Cost │ │
│  │ Mar 14     | ✅     | 247   | 98        | $0.38│ │
│  │ Mar 7      | ✅     | 231   | 87        | $0.35│ │
│  │ Feb 28     | ⚠️     | 198   | 72        | $0.31│ │
│  └────────────────────────────────────────────────┘ │
│                                                     │
│  [▶ Run Pipeline Now]  [⚙ Settings]                │
└─────────────────────────────────────────────────────┘
```

### Page 2: Lead Browser

```
┌─────────────────────────────────────────────────────┐
│ Lead Browser                                         │
├─────────────────────────────────────────────────────┤
│                                                     │
│  Filters:                                           │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────┐│
│  │Hiring: ▼ │ │Confid: ▼ │ │Industry:▼│ │Location││
│  │Min: 50   │ │Min: 40   │ │All       │ │All     ││
│  └──────────┘ └──────────┘ └──────────┘ └────────┘│
│                                                     │
│  ┌──────┐ ┌──────────┐ ┌──────────────┐            │
│  │Tech: │ │Priority: │ │Search company│            │
│  │All ▼ │ │All ▼     │ │_____________ │            │
│  └──────┘ └──────────┘ └──────────────┘            │
│                                                     │
│  Showing 142 leads  [Export Selected] [Export All]  │
│                                                     │
│  ┌─────────────────────────────────────────────────┐│
│  │□ Company    │Score│Conf│Contact      │Status    ││
│  │─────────────┼─────┼────┼─────────────┼──────────││
│  │□ Stripe     │ 92  │ 88 │K.Raghavan   │PRIORITY  ││
│  │□ Datadog    │ 87  │ 91 │A.Singh      │PRIORITY  ││
│  │□ Linear     │ 78  │ 72 │K.Rawlings   │PRIORITY  ││
│  │□ Supabase   │ 74  │ 45 │—            │REVIEW    ││
│  │□ Acme Inc   │ 65  │ 82 │J.Chen       │PRIORITY  ││
│  │  ...        │     │    │             │          ││
│  └─────────────────────────────────────────────────┘│
│                                                     │
│  ┌─── Lead Detail (click to expand) ──────────────┐ │
│  │ STRIPE (stripe.com)                            │ │
│  │ Industry: Fintech | HQ: San Francisco          │ │
│  │ Employees: 7000+ | Tech: Ruby, Go, React       │ │
│  │                                                 │ │
│  │ Contact: Kris Raghavan, VP Engineering          │ │
│  │ Email: kris.raghavan@stripe.com (high)          │ │
│  │ LinkedIn: linkedin.com/in/krisraghavan ✅       │ │
│  │                                                 │ │
│  │ Hiring: 92 (RED HOT) | Confidence: 88 (VERIFIED)│
│  │ 12 open roles | Accelerating (+5 vs last week) │ │
│  │ Top: Sr Backend Eng, DevOps Lead, Staff Eng     │ │
│  │                                                 │ │
│  │ Verification: ✅ Person confirmed ✅ Title ok    │ │
│  │ ✅ Domain active ✅ MX records ✅ LinkedIn live   │ │
│  │                                                 │ │
│  │ Sources: LinkedIn, Crunchbase                   │ │
│  │ First seen: Feb 12 | Last seen: Mar 14          │ │
│  │ Times seen: 5 runs                              │ │
│  │                                                 │ │
│  │ [Mark Verified] [Reject] [Add Note] [Re-Enrich]│ │
│  └─────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────┘
```

### Page 3: Manual Search

```
┌─────────────────────────────────────────────────────┐
│ Manual Search                                        │
├─────────────────────────────────────────────────────┤
│                                                     │
│  ┌─── Search Mode ───────────────────────────────┐  │
│  │ ○ Company Lookup  ○ Contact Finder  ○ Market  │  │
│  │                                     Scan      │  │
│  └───────────────────────────────────────────────┘  │
│                                                     │
│  ── Company Lookup ──                               │
│  ┌─────────────────────────────────────────┐        │
│  │ Company name or domain: [stripe.com   ] │        │
│  │ [🔍 Search]                              │        │
│  └─────────────────────────────────────────┘        │
│  Searches OpenAI with web search. Returns           │
│  company info + contact + email patterns.           │
│  Cost: ~$0.02 per search                            │
│                                                     │
│  ── Contact Finder ──                               │
│  ┌─────────────────────────────────────────┐        │
│  │ Company: [stripe.com              ]      │        │
│  │ Title:   [VP Engineering          ] (opt)│        │
│  │ [🔍 Find Contact]                        │        │
│  └─────────────────────────────────────────┘        │
│  Finds the decision-maker + generates emails.       │
│                                                     │
│  ── Market Scan ──                                  │
│  ┌─────────────────────────────────────────┐        │
│  │ Market: [Tech companies in Dubai    ]    │        │
│  │ Max results: [20 ▼]                      │        │
│  │ [🔍 Scan Market]                          │        │
│  └─────────────────────────────────────────┘        │
│  Discovers companies in a market. Like running      │
│  Stage 1 manually for a specific query.             │
│                                                     │
│  ┌─── Results ────────────────────────────────────┐ │
│  │ (results appear here after search)             │ │
│  │                                                │ │
│  │ [Add to Pipeline] [Export CSV] [Save to DB]    │ │
│  └────────────────────────────────────────────────┘ │
│                                                     │
│  ┌─── Search History ─────────────────────────────┐ │
│  │ Time      | Type       | Query        | Count  │ │
│  │ 2:15 PM   | Company    | stripe.com   | 1      │ │
│  │ 1:40 PM   | Market     | Dubai tech   | 18     │ │
│  │ 11:20 AM  | Contact    | figma.com    | 1      │ │
│  └────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────┘
```

### Page 4: Analytics

```
┌─────────────────────────────────────────────────────┐
│ Analytics                                            │
├─────────────────────────────────────────────────────┤
│                                                     │
│  Date Range: [Last 30 days ▼]  [Custom: ___ to ___]│
│                                                     │
│  ┌─── Weekly Trends (Line Chart) ─────────────────┐ │
│  │ Lines: Companies Found, Leads Delivered,        │ │
│  │        Avg Hiring Score, Avg Confidence          │ │
│  │ X-axis: Weeks | Y-axis: Count/Score             │ │
│  └─────────────────────────────────────────────────┘│
│                                                     │
│  ┌─── Score Distribution ─────────────────────────┐ │
│  │ Two histograms side by side:                    │ │
│  │ Left: Hiring Intensity distribution             │ │
│  │ Right: Data Confidence distribution             │ │
│  └─────────────────────────────────────────────────┘│
│                                                     │
│  ┌─── Scatter: Hiring vs Confidence ──────────────┐ │
│  │ X: Hiring Intensity | Y: Data Confidence        │ │
│  │ Each dot = 1 company | Color = Priority Tier    │ │
│  │ Quadrants labeled: PRIORITY, REVIEW, etc        │ │
│  └─────────────────────────────────────────────────┘│
│                                                     │
│  ┌─── Top Industries ────┐ ┌─── Top Tech Stacks ──┐│
│  │ 1. SaaS (34%)         │ │ 1. Python (28%)      ││
│  │ 2. Fintech (22%)      │ │ 2. React (24%)       ││
│  │ 3. AI/ML (18%)        │ │ 3. Go (15%)          ││
│  │ 4. DevTools (12%)     │ │ 4. TypeScript (14%)  ││
│  │ 5. Healthtech (8%)    │ │ 5. AWS (12%)         ││
│  └───────────────────────┘ └──────────────────────┘│
│                                                     │
│  ┌─── Verification Pass Rates ────────────────────┐ │
│  │ DNS Check:        97% ██████████████████████▓   │ │
│  │ MX Records:       94% █████████████████████▓    │ │
│  │ LinkedIn Valid:    67% ██████████████▓           │ │
│  │ Person Verified:   72% ███████████████▓          │ │
│  │ Title Current:     68% ██████████████▓           │ │
│  └─────────────────────────────────────────────────┘│
│                                                     │
│  ┌─── Hiring Velocity Heatmap ────────────────────┐ │
│  │ Rows: Companies | Columns: Weeks               │ │
│  │ Color: Green=accelerating, Gray=stable,         │ │
│  │        Red=declining                            │ │
│  │ Shows which companies are ramping up over time  │ │
│  └─────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────┘
```

### Page 5: Agency Management

```
┌─────────────────────────────────────────────────────┐
│ Agencies                                             │
├─────────────────────────────────────────────────────┤
│                                                     │
│  [+ Add Agency]                                     │
│                                                     │
│  ┌─────────────────────────────────────────────────┐│
│  │ Agency        │Leads Sent│Last Delivery│Status  ││
│  │───────────────┼──────────┼─────────────┼────────││
│  │ TechRecruit   │ 156      │ Mar 14      │ Active ││
│  │ HireFast UAE  │ 89       │ Mar 14      │ Active ││
│  │ CodeTalent    │ 0        │ —           │ Trial  ││
│  └─────────────────────────────────────────────────┘│
│                                                     │
│  ┌─── Agency Detail: TechRecruit ─────────────────┐ │
│  │                                                 │ │
│  │ Contact: Rahul Verma (rahul@techrecruit.in)    │ │
│  │ Plan: ₹20,000/month | Status: Active           │ │
│  │ Delivery: Every Monday to leads@techrecruit.in  │ │
│  │ Max leads/week: 50                              │ │
│  │                                                 │ │
│  │ ICP Configuration:                              │ │
│  │ ┌───────────────────────────────────────┐       │ │
│  │ │ Industries: SaaS, Fintech, AI         │       │ │
│  │ │ Locations: US, UK, India              │       │ │
│  │ │ Company Size: 20-500 employees        │       │ │
│  │ │ Min Hiring Score: 50                  │       │ │
│  │ │ Min Confidence: 60                    │       │ │
│  │ │ Preferred Stack: React, Python, Go    │       │ │
│  │ │ Excluded: google.com, meta.com        │       │ │
│  │ │ [Edit ICP]                            │       │ │
│  │ └───────────────────────────────────────┘       │ │
│  │                                                 │ │
│  │ Delivery History:                               │ │
│  │ ┌────────────────────────────────────────┐      │ │
│  │ │ Date    │ Leads │ Avg Score │ File     │      │ │
│  │ │ Mar 14  │ 48    │ 74       │ Download │      │ │
│  │ │ Mar 7   │ 42    │ 71       │ Download │      │ │
│  │ │ Feb 28  │ 39    │ 68       │ Download │      │ │
│  │ └────────────────────────────────────────┘      │ │
│  │                                                 │ │
│  │ [Generate Delivery Now] [Pause] [Delete Agency] │ │
│  └─────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────┘
```

### Page 6: Cost & Usage

```
┌─────────────────────────────────────────────────────┐
│ Cost & API Usage                                     │
├─────────────────────────────────────────────────────┤
│                                                     │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────┐│
│  │ $0.38    │ │ $8.42    │ │ 87/100   │ │ $0.04  ││
│  │ Today    │ │ This     │ │ SerpAPI  │ │ Per    ││
│  │          │ │ Month    │ │ Credits  │ │ Lead   ││
│  └──────────┘ └──────────┘ └──────────┘ └────────┘│
│                                                     │
│  ┌─── Daily Cost (Bar Chart) ─────────────────────┐ │
│  │ Stacked bars: Discovery | Enrichment |          │ │
│  │               Verification | Email Gen          │ │
│  └─────────────────────────────────────────────────┘│
│                                                     │
│  ┌─── Cost Per Stage (This Run) ──────────────────┐ │
│  │ Discovery:    $0.12 (32%)                       │ │
│  │ Enrichment:   $0.14 (37%)                       │ │
│  │ Verification: $0.09 (24%)                       │ │
│  │ Email Gen:    $0.03 (7%)                        │ │
│  └─────────────────────────────────────────────────┘│
│                                                     │
│  ┌─── API Call Log (Detailed) ────────────────────┐ │
│  │ Time    │ API      │ Company    │ Cost  │Status│ │
│  │ 6:01 AM │ OpenAI   │ stripe.com │ $0.01 │ ✅  │ │
│  │ 6:01 AM │ OpenAI   │ linear.app │ $0.01 │ ✅  │ │
│  │ 6:02 AM │ SerpAPI  │ —          │ —     │ ✅  │ │
│  │ 6:02 AM │ OpenAI   │ figma.com  │ $0.01 │ ⚠️  │ │
│  └─────────────────────────────────────────────────┘│
│                                                     │
│  Budget Alert: [Daily limit: $5.00]                 │
│  SerpAPI Alert: [13 credits remaining]              │
└─────────────────────────────────────────────────────┘
```

### Page 7: Settings

```
┌─────────────────────────────────────────────────────┐
│ Settings                                             │
├─────────────────────────────────────────────────────┤
│                                                     │
│  ── Pipeline Schedule ──                            │
│  Run automatically: [✅ Enabled]                     │
│  Schedule: Every [Monday ▼] at [6:00 AM ▼]         │
│  Target market: [US tech companies_________]        │
│  Max companies per run: [200]                       │
│                                                     │
│  ── API Keys ──                                     │
│  OpenAI: sk-****...****7f2a [Test] [Update]        │
│  SerpAPI: ****...****3b1c [Test] [Update]          │
│                                                     │
│  ── Scoring Thresholds ──                           │
│  Min hiring score for delivery: [50]                │
│  Min confidence for delivery: [40]                  │
│  Min hiring score for "RED HOT": [80]              │
│                                                     │
│  ── Enrichment ──                                   │
│  Delay between API calls: [2] seconds              │
│  Skip if enriched within: [7] days                 │
│  Enable verification stage: [✅]                     │
│                                                     │
│  ── Notifications ──                                │
│  Email for alerts: [you@email.com_______]          │
│  Notify on: [✅ Pipeline complete] [✅ Errors]       │
│             [✅ Hot lead found] [✅ Budget warning]   │
│                                                     │
│  ── Data Management ──                              │
│  Data retention: [180] days                        │
│  [🗑 Purge Old Data] [📥 Export Full Database]       │
│  [🔄 Reset All Scores] [⚠️ Delete All Data]         │
│                                                     │
│  [Save Settings]                                    │
└─────────────────────────────────────────────────────┘
```

### Page 8: Notifications

```
┌─────────────────────────────────────────────────────┐
│ Notifications                                        │
├─────────────────────────────────────────────────────┤
│                                                     │
│  [Mark All Read]  Showing: [All ▼]                  │
│                                                     │
│  🔴 Pipeline Error — Mar 14, 6:45 AM                │
│  OpenAI rate limit hit during enrichment.           │
│  14 companies skipped. Re-run to complete.          │
│  [Re-run Enrichment] [Dismiss]                      │
│                                                     │
│  🟡 Budget Warning — Mar 13, 11:00 PM               │
│  OpenAI spend at $4.20 today (84% of $5 limit).    │
│  [Adjust Budget] [Dismiss]                          │
│                                                     │
│  🟢 Delivery Sent — Mar 14, 7:00 AM                 │
│  48 leads delivered to TechRecruit.                 │
│  Avg hiring score: 74. File: Download               │
│  [View Delivery] [Dismiss]                          │
│                                                     │
│  🔵 Hot Lead Found — Mar 14, 6:12 AM                │
│  Stripe scored 92 (RED HOT) with 12 open roles     │
│  and accelerating velocity. Contact verified.       │
│  [View Lead] [Dismiss]                              │
│                                                     │
└─────────────────────────────────────────────────────┘
```

---

## 10. Manual Search Interface

Already covered in Dashboard Page 3. Three search modes:

1. **Company Lookup**: Type a domain, get full enrichment + verification instantly
2. **Contact Finder**: Type a domain + optional title, find the decision-maker
3. **Market Scan**: Type a market description, discover 20 companies on-demand

All manual search results can be saved to the database and added to the pipeline.

---

## 11. Automation & Scheduling

### Scheduler Design (APScheduler)

```python
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

scheduler = BackgroundScheduler()

# Main pipeline — runs every Monday at 6 AM
scheduler.add_job(
    run_full_pipeline,
    CronTrigger.from_crontab(settings.get("pipeline_schedule")),  # "0 6 * * 1"
    id="main_pipeline",
    name="Weekly Pipeline Run",
    replace_existing=True
)

# Daily health check — lightweight, just checks if APIs are working
scheduler.add_job(
    run_health_check,
    CronTrigger(hour=8, minute=0),  # every day at 8 AM
    id="health_check"
)

# Weekly cleanup — archive old data
scheduler.add_job(
    run_data_cleanup,
    CronTrigger(day_of_week="sun", hour=3),  # Sunday 3 AM
    id="cleanup"
)

scheduler.start()
```

### Pipeline Orchestrator

```python
async def run_full_pipeline(target_market: str = None):
    run = create_pipeline_run(run_type="full")
    
    try:
        # Stage 1: Discover
        companies = await discover(target_market or settings.get("default_target_market"))
        run.companies_discovered = len(companies)
        
        # Stage 2: Enrich (only top N by preliminary score)
        enriched = await enrich_batch(companies, max_count=settings.get("max_companies_per_run"))
        run.companies_enriched = len(enriched)
        
        # Stage 3: Verify
        if settings.get("verification_enabled"):
            verified = await verify_batch(enriched)
            run.companies_verified = len(verified)
        
        # Stage 4: Score
        leads = score_batch(verified or enriched)
        run.leads_generated = len(leads)
        
        # Stage 5: Export & Deliver (per agency)
        for agency in get_active_agencies():
            filtered = filter_leads_for_agency(leads, agency)
            deduped = remove_already_delivered(filtered, agency)
            if deduped:
                file_path = generate_excel(deduped, agency)
                record_delivery(deduped, agency, file_path)
                run.leads_delivered += len(deduped)
                create_notification("delivery_sent", f"{len(deduped)} leads to {agency.name}")
        
        run.status = "completed"
        
    except Exception as e:
        run.status = "failed"
        run.errors = [str(e)]
        create_notification("pipeline_failed", str(e), severity="error")
    
    finally:
        run.completed_at = datetime.now()
        run.duration_seconds = (run.completed_at - run.started_at).total_seconds()
        run.openai_cost_usd = sum_api_costs(run.id)
        save_pipeline_run(run)
```

---

## 12. Agency Management System

Covered in Dashboard Page 5. Key operations:

- **Add Agency**: Name, contact info, ICP config, delivery schedule
- **Edit ICP**: Change target industries, locations, tech stack, company size, exclusions
- **Generate Delivery**: On-demand delivery outside the scheduled run
- **View History**: All deliveries with download links
- **Pause/Resume**: Stop deliveries without losing config
- **Feedback Tracking**: If agency marks leads as useful/not_useful/converted, use that data to improve scoring

---

## 13. Notification System

### Notification Types

| Type | Severity | Trigger |
|------|----------|---------|
| `pipeline_complete` | info | Pipeline finishes successfully |
| `pipeline_failed` | error | Pipeline crashes or times out |
| `hot_lead_found` | info | Lead scores 85+ on hiring intensity |
| `api_limit_warning` | warning | API spend exceeds 80% of daily budget |
| `serpapi_low` | warning | SerpAPI credits below 20 |
| `delivery_sent` | info | Leads emailed to an agency |
| `verification_failure_rate` | warning | More than 30% of leads fail verification |
| `new_agency_signup` | info | Agency added to the system |

### Notification Delivery

**MVP (Phase 1):** Dashboard-only. Notifications badge in sidebar.
**Phase 2:** Email notifications via SMTP (Python `smtplib`).
**Phase 3:** Slack webhook integration (optional).

---

## 14. Rate Limiting & Queue Management

### OpenAI Rate Limits
- `enrichment_delay_seconds`: 2 seconds between calls (configurable)
- `daily_budget_usd`: $5.00 (stop all non-critical calls if exceeded)
- Track in `api_usage` table, sum daily costs before each call
- If budget exceeded: skip enrichment/verification for remaining companies, use fallback emails

### SerpAPI Rate Limits
- Track `serpapi_calls` in `pipeline_runs`
- Check against `serpapi_monthly_limit` setting
- If approaching limit: reduce discovery scope, rely more on OpenAI discovery

### Queue for Large Batches
For batches > 100 companies:
- Process in chunks of 50
- Save progress after each chunk (allows resume on failure)
- Update dashboard progress bar: "Enriching 50/200..."

---

## 15. Logging Architecture

### Structured Logging (structlog)

```python
import structlog

logger = structlog.get_logger()

# Every log entry includes context
logger.info("enrichment_complete",
    company="stripe.com",
    contact_found=True,
    contact_name="Kris Raghavan",
    confidence=88,
    api_cost=0.01,
    duration_ms=2340,
    pipeline_run_id=42
)
```

### Log Levels
- **DEBUG**: API request/response bodies (only in dev mode)
- **INFO**: Successful operations, pipeline progress
- **WARNING**: Non-critical failures (one company failed, pipeline continues)
- **ERROR**: Stage failures, API errors that stop processing
- **CRITICAL**: Pipeline crash, API key invalid, database connection lost

### Log Storage
- File: `logs/connectoros_{date}.jsonl` (JSON lines format)
- Retained for 30 days
- Queryable from the dashboard (Page 6: Cost & Usage includes error logs)

---

## 16. Error Recovery & Retry

### Retry Strategy

```python
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=2, max=30),
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.HTTPStatusError))
)
async def call_openai(messages, tools=None):
    # ... API call logic
```

### Error Scenarios

| Error | Action | Resume Strategy |
|-------|--------|-----------------|
| OpenAI 429 (rate limit) | Wait 30s, retry 3x | Resume from where it stopped |
| OpenAI 401 (bad key) | STOP pipeline, alert | Fix key in settings, re-run |
| OpenAI 500 (server error) | Retry 3x with backoff | Skip company, continue batch |
| OpenAI timeout (>30s) | Skip company | Log warning, move to next |
| JSON parse error | Try regex extraction | If fails, use fallback data |
| SerpAPI error | Skip job board source | Continue with other sources |
| Database error | STOP pipeline, alert | Fix DB, re-run from checkpoint |
| Network error | Retry 3x | If persistent, stop and alert |

### Checkpointing
After processing every 10 companies, save progress to database. If pipeline crashes, the next run can query "companies discovered but not enriched" and resume from there.

---

## 17. Data Retention & Cleanup

### Cleanup Job (runs weekly on Sunday 3 AM)

```python
def cleanup_old_data():
    retention_days = int(settings.get("data_retention_days"))  # default 180
    cutoff = datetime.now() - timedelta(days=retention_days)
    
    # Archive old leads (don't delete — move to archive status)
    db.execute("UPDATE leads SET status = 'archived' WHERE created_at < ? AND status = 'new'", cutoff)
    
    # Delete old API usage logs (these can be deleted)
    db.execute("DELETE FROM api_usage WHERE created_at < ?", cutoff)
    
    # Delete old notifications
    db.execute("DELETE FROM notifications WHERE created_at < ? AND is_dismissed = TRUE", cutoff)
    
    # Delete old search history
    db.execute("DELETE FROM search_history WHERE created_at < ?", cutoff)
    
    # Mark inactive job postings
    db.execute("UPDATE job_postings SET is_active = FALSE WHERE last_scraped < ?",
               datetime.now() - timedelta(days=30))
    
    # NEVER delete: companies, contacts, deliveries (these are your historical moat)
```

---

## 18. Settings & Configuration

All settings stored in the `settings` database table (see Section 2). Editable from Dashboard Page 7.

### Environment Variables (.env)

```env
# API Keys (NEVER commit these)
OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxx
SERPAPI_KEY=xxxxxxxxxxxxxxxx

# Database
DATABASE_URL=sqlite:///data/connectoros.db

# Server
HOST=0.0.0.0
PORT=8000
LOG_LEVEL=INFO

# Dashboard
STREAMLIT_PORT=8501
```

---

## 19. All OpenAI Prompts (Final)

See the separate `prompts.yaml` file delivered earlier. It contains:
- Discovery system + user prompts
- Enrichment system + user prompts
- Email generation system + user prompts
- Verification system + user prompts
- Fallback email patterns

---

## 20. Complete File Structure

```
connectoros/
├── core/
│   ├── __init__.py
│   ├── config.py              # Load .env + settings table
│   ├── models.py              # All Pydantic models (Section 3)
│   ├── database.py            # SQLAlchemy setup + all table definitions
│   ├── exceptions.py          # CustomError, APIError, ValidationError, etc.
│   └── logger.py              # structlog configuration
│
├── discovery/
│   ├── __init__.py
│   ├── serpapi_collector.py    # SerpAPI Google Jobs scraper
│   ├── remoteok_collector.py  # RemoteOK JSON API
│   ├── hn_collector.py        # HN Who's Hiring parser
│   ├── wellfound_collector.py # Wellfound scraper
│   ├── openai_discovery.py    # OpenAI web search discovery
│   ├── deduplicator.py        # Domain normalization + fuzzy matching
│   └── discovery_engine.py    # Orchestrates all discovery sources
│
├── enrichment/
│   ├── __init__.py
│   ├── openai_enricher.py     # Contact finding via OpenAI web search
│   ├── email_generator.py     # Email pattern generation via OpenAI
│   ├── fallback_emails.py     # Generic role-based emails (no API)
│   └── enrichment_engine.py   # Orchestrates enrichment waterfall
│
├── verification/
│   ├── __init__.py
│   ├── openai_verifier.py     # Cross-check via OpenAI web search
│   ├── technical_checks.py    # DNS, MX, LinkedIn, email format checks
│   ├── confidence_scorer.py   # Calculate data_confidence 0-100
│   └── verification_engine.py # Orchestrates all verification layers
│
├── scoring/
│   ├── __init__.py
│   ├── hiring_scorer.py       # Hiring intensity 0-100
│   ├── priority_matrix.py     # Combine scores into priority tiers
│   └── notes_generator.py     # Auto-generate lead summary notes
│
├── export/
│   ├── __init__.py
│   ├── excel_generator.py     # Multi-sheet .xlsx with formatting
│   ├── csv_generator.py       # Simple CSV export
│   └── delivery_ledger.py     # Track deliveries, prevent duplicates
│
├── dashboard/
│   ├── app.py                 # Streamlit entry point + sidebar nav
│   ├── pages/
│   │   ├── 1_pipeline_overview.py
│   │   ├── 2_lead_browser.py
│   │   ├── 3_manual_search.py
│   │   ├── 4_analytics.py
│   │   ├── 5_agencies.py
│   │   ├── 6_cost_usage.py
│   │   ├── 7_settings.py
│   │   └── 8_notifications.py
│   └── components/
│       ├── lead_card.py       # Reusable lead detail component
│       ├── score_badge.py     # Color-coded score display
│       └── charts.py          # Plotly chart helpers
│
├── pipeline/
│   ├── __init__.py
│   ├── orchestrator.py        # Main pipeline: runs all stages
│   └── scheduler.py           # APScheduler cron setup
│
├── api/
│   ├── __init__.py
│   ├── main.py                # FastAPI app
│   ├── routes/
│   │   ├── pipeline.py        # /start, /stop, /status endpoints
│   │   ├── leads.py           # /leads, /leads/{id} endpoints
│   │   ├── agencies.py        # /agencies CRUD endpoints
│   │   └── search.py          # /search/company, /search/contact endpoints
│   └── middleware.py           # Auth, logging, error handling
│
├── config/
│   ├── prompts.yaml           # All OpenAI prompts
│   └── icp_templates/         # Preset ICP configs for common agency types
│       ├── tech_us.yaml
│       ├── tech_india.yaml
│       └── tech_uae.yaml
│
├── data/                      # SQLite database + exports live here
│   ├── connectoros.db
│   └── exports/               # Generated Excel files
│
├── logs/                      # JSON structured logs
│
├── tests/
│   ├── test_discovery.py
│   ├── test_enrichment.py
│   ├── test_verification.py
│   ├── test_scoring.py
│   └── test_export.py
│
├── .env                       # API keys (never commit)
├── .gitignore
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
└── README.md
```

---

## 21. Dependencies (requirements.txt)

```
# Core
python-dotenv==1.0.0
pydantic==2.6.0
structlog==24.1.0

# Database
sqlalchemy==2.0.25
alembic==1.13.0          # migrations

# API Framework
fastapi==0.109.0
uvicorn==0.27.0

# HTTP Client
httpx==0.26.0
tenacity==8.2.3          # retry logic

# AI
openai==1.12.0

# Job Boards
google-search-results==2.4.2   # SerpAPI

# Dashboard
streamlit==1.31.0
plotly==5.18.0

# Excel Export
openpyxl==3.1.2

# Data Processing
pandas==2.2.0

# DNS Checks
dnspython==2.5.0

# Fuzzy Matching
thefuzz==0.22.1          # for company name dedup
python-Levenshtein==0.25.0

# Scheduling
apscheduler==3.10.4

# YAML Config
pyyaml==6.0.1
```

---

## 22. Build Order (Day by Day)

### Day 1: Foundation + Discovery
- Set up project structure (all directories)
- Create `.env`, `config.py`, `models.py`
- Create `database.py` with ALL table definitions
- Run `alembic init` for future migrations
- Port existing SerpAPI collector
- Test: run discovery, see companies in database

### Day 2: Enrichment + Email
- Build `openai_enricher.py` (with web_search_preview)
- Build `email_generator.py`
- Build `enrichment_engine.py` (orchestrator)
- Test: enrich 10 companies, check contacts in database
- Check: are names real? Are LinkedIn URLs valid?

### Day 3: Verification + Scoring
- Build `technical_checks.py` (DNS, MX, LinkedIn, email format)
- Build `openai_verifier.py` (cross-check prompt)
- Build `confidence_scorer.py`
- Build `hiring_scorer.py` + `priority_matrix.py`
- Test: verify 10 enriched companies, check scores make sense

### Day 4: Export + Pipeline
- Build `excel_generator.py` (multi-sheet, formatted)
- Build `delivery_ledger.py`
- Build `pipeline/orchestrator.py` (wire all 5 stages)
- Test: run full pipeline end-to-end for 50 companies
- Open the Excel in a spreadsheet — does it look professional?

### Day 5: Dashboard Part 1
- Build Streamlit `app.py` with sidebar navigation
- Build Page 1: Pipeline Overview
- Build Page 2: Lead Browser (table + detail view)
- Build Page 3: Manual Search
- Test: can you search a company and see results?

### Day 6: Dashboard Part 2
- Build Page 4: Analytics (charts, distributions)
- Build Page 5: Agency Management (CRUD + ICP config)
- Build Page 6: Cost & Usage
- Build Page 7: Settings
- Build Page 8: Notifications

### Day 7: Polish + Launch
- Add `scheduler.py` (APScheduler for automated runs)
- Add error handling everywhere (try/catch on all API calls)
- Add logging (structlog on all operations)
- Run full pipeline 3 times, fix any bugs
- Generate sample delivery for a mock agency
- Review every field in the Excel for accuracy
- **Start reaching out to agencies**

---

## 23. Cost Breakdown (Final)

### Per Pipeline Run (50 companies)

| Stage | API Calls | Cost Per Call | Total |
|-------|-----------|--------------|-------|
| Discovery (job boards) | 3-5 SerpAPI | Free tier | $0.00 |
| Discovery (OpenAI) | 2-3 calls | $0.01-0.03 | $0.06 |
| Enrichment | 50 calls | $0.01 | $0.50 |
| Email Generation | 50 calls | $0.003 | $0.15 |
| Verification | 50 calls | $0.01 | $0.50 |
| **Total per run** | | | **$1.21** |

### Monthly (4 runs)

| Item | Cost |
|------|------|
| OpenAI API | ~$5.00 |
| SerpAPI (free tier) | $0.00 |
| Hosting (local) | $0.00 |
| **Total monthly** | **~$5.00 (~₹420)** |

### Revenue vs Cost

| Clients | Monthly Revenue | Monthly Cost | Profit | Margin |
|---------|----------------|--------------|--------|--------|
| 1 agency | ₹15,000 | ₹420 | ₹14,580 | 97% |
| 3 agencies | ₹60,000 | ₹420 | ₹59,580 | 99% |
| 5 agencies | ₹1,00,000 | ₹420 | ₹99,580 | 99.6% |

---

> **This document is complete. Everything you need is here.**
> Database tables. Pydantic models. Pipeline logic. Verification algorithms.
> Scoring formulas. Dashboard wireframes for every page. Manual search interface.
> Scheduling. Agency management. Notifications. Error handling. Logging.
> File structure. Dependencies. Build order. Cost math.
>
> **Stop planning. Start building. Day 1 starts now.**
