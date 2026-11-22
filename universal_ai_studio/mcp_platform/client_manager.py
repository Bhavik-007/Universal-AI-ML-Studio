"""Short-lived MCP client sessions supporting STDIO and Streamable HTTP."""
from __future__ import annotations
import asyncio, os
from contextlib import asynccontextmanager
from typing import Any
from .models import MCPServer

class MCPUnavailable(RuntimeError): pass

def _server_env(server: MCPServer) -> dict[str, str]:
    result = {}
    for child_name, parent_name in (server.env_refs or {}).items():
        value = os.getenv(parent_name)
        if value:
            result[child_name] = value
    return result

@asynccontextmanager
async def _session(server: MCPServer):
    try:
        from mcp.client.session import ClientSession
        if server.transport == "stdio":
            from mcp.client.stdio import StdioServerParameters, stdio_client
            params = StdioServerParameters(command=server.command, args=list(server.args), env=_server_env(server) or None)
            async with stdio_client(params) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    yield session
        else:
            # MCP Python SDK v1.x API (dependency is constrained below v2).
            from mcp.client.streamable_http import streamablehttp_client
            headers = {}
            token_ref = (server.env_refs or {}).get("MCP_AUTHORIZATION")
            token = os.getenv(token_ref, "") if token_ref else ""
            if token:
                headers["Authorization"] = token if token.lower().startswith(("bearer ", "basic ")) else f"Bearer {token}"
            async with streamablehttp_client(
                server.url, headers=headers or None,
                timeout=server.timeout_seconds,
                sse_read_timeout=max(server.timeout_seconds, 60),
            ) as (read_stream, write_stream, _get_session_id):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    yield session
    except ImportError as exc:
        raise MCPUnavailable("MCP SDK is not installed. Install the root requirements.txt.") from exc

class MCPClientManager:
    """Each operation owns and closes a real protocol session; no stale pooled process."""
    def __init__(self, timeout_seconds: int = 30): self.timeout_seconds = timeout_seconds

    async def discover(self, server: MCPServer) -> dict[str, Any]:
        async with asyncio.timeout(server.timeout_seconds):
            async with _session(server) as session:
                tools = await session.list_tools()
                resources = await session.list_resources()
                prompts = await session.list_prompts()
                return {
                    "tools": [self._model_dump(item) for item in tools.tools],
                    "resources": [self._model_dump(item) for item in resources.resources],
                    "prompts": [self._model_dump(item) for item in prompts.prompts],
                }

    async def call_tool(self, server: MCPServer, name: str, arguments: dict[str, Any]) -> Any:
        async with asyncio.timeout(server.timeout_seconds):
            async with _session(server) as session:
                result = await session.call_tool(name, arguments)
                return self._model_dump(result)

    async def read_resource(self, server: MCPServer, uri: str) -> Any:
        async with asyncio.timeout(server.timeout_seconds):
            async with _session(server) as session:
                return self._model_dump(await session.read_resource(uri))

    async def get_prompt(self, server: MCPServer, name: str, arguments: dict[str, str] | None = None) -> Any:
        async with asyncio.timeout(server.timeout_seconds):
            async with _session(server) as session:
                return self._model_dump(await session.get_prompt(name, arguments or {}))

    @staticmethod
    def _model_dump(value: Any) -> Any:
        if hasattr(value, "model_dump"): return value.model_dump(mode="json")
        if hasattr(value, "dict"): return value.dict()
        if isinstance(value, list): return [MCPClientManager._model_dump(v) for v in value]
        return str(value)

def run_async(awaitable):
    """Run async MCP work from Streamlit's synchronous script context."""
    try: asyncio.get_running_loop()
    except RuntimeError: return asyncio.run(awaitable)
    raise RuntimeError("An asyncio event loop is already running; invoke MCP work from a worker context.")
