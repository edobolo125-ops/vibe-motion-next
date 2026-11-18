"""Log ke berkas (berputar, maks ~1.5 MB) + penangkap error tak terduga."""
from __future__ import annotations

import logging
import sys
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .paths import app_data_dir

_configured = False


def log_dir() -> Path:
    d = app_data_dir() / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def setup_logging(level: int = logging.INFO, directory: Path | None = None) -> logging.Logger:
    """Idempoten. Mengarahkan sys.excepthook dan threading.excepthook ke log."""
    global _configured
    logger = logging.getLogger("vibemotion")
    if _configured:
        return logger
    logger.setLevel(level)
    handler = RotatingFileHandler((directory or log_dir()) / "app.log", maxBytes=500_000, backupCount=2,
                                  encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)

    def on_exc(exc_type, exc, tb):
        logger.critical("Unhandled exception", exc_info=(exc_type, exc, tb))

    sys.excepthook = on_exc
    threading.excepthook = lambda a: logger.critical(
        "Unhandled thread exception in %s", getattr(a.thread, "name", "?"),
        exc_info=(a.exc_type, a.exc_value, a.exc_traceback))
    _configured = True
    logger.info("=== start ===")
    return logger


def get_logger(name: str = "") -> logging.Logger:
    return logging.getLogger("vibemotion" + (f".{name}" if name else ""))
