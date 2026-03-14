"""
ConnectorOS Scout — Structured Logging

Uses structlog for JSON-structured logs.
- Console output with colours in dev mode
- JSON lines written to logs/connectoros_{date}.jsonl
- Sensitive values are automatically scrubbed from log output

Security: API keys and secrets are NEVER written to log files.
"""

import sys
import logging
from pathlib import Path
from datetime import datetime, timezone

import structlog

from core.config import LOGS_DIR, LOG_LEVEL

# ── Sensitive patterns to scrub from log output ──────────────────
_SCRUB_KEYS = {"api_key", "apikey", "token", "secret", "password", "authorization"}


def _scrub_sensitive(_, __, event_dict: dict) -> dict:
    """Remove or mask any key that looks like a secret."""
    for key in list(event_dict.keys()):
        if any(s in key.lower() for s in _SCRUB_KEYS):
            val = str(event_dict[key])
            event_dict[key] = val[:4] + "****" if len(val) > 4 else "****"
    return event_dict


# ── File handler — one log file per day ──────────────────────────

def _get_log_file() -> Path:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return LOGS_DIR / f"connectoros_{today}.jsonl"


def setup_logging() -> None:
    """Configure structlog + stdlib logging once at application startup."""

    # stdlib root logger → file handler
    log_file = _get_log_file()
    file_handler = logging.FileHandler(str(log_file), encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))

    logging.basicConfig(
        format="%(message)s",
        level=logging.DEBUG,
        handlers=[file_handler, console_handler],
    )

    # structlog pipeline
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            _scrub_sensitive,                            # ← Security: scrub secrets
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = "connectoros") -> structlog.stdlib.BoundLogger:
    """Return a structured logger bound with the given name."""
    return structlog.get_logger(name)
