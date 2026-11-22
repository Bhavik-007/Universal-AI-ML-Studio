"""Defence-in-depth validation for LLM-proposed, read-only SQL."""
from __future__ import annotations

import re


class SqlSafetyError(ValueError):
    pass


FORBIDDEN = re.compile(r"\b(insert|update|delete|drop|alter|create|grant|revoke|exec(?:ute)?|merge|truncate|backup|restore|into|attach|detach)\b", re.I)
COMMENT = re.compile(r"(--|/\*|\*/)")


def validate_read_only_sql(statement: str, allowed_tables: set[str] | None = None) -> str:
    normalized = " ".join(statement.strip().split())
    if not normalized or not re.match(r"^(select|with)\b", normalized, re.I):
        raise SqlSafetyError("Only SELECT or CTE queries are permitted.")
    if ";" in normalized.rstrip(";") or COMMENT.search(normalized) or FORBIDDEN.search(normalized):
        raise SqlSafetyError("Potentially unsafe SQL was rejected.")
    if allowed_tables:
        referenced = {name.lower() for name in re.findall(r"\b(?:from|join)\s+([\w.\[\]]+)", normalized, re.I)}
        permitted = {name.lower() for name in allowed_tables}
        if not referenced.issubset(permitted):
            raise SqlSafetyError("The query references a table outside the approved allowlist.")
    return normalized.rstrip(";")
