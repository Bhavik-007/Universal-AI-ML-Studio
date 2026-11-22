import json
import pytest
from universal_ai_studio.mcp_platform.models import MCPServer
from universal_ai_studio.mcp_platform.registry import MCPRegistry
from universal_ai_studio.mcp_platform.permissions import authorize, MCPAccessDenied

def server(**overrides):
    values=dict(key="shared_tools",name="Shared Tools",transport="streamable_http",
                url="http://localhost:8000/mcp",allowed_apps=("marketing",),
                allowed_roles=("admin","user"),allowed_tools=("lookup",))
    values.update(overrides)
    return MCPServer(**values)

def test_registry_round_trip_and_secret_reference_only(tmp_path):
    path=tmp_path/"mcp_servers.json"
    registry=MCPRegistry(path)
    item=server(env_refs={"MCP_AUTHORIZATION":"INTERNAL_MCP_TOKEN"})
    registry.upsert(item)
    saved=path.read_text()
    assert "INTERNAL_MCP_TOKEN" in saved
    assert "actual-secret-value" not in saved
    loaded=registry.list()
    assert loaded[0].key=="shared_tools"
    assert loaded[0].env_refs["MCP_AUTHORIZATION"]=="INTERNAL_MCP_TOKEN"

def test_registry_rejects_unapproved_stdio_command():
    with pytest.raises(ValueError,match="allow-listed"):
        server(transport="stdio",command="bash",args=("-c","echo unsafe"),url="").validate()

def test_registry_rejects_invalid_http_endpoint():
    with pytest.raises(ValueError,match="valid http"):
        server(url="file:///etc/passwd").validate()

def test_authorization_enforces_application_scope():
    with pytest.raises(MCPAccessDenied,match="application"):
        authorize(server(),username="u",role="user",app_id="finance",tool_name="lookup")

def test_authorization_enforces_tool_allowlist():
    with pytest.raises(MCPAccessDenied,match="allow-listed"):
        authorize(server(),username="u",role="user",app_id="marketing",tool_name="delete_all")

def test_authorization_enforces_explicit_denial():
    with pytest.raises(MCPAccessDenied,match="explicitly denied"):
        authorize(server(allowed_tools=("*",),denied_tools=("dangerous",)),username="u",role="admin",app_id="marketing",tool_name="dangerous")

def test_disabled_server_fails_closed():
    with pytest.raises(MCPAccessDenied,match="disabled"):
        authorize(server(enabled=False),username="u",role="admin",app_id="marketing")


def test_authorization_enforces_user_allowlist():
    with pytest.raises(MCPAccessDenied,match="user"):
        authorize(server(allowed_users=("alice",)),username="bob",role="user",app_id="marketing",tool_name="lookup")

def test_authorization_enforces_explicit_user_deny():
    with pytest.raises(MCPAccessDenied,match="user"):
        authorize(server(denied_users=("bob",)),username="bob",role="admin",app_id="marketing",tool_name="lookup")
