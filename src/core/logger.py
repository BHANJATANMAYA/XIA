"""
core/logger.py

Centralized logging for xia.
- Logs to both console and rotating file on the SSD.
- Uses Rich for pretty console output.
- Single call to get_logger() from anywhere in the codebase.

Usage:
    from core.logger import get_logger
    log = get_logger(__name__)
    log.info("Agent started")
    log.debug("Tool called: %s", tool_name)
"""

import logging
import logging.handlers
from typing import Optional

from core.paths import PATHS


# Will be set properly after config loads — use a default until then
_DEFAULT_LEVEL = "INFO"
_initialized = False


def _get_log_level(level_str: str) -> int:
    return getattr(logging, level_str.upper(), logging.INFO)


def setup_logging(
    level: str = _DEFAULT_LEVEL,
    log_to_file: bool = True,
    max_bytes: int = 10 * 1024 * 1024,
    backup_count: int = 3,
):
    """
    Configure root logger. Call once at application startup.
    Subsequent calls to get_logger() will inherit this config.
    """
    global _initialized

    root = logging.getLogger()
    root.setLevel(_get_log_level(level))

    # Avoid adding duplicate handlers on re-import
    if _initialized:
        return
    _initialized = True

    fmt = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)-25s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # ── Console handler ───────────────────────────────────────────────────
    console = logging.StreamHandler()
    console.setFormatter(fmt)
    
    # Only show WARNING+ on the console to prevent cluttering the clean CLI UI,
    # unless the user explicitly requested DEBUG level (e.g. via XIA_DEBUG=true)
    console_level = logging.DEBUG if level.upper() == "DEBUG" else logging.WARNING
    console.setLevel(console_level)
    
    root.addHandler(console)

    # ── File handler (rotating) ────────────────────────────────────────────
    if log_to_file:
        log_file = PATHS.main_log_file
        file_handler = logging.handlers.RotatingFileHandler(
            filename=log_file,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        file_handler.setFormatter(fmt)
        file_handler.setLevel(logging.DEBUG)  # File always captures DEBUG
        root.addHandler(file_handler)

    # Silence noisy third-party loggers
    for noisy in ["httpx", "httpcore", "urllib3", "chromadb"]:
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """
    Get a named logger. Call at the top of each module:
        log = get_logger(__name__)
    """
    return logging.getLogger(name or "xia")
