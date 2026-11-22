"""Atomic JSON registry for MCP server definitions; secrets remain in process env."""
from __future__ import annotations
import json, os, tempfile
from pathlib import Path
from typing import Iterable
from .models import MCPServer

ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT / "config" / "mcp_servers.json"

class MCPRegistry:
    def __init__(self, path: Path = REGISTRY_PATH):
        self.path = Path(path)

    def list(self, enabled_only: bool = False) -> list[MCPServer]:
        if not self.path.exists():
            return []
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            items = [MCPServer.from_dict(item) for item in payload.get("servers", [])]
            for item in items: item.validate()
            return [item for item in items if item.enabled or not enabled_only]
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            raise RuntimeError("MCP server registry is invalid. Review config/mcp_servers.json.") from exc

    def save(self, servers: Iterable[MCPServer]) -> None:
        items = list(servers)
        keys = [item.key for item in items]
        if len(keys) != len(set(keys)):
            raise ValueError("MCP server keys must be unique.")
        for item in items: item.validate()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp = tempfile.mkstemp(prefix=".mcp-servers-", suffix=".tmp", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump({"schema_version": 1, "servers": [item.to_dict() for item in items]}, stream, indent=2)
                stream.flush(); os.fsync(stream.fileno())
            try: os.chmod(temp, 0o600)
            except OSError: pass
            os.replace(temp, self.path)
        finally:
            if os.path.exists(temp): os.unlink(temp)

    def upsert(self, server: MCPServer) -> None:
        server.validate()
        items = {item.key: item for item in self.list()}
        items[server.key] = server
        self.save(items.values())

    def delete(self, key: str) -> None:
        self.save(item for item in self.list() if item.key != key)

registry = MCPRegistry()
