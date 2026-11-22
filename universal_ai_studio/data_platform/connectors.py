"""Dataset connectors backed by centrally configured platform integrations."""
from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import pandas as pd


class DatasetConnectionError(RuntimeError):
    """Raised when a dataset source cannot be read as a tabular frame."""


def list_sql_server_tables() -> list[str]:
    """List tables from the administrator-configured SQL Server integration."""
    from sqlalchemy import inspect
    from universal_ai_studio.integrations.manager import IntegrationManager

    try:
        engine = IntegrationManager().create_sqlalchemy_engine()
        try:
            inspector = inspect(engine)
            schemas = inspector.get_schema_names()
            preferred = inspector.default_schema_name
            schema = preferred if preferred in schemas else ("dbo" if "dbo" in schemas else None)
            names = inspector.get_table_names(schema=schema)
            return [f"{schema}.{name}" for name in names] if schema else names
        finally:
            engine.dispose()
    except Exception as exc:
        raise DatasetConnectionError(
            "Could not list SQL Server tables. Check Platform Administration → Integrations, "
            f"SQL Server enablement, network access and encrypted credentials. Details: {exc}"
        ) from exc


def load_sql_server_table(table_name: str, *, max_rows: int = 100_000) -> pd.DataFrame:
    """Read a bounded sample of a reflected table from configured SQL Server."""
    from sqlalchemy import MetaData, Table, select
    from universal_ai_studio.integrations.manager import IntegrationManager

    if not table_name or len(table_name) > 256 or any(token in table_name for token in (";", "--", "/*", "*/")):
        raise DatasetConnectionError("Invalid table selection.")
    schema, separator, name = table_name.partition(".")
    if not separator:
        name, schema = schema, None
    try:
        engine = IntegrationManager().create_sqlalchemy_engine()
        try:
            table = Table(name, MetaData(), schema=schema, autoload_with=engine)
            frame = pd.read_sql_query(select(table).limit(int(max_rows)), engine)
        finally:
            engine.dispose()
    except Exception as exc:
        raise DatasetConnectionError(f"Could not read SQL Server table '{table_name}': {exc}") from exc
    if frame.empty:
        raise DatasetConnectionError(f"SQL Server table '{table_name}' returned no rows.")
    return frame


def load_rest_dataset(endpoint_path: str, *, max_response_bytes: int = 100 * 1024 * 1024) -> pd.DataFrame:
    """Read a JSON tabular response from the administrator-configured REST API."""
    from universal_ai_studio.integrations.manager import IntegrationManager

    path = (endpoint_path or "").strip()
    parsed = urlparse(path)
    if not path or parsed.scheme or parsed.netloc or path.startswith("//") or ".." in path.split("/"):
        raise DatasetConnectionError("Enter a relative endpoint path, not a full URL or path traversal.")
    try:
        session, base_url, timeout = IntegrationManager().create_rest_session()
        response = session.get(base_url.rstrip("/") + "/" + path.lstrip("/"), timeout=timeout, stream=True)
        response.raise_for_status()
        chunks, total = [], 0
        for chunk in response.iter_content(chunk_size=64 * 1024):
            if not chunk:
                continue
            total += len(chunk)
            if total > max_response_bytes:
                raise DatasetConnectionError("REST response exceeded the configured 100 MB limit.")
            chunks.append(chunk)
        import json
        raw: Any = json.loads(b"".join(chunks).decode("utf-8-sig"))
        if isinstance(raw, dict):
            candidates = [value for value in raw.values() if isinstance(value, list)]
            if len(candidates) == 1 and candidates[0] and isinstance(candidates[0][0], dict):
                raw = candidates[0]
            elif all(not isinstance(value, (dict, list)) for value in raw.values()):
                raw = [raw]
        frame = pd.json_normalize(raw) if isinstance(raw, (list, dict)) else pd.DataFrame()
    except DatasetConnectionError:
        raise
    except Exception as exc:
        raise DatasetConnectionError(f"REST dataset request failed: {type(exc).__name__}: {exc}") from exc
    if frame.empty:
        raise DatasetConnectionError("The REST endpoint returned no tabular records.")
    return frame
