"""Structured application logging with conservative secret/PII redaction."""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone

from app.infra.config import settings


_REDACTIONS = (
    (re.compile(r"(?i)(authorization\s*[:=]\s*bearer\s+)[^\s,;]+"), r"\1[REDACTED]"),
    (re.compile(r"(?i)(password|passwd|secret|token|cookie|session|api[_-]?key)(\s*[:=]\s*)[^\s,;&]+"), r"\1\2[REDACTED]"),
    (re.compile(r"(?i)(postgres(?:ql)?(?:\+\w+)?://[^:/\s]+:)[^@/\s]+(@)"), r"\1[REDACTED]\2"),
    (re.compile(r"(?i)\b(https?://[^/\s?#]+)(?:[^\s]*)"), r"\1/[REDACTED_URL]"),
    (re.compile(r"\b[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"), "[REDACTED_JWT]"),
    (re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b"), "[REDACTED_EMAIL]"),
    (re.compile(r"(?<!\d)(?:\+?98|0)?9\d{9}(?!\d)"), "[REDACTED_PHONE]"),
)


def redact(value: object) -> str:
    text = str(value)
    for pattern, replacement in _REDACTIONS:
        text = pattern.sub(replacement, text)
    return text


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "service": getattr(record, "service", os.getenv("SERVICE_NAME", "crawler")),
            "logger": record.name,
            "message": redact(record.getMessage()),
        }
        if record.exc_info:
            payload["exception"] = redact(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False)


class ServiceFilter(logging.Filter):
    def __init__(self, service: str):
        super().__init__()
        self.service = service

    def filter(self, record: logging.LogRecord) -> bool:
        record.service = self.service
        return True


def configure_logging(service: str) -> None:
    """Configure stdout once per process; Docker handles rotation/persistence."""
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    handler.addFilter(ServiceFilter(service))

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(settings.log_level.upper())
