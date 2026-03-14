"""
ConnectorOS Scout — Configuration Manager

Security:
  - API keys loaded from .env file ONLY (never hardcoded)
  - .env is in .gitignore — never committed to version control
  - Settings with sensitive values are masked when logged
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
ROOT_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT_DIR / ".env"
load_dotenv(ENV_PATH)


# Runtime + writable directories
IS_VERCEL = os.getenv("VERCEL", "").lower() in {"1", "true"} or bool(os.getenv("VERCEL_ENV"))


def _resolve_runtime_base_dir() -> Path:
    """
    Resolve writable base directory for runtime artifacts.

    Vercel serverless functions use a read-only project filesystem, so we use
    /tmp (or TMPDIR/TMP) for mutable files like logs/exports.
    """
    if IS_VERCEL:
        tmp_base = Path(os.getenv("TMPDIR") or os.getenv("TMP") or "/tmp")
        return tmp_base / "connectoros"
    return ROOT_DIR


RUNTIME_BASE_DIR = _resolve_runtime_base_dir()
DATA_DIR = RUNTIME_BASE_DIR / "data"
EXPORTS_DIR = DATA_DIR / "exports"
LOGS_DIR = RUNTIME_BASE_DIR / "logs"

for _dir in (DATA_DIR, EXPORTS_DIR, LOGS_DIR):
    _dir.mkdir(parents=True, exist_ok=True)


# Environment Variable Access

def get_env(key: str, default: str = "") -> str:
    """Read an environment variable with a fallback default."""
    return os.getenv(key, default)


def get_env_list(key: str, default: list[str] | None = None) -> list[str]:
    """Read a comma-separated environment variable into a clean string list."""
    raw = os.getenv(key, "")
    if not raw:
        return list(default or [])
    return [item.strip() for item in raw.split(",") if item.strip()]


# API Keys (NEVER log these)
OPENAI_API_KEY: str = get_env("OPENAI_API_KEY")
SERPAPI_KEY: str = get_env("SERPAPI_KEY")


# Database (Supabase/Postgres only)
def _is_http_url(value: str) -> bool:
    return value.startswith("http://") or value.startswith("https://")


def _resolve_database_url() -> str:
    """
    Resolve database URL from env in Supabase/Postgres-only mode.

    Priority:
      1) DATABASE_URL
      2) SUPABASE_DB_URL / SUPABASE_DATABASE_URL
    """
    database_url = get_env("DATABASE_URL", "").strip()
    supabase_db_url = get_env("SUPABASE_DB_URL", "").strip() or get_env("SUPABASE_DATABASE_URL", "").strip()
    resolved = database_url or supabase_db_url

    if not resolved:
        raise ValueError(
            "Database URL is required. Set DATABASE_URL (or SUPABASE_DB_URL) to your Supabase Postgres URI."
        )

    if _is_http_url(resolved):
        raise ValueError(
            "Supabase API URL detected where database URL was expected. "
            "Set DATABASE_URL (or SUPABASE_DB_URL) to your Supabase Postgres URI."
        )

    if resolved.startswith("postgres://"):
        resolved = "postgresql://" + resolved[len("postgres://"):]

    if not (resolved.startswith("postgresql://") or resolved.startswith("postgresql+psycopg2://")):
        raise ValueError(
            "Only PostgreSQL connection strings are supported. "
            "Use Supabase Postgres URI like postgresql://...pooler.supabase.com:6543/postgres"
        )

    return resolved


DATABASE_URL: str = _resolve_database_url()


# Server
HOST: str = get_env("HOST", "0.0.0.0")
PORT: int = int(get_env("PORT", "8000"))
LOG_LEVEL: str = get_env("LOG_LEVEL", "INFO")


# Frontend / CORS
FRONTEND_PORT: str = get_env("FRONTEND_PORT", "5173")
FRONTEND_ORIGIN: str = get_env("FRONTEND_ORIGIN", f"http://localhost:{FRONTEND_PORT}")
CORS_ALLOWED_ORIGINS: list[str] = get_env_list(
    "CORS_ALLOWED_ORIGINS",
    default=[
        FRONTEND_ORIGIN,
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ],
)


# Sensitive keys that must never appear in logs
_SENSITIVE_KEYS = {"OPENAI_API_KEY", "SERPAPI_KEY"}


def mask_value(key: str, value: str) -> str:
    """Mask a value if its key is in the sensitive list."""
    if key.upper() in _SENSITIVE_KEYS and len(value) > 8:
        return value[:4] + "****" + value[-4:]
    return value


def get_safe_config_dict() -> dict:
    """Return config values safe for logging (secrets masked)."""
    return {
        "DATABASE_URL": DATABASE_URL,
        "HOST": HOST,
        "PORT": PORT,
        "LOG_LEVEL": LOG_LEVEL,
        "OPENAI_API_KEY": mask_value("OPENAI_API_KEY", OPENAI_API_KEY),
        "SERPAPI_KEY": mask_value("SERPAPI_KEY", SERPAPI_KEY),
    }
