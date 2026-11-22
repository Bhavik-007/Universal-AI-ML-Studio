"""Fail-closed application, role, server and tool authorization."""
from __future__ import annotations
from .models import MCPServer

class MCPAccessDenied(PermissionError): pass

def authorize(server: MCPServer, *, username: str, role: str, app_id: str, tool_name: str | None = None) -> None:
    if not server.enabled:
        raise MCPAccessDenied("MCP server is disabled.")
    if role.lower() not in {item.lower() for item in server.allowed_roles}:
        raise MCPAccessDenied("Your role is not authorized for this MCP server.")
    platform_admin = app_id == "platform_admin" and role.lower() in {"admin", "administrator"}
    if not platform_admin and (username in server.denied_users or ("*" not in server.allowed_users and username not in server.allowed_users)):
        raise MCPAccessDenied("This user is not authorized for this MCP server.")
    if not platform_admin and "*" not in server.allowed_apps and app_id not in server.allowed_apps:
        raise MCPAccessDenied("This application is not authorized for this MCP server.")
    if tool_name:
        if tool_name in server.denied_tools:
            raise MCPAccessDenied("This tool is explicitly denied by policy.")
        if "*" not in server.allowed_tools and tool_name not in server.allowed_tools:
            raise MCPAccessDenied("This tool is not allow-listed for this MCP server.")
