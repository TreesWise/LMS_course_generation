# core/config/logger.py
from __future__ import annotations

import logging
import logging.handlers
import os
import sys
from pathlib import Path
from typing import Dict, Optional


# -------- Settings (can be overridden via env vars) --------
DEFAULT_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
BACKUP_DAYS = int(os.getenv("LOG_BACKUP_DAYS", "14"))

# Default log dir: <project_root>/logs
# This file is .../oceanai_agents/config/logger.py  -> project root is 3 parents up
DEFAULT_LOG_DIR = Path(
    os.getenv("LOG_DIR", Path(__file__).resolve().parents[2] / "logs")
)


# -------- Colored formatter (no third-party deps) --------
class _Color:
    RESET = "\x1b[0m"
    DIM = "\x1b[2m"

    # Level colors
    COLORS = {
        "DEBUG": "\x1b[36m",  # cyan
        "INFO": "\x1b[32m",  # green
        "WARNING": "\x1b[33m",  # yellow
        "ERROR": "\x1b[31m",  # red
        "CRITICAL": "\x1b[35m",  # magenta
    }


def _supports_color(stream) -> bool:
    # Basic TTY check; Windows 10+ PowerShell supports ANSI by default.
    try:
        return stream.isatty()
    except Exception:
        return False


class ColoredFormatter(logging.Formatter):
    def __init__(self, fmt: str, datefmt: Optional[str] = None, use_color: bool = True):
        super().__init__(fmt=fmt, datefmt=datefmt)
        self.use_color = use_color and _supports_color(sys.stdout)

    def format(self, record: logging.LogRecord) -> str:
        original_levelname = record.levelname
        if self.use_color and original_levelname in _Color.COLORS:
            color = _Color.COLORS[original_levelname]
            record.levelname = f"{color}{original_levelname}{_Color.RESET}"
        try:
            return super().format(record)
        finally:
            record.levelname = original_levelname


# -------- Singleton logger configuration --------
_configured = False
_loggers: Dict[str, logging.Logger] = {}


def _ensure_log_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _build_handlers(log_dir: Path, level: int):
    # Console handler (colored)
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(level)
    console.setFormatter(
        ColoredFormatter(
            fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
            use_color=True,
        )
    )

    # File handler (size-based rotation, more Windows-friendly)
    _ensure_log_dir(log_dir)
    log_file = log_dir / "app.log"
    file_handler = logging.handlers.RotatingFileHandler(
        filename=str(log_file),
        maxBytes=10 * 1024 * 1024,  # 10MB per file
        backupCount=BACKUP_DAYS,  # Keep 14 backup files
        encoding="utf-8",
        delay=True,  # Don't open file until first write
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )

    return console, file_handler


def configure_logging(
    level: str | int = DEFAULT_LEVEL,
    log_dir: Path | str = DEFAULT_LOG_DIR,
) -> None:
    """
    Configure root logging once for the whole process.
    Safe to call multiple times; subsequent calls are no-ops.
    """
    global _configured

    if _configured:
        return

    numeric_level = (
        logging.getLevelName(level) if isinstance(level, str) else int(level)
    )
    if isinstance(numeric_level, str):  # invalid string -> fallback
        numeric_level = logging.INFO

    log_dir = Path(log_dir)

    # Configure root
    root = logging.getLogger()
    root.setLevel(numeric_level)

    # Remove any pre-existing default handlers to avoid duplicates
    for h in list(root.handlers):
        root.removeHandler(h)

    console, file_handler = _build_handlers(log_dir, numeric_level)
    root.addHandler(console)
    root.addHandler(file_handler)

    # Make third-party libraries a bit quieter by default (adjust as needed)
    logging.getLogger("uvicorn.error").setLevel(numeric_level)
    logging.getLogger("uvicorn.access").setLevel(numeric_level)
    logging.getLogger("httpx").setLevel(max(numeric_level, logging.WARNING))

    # Suppress Windows-specific asyncio ConnectionResetError noise
    # This is a known issue with ProactorEventLoop on Windows when connections close
    asyncio_logger = logging.getLogger("asyncio")
    asyncio_logger.setLevel(logging.CRITICAL)
    # Alternative: use a filter to suppress only connection reset errors
    # asyncio_logger.addFilter(lambda record: "ConnectionResetError" not in str(record.msg))

    _configured = True


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """
    Get a module-specific logger. Ensures global config is applied.
    Usage:
        logger = get_logger(__name__)
    """
    if not _configured:
        configure_logging()
    if name is None:
        name = "oceanai"
    if name not in _loggers:
        _loggers[name] = logging.getLogger(name)
    return _loggers[name]


# Optional utility to change level at runtime
def set_level(level: str | int) -> None:
    if not _configured:
        configure_logging(level=level)
    logging.getLogger().setLevel(
        level if isinstance(level, int) else logging.getLevelName(level)
    )
