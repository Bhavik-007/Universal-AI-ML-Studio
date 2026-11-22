"""Structured logging with secret-safe fields only."""
from __future__ import annotations

import json
import logging
import re
from logging.handlers import RotatingFileHandler
from datetime import datetime, timezone

SENSITIVE_KEYS = {"authorization", "password", "token", "api_key", "secret", "connection_string"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "service": getattr(record, "service", "universal-ai-studio"),
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", None),
            "correlation_id": getattr(record, "correlation_id", None),
        }
        return json.dumps({key: value for key, value in event.items() if value is not None})


SECRET_PATTERNS = (
    re.compile(r"(?i)(password|pwd|api[_-]?key|access[_-]?token|client[_-]?secret|authorization)\s*[:=]\s*(?:Bearer\s+)?([^\s;,]+)"),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+"),
)


def redact_log_text(value: str) -> str:
    redacted = value
    for pattern in SECRET_PATTERNS:
        if pattern.pattern.lower().startswith("(?i)(password"):
            redacted = pattern.sub(r"\1=[REDACTED]", redacted)
        else:
            redacted = pattern.sub("Bearer [REDACTED]", redacted)
    return redacted


class SecretRedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            record.msg = redact_log_text(record.getMessage())
            record.args = ()
        except Exception:
            record.msg = "[log message redacted due to formatting error]"
            record.args = ()
        return True


def configure_logging() -> None:
    """Add a rotating JSONL file handler without removing host/Streamlit handlers."""
    root = logging.getLogger()
    for existing_handler in root.handlers:
        if not getattr(existing_handler, "_uas_redaction_filter", False):
            existing_handler.addFilter(SecretRedactionFilter())
            existing_handler._uas_redaction_filter = True
    if not any(getattr(handler, "_uas_file_handler", False) for handler in root.handlers):
        log_path = ROOT / "logs" / "application.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(log_path, maxBytes=5_000_000, backupCount=5, encoding="utf-8")
        handler.setFormatter(JsonFormatter())
        handler.addFilter(SecretRedactionFilter())
        handler._uas_redaction_filter = True
        handler._uas_file_handler = True
        root.addHandler(handler)
    root.setLevel(logging.INFO)

# Local audit events are kept separately from ordinary diagnostic logs. Values
# under secret-like keys are redacted recursively before writing.
from pathlib import Path
import os
import threading

ROOT = Path(__file__).resolve().parents[2]
AUDIT_LOG_PATH = ROOT / "logs" / "audit_events.jsonl"
_AUDIT_LOCK = threading.Lock()


def _redact_audit_details(value, key: str = ""):
    normalized = key.lower()
    if any(secret in normalized for secret in SENSITIVE_KEYS):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {str(k): _redact_audit_details(v, str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_redact_audit_details(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def write_audit_event(*, actor: str, event: str, details: dict | None = None) -> None:
    """Append a structured, secret-redacted administrator audit event."""
    from datetime import datetime, timezone
    import json

    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "actor": actor or "unknown",
        "event": event,
        "details": _redact_audit_details(details or {}),
    }
    AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(record, ensure_ascii=False, sort_keys=True)
    with _AUDIT_LOCK:
        with AUDIT_LOG_PATH.open("a", encoding="utf-8") as stream:
            stream.write(payload + "\n")
            stream.flush()
        try:
            os.chmod(AUDIT_LOG_PATH, 0o600)
        except OSError:
            pass
