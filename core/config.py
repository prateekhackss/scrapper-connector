"""
ConnectorOS Scout — Configuration Manager

Security:
  - API keys loaded from .env file ONLY (never hardcoded)
  - .env is in .gitignore — never committed to version control
  - Settings with sensitive values are masked when logged
"""

import os
import shutil
from pathlib import Path
from dotenv import load_dotenv

# ── Load .env from project root ──────────────────────────────────
ROOT_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT_DIR / ".env"
load_dotenv(ENV_PATH)


# ── Data & Log Directories (auto-created) ────────────────────────
DATA_DIR = ROOT_DIR / "data"
EXPORTS_DIR = DATA_DIR / "exports"
LOGS_DIR = ROOT_DIR / "logs"

for _dir in (DATA_DIR, EXPORTS_DIR, LOGS_DIR):
    _dir.mkdir(parents=True, exist_ok=True)


# ── Environment Variable Access ──────────────────────────────────

def get_env(key: str, default: str = "") -> str:
    """Read an environment variable with a fallback default."""
    return os.getenv(key, default)


# ── API Keys (NEVER log these) ───────────────────────────────────
OPENAI_API_KEY: str = get_env("OPENAI_API_KEY")
SERPAPI_KEY: str = get_env("SERPAPI_KEY")

# ── Database ─────────────────────────────────────────────────────
def _default_sqlite_path() -> Path:
    """
    Resolve a stable default SQLite path.

    On Windows + OneDrive workspaces, SQLite can throw disk I/O errors due to
    sync/file-lock behavior. In that case, prefer LOCALAPPDATA storage.
    """
    default_path = DATA_DIR / "connectoros.db"

    if os.name != "nt":
        return default_path

    root_str = str(ROOT_DIR).lower()
    if "onedrive" not in root_str:
        return default_path

    local_appdata = os.getenv("LOCALAPPDATA")
    if not local_appdata:
        return default_path

    fallback_dir = Path(local_appdata) / "ConnectorOSScout" / "data"
    try:
        fallback_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        return default_path

    fallback_path = fallback_dir / "connectoros.db"

    # One-time best-effort copy from legacy project DB path to keep old data.
    if default_path.exists() and not fallback_path.exists():
        try:
            shutil.copy2(default_path, fallback_path)
        except Exception:
            pass

    return fallback_path


_default_db_file = _default_sqlite_path().as_posix()


def _is_http_url(value: str) -> bool:
    return value.startswith("http://") or value.startswith("https://")


def _resolve_database_url() -> str:
    """
    Resolve database URL from env with Supabase-friendly aliases.

    Priority:
      1) DATABASE_URL
      2) SUPABASE_DB_URL / SUPABASE_DATABASE_URL
      3) fallback SQLite
    """
    database_url = get_env("DATABASE_URL", "").strip()
    if database_url:
        return database_url

    supabase_db_url = get_env("SUPABASE_DB_URL", "").strip() or get_env("SUPABASE_DATABASE_URL", "").strip()
    if supabase_db_url:
        return supabase_db_url

    # Common misconfiguration: Supabase REST project URL is not a SQLAlchemy DB URL.
    supabase_api_url = get_env("SUPABASE_URL", "").strip() or get_env("NEXT_PUBLIC_SUPABASE_URL", "").strip()
    if supabase_api_url and _is_http_url(supabase_api_url):
        raise ValueError(
            "Supabase API URL detected, but a Postgres connection string is required for DATABASE_URL. "
            "Set DATABASE_URL (or SUPABASE_DB_URL) to your Supabase Postgres URI."
        )

    return f"sqlite:///{_default_db_file}"


DATABASE_URL: str = _resolve_database_url()

# ── Server ───────────────────────────────────────────────────────
HOST: str = get_env("HOST", "0.0.0.0")
PORT: int = int(get_env("PORT", "8000"))
LOG_LEVEL: str = get_env("LOG_LEVEL", "INFO")

# ── Sensitive Keys That Must Never Appear in Logs ────────────────
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
