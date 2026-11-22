from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_entrypoint_uses_the_shared_login_manager():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    assert "from auth.login_manager import login_manager" in source
    assert "login_manager()" in source


def test_entrypoint_registers_persistent_sidebar_navigation_and_workspace_switcher():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    assert 'st.Page(' in source
    assert '"enterprise_dashboard.py"' in source
    assert 'from universal_ai_studio.applications import registry' in source
    assert 'registry.list(enabled_only=True, available_only=True)' in source
    assert 'st.navigation(nav_groups, position="sidebar")' in source
    assert 'st.navigation(nav_groups, position="top")' not in source
    assert 'st.navigation([st.Page("login_app.py", title="Sign in", url_path="sign-in")], position="hidden")' in source
    assert 'key="uas_global_switcher"' not in source
    assert 'st.switch_page(target_path)' not in source
    assert 'selected_page.run()' in source


def test_dashboard_exposes_all_registered_apps_and_separate_platform_admin():
    source = (ROOT / "enterprise_dashboard.py").read_text(encoding="utf-8")
    assert 'registry.list(enabled_only=True, available_only=True)' in source
    assert 'st.page_link(app.path' in source
    assert 'Platform administration' in source
    assert "Mail client application" in source


def test_shared_entrypoint_authenticates_before_running_registered_pages():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    assert source.index("login_manager()") < source.index("selected_page.run()")
    assert "if not st.session_state.get(\"logged_in\")" in source
    assert source.index('st.navigation([st.Page("login_app.py", title="Sign in", url_path="sign-in")], position="hidden")') < source.index("login_manager()")


def test_market_intelligence_uses_shared_authentication_not_a_second_login_flow():
    source = (ROOT / "pages/15_Tensor_trade_business/app.py").read_text(encoding="utf-8")
    assert "login_manager()" not in source
    assert "protect_page()" not in source
    assert "st.set_page_config" not in source


def test_workspace_layout_and_logout_are_consistent():
    for path in (ROOT / "pages").rglob("*.py"):
        if "backup" in path.parts or path.parent.name == "platform":
            continue
        source = path.read_text(encoding="utf-8")
        assert 'layout="centered"' not in source, path.relative_to(ROOT)
        assert 'st.button("🚪 Logout")' not in source, path.relative_to(ROOT)
    entrypoint = (ROOT / "app.py").read_text(encoding="utf-8")
    assert 'key="uas_global_signout"' in entrypoint
    assert 'st.session_state.clear()' in entrypoint
    assert 'position: fixed;' in entrypoint
    assert 'key="uas_global_switcher"' not in entrypoint


def test_platform_routes_are_real_page_entrypoints():
    routes = (
        "application_management.py",
        "integrations.py",
        "ai_providers.py",
        "health.py",
        "mcp_management.py",
    )
    for name in routes:
        path = ROOT / "pages" / "platform" / name
        assert path.is_file(), name
        assert "_page()" in path.read_text(encoding="utf-8"), name


def test_workspace_does_not_require_a_separate_uvicorn_process():
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8").lower()
    assert "uvicorn" not in requirements
    assert "fastapi" not in requirements

    graphql_page = (ROOT / "pages/13_GraphQL_API/app.py").read_text(encoding="utf-8")
    agent_page = (ROOT / "pages/14_Fast_API_Intent_detaction/app.py").read_text(encoding="utf-8")
    assert "schema.execute_sync" in graphql_page
    assert "backend.process_chat" in agent_page
    assert "uvicorn" not in graphql_page.lower()
    assert "requests.post" not in agent_page.lower()
    assert "FASTAPI_URL" not in agent_page


def test_platform_administration_is_first_navigation_group_and_home_is_global():
    entrypoint = (ROOT / "app.py").read_text(encoding="utf-8")
    assert 'nav_groups["Platform Administration"]' in entrypoint
    assert entrypoint.index('nav_groups["Platform Administration"]') < entrypoint.index('nav_groups["Home"]')
    assert 'nav_groups["Home"] = [home_page]' in entrypoint
    assert 'route_targets = {"home": "enterprise_dashboard.py"}' in entrypoint
    assert 'st.navigation(nav_groups, position="sidebar")' in entrypoint


def test_dashboard_places_platform_administration_before_application_catalogue():
    dashboard = (ROOT / "enterprise_dashboard.py").read_text(encoding="utf-8")
    assert dashboard.index('st.subheader("⚙️ Platform administration")') < dashboard.index('st.subheader("Application workspace")')


def test_primary_navigation_categories_are_rendered_in_left_sidebar():
    entrypoint = (ROOT / "app.py").read_text(encoding="utf-8")
    assert '"Platform Administration"' in entrypoint
    assert '"Home"' in entrypoint
    assert '"Analytics"' in entrypoint
    assert '"Data"' in entrypoint
    assert '"AI & Marketing"' in entrypoint
    assert '"Integrations & Tools"' in entrypoint
    assert 'position="sidebar"' in entrypoint
    assert "--uas-sidebar-width: 18rem" in entrypoint
    assert "stSidebarNav" in entrypoint
