import json

from universal_ai_studio.core import logging as platform_logging


def test_audit_events_redact_secret_fields(monkeypatch, tmp_path):
    monkeypatch.setattr(platform_logging, "AUDIT_LOG_PATH", tmp_path / "logs" / "audit.jsonl")
    platform_logging.write_audit_event(
        actor="admin",
        event="integration.settings_updated",
        details={"integration": "sql_server", "password": "do-not-write", "nested": {"api_key": "also-secret"}},
    )
    record = json.loads(platform_logging.AUDIT_LOG_PATH.read_text(encoding="utf-8"))
    assert record["actor"] == "admin"
    assert record["details"]["password"] == "[REDACTED]"
    assert record["details"]["nested"]["api_key"] == "[REDACTED]"
    assert "do-not-write" not in platform_logging.AUDIT_LOG_PATH.read_text(encoding="utf-8")


def test_log_redaction_masks_passwords_and_bearer_tokens():
    assert platform_logging.redact_log_text("connection password=hunter2") == "connection password=[REDACTED]"
    assert platform_logging.redact_log_text("Authorization: Bearer abc.def.ghi") == "Authorization=[REDACTED]"
