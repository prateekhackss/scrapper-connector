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
DATABASE_URL: str = get_env("DATABASE_URL", f"sqlite:///{DATA_DIR / 'connectoros.db'}")

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
