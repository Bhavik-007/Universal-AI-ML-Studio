"""Shared clients for centrally configured external integrations."""
from __future__ import annotations

from typing import Any

from universal_ai_studio.core.configuration import get_integration_secret, load_platform_config


class IntegrationDisabledError(RuntimeError):
    pass


class IntegrationManager:
    """Create clients from persisted platform settings rather than module-local env parsing."""

    def __init__(self) -> None:
        self.config = load_platform_config()["integrations"]

    def _section(self, name: str) -> dict[str, Any]:
        section = self.config.get(name, {})
        if not section.get("enabled", False):
            raise IntegrationDisabledError(f"Integration '{name}' is disabled in platform configuration.")
        return section

    def create_sqlalchemy_engine(self):
        from sqlalchemy import URL, create_engine
        section = self._section("sql_server")
        driver = section.get("driver", "ODBC Driver 18 for SQL Server")
        query = {
            "driver": driver,
            "Encrypt": section.get("encrypt", "yes"),
            "TrustServerCertificate": section.get("trust_server_certificate", "no"),
        }
        if section.get("auth_mode", "SQL").upper() == "WINDOWS":
            query["Trusted_Connection"] = "yes"
            url = URL.create("mssql+pyodbc", host=section["server"], database=section["database"], query=query)
        else:
            username = get_integration_secret("sql_server", "username")
            password = get_integration_secret("sql_server", "password")
            if not username or not password:
                raise ValueError("SQL Server credentials are not configured in encrypted storage.")
            url = URL.create("mssql+pyodbc", username=username, password=password, host=section["server"], database=section["database"], query=query)
        return create_engine(url, pool_pre_ping=True, pool_recycle=1800, connect_args={"timeout": 8})

    def create_rest_session(self):
        import requests
        section = self._section("rest_api")
        session = requests.Session()
        auth_type = section.get("auth_type", "none")
        token = get_integration_secret("rest_api", "bearer_token")
        api_key = get_integration_secret("rest_api", "api_key")
        if auth_type == "bearer_token" and token:
            session.headers["Authorization"] = f"Bearer {token}"
        elif auth_type == "api_key" and api_key:
            session.headers["X-API-Key"] = api_key
        session.headers.setdefault("Accept", "application/json")
        return session, section["base_url"], int(section.get("timeout", 20))

    def execute_graphql(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        import requests
        section = self._section("graphql")
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        auth_type = section.get("auth_type", "none")
        token = get_integration_secret("graphql", "bearer_token")
        api_key = get_integration_secret("graphql", "api_key")
        if auth_type == "bearer_token" and token:
            headers["Authorization"] = f"Bearer {token}"
        elif auth_type == "api_key" and api_key:
            headers["X-API-Key"] = api_key
        response = requests.post(section["endpoint"], json={"query": query, "variables": variables or {}}, headers=headers, timeout=int(section.get("timeout", 20)))
        response.raise_for_status()
        payload = response.json()
        if payload.get("errors"):
            raise RuntimeError("GraphQL endpoint returned one or more execution errors.")
        return payload.get("data", {})

    def create_elasticsearch_client(self):
        from elasticsearch import Elasticsearch
        section = self._section("elasticsearch")
        kwargs: dict[str, Any] = {"hosts": [section["url"]], "verify_certs": bool(section.get("verify_certs", True)), "request_timeout": int(section.get("timeout", 20))}
        api_key = get_integration_secret("elasticsearch", "api_key")
        username = get_integration_secret("elasticsearch", "username")
        password = get_integration_secret("elasticsearch", "password")
        if api_key:
            kwargs["api_key"] = api_key
        elif username and password:
            kwargs["basic_auth"] = (username, password)
        return Elasticsearch(**kwargs)
