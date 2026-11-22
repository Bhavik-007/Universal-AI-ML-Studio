"""Typed structures and validation helpers for registered MCP servers."""
from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Any
import re

SERVER_KEY = re.compile(r"^[a-z][a-z0-9_-]{1,62}$")
ENV_NAME = re.compile(r"^[A-Z_][A-Z0-9_]{1,127}$")
ALLOWED_STDIO_COMMANDS = {"python", "python3", "uv", "uvx", "npx", "node", "docker"}

@dataclass(frozen=True)
class MCPServer:
    key: str
    name: str
    transport: str
    enabled: bool = True
    url: str = ""
    command: str = ""
    args: tuple[str, ...] = ()
    env_refs: dict[str, str] | None = None
    allowed_users: tuple[str, ...] = ("*",)
    denied_users: tuple[str, ...] = ()
    allowed_apps: tuple[str, ...] = ("*",)
    allowed_roles: tuple[str, ...] = ("admin", "user")
    allowed_tools: tuple[str, ...] = ("*",)
    denied_tools: tuple[str, ...] = ()
    timeout_seconds: int = 30
    description: str = ""

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "MCPServer":
        return cls(
            key=str(value["key"]), name=str(value["name"]),
            transport=str(value.get("transport", "streamable_http")),
            enabled=bool(value.get("enabled", True)), url=str(value.get("url", "")),
            command=str(value.get("command", "")), args=tuple(value.get("args", [])),
            env_refs=dict(value.get("env_refs", {})),
            allowed_users=tuple(value.get("allowed_users", ["*"])),
            denied_users=tuple(value.get("denied_users", [])),
            allowed_apps=tuple(value.get("allowed_apps", ["*"])),
            allowed_roles=tuple(value.get("allowed_roles", ["admin", "user"])),
            allowed_tools=tuple(value.get("allowed_tools", ["*"])),
            denied_tools=tuple(value.get("denied_tools", [])),
            timeout_seconds=max(1, min(int(value.get("timeout_seconds", 30)), 300)),
            description=str(value.get("description", "")),
        )

    def validate(self) -> None:
        if not SERVER_KEY.fullmatch(self.key):
            raise ValueError("Server key must be lowercase letters, numbers, underscore or hyphen.")
        if not self.name.strip() or len(self.name) > 100:
            raise ValueError("Server name must contain 1–100 characters.")
        if self.transport not in {"stdio", "streamable_http"}:
            raise ValueError("Transport must be stdio or streamable_http.")
        if self.transport == "streamable_http":
            from urllib.parse import urlparse
            parsed = urlparse(self.url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError("Streamable HTTP requires a valid http:// or https:// MCP endpoint.")
        else:
            import os
            executable = self.command.replace("\\\\", "/").rsplit("/", 1)[-1].lower().split(".", 1)[0]
            if executable not in ALLOWED_STDIO_COMMANDS:
                raise ValueError(f"STDIO command is not allow-listed. Allowed: {', '.join(sorted(ALLOWED_STDIO_COMMANDS))}")
            if any(not isinstance(arg, str) or len(arg) > 2048 for arg in self.args):
                raise ValueError("STDIO arguments must be strings no longer than 2048 characters.")
        for key, ref in (self.env_refs or {}).items():
            if not ENV_NAME.fullmatch(key) or not ENV_NAME.fullmatch(ref):
                raise ValueError("Environment variable names and references must be uppercase identifiers.")
        if not self.allowed_users or not self.allowed_apps or not self.allowed_roles:
            raise ValueError("At least one user, application and role scope is required.")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
