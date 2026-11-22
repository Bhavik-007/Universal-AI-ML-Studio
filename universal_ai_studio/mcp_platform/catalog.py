"""Persistent metadata catalogue for discovered MCP tools, resources and prompts."""
from __future__ import annotations
import json, os, tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
ROOT=Path(__file__).resolve().parents[2]
CATALOG_PATH=ROOT/"config"/"mcp_capabilities.json"

class MCPCapabilityCatalog:
    def __init__(self,path:Path=CATALOG_PATH): self.path=Path(path)
    def _read(self):
        if not self.path.exists(): return {"schema_version":1,"servers":{}}
        try:
            value=json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(value,dict) or not isinstance(value.get("servers",{}),dict): raise ValueError
            return value
        except Exception as exc: raise RuntimeError("MCP capability catalogue is invalid.") from exc
    def get(self,key:str)->dict[str,Any] | None:
        return self._read()["servers"].get(key)
    def list(self)->dict[str,Any]:
        return self._read()["servers"]
    def save(self,key:str,capabilities:dict[str,Any],status:str="healthy",error:str="")->None:
        value=self._read()
        value["servers"][key]={
            "last_checked":datetime.now(timezone.utc).isoformat(),
            "status":status,
            "error":error[:1000],
            "tools":capabilities.get("tools",[]),
            "resources":capabilities.get("resources",[]),
            "prompts":capabilities.get("prompts",[]),
        }
        self.path.parent.mkdir(parents=True,exist_ok=True)
        fd,temp=tempfile.mkstemp(prefix=".mcp-catalog-",suffix=".tmp",dir=self.path.parent)
        try:
            with os.fdopen(fd,"w",encoding="utf-8") as stream:
                json.dump(value,stream,indent=2,ensure_ascii=False,default=str)
                stream.flush(); os.fsync(stream.fileno())
            try: os.chmod(temp,0o600)
            except OSError: pass
            os.replace(temp,self.path)
        finally:
            if os.path.exists(temp): os.unlink(temp)

catalog=MCPCapabilityCatalog()
