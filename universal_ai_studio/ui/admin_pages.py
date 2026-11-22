"""Streamlit administrator pages for feature flags, integrations and health."""
from __future__ import annotations

import streamlit as st

from universal_ai_studio.applications import registry
from universal_ai_studio.core.dependency_manager import validate_module_dependencies
from universal_ai_studio.core.configuration import (
    ConfigurationError, get_integration_secret as _get_integration_secret, load_platform_config,
    save_integration_secret, save_platform_config,
)
from universal_ai_studio.core.logging import write_audit_event
from universal_ai_studio.integrations.health import (
    check_elasticsearch, check_graphql, check_kibana, check_ollama, check_rest_api, check_sql_server,
)



def _save_configuration(config: dict, secret_updates: list[tuple[str, str, str]]) -> None:
    """Persist settings and only then encrypted credentials, avoiding partial saves."""
    import os
    if any(value for _, _, value in secret_updates) and not os.getenv("UAS_CONFIG_ENCRYPTION_KEY"):
        raise ConfigurationError("Set UAS_CONFIG_ENCRYPTION_KEY in .env before saving integration credentials.")
    save_platform_config(config)
    for integration, name, value in secret_updates:
        if value:
            save_integration_secret(integration, name, value)

def _record_audit(event: str, **details) -> None:
    write_audit_event(actor=str(st.session_state.get("username", "unknown")), event=event, details=details)


def _admin_guard() -> None:
    from auth.auth_guard import protect_page
    protect_page()
    if str(st.session_state.get("role", "user")).lower() not in {"admin", "administrator"}:
        st.error("Administrator access is required to manage platform configuration.")
        st.stop()


def feature_management_page() -> None:
    st.set_page_config(page_title="Feature Management | Universal AI Studio", layout="wide")
    _admin_guard()
    st.title("Feature & Module Management")
    st.caption("Enable or disable registered applications, or register an existing repository-local Streamlit page without editing the central navigation code.")
    with st.expander("Register an existing application page", expanded=False):
        with st.form("register_module_form"):
            module_key = st.text_input("Unique module key", placeholder="customer_insights")
            module_name = st.text_input("Display name", placeholder="Customer Insights")
            module_path = st.text_input("Relative Python entry-point path", placeholder="pages/customer_insights/app.py")
            module_category = st.text_input("Category", value="Custom")
            module_dependencies = st.text_input("Python import dependencies (comma-separated)", value="streamlit", help="Use import names, for example: streamlit,pandas,requests")
            register_clicked = st.form_submit_button("Register module")
            if register_clicked:
                try:
                    application = registry.register_manifest(
                        key=module_key.strip(), name=module_name.strip(), path=module_path.strip(), category=module_category.strip(),
                        dependencies=tuple(item.strip() for item in module_dependencies.split(",") if item.strip())
                    )
                    _record_audit("module.registered", module_key=application.key, module_path=application.path)
                    st.success(f"Registered {application.name}. It is disabled by default; enable it below after dependencies are installed.")
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
    applications = registry.list()
    for manifest_error in registry.manifest_errors:
        st.warning(f"Module manifest skipped: {manifest_error}")
    config = load_platform_config()
    features = config.setdefault("features", {})
    changes = {}
    dependency_results = {}
    for application in applications:
        ready, missing = validate_module_dependencies(application.key, application.dependencies if application.discovered else None)
        dependency_results[application.key] = (ready, missing)
        current = bool(features.get(application.key, application.default_enabled))
        if not ready:
            st.warning(f"{application.name}: missing dependencies: {', '.join(missing)}")
        changes[application.key] = st.toggle(
            f"{application.name} ({application.category})",
            value=current,
            key=f"feature_{application.key}",
            disabled=(not ready and not current),
        )
    if st.button("Save feature configuration", type="primary"):
        blocked = [key for key, enabled in changes.items() if enabled and not dependency_results[key][0]]
        if blocked:
            st.error("Cannot enable modules until their dependencies are installed: " + ", ".join(blocked))
            return
        config["features"].update(changes)
        try:
            save_platform_config(config)
            _record_audit("features.updated", enabled_modules=[key for key, enabled in changes.items() if enabled], disabled_modules=[key for key, enabled in changes.items() if not enabled])
            st.success("Feature configuration saved.")
            st.rerun()
        except ConfigurationError as exc:
            st.error(str(exc))


def integration_management_page() -> None:
    st.set_page_config(page_title="Integration Management | Universal AI Studio", layout="wide")
    _admin_guard()
    st.title("Integration Management")
    st.caption("Configure endpoints and credentials. Credentials are encrypted at rest and never displayed after saving.")
    try:
        config = load_platform_config()
    except ConfigurationError as exc:
        st.error(str(exc))
        return
    integrations = config["integrations"]
    import os
    if not os.getenv("UAS_CONFIG_ENCRYPTION_KEY"):
        st.warning("Secure credential storage is not initialized. Restart the app from the project root; startup will generate UAS_CONFIG_ENCRYPTION_KEY in .env automatically. Your Google AI API key is separate and does not need to be regenerated.")

    with st.form("sql_server_form"):
        st.subheader("SQL Server")
        sql = integrations["sql_server"]
        sql_enabled = st.toggle("Enable SQL Server integration", value=sql["enabled"], key="sql_enabled")
        c1, c2 = st.columns(2)
        server = c1.text_input("Server / host", value=sql["server"])
        database = c2.text_input("Database", value=sql["database"])
        driver = c1.text_input("ODBC driver", value=sql["driver"])
        auth_mode = c2.selectbox("Authentication", ["SQL", "WINDOWS"], index=0 if sql["auth_mode"] == "SQL" else 1)
        encrypt = c1.selectbox("Encrypt", ["yes", "no"], index=0 if sql["encrypt"] == "yes" else 1)
        trust = c2.selectbox("Trust server certificate", ["no", "yes"], index=0 if sql["trust_server_certificate"] == "no" else 1)
        sql_user = st.text_input("SQL username (leave blank to retain saved value)")
        sql_password = st.text_input("SQL password (leave blank to retain saved value)", type="password")
        save_sql = st.form_submit_button("Save SQL Server settings")
        if save_sql:
            sql.update(enabled=sql_enabled, server=server.strip(), database=database.strip(), driver=driver.strip(), auth_mode=auth_mode, encrypt=encrypt, trust_server_certificate=trust)
            try:
                _save_configuration(config, [("sql_server", "username", sql_user), ("sql_server", "password", sql_password)])
                _record_audit("integration.settings_updated", integration="sql_server", enabled=sql_enabled)
                st.success("SQL Server settings saved securely.")
            except ConfigurationError as exc:
                st.error(str(exc))

    with st.form("rest_form"):
        st.subheader("REST API")
        rest = integrations["rest_api"]
        rest_enabled = st.toggle("Enable REST API integration", value=rest["enabled"], key="rest_enabled")
        rest_url = st.text_input("REST API base / health URL", value=rest["base_url"])
        rest_auth_type = st.selectbox("REST authentication type", ["none", "bearer_token", "api_key"], index=["none", "bearer_token", "api_key"].index(rest.get("auth_type", "none")))
        rest_timeout = st.number_input("REST timeout (seconds)", min_value=1, max_value=300, value=int(rest["timeout"]))
        rest_token = st.text_input("Bearer token (leave blank to retain saved value)", type="password")
        rest_key = st.text_input("API key (leave blank to retain saved value)", type="password")
        if st.form_submit_button("Save REST API settings"):
            rest.update(enabled=rest_enabled, base_url=rest_url.strip(), auth_type=rest_auth_type, timeout=int(rest_timeout))
            try:
                _save_configuration(config, [("rest_api", "bearer_token", rest_token), ("rest_api", "api_key", rest_key)])
                _record_audit("integration.settings_updated", integration="rest_api", enabled=rest_enabled, auth_type=rest_auth_type)
                st.success("REST API settings saved.")
            except ConfigurationError as exc: st.error(str(exc))

    with st.form("graphql_form"):
        st.subheader("GraphQL")
        gql = integrations["graphql"]
        gql_enabled = st.toggle("Enable GraphQL integration", value=gql["enabled"], key="gql_enabled")
        gql_url = st.text_input("GraphQL endpoint", value=gql["endpoint"])
        gql_auth_type = st.selectbox("GraphQL authentication type", ["none", "bearer_token", "api_key"], index=["none", "bearer_token", "api_key"].index(gql.get("auth_type", "none")))
        gql_timeout = st.number_input("GraphQL timeout (seconds)", min_value=1, max_value=300, value=int(gql["timeout"]))
        gql_token = st.text_input("Bearer token (leave blank to retain saved value)", type="password")
        gql_key = st.text_input("API key (leave blank to retain saved value)", type="password")
        if st.form_submit_button("Save GraphQL settings"):
            gql.update(enabled=gql_enabled, endpoint=gql_url.strip(), auth_type=gql_auth_type, timeout=int(gql_timeout))
            try:
                _save_configuration(config, [("graphql", "bearer_token", gql_token), ("graphql", "api_key", gql_key)])
                _record_audit("integration.settings_updated", integration="graphql", enabled=gql_enabled, auth_type=gql_auth_type)
                st.success("GraphQL settings saved.")
            except ConfigurationError as exc: st.error(str(exc))

    with st.form("elasticsearch_form"):
        st.subheader("Elasticsearch — primary and only vector database")
        es = integrations["elasticsearch"]
        es_enabled = st.toggle("Enable Elasticsearch", value=es["enabled"], key="es_enabled")
        es_url = st.text_input("Elasticsearch URL", value=es["url"])
        es_prefix = st.text_input("Index prefix", value=es["index_prefix"])
        es_schema_index = st.text_input("Schema metadata index", value=es.get("schema_index", "uas_schema_metadata"))
        es_document_index = st.text_input("Document chunks index", value=es.get("document_index", "uas_document_chunks"))
        es_marketing_index = st.text_input("Marketing Campaign Studio index", value=es.get("marketing_index", "marketing-documents-v1"))
        es_verify = st.checkbox("Verify TLS certificates", value=bool(es["verify_certs"]))
        es_timeout = st.number_input("Request timeout (seconds)", min_value=1, max_value=300, value=int(es["timeout"]))
        es_api_key = st.text_input("API key (leave blank to retain saved value)", type="password")
        es_user = st.text_input("Username (leave blank to retain saved value)")
        es_password = st.text_input("Password (leave blank to retain saved value)", type="password")
        if st.form_submit_button("Save Elasticsearch settings"):
            es.update(enabled=es_enabled, url=es_url.strip(), index_prefix=es_prefix.strip(), schema_index=es_schema_index.strip(), document_index=es_document_index.strip(), marketing_index=es_marketing_index.strip(), verify_certs=es_verify, timeout=int(es_timeout))
            try:
                _save_configuration(config, [("elasticsearch", "api_key", es_api_key), ("elasticsearch", "username", es_user), ("elasticsearch", "password", es_password)])
                _record_audit("integration.settings_updated", integration="elasticsearch", enabled=es_enabled, schema_index=es_schema_index, document_index=es_document_index, marketing_index=es_marketing_index)
                st.success("Elasticsearch settings saved securely.")
            except ConfigurationError as exc: st.error(str(exc))


    with st.form("kibana_form"):
        st.subheader("Kibana — Elasticsearch management and observability")
        kibana = integrations.setdefault("kibana", {"enabled": True, "url": "http://localhost:5601", "timeout": 10})
        kibana_enabled = st.toggle("Enable Kibana health check", value=bool(kibana.get("enabled", True)), key="kibana_enabled")
        kibana_url = st.text_input("Kibana URL", value=kibana.get("url", "http://localhost:5601"))
        kibana_timeout = st.number_input("Kibana timeout (seconds)", min_value=1, max_value=120, value=int(kibana.get("timeout", 10)), key="kibana_timeout")
        if st.form_submit_button("Save Kibana settings"):
            kibana.update(enabled=kibana_enabled, url=kibana_url.strip(), timeout=int(kibana_timeout))
            try:
                save_platform_config(config)
                _record_audit("integration.settings_updated", integration="kibana", enabled=kibana_enabled)
                st.success("Kibana settings saved.")
            except ConfigurationError as exc:
                st.error(str(exc))


    st.divider()
    st.subheader("Connection tests")
    probes = [("SQL Server", check_sql_server), ("REST API", check_rest_api), ("GraphQL", check_graphql), ("Elasticsearch", check_elasticsearch), ("Kibana", check_kibana), ("Ollama", check_ollama)]
    for label, probe in probes:
        if st.button(f"Test {label}", key=f"test_{label}"):
            with st.spinner(f"Testing {label}..."):
                ok, message = probe()
            (st.success if ok else st.error)(message)



def ai_provider_management_page() -> None:
    """Central provider configuration for Google Gemini, OpenAI and Ollama."""
    import os
    from universal_ai_studio.ai_platform.providers import ProviderManager

    st.set_page_config(page_title="AI Provider Management | Universal AI Studio", layout="wide")
    _admin_guard()
    st.title("AI Provider Management")
    st.caption("Configure approved AI services centrally. Application modules should use the shared provider interface rather than provider-specific SDKs.")
    try:
        config = load_platform_config()
    except ConfigurationError as exc:
        st.error(str(exc))
        return

    integrations = config["integrations"]
    ai_settings = config.setdefault("ai_provider", {})
    st.info("Credentials entered here are encrypted at rest. Alternatively, provide GOOGLE_API_KEY / GEMINI_API_KEY, OPENAI_API_KEY and OLLAMA_BASE_URL in the root .env file. Blank credential fields retain existing values.")
    if not os.getenv("UAS_CONFIG_ENCRYPTION_KEY"):
        st.warning("To save API keys through this page, configure UAS_CONFIG_ENCRYPTION_KEY in .env. Keys already supplied through .env can be used without saving them here.")

    with st.form("ai_provider_management_form"):
        st.subheader("Google Gemini")
        gemini = integrations["gemini"]
        gemini_enabled = st.toggle("Allow Google Gemini", value=bool(gemini.get("enabled")), key="provider_gemini_enabled")
        gemini_model = st.text_input("Gemini model", value=gemini.get("model", "gemini-3.8-flash"), key="provider_gemini_model")
        gemini_key = st.text_input("Google API key (optional; .env fallback supported)", type="password", key="provider_gemini_key")

        st.divider()
        st.subheader("OpenAI")
        openai = integrations["openai"]
        openai_enabled = st.toggle("Allow OpenAI", value=bool(openai.get("enabled")), key="provider_openai_enabled")
        openai_model = st.text_input("OpenAI model", value=openai.get("model", "gpt-4o-mini"), key="provider_openai_model")
        openai_base_url = st.text_input("Optional OpenAI-compatible base URL", value=openai.get("base_url", ""), key="provider_openai_base_url", help="Leave blank for the official OpenAI API. Can be used with compatible gateways that implement the Chat Completions API.")
        openai_key = st.text_input("OpenAI API key (optional; .env fallback supported)", type="password", key="provider_openai_key")

        st.divider()
        st.subheader("Ollama — local models")
        ollama = integrations["ollama"]
        ollama_enabled = st.toggle("Allow Ollama", value=bool(ollama.get("enabled")), key="provider_ollama_enabled")
        ollama_url = st.text_input("Ollama base URL", value=ollama.get("base_url", "http://localhost:11434"), key="provider_ollama_url")
        ollama_model = st.text_input("Ollama model", value=ollama.get("model", "llama3.1"), key="provider_ollama_model")

        st.divider()
        st.subheader("Default model behaviour")
        provider_labels = {"gemini": "Google Gemini", "openai": "OpenAI", "ollama": "Ollama"}
        default_provider = st.selectbox(
            "Default provider for provider-aware modules",
            options=list(provider_labels),
            format_func=lambda value: provider_labels[value],
            index=list(provider_labels).index(ai_settings.get("default_provider", "gemini")) if ai_settings.get("default_provider", "gemini") in provider_labels else 0,
        )
        c1, c2, c3 = st.columns(3)
        temperature = c1.slider("Temperature", min_value=0.0, max_value=2.0, value=float(ai_settings.get("temperature", 0.2)), step=0.1)
        max_tokens = c2.number_input("Maximum output tokens", min_value=32, max_value=32768, value=int(ai_settings.get("max_tokens", 2048)), step=128)
        timeout = c3.number_input("Provider timeout (seconds)", min_value=5, max_value=600, value=int(ai_settings.get("timeout", 60)), step=5)
        save = st.form_submit_button("Save AI provider configuration", type="primary")

    if save:
        integrations["gemini"].update(enabled=gemini_enabled, model=gemini_model.strip())
        integrations["openai"].update(enabled=openai_enabled, model=openai_model.strip(), base_url=openai_base_url.strip(), timeout=int(timeout))
        integrations["ollama"].update(enabled=ollama_enabled, base_url=ollama_url.strip(), model=ollama_model.strip(), timeout=int(timeout))
        ai_settings.update(default_provider=default_provider, temperature=float(temperature), max_tokens=int(max_tokens), timeout=int(timeout))
        selected_enabled = {"gemini": gemini_enabled, "openai": openai_enabled, "ollama": ollama_enabled}[default_provider]
        if not selected_enabled:
            st.error("The selected default provider must be enabled before saving.")
            return
        try:
            _save_configuration(config, [("gemini", "api_key", gemini_key), ("openai", "api_key", openai_key)])
            _record_audit("ai_provider.configuration_updated", default_provider=default_provider, enabled_providers=[name for name, enabled in (("gemini", gemini_enabled), ("openai", openai_enabled), ("ollama", ollama_enabled)) if enabled])
            st.success("AI provider configuration saved.")
            st.rerun()
        except ConfigurationError as exc:
            st.error(str(exc))

    st.divider()
    st.subheader("Provider readiness and connection tests")
    manager = ProviderManager(config)
    available = manager.available_providers()
    st.write("**Configured and enabled:** " + (", ".join(available) if available else "None detected"))
    for provider, label in (("gemini", "Google Gemini"), ("openai", "OpenAI"), ("ollama", "Ollama")):
        section = integrations[provider]
        credential_ready = provider == "ollama" or bool(
            (os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY") or _get_integration_secret("gemini", "api_key")) if provider == "gemini"
            else (os.getenv("OPENAI_API_KEY") or _get_integration_secret("openai", "api_key"))
        )
        status = "Enabled" if section.get("enabled") else "Disabled"
        st.write(f"**{label}:** {status} · " + ("Credential/endpoint detected" if credential_ready else "Credential not detected"))
        if st.button(f"Test {label}", key=f"provider_test_{provider}", disabled=not section.get("enabled") or not credential_ready):
            with st.spinner(f"Testing {label}..."):
                ok, message = manager.test(provider)
            (st.success if ok else st.error)(message)
    st.caption("Provider selection applies to modules migrated to the shared ProviderManager interface. Legacy modules that directly instantiate a vendor SDK must be migrated before their provider can be switched from this page.")


def health_dashboard_page() -> None:
    st.set_page_config(page_title="Platform Health | Universal AI Studio", layout="wide")
    _admin_guard()
    st.title("Platform Health")
    st.caption("Live connectivity checks are initiated only when you request them.")
    st.subheader("Registered module readiness")
    module_rows = []
    for application in registry.list(available_only=False):
        ready, missing = validate_module_dependencies(application.key, application.dependencies if application.discovered else None)
        module_rows.append({"Module": application.name, "Enabled": application.enabled, "Entry point": "Available" if application.available else "Missing", "Dependencies": "Ready" if ready else "Missing: " + ", ".join(missing)})
    st.dataframe(module_rows, width="stretch", hide_index=True)
    probes = [("SQL Server", check_sql_server), ("REST API", check_rest_api), ("GraphQL", check_graphql), ("Elasticsearch", check_elasticsearch), ("Kibana", check_kibana), ("Ollama", check_ollama)]
    if st.button("Run all health checks", type="primary"):
        for label, probe in probes:
            with st.spinner(f"Checking {label}..."):
                ok, message = probe()
            st.write(f"{'🟢' if ok else '🔴'} **{label}:** {message}")
