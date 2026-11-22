"""Stable application-facing facade for shared MCP discovery and execution."""
from __future__ import annotations
from .registry import registry
from .execution import engine

def discover_for_app(server_key: str, *, username: str, role: str, app_id: str):
    server = next((item for item in registry.list(enabled_only=True) if item.key == server_key), None)
    if server is None: raise KeyError(f"Enabled MCP server '{server_key}' was not found.")
    return engine.discover(server, username=username, role=role, app_id=app_id)

def execute_for_app(server_key: str, tool_name: str, arguments: dict, *, username: str, role: str, app_id: str):
    server = next((item for item in registry.list(enabled_only=True) if item.key == server_key), None)
    if server is None: raise KeyError(f"Enabled MCP server '{server_key}' was not found.")
    return engine.call_tool(server, tool_name, arguments, username=username, role=role, app_id=app_id)

def list_authorized_servers(*, username: str, role: str, app_id: str):
    from .permissions import authorize, MCPAccessDenied
    allowed=[]
    for server in registry.list(enabled_only=True):
        try: authorize(server, username=username, role=role, app_id=app_id)
        except MCPAccessDenied: continue
        allowed.append(server)
    return allowed


def read_resource_for_app(server_key: str, uri: str, *, username: str, role: str, app_id: str):
    server = next((item for item in registry.list(enabled_only=True) if item.key == server_key), None)
    if server is None: raise KeyError(f"Enabled MCP server '{server_key}' was not found.")
    return engine.read_resource(server, uri, username=username, role=role, app_id=app_id)

def get_prompt_for_app(server_key: str, prompt_name: str, arguments: dict[str, str] | None = None, *, username: str, role: str, app_id: str):
    server = next((item for item in registry.list(enabled_only=True) if item.key == server_key), None)
    if server is None: raise KeyError(f"Enabled MCP server '{server_key}' was not found.")
    return engine.get_prompt(server, prompt_name, arguments, username=username, role=role, app_id=app_id)
