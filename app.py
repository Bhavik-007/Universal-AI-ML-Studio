"""Universal AI Studio entry point and persistent application navigation."""
from __future__ import annotations

import streamlit as st
from pathlib import Path
from dotenv import load_dotenv

# Initialize the local Fernet key before loading .env and before any admin page
# attempts to persist integration credentials. This preserves existing values
# (including GOOGLE_API_KEY) and only fills a missing encryption key.
from scripts.initialize_local_env import initialize_env_file
_PROJECT_ROOT = Path(__file__).resolve().parent
initialize_env_file(_PROJECT_ROOT / ".env", _PROJECT_ROOT / ".env.example")

from auth.login_manager import login_manager
from universal_ai_studio.applications import registry
from universal_ai_studio.core.configuration import apply_runtime_configuration
from universal_ai_studio.core.logging import configure_logging
from universal_ai_studio.ui.guidance import render_workspace_guidance

load_dotenv()
st.set_page_config(
    page_title="Universal AI Studio",
    page_icon="✦",
    layout="wide",
    initial_sidebar_state="expanded",
)
# Explicitly disable Streamlit's automatic pages/ navigation while unauthenticated.
# A valid hidden page keeps the navigation API initialized without exposing
# discovered application modules before authentication succeeds.
if not st.session_state.get("logged_in", False):
    st.navigation([st.Page("login_app.py", title="Sign in", url_path="sign-in")], position="hidden")
    login_manager()

configure_logging()
if not st.session_state.get("logged_in"):
    st.stop()

try:
    apply_runtime_configuration()
except Exception as exc:
    st.error(f"Platform configuration could not be loaded: {type(exc).__name__}: {exc}")

# A single native navigation tree is the source of truth for all platform
# routes. The complete category hierarchy lives in the persistent left sidebar;
# Streamlit owns URL changes and browser history while session state is retained.
home_page = st.Page(
    "enterprise_dashboard.py",
    title="Dashboard",
    icon=":material/dashboard:",
    url_path="home",
    default=True,
)

# Build one per-rerun catalogue snapshot. Previously this refreshed manifests
# and re-read platform configuration repeatedly while constructing navigation.
applications = registry.list(enabled_only=True, available_only=True)
app_pages = {}
for item in applications:
    app_pages[item.key] = st.Page(
        item.path,
        title=item.name,
        icon=item.icon,
        url_path=item.url_path,
    )

platform_pages = {}
if str(st.session_state.get("role", "user")).lower() in {"admin", "administrator"}:
    platform_page_paths = {
        "feature_management": "pages/platform/application_management.py",
        "integration_management": "pages/platform/integrations.py",
        "ai_provider_management": "pages/platform/ai_providers.py",
        "platform_health": "pages/platform/health.py",
        "mcp_management": "pages/platform/mcp_management.py",
    }
    platform_page_metadata = {
        "feature_management": ("Application Management", ":material/apps:", "application-management"),
        "integration_management": ("Integrations", ":material/lan:", "integrations"),
        "ai_provider_management": ("AI Providers", ":material/smart_toy:", "ai-providers"),
        "platform_health": ("Platform Health", ":material/health_and_safety:", "platform-health"),
        "mcp_management": ("MCP Management", ":material/hub:", "mcp-management"),
    }
    platform_pages = {
        key: st.Page(platform_page_paths[key], title=metadata[0], icon=metadata[1], url_path=metadata[2])
        for key, metadata in platform_page_metadata.items()
    }

# Keep the primary navigation in the left sidebar. Platform Administration
# is intentionally first for administrators, followed by Home and the grouped
# application catalogue. A compact quick switcher remains in the page toolbar.
category_groups = {
    "Analytics": {"Analytics", "Risk"},
    "Data": {"Data", "Documents"},
    "AI & Marketing": {"AI", "Marketing"},
    "Integrations & Tools": {"Integrations", "Voice", "Platform Tools"},
}
nav_groups = {}
if platform_pages:
    nav_groups["Platform Administration"] = list(platform_pages.values())
nav_groups["Home"] = [home_page]
for group_name, categories in category_groups.items():
    pages = [app_pages[item.key] for item in applications if item.key in app_pages and item.category in categories]
    if pages:
        nav_groups[group_name] = pages

selected_page = st.navigation(nav_groups, position="sidebar")
current_route = selected_page.url_path
st.session_state["uas_current_route"] = current_route

# This global switcher is rendered before every module. It provides a reliable
# return path to Dashboard and direct app-to-app switching without restarting
# a workflow. Native navigation also preserves browser Back/Forward behaviour.
route_targets = {"home": "enterprise_dashboard.py"}
route_labels = {"home": "Dashboard"}
for item in applications:
    if item.key in app_pages:
        route_targets[item.url_path] = item.path
        route_labels[item.url_path] = f"{item.icon}  {item.name}"
for route, page in platform_pages.items():
    route_targets[page.url_path] = platform_page_paths[route]
    route_labels[page.url_path] = f"⚙️  {page.title}"

st.markdown(
    """
    <style>
    :root {
        --uas-sidebar-width: 18rem;
        --uas-border: rgba(128,128,128,.22);
        --uas-muted: #667085;
    }
    [data-testid="stHeader"] { background: rgba(255,255,255,0.02); }
    [data-testid="stMainBlockContainer"] {
        padding-top: 1.05rem;
        padding-bottom: 2.5rem;
        max-width: 1600px;
    }
    /* The native Streamlit navigation tree is the primary application nav. */
    section[data-testid="stSidebar"] {
        width: var(--uas-sidebar-width) !important;
        min-width: var(--uas-sidebar-width) !important;
        border-right: 1px solid var(--uas-border);
    }
    section[data-testid="stSidebar"] > div {
        width: var(--uas-sidebar-width) !important;
    }
    [data-testid="stSidebarNav"] { padding-top: .45rem; }
    [data-testid="stSidebarNav"] a {
        border-radius: 9px;
        margin: 2px 8px;
        min-height: 2.45rem;
    }
    [data-testid="stSidebarNav"] a[aria-current="page"] {
        background: rgba(49, 130, 206, .12);
        font-weight: 650;
    }
    .uas-brand-fallback { color: #344054; font-size: 1rem; font-weight: 700; text-align: center; padding: .6rem; }
    [data-testid="stAlert"] { border-radius: 10px; }
    [data-testid="stFileUploader"] section { border-radius: 12px; }
    [data-testid="stFileUploader"] button { border-radius: 9px; }
    h1, h2, h3 { letter-spacing: -.015em; }
    [data-testid="stSidebar"] [data-testid="stVerticalBlock"] { gap: .55rem; }
    .uas-shell-toolbar {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 1rem;
        border-bottom: 1px solid var(--uas-border);
        padding: 0 0 .6rem 0;
        margin-bottom: .8rem;
    }
    .uas-shell-brand {
        color: var(--uas-muted);
        font-size: .72rem;
        font-weight: 700;
        letter-spacing: .08em;
        text-transform: uppercase;
    }
    div[data-testid="stSelectbox"] label { font-size: .76rem; opacity: .72; }
    div[data-testid="stSelectbox"] [data-baseweb="select"] { min-height: 2.5rem; }
    div.stButton > button { border-radius: 9px; min-height: 2.5rem; }
    @media (max-width: 760px) {
        [data-testid="stMainBlockContainer"] { padding-left: .8rem; padding-right: .8rem; }
        section[data-testid="stSidebar"] { width: min(86vw, 18rem) !important; min-width: min(86vw, 18rem) !important; }
        section[data-testid="stSidebar"] > div { width: min(86vw, 18rem) !important; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# The native Streamlit sidebar is the single source of truth for navigation.
# Keep sign-out outside the navigation tree and pin it to the sidebar footer.
st.markdown(
    """
    <style>
    :root {
        --uas-sidebar-width: 18rem;
        --uas-border: rgba(128,128,128,.22);
        --uas-muted: #667085;
    }
    [data-testid="stHeader"] { background: rgba(255,255,255,0.02); }
    [data-testid="stMainBlockContainer"] {
        padding-top: 1.05rem;
        padding-bottom: 2.5rem;
        max-width: 1600px;
    }
    section[data-testid="stSidebar"] {
        width: var(--uas-sidebar-width) !important;
        min-width: var(--uas-sidebar-width) !important;
        border-right: 1px solid var(--uas-border);
    }
    section[data-testid="stSidebar"] > div {
        width: var(--uas-sidebar-width) !important;
    }
    [data-testid="stSidebarNav"] { padding-top: .45rem; padding-bottom: 5rem; }
    [data-testid="stSidebarNav"] a {
        border-radius: 9px;
        margin: 2px 8px;
        min-height: 2.45rem;
    }
    [data-testid="stSidebarNav"] a[aria-current="page"] {
        background: rgba(49, 130, 206, .12);
        font-weight: 650;
    }
    .uas-brand-fallback { color: #344054; font-size: 1rem; font-weight: 700; text-align: center; padding: .6rem; }
    [data-testid="stAlert"] { border-radius: 10px; }
    [data-testid="stFileUploader"] section { border-radius: 12px; }
    [data-testid="stFileUploader"] button { border-radius: 9px; }
    h1, h2, h3 { letter-spacing: -.015em; }
    [data-testid="stSidebar"] [data-testid="stVerticalBlock"] { gap: .55rem; }

    /* Anchor sign-out below navigation, independent of menu length. */
    section[data-testid="stSidebar"] div.st-key-uas_global_signout {
        position: fixed;
        bottom: .8rem;
        left: .75rem;
        width: calc(var(--uas-sidebar-width) - 1.5rem);
        z-index: 1000;
        padding-top: .45rem;
        background: var(--background-color, white);
        border-top: 1px solid var(--uas-border);
    }
    section[data-testid="stSidebar"] div.st-key-uas_global_signout button {
        width: 100%;
        border-radius: 9px;
        min-height: 2.5rem;
    }
    @media (max-width: 760px) {
        [data-testid="stMainBlockContainer"] { padding-left: .8rem; padding-right: .8rem; }
        section[data-testid="stSidebar"] {
            width: min(86vw, 18rem) !important;
            min-width: min(86vw, 18rem) !important;
        }
        section[data-testid="stSidebar"] > div { width: min(86vw, 18rem) !important; }
        section[data-testid="stSidebar"] div.st-key-uas_global_signout {
            width: calc(min(86vw, 18rem) - 1.5rem);
        }
    }
    div.stButton > button { border-radius: 9px; min-height: 2.5rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

# This code is reached only after login_manager() has authenticated the user.
with st.sidebar:
    st.markdown("---")
    st.caption(f"Signed in as **{st.session_state.get('username', 'User')}**")
    if st.button("Sign out", key="uas_global_signout", use_container_width=True):
        # Clear all per-session state, including widget values, upload references,
        # route state and user-specific temporary data.
        st.session_state.clear()
        st.rerun()

selected_page.run()
