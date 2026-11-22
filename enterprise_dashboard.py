"""Central application catalogue and platform landing page."""
from __future__ import annotations

import streamlit as st

from auth.auth_guard import protect_page
from auth.login_manager import login_manager
from universal_ai_studio.applications import registry
from universal_ai_studio.config.settings import get_settings
from universal_ai_studio.core.configuration import load_platform_config
from universal_ai_studio.core.dependency_manager import missing_dependencies

st.set_page_config(page_title="Universal AI Studio | Dashboard", page_icon="✦", layout="wide")
login_manager()
protect_page()

st.markdown(
    """
    <style>
    .block-container { padding-top: 1.3rem; padding-bottom: 3rem; max-width: 1600px; }
    .uas-hero { border-radius: 18px; padding: 1.55rem 1.8rem; background: linear-gradient(115deg,rgba(70,105,245,.16),rgba(20,184,166,.10)); border: 1px solid rgba(128,128,128,.18); }
    .uas-kicker { font-size: .76rem; letter-spacing: .13em; text-transform: uppercase; opacity: .72; font-weight: 700; }
    .uas-card-desc { font-size: .88rem; opacity: .78; min-height: 3.0rem; }
    div[data-testid="stVerticalBlockBorderWrapper"] { border-radius: 15px; }
    div[data-testid="stVerticalBlockBorderWrapper"] { min-height: 13.2rem; }
    .uas-card-desc { min-height: 3.3rem; line-height: 1.45; }
    @media (max-width: 900px) { .block-container { padding-left: 1rem; padding-right: 1rem; } }
    div.stButton > button, div[data-testid="stPageLink"] a { border-radius: 10px; }
    </style>
    """,
    unsafe_allow_html=True,
)

settings = get_settings()
applications = registry.list(enabled_only=True, available_only=True)
all_available_applications = registry.list(available_only=True)
config = load_platform_config()
enabled_integrations = sum(bool(item.get("enabled")) for item in config["integrations"].values())
configured_providers = (
    int(bool(config["integrations"]["ollama"].get("enabled")))
    + int(bool(config["integrations"]["openai"].get("enabled") and settings.openai_api_key))
    + int(bool(config["integrations"]["gemini"].get("enabled") and settings.gemini_api_key))
)

st.markdown(
    '<div class="uas-hero"><div class="uas-kicker">Enterprise AI workspace</div>'
    '<h1 style="margin:.35rem 0">Welcome to Universal AI Studio</h1>'
    '<p style="margin:0;opacity:.82">Discover applications, use the persistent left sidebar to move between workspaces, and manage shared platform services from one place.</p></div>',
    unsafe_allow_html=True,
)
st.write("")
metric_cols = st.columns(4)
metric_cols[0].metric("Available applications", len(all_available_applications))
metric_cols[1].metric("Enabled applications", len(applications))
metric_cols[2].metric("Enabled integrations", enabled_integrations)
metric_cols[3].metric("Configured AI providers", configured_providers)
st.divider()

if str(st.session_state.get("role", "user")).lower() in {"admin", "administrator"}:
    st.divider()
    st.subheader("⚙️ Platform administration")
    st.caption("Administrator-only controls are presented first. Global configuration is separate from application-specific workflows.")
    admin_cards = [
        ("🗂️ Application Management", "Register modules, enable applications and inspect dependencies.", "pages/platform/application_management.py"),
        ("🔌 Integration Management", "Configure databases, APIs, Elasticsearch and Kibana connections.", "pages/platform/integrations.py"),
        ("🤖 AI Provider Management", "Manage Gemini, OpenAI and Ollama provider configuration.", "pages/platform/ai_providers.py"),
        ("🩺 Platform Health", "Review configured integration health and diagnostics.", "pages/platform/health.py"),
        ("🧩 MCP Management", "Register MCP servers, discover capabilities and govern tool execution.", "pages/platform/mcp_management.py"),
    ]
    for start in range(0, len(admin_cards), 3):
        cols = st.columns(3, gap="large")
        for col, (title, description, page_path) in zip(cols, admin_cards[start:start + 3]):
            with col:
                with st.container(border=True):
                    st.markdown(f"### {title}")
                    st.markdown(f'<div class="uas-card-desc">{description}</div>', unsafe_allow_html=True)
                    st.page_link(page_path, label="Open management", icon=":material/settings:", use_container_width=True)


st.divider()

st.subheader("Application workspace")
st.caption("Open an application here, or use the persistent left sidebar to move directly between workspaces.")

category_order = ["Analytics", "Data", "Documents", "AI", "Marketing", "Integrations", "Risk", "Voice", "Platform Tools", "Custom"]
for category in category_order:
    grouped = [app for app in applications if app.category.casefold() == category.casefold()]
    if not grouped:
        continue
    st.markdown(f"#### {category}")
    for start in range(0, len(grouped), 3):
        cols = st.columns(3, gap="large")
        for col, app in zip(cols, grouped[start:start + 3]):
            with col:
                with st.container(border=True):
                    st.markdown(f"### {app.icon} {app.name}")
                    st.markdown(f'<div class="uas-card-desc">{app.description}</div>', unsafe_allow_html=True)
                    missing = missing_dependencies(app.key)
                    if missing:
                        st.warning("Missing dependencies: " + ", ".join(missing))
                    st.page_link(app.path, label=f"Open {app.name}", icon=":material/arrow_forward:", use_container_width=True)
    st.write("")


st.divider()
st.caption(f"Environment: {settings.environment.title()} · Vector database: Elasticsearch only · Signed in as {st.session_state.get('username', 'User')}")

st.info("Email campaign creation and delivery currently live inside Marketing Campaign Studio. This package does not contain a separate Mail client application.")
