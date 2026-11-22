"""In-process Strawberry GraphQL schema for the Streamlit GraphQL Explorer.

The schema is executed directly by the Streamlit page. No ASGI server or
separate Uvicorn process is needed for the integrated workspace.
"""
from __future__ import annotations

import json
import tomllib
from pathlib import Path

import strawberry

from database import get_table_columns, get_table_data, get_allowed_tables


@strawberry.type
class ColumnInfo:
    name: str
    data_type: str


@strawberry.type
class TableData:
    table_name: str
    columns: list[ColumnInfo]
    rows: list[str]


@strawberry.type
class Query:
    @strawberry.field
    def allowed_tables(self) -> list[str]:
        return get_allowed_tables()

    @strawberry.field
    def table_data(self, table_name: str, limit: int = 1000) -> TableData:
        if table_name not in get_allowed_tables():
            raise ValueError(f"Table '{table_name}' is not approved for access.")
        config_path = Path(__file__).with_name("config.toml")
        with config_path.open("rb") as stream:
            config = tomllib.load(stream)
        effective_limit = limit if limit > 0 else int(config.get("app", {}).get("page_size", 1000))
        column_names, rows = get_table_data(table_name, effective_limit)
        metadata = get_table_columns(table_name)
        columns = [
            ColumnInfo(name=item["name"], data_type=item.get("type") or "unknown")
            for item in metadata
            if item["name"] in column_names
        ]
        return TableData(
            table_name=table_name,
            columns=columns,
            rows=[json.dumps(row, default=str) for row in rows],
        )


schema = strawberry.Schema(query=Query)
