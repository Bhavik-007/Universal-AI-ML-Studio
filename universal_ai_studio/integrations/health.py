"""Connectivity probes for configured platform integrations."""
from __future__ import annotations

from typing import Any

from universal_ai_studio.core.configuration import get_integration_secret, load_platform_config


def check_elasticsearch() -> tuple[bool, str]:
    config = load_platform_config()["integrations"]["elasticsearch"]
    try:
        from elasticsearch import Elasticsearch
        kwargs: dict[str, Any] = {"hosts": [config["url"]], "verify_certs": config.get("verify_certs", True), "request_timeout": int(config.get("timeout", 20))}
        api_key = get_integration_secret("elasticsearch", "api_key")
        username = get_integration_secret("elasticsearch", "username")
        password = get_integration_secret("elasticsearch", "password")
        if api_key:
            kwargs["api_key"] = api_key
        elif username and password:
            kwargs["basic_auth"] = (username, password)
        client = Elasticsearch(**kwargs)
        info = client.info()
        client.close()
        return True, f"Connected to Elasticsearch {info.get('version', {}).get('number', 'unknown')}"
    except Exception as exc:
        return False, f"Elasticsearch connection failed: {type(exc).__name__}: {exc}"


def check_kibana() -> tuple[bool, str]:
    """Check that Kibana's status API is reachable."""
    config = load_platform_config()["integrations"].get("kibana", {})
    if not config.get("enabled", True) or not config.get("url"):
        return False, "Kibana URL is not configured or the integration is disabled."
    try:
        import requests
        url = config["url"].rstrip("/") + "/api/status"
        response = requests.get(
            url, headers={"kbn-xsrf": "true"}, timeout=int(config.get("timeout", 10))
        )
        if not response.ok:
            return False, f"Kibana status endpoint returned HTTP {response.status_code}."
        try:
            payload = response.json()
            overall = payload.get("status", {}).get("overall", {})
            state = overall.get("state", "available")
            title = overall.get("title", "Kibana")
            return True, f"{title} is reachable (status: {state})."
        except (ValueError, AttributeError):
            return True, "Kibana status endpoint is reachable."
    except Exception as exc:
        return False, f"Kibana connection failed: {type(exc).__name__}: {exc}"


def check_ollama() -> tuple[bool, str]:
    config = load_platform_config()["integrations"]["ollama"]
    try:
        import requests
        response = requests.get(config["base_url"].rstrip("/") + "/api/tags", timeout=int(config.get("timeout", 60)))
        response.raise_for_status()
        return True, "Ollama API is reachable."
    except Exception as exc:
        return False, f"Ollama connection failed: {type(exc).__name__}: {exc}"


def check_rest_api() -> tuple[bool, str]:
    config = load_platform_config()["integrations"]["rest_api"]
    if not config.get("base_url"):
        return False, "REST API base URL is not configured."
    try:
        import requests
        headers = {}
        auth_type = config.get("auth_type", "none")
        token = get_integration_secret("rest_api", "bearer_token")
        api_key = get_integration_secret("rest_api", "api_key")
        if auth_type == "bearer_token" and token:
            headers["Authorization"] = f"Bearer {token}"
        elif auth_type == "api_key" and api_key:
            headers["X-API-Key"] = api_key
        response = requests.get(config["base_url"], headers=headers, timeout=int(config.get("timeout", 20)))
        return response.ok, f"HTTP {response.status_code} from configured REST endpoint."
    except Exception as exc:
        return False, f"REST API connection failed: {type(exc).__name__}: {exc}"


def check_graphql() -> tuple[bool, str]:
    config = load_platform_config()["integrations"]["graphql"]
    if not config.get("endpoint"):
        return False, "GraphQL endpoint is not configured."
    try:
        import requests
        headers = {"Content-Type": "application/json"}
        auth_type = config.get("auth_type", "none")
        token = get_integration_secret("graphql", "bearer_token")
        api_key = get_integration_secret("graphql", "api_key")
        if auth_type == "bearer_token" and token:
            headers["Authorization"] = f"Bearer {token}"
        elif auth_type == "api_key" and api_key:
            headers["X-API-Key"] = api_key
        response = requests.post(config["endpoint"], json={"query": "query HealthCheck { __typename }"}, headers=headers, timeout=int(config.get("timeout", 20)))
        if not response.ok:
            return False, f"HTTP {response.status_code} from GraphQL endpoint."
        payload = response.json()
        return "errors" not in payload, "GraphQL endpoint responded to introspection health query." if "errors" not in payload else "GraphQL endpoint returned an error response."
    except Exception as exc:
        return False, f"GraphQL connection failed: {type(exc).__name__}: {exc}"


def check_sql_server() -> tuple[bool, str]:
    config = load_platform_config()["integrations"]["sql_server"]
    if not config.get("server") or not config.get("database"):
        return False, "SQL Server host or database is not configured."
    try:
        import pyodbc
        parts = [f"DRIVER={{{config.get('driver', 'ODBC Driver 18 for SQL Server')}}}", f"SERVER={config['server']}", f"DATABASE={config['database']}", f"Encrypt={config.get('encrypt', 'yes')}", f"TrustServerCertificate={config.get('trust_server_certificate', 'no')}"]
        if config.get("auth_mode", "SQL").upper() == "WINDOWS":
            parts.append("Trusted_Connection=yes")
        else:
            username = get_integration_secret("sql_server", "username")
            password = get_integration_secret("sql_server", "password")
            if not username or not password:
                return False, "SQL Server username/password are not configured."
            parts.extend([f"UID={username}", f"PWD={password}"])
        connection = pyodbc.connect(";".join(parts), timeout=8)
        connection.close()
        return True, "SQL Server connection succeeded."
    except Exception as exc:
        return False, f"SQL Server connection failed: {type(exc).__name__}: {exc}"
