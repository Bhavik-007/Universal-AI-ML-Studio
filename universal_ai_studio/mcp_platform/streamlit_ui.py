"""Reusable Streamlit panel for application-scoped shared MCP tools."""
from __future__ import annotations
import json
import streamlit as st
from .api import list_authorized_servers
from .execution import engine

def render_shared_mcp_tools(app_id: str) -> None:
    """Render an opt-in tool panel; authorization is rechecked by the execution engine."""
    username=str(st.session_state.get("username","unknown"))
    role=str(st.session_state.get("role","user"))
    try:
        servers=list_authorized_servers(username=username,role=role,app_id=app_id)
    except Exception as exc:
        st.warning(f"Shared MCP service is unavailable: {type(exc).__name__}")
        return
    if not servers:
        return
    with st.expander("🧩 Shared MCP tools", expanded=False):
        st.caption("Tools are provided by the central MCP platform and restricted to this application and your role.")
        server=st.selectbox("MCP server",[item.key for item in servers],key=f"{app_id}_mcp_server")
        selected=next(item for item in servers if item.key==server)
        if st.button("Discover shared tools",key=f"{app_id}_mcp_discover"):
            try:
                result=engine.discover(selected,username=username,role=role,app_id=app_id)
                cache=st.session_state.get(f"{app_id}_mcp_capabilities",{})
                cache[server]=result
                st.session_state[f"{app_id}_mcp_capabilities"]=cache
                st.success(f"Discovered {len(result['tools'])} tools.")
            except Exception as exc: st.error(str(exc))
        capabilities=st.session_state.get(f"{app_id}_mcp_capabilities",{}).get(server,{})
        tools=capabilities.get("tools",[])
        if tools:
            tool_names=[item.get("name","") for item in tools if item.get("name")]
            chosen=st.selectbox("Tool",tool_names,key=f"{app_id}_mcp_tool")
            schema=next((item.get("inputSchema",{}) for item in tools if item.get("name")==chosen),{})
            st.caption(next((item.get("description","") for item in tools if item.get("name")==chosen),""))
            st.code(json.dumps(schema,indent=2),language="json")
            with st.form(f"{app_id}_mcp_exec_form"):
                raw=st.text_area("Tool arguments (JSON)",value="{}",key=f"{app_id}_mcp_args")
                approved=st.checkbox("I approve this tool execution.",key=f"{app_id}_mcp_approved")
                submit=st.form_submit_button("Execute shared MCP tool")
            if submit:
                if not approved: st.warning("Confirm the tool execution first.")
                else:
                    try:
                        arguments=json.loads(raw or "{}")
                        if not isinstance(arguments,dict): raise ValueError("Tool arguments must be a JSON object.")
                        output=engine.call_tool(selected,chosen,arguments,username=username,role=role,app_id=app_id)
                        st.json(output)
                    except Exception as exc: st.error(str(exc))
