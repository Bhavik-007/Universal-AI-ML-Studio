"""Policy-checked MCP operations and execution audit."""
from __future__ import annotations
import json, time, uuid
from typing import Any
from .audit import record
from .client_manager import MCPClientManager, run_async
from .permissions import authorize

class MCPExecutionError(RuntimeError): pass

class MCPExecutionEngine:
    def __init__(self, manager: MCPClientManager | None = None):
        self.manager = manager or MCPClientManager()

    def discover(self, server, *, username: str, role: str, app_id: str = "platform_admin"):
        authorize(server, username=username, role=role, app_id=app_id)
        started=time.monotonic(); execution_id=str(uuid.uuid4())
        try:
            result=run_async(self.manager.discover(server))
            from .catalog import catalog
            catalog.save(server.key,result,status="healthy")
            record({"execution_id":execution_id,"actor":username,"role":role,"app_id":app_id,"server":server.key,"operation":"discover","status":"success","duration_ms":round((time.monotonic()-started)*1000),"counts":{k:len(v) for k,v in result.items()}})
            return result
        except Exception as exc:
            from .catalog import catalog
            try: catalog.save(server.key,{},status="unhealthy",error=f"{type(exc).__name__}: {exc}")
            except Exception: pass
            record({"execution_id":execution_id,"actor":username,"role":role,"app_id":app_id,"server":server.key,"operation":"discover","status":"failed","duration_ms":round((time.monotonic()-started)*1000),"error":type(exc).__name__})
            raise MCPExecutionError(f"MCP discovery failed: {type(exc).__name__}: {exc}") from exc

    def call_tool(self, server, tool_name: str, arguments: dict[str, Any], *, username: str, role: str, app_id: str):
        authorize(server, username=username, role=role, app_id=app_id, tool_name=tool_name)
        started=time.monotonic(); execution_id=str(uuid.uuid4())
        try:
            discovery=run_async(self.manager.discover(server))
            tool=next((item for item in discovery["tools"] if item.get("name")==tool_name),None)
            if not tool: raise MCPExecutionError("Tool is not advertised by this server.")
            schema=tool.get("inputSchema") or {"type":"object"}
            try:
                from jsonschema import validate
                validate(instance=arguments, schema=schema)
            except ImportError:
                if not isinstance(arguments, dict): raise ValueError("Tool arguments must be a JSON object.")
            result=run_async(self.manager.call_tool(server,tool_name,arguments))
            record({"execution_id":execution_id,"actor":username,"role":role,"app_id":app_id,"server":server.key,"operation":"tool_call","tool":tool_name,"request":arguments,"response":result,"status":"success","duration_ms":round((time.monotonic()-started)*1000)})
            return result
        except Exception as exc:
            record({"execution_id":execution_id,"actor":username,"role":role,"app_id":app_id,"server":server.key,"operation":"tool_call","tool":tool_name,"request":arguments,"status":"failed","duration_ms":round((time.monotonic()-started)*1000),"error":type(exc).__name__,"message":str(exc)[:1000]})
            if isinstance(exc,MCPExecutionError): raise
            raise MCPExecutionError(f"MCP tool execution failed: {type(exc).__name__}: {exc}") from exc

    def read_resource(self, server, uri: str, *, username: str, role: str, app_id: str):
        authorize(server, username=username, role=role, app_id=app_id)
        started=time.monotonic(); execution_id=str(uuid.uuid4())
        try:
            result=run_async(self.manager.read_resource(server,uri))
            record({"execution_id":execution_id,"actor":username,"role":role,"app_id":app_id,"server":server.key,"operation":"resource_read","resource_uri":uri,"response":result,"status":"success","duration_ms":round((time.monotonic()-started)*1000)})
            return result
        except Exception as exc:
            record({"execution_id":execution_id,"actor":username,"role":role,"app_id":app_id,"server":server.key,"operation":"resource_read","resource_uri":uri,"status":"failed","duration_ms":round((time.monotonic()-started)*1000),"error":type(exc).__name__,"message":str(exc)[:1000]})
            raise MCPExecutionError(f"MCP resource read failed: {type(exc).__name__}: {exc}") from exc

    def get_prompt(self, server, prompt_name: str, arguments: dict[str, str] | None = None, *, username: str, role: str, app_id: str):
        authorize(server, username=username, role=role, app_id=app_id)
        started=time.monotonic(); execution_id=str(uuid.uuid4())
        try:
            result=run_async(self.manager.get_prompt(server,prompt_name,arguments))
            record({"execution_id":execution_id,"actor":username,"role":role,"app_id":app_id,"server":server.key,"operation":"prompt_get","prompt":prompt_name,"request":arguments or {},"response":result,"status":"success","duration_ms":round((time.monotonic()-started)*1000)})
            return result
        except Exception as exc:
            record({"execution_id":execution_id,"actor":username,"role":role,"app_id":app_id,"server":server.key,"operation":"prompt_get","prompt":prompt_name,"status":"failed","duration_ms":round((time.monotonic()-started)*1000),"error":type(exc).__name__,"message":str(exc)[:1000]})
            raise MCPExecutionError(f"MCP prompt retrieval failed: {type(exc).__name__}: {exc}") from exc

engine = MCPExecutionEngine()
