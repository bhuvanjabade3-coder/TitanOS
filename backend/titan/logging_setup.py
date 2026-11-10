"""Logging: console + rotating file, with secret redaction."""
from __future__ import annotations

import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path

_SECRET_PATTERNS = [
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9_\-\.]{16,}"),
    re.compile(r"(?i)((?:api[_-]?key|token|password|secret)\s*[=:]\s*)\S+"),
]


def redact(text: str) -> str:
    text = _SECRET_PATTERNS[0].sub("[REDACTED]", text)
    text = _SECRET_PATTERNS[1].sub(r"\1[REDACTED]", text)
    return _SECRET_PATTERNS[2].sub(r"\1[REDACTED]", text)


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(record.getMessage())
        record.args = None
        return True


def configure_logging(log_dir: Path, level: str = "INFO") -> logging.Logger:
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("titan")
    logger.setLevel(level.upper())
    for h in list(logger.handlers):  # idempotent across app re-creation
        logger.removeHandler(h)
        h.close()
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    handlers: list[logging.Handler] = [
        logging.StreamHandler(),
        RotatingFileHandler(log_dir / "titan.log", maxBytes=2_000_000, backupCount=5),
    ]
    for h in handlers:
        h.setFormatter(fmt)
        h.addFilter(RedactingFilter())
        logger.addHandler(h)
    logger.propagate = False
    return logger
