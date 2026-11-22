"""Central MCP server, discovery, execution and audit administration UI."""
from __future__ import annotations
import json
from pathlib import Path
import streamlit as st
from auth.auth_guard import protect_page
from universal_ai_studio.mcp_platform.models import MCPServer
from universal_ai_studio.mcp_platform.registry import registry
from universal_ai_studio.mcp_platform.execution import engine, MCPExecutionError

def _guard():
    protect_page()
    if str(st.session_state.get("role", "user")).lower() not in {"admin", "administrator"}:
        st.error("Administrator access is required to manage MCP servers.")
        st.stop()

def mcp_management_page():
    st.set_page_config(page_title="MCP Management | Universal AI Studio", page_icon=":material/hub:", layout="wide")
    _guard()
    st.title("Central MCP Management")
    st.caption("One governed MCP control plane for registered applications. Server secrets are referenced from environment variables and are never stored in the registry.")
    tabs=st.tabs(["Server Registry", "Discovery & Execution", "Resources & Prompts", "Audit History"])
    with tabs[0]:
        st.subheader("Registered MCP servers")
        try: servers=registry.list()
        except Exception as exc:
            st.error(str(exc)); servers=[]
        if servers:
            from universal_ai_studio.mcp_platform.catalog import catalog
            snapshots=catalog.list()
            st.dataframe([{"Key":s.key,"Name":s.name,"Transport":s.transport,"Enabled":s.enabled,"Last discovery":snapshots.get(s.key,{}).get("last_checked","Not checked"),"Health":snapshots.get(s.key,{}).get("status","Unknown"),"Tools":len(snapshots.get(s.key,{}).get("tools",[])),"Resources":len(snapshots.get(s.key,{}).get("resources",[])),"Prompts":len(snapshots.get(s.key,{}).get("prompts",[])),"Users":", ".join(s.allowed_users),"Applications":", ".join(s.allowed_apps),"Roles":", ".join(s.allowed_roles)} for s in servers], use_container_width=True, hide_index=True)
            selected=st.selectbox("Select server to edit or remove", [s.key for s in servers], key="mcp_selected_server")
            current=next(s for s in servers if s.key==selected)
            with st.form("mcp_edit_form"):
                c1,c2=st.columns(2)
                name=c1.text_input("Display name", value=current.name)
                enabled=c2.toggle("Enabled", value=current.enabled)
                description=st.text_area("Description", value=current.description)
                transport=st.selectbox("Transport", ["streamable_http","stdio"], index=0 if current.transport=="streamable_http" else 1)
                url=st.text_input("Streamable HTTP URL", value=current.url, disabled=transport!="streamable_http")
                command=st.text_input("STDIO executable (allow-listed)", value=current.command, disabled=transport!="stdio")
                args=st.text_area("STDIO arguments (one per line)", value="\n".join(current.args), disabled=transport!="stdio")
                env_refs=st.text_area("Environment references (JSON object)", value=json.dumps(current.env_refs or {}, indent=2), help='Example: {"API_TOKEN":"MY_SERVER_API_TOKEN"}')
                allowed_users=st.text_input("Allowed usernames (comma-separated; * = all)", value=",".join(current.allowed_users))
                denied_users=st.text_input("Explicitly denied usernames", value=",".join(current.denied_users))
                allowed_apps=st.text_input("Allowed application IDs (comma-separated; * = all)", value=",".join(current.allowed_apps))
                allowed_roles=st.text_input("Allowed roles (comma-separated)", value=",".join(current.allowed_roles))
                allowed_tools=st.text_input("Allowed tools (comma-separated; * = all)", value=",".join(current.allowed_tools))
                denied_tools=st.text_input("Explicitly denied tools (comma-separated)", value=",".join(current.denied_tools))
                timeout=st.number_input("Timeout (seconds)", min_value=1,max_value=300,value=current.timeout_seconds)
                if st.form_submit_button("Save server settings", type="primary"):
                    try:
                        refs=json.loads(env_refs or "{}")
                        updated=MCPServer(key=current.key,name=name,transport=transport,enabled=enabled,url=url.strip(),command=command.strip(),args=tuple(x for x in args.splitlines() if x.strip()),env_refs=refs,allowed_users=tuple(x.strip() for x in allowed_users.split(",") if x.strip()),denied_users=tuple(x.strip() for x in denied_users.split(",") if x.strip()),allowed_apps=tuple(x.strip() for x in allowed_apps.split(",") if x.strip()),allowed_roles=tuple(x.strip() for x in allowed_roles.split(",") if x.strip()),allowed_tools=tuple(x.strip() for x in allowed_tools.split(",") if x.strip()),denied_tools=tuple(x.strip() for x in denied_tools.split(",") if x.strip()),timeout_seconds=int(timeout),description=description)
                        registry.upsert(updated); st.success("MCP server settings saved."); st.rerun()
                    except Exception as exc: st.error(f"Could not save server: {exc}")
            if st.button("Delete selected MCP server", type="secondary"):
                registry.delete(selected); st.success("Server removed from registry."); st.rerun()
        else:
            st.info("No MCP servers are registered yet.")
        st.divider()
        st.subheader("Register a server")
        with st.form("mcp_add_form"):
            c1,c2=st.columns(2)
            key=c1.text_input("Unique key", placeholder="internal_tools")
            display_name=c2.text_input("Name", placeholder="Internal Tools")
            tr=st.selectbox("Transport",["streamable_http","stdio"])
            endpoint=st.text_input("Streamable HTTP endpoint", placeholder="http://localhost:8000/mcp",disabled=tr!="streamable_http")
            executable=st.text_input("STDIO executable",placeholder="uvx",disabled=tr!="stdio")
            command_args=st.text_area("STDIO arguments (one per line)",disabled=tr!="stdio",placeholder="my-mcp-server")
            refs=st.text_area("Environment references (JSON object)",value="{}",help='Only names are saved. Put secret values in .env; example {"API_TOKEN":"MY_MCP_TOKEN"}. For HTTP auth use key MCP_AUTHORIZATION.')
            users=st.text_input("Allowed usernames",value="*")
            denied=st.text_input("Denied usernames",value="")
            apps=st.text_input("Allowed application IDs",value="*")
            roles=st.text_input("Allowed roles",value="admin,user")
            tools=st.text_input("Allowed tool names",value="*")
            if st.form_submit_button("Register MCP server"):
                try:
                    server=MCPServer(key=key.strip(),name=display_name.strip(),transport=tr,url=endpoint.strip(),command=executable.strip(),args=tuple(x for x in command_args.splitlines() if x.strip()),env_refs=json.loads(refs or "{}"),allowed_users=tuple(x.strip() for x in users.split(",") if x.strip()),denied_users=tuple(x.strip() for x in denied.split(",") if x.strip()),allowed_apps=tuple(x.strip() for x in apps.split(",") if x.strip()),allowed_roles=tuple(x.strip() for x in roles.split(",") if x.strip()),allowed_tools=tuple(x.strip() for x in tools.split(",") if x.strip()))
                    registry.upsert(server); st.success("MCP server registered."); st.rerun()
                except Exception as exc: st.error(f"Registration failed: {exc}")
    with tabs[1]:
        servers=registry.list(enabled_only=True)
        if not servers: st.info("Register and enable an MCP server to discover its capabilities.")
        else:
            selected=st.selectbox("MCP server", [s.key for s in servers], key="mcp_discovery_server")
            server=next(s for s in servers if s.key==selected)
            if st.button("Connect and discover capabilities",type="primary"):
                try:
                    result=engine.discover(server,username=str(st.session_state.get("username","unknown")),role=str(st.session_state.get("role","user")),app_id="platform_admin")
                    st.session_state["mcp_discovery_cache"]={selected:result}
                    st.success(f"Discovery complete: {len(result['tools'])} tools, {len(result['resources'])} resources, {len(result['prompts'])} prompts.")
                except Exception as exc: st.error(str(exc))
            result=st.session_state.get("mcp_discovery_cache",{}).get(selected)
            if result:
                st.write("**Available tools**")
                st.dataframe([{"Tool":x.get("name"),"Description":x.get("description",""),"Input schema":json.dumps(x.get("inputSchema",{}),ensure_ascii=False)} for x in result["tools"]],use_container_width=True,hide_index=True)
                if result["tools"]:
                    st.divider(); st.subheader("Controlled tool execution")
                    names=[x["name"] for x in result["tools"]]
                    with st.form("mcp_tool_execute_form"):
                        tool_name=st.selectbox("Tool",names)
                        raw_args=st.text_area("Arguments (JSON object)",value="{}")
                        confirm=st.checkbox("I confirm this tool call may perform actions on the connected system.")
                        execute=st.form_submit_button("Execute tool",type="primary")
                    if execute:
                        if not confirm: st.warning("Confirm the action before execution.")
                        else:
                            try:
                                args=json.loads(raw_args or "{}")
                                if not isinstance(args,dict): raise ValueError("Arguments must be a JSON object.")
                                output=engine.call_tool(server,tool_name,args,username=str(st.session_state.get("username","unknown")),role=str(st.session_state.get("role","user")),app_id="platform_admin")
                                st.success("Tool execution completed."); st.json(output)
                            except Exception as exc: st.error(str(exc))
    with tabs[2]:
        from universal_ai_studio.mcp_platform.catalog import catalog
        selected_key=st.session_state.get("mcp_discovery_server","")
        result=st.session_state.get("mcp_discovery_cache",{}).get(selected_key) or (catalog.get(selected_key) or {})
        c1,c2=st.columns(2)
        with c1:
            st.subheader("Resources")
            resources=result.get("resources",[])
            if not resources: st.caption("No discovered resources in the current session.")
            for resource in resources:
                uri=str(resource.get("uri",""))
                with st.expander(f"{resource.get('name',uri)}"):
                    st.caption(uri)
                    if st.button("Read resource",key=f"read_resource_{uri}"):
                        try:
                            server=next(s for s in registry.list(enabled_only=True) if s.key==st.session_state.get("mcp_discovery_server"))
                            st.json(engine.read_resource(server,uri,username=str(st.session_state.get("username","unknown")),role=str(st.session_state.get("role","user")),app_id="platform_admin"))
                        except Exception as exc: st.error(str(exc))
        with c2:
            st.subheader("Prompts")
            prompts=result.get("prompts",[])
            if not prompts: st.caption("No discovered prompts in the current session.")
            for prompt in prompts:
                with st.expander(prompt.get("name","Unnamed prompt")):
                    st.write(prompt.get("description",""))
                    if st.button("Load prompt",key=f"load_prompt_{prompt.get('name')}"):
                        try:
                            server=next(s for s in registry.list(enabled_only=True) if s.key==st.session_state.get("mcp_discovery_server"))
                            st.json(engine.get_prompt(server,prompt["name"],username=str(st.session_state.get("username","unknown")),role=str(st.session_state.get("role","user")),app_id="platform_admin"))
                        except Exception as exc: st.error(str(exc))
    with tabs[3]:
        audit_path=Path(__file__).resolve().parents[2]/"logs"/"mcp_execution.jsonl"
        if audit_path.exists():
            lines=audit_path.read_text(encoding="utf-8").splitlines()[-500:]
            records=[]
            for line in lines:
                try: records.append(json.loads(line))
                except json.JSONDecodeError: continue
            if records: st.dataframe(records,use_container_width=True,hide_index=True)
            else: st.info("No MCP execution events recorded.")
        else: st.info("No MCP execution events recorded yet.")
