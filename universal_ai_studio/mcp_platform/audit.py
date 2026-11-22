"""Append-only local JSONL audit events with conservative secret redaction."""
from __future__ import annotations
import json, re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
ROOT = Path(__file__).resolve().parents[2]
AUDIT_PATH = ROOT / "logs" / "mcp_execution.jsonl"
SECRET_KEYS = re.compile(r"(password|secret|token|api[_-]?key|authorization|credential)", re.I)

def redact(value: Any, depth: int = 0) -> Any:
    if depth > 8: return "[truncated]"
    if isinstance(value, dict):
        return {str(k): ("[REDACTED]" if SECRET_KEYS.search(str(k)) else redact(v, depth+1)) for k,v in value.items()}
    if isinstance(value, (list, tuple)): return [redact(v, depth+1) for v in value[:100]]
    if isinstance(value, str): return value[:12000]
    if value is None or isinstance(value, (bool,int,float)): return value
    return str(value)[:2000]

def record(event: dict[str, Any]) -> None:
    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {"timestamp": datetime.now(timezone.utc).isoformat(), **redact(event)}
    with AUDIT_PATH.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
