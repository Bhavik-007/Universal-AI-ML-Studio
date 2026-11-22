# Centralized MCP Platform

## Purpose and boundaries

Universal AI Studio provides one shared MCP control plane. Application modules should call
`universal_ai_studio.mcp_platform.api` rather than create their own MCP clients or registries.
The existing `pages/9_MCP_Model.py` is retained unchanged: it is the legacy repository
folder-structure explorer, not an MCP protocol client. The new administrator page is
**Central MCP Management**.

## Components

- `registry.py`: atomic, validated server registry at `config/mcp_servers.json`.
- `client_manager.py`: real MCP SDK sessions over STDIO and Streamable HTTP; sessions are
  opened for an operation and closed deterministically.
- `execution.py`: discovery and tool execution, input-schema validation, policy checks,
  bounded operation timeouts at the server configuration layer, error normalization and audit.
- `permissions.py`: fail-closed user, role, application, server and tool authorization.
- `catalog.py`: persistent metadata catalogue of discovered tools, resources, prompts and last discovery health status in `config/mcp_capabilities.json`.\n- `audit.py`: JSONL execution history in `logs/mcp_execution.jsonl`, with conservative
  secret-key redaction.
- `ui/mcp_management.py`: administrator UI for server registration, discovery, tool execution,
  resource reads, prompt retrieval and audit review.

## Transports and credentials

Install from the single root manifest. Supported transports are `stdio` and `streamable_http`.
STDIO executable names are allow-listed (`python`, `python3`, `uv`, `uvx`, `npx`, `node`,
`docker`) and commands are launched without a shell. STDIO environment mappings store only
child-variable to parent-variable names; secret values remain in the process environment.
For Streamable HTTP, use the `MCP_AUTHORIZATION` mapping key to point to an environment
variable containing a bearer token or authorization value.

Example server registry entry (the management UI can create it):

```json
{
  "key": "internal_tools",
  "name": "Internal Tools",
  "transport": "streamable_http",
  "enabled": true,
  "url": "http://localhost:8000/mcp",
  "env_refs": {"MCP_AUTHORIZATION": "INTERNAL_MCP_TOKEN"},
  "allowed_users": ["*"],
  "denied_users": [],
  "allowed_apps": ["marketing", "rag_sql"],
  "allowed_roles": ["admin", "user"],
  "allowed_tools": ["search", "summarize"],
  "denied_tools": [],
  "timeout_seconds": 30
}
```

Put `INTERNAL_MCP_TOKEN` in `.env` or the deployment secret manager. Do not place token values
in `config/mcp_servers.json`, source control, or application logs. For STDIO, use for example
`"env_refs": {"SERVICE_API_KEY": "SERVICE_API_KEY"}`.

## Application integration

```python
from universal_ai_studio.mcp_platform.api import (
    list_authorized_servers, discover_for_app, execute_for_app,
    read_resource_for_app, get_prompt_for_app,
)

servers = list_authorized_servers(username=username, role=user_role, app_id="marketing")
capabilities = discover_for_app(
    "internal_tools", username=username, role=user_role, app_id="marketing"
)
result = execute_for_app(
    "internal_tools", "search", {"query": "campaign performance"},
    username=username, role=user_role, app_id="marketing",
)
resource = read_resource_for_app(
    "internal_tools", "docs://campaign-policy",
    username=username, role=user_role, app_id="marketing",
)
prompt = get_prompt_for_app(
    "internal_tools", "campaign_brief", {"region": "APAC"},
    username=username, role=user_role, app_id="marketing",
)
```

The `app_id` must match the application's registered key and the server's policy.
The shared API rejects disabled servers and denied roles/apps/tools. Do not pass user-supplied
server commands or endpoints into these functions; administrators own server registration.

## Security and operational notes

- The initial control plane is administrator-managed; non-admin applications consume the
  application-facing facade and remain constrained by server policy.
- The execution UI requires an explicit confirmation before tool invocation.
- Tool inputs are validated against the server-advertised JSON Schema when `jsonschema` is
  installed (it is included in the root manifest).
- Execution history records actor, role, app, server, operation, status, timing and bounded
  request/response/error details. Treat audit logs as sensitive operational data and restrict
  filesystem access to the application service account.
- Each operation creates and closes a protocol session. This avoids stale subprocess/session
  state in Streamlit reruns; a long-lived pooled connection manager is a future optimization.
- The server registry and capability catalogue are local JSON control-plane stores; discovery health is updated on demand, not by a scheduled monitor. For multi-replica deployment,
  replace it with a shared transactional store and centralize audit delivery before scaling.
- OAuth authorization flows, per-user delegated credentials, server health scheduling,
  approval workflows, distributed rate limiting and a multi-tenant secret vault are not
  claimed as implemented in this phase.
- STDIO servers execute local processes. Only administrators should register trusted commands
  and arguments; isolate the application runtime and restrict OS-level process/network access.

## Validation

Unit tests cover registry validation, scope authorization, and application facade policy
behaviour. Live transport verification requires reachable MCP servers and credentials; the
repository does not ship a test MCP server or credentials. A successful registry save is not
proof that a server is reachable.
