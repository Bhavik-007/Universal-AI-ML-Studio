# Platform configuration and integrations

## Administrator pages

The following pages are available to administrator accounts:

- **Feature Management:** enable/disable built-in applications, inspect missing Python dependencies, and register existing repository-local Streamlit pages.
- **Integration Management:** configure SQL Server, REST API, GraphQL, Elasticsearch and LLM providers; save endpoint settings and credentials; run connection tests.
- **Platform Health:** inspect module readiness and run on-demand external-service health checks.

## Configuration storage

- Non-secret settings: `config/platform.json`.
- Custom module manifests: `config/modules/*.json`.
- Encrypted integration credentials: `config/secrets.enc`.
- Administrator configuration audit events: `logs/audit_events.jsonl` (secret-like values are redacted).
- Encryption key: `UAS_CONFIG_ENCRYPTION_KEY` in the local `.env` or an approved secrets manager.

The Windows `setup.bat` initializes `.env` after installing dependencies. On application startup, the app also checks the setting and automatically generates a Fernet key if it is missing or blank. Existing `.env` values (including `GOOGLE_API_KEY`) and any existing non-empty encryption key are preserved. The key is written only to the local `.env`; it is never derived from or substituted for a provider API key. Back up the key separately from `config/secrets.enc`; losing the key makes stored credentials unrecoverable. Never commit `.env` or `config/secrets.enc`.

## Supported integration settings

### SQL Server

Configure host, database, ODBC driver, SQL or Windows authentication, encryption, certificate trust, username and password. The connection test requires a compatible Microsoft ODBC Driver to be installed on the machine.

### REST API

Configure the base/health URL, timeout, bearer token and/or API key. The connection test issues an HTTP GET to the configured URL.

### GraphQL

Configure the endpoint, timeout, bearer token and/or API key. The connection test sends a small `__typename` query. A server that disables this query may return a failed probe even if another application-specific query is allowed.

### Elasticsearch

Configure the endpoint, TLS verification, timeout, authentication, index prefix, schema metadata index, document chunks index and Marketing Campaign Studio index. Elasticsearch is the only vector database in this application. Existing indexes are not deleted or recreated by saving settings. Mapping changes and re-embedding require a separate migration plan.

### LLM providers

Configure Ollama endpoint/model and OpenAI/Gemini model names and credentials. A configured provider is not necessarily reachable; use provider-specific checks or application workflows where available.

## Runtime behavior and migration

Saved integration values are applied after authentication and exposed to legacy modules through process environment variables. This compatibility bridge lets existing modules adopt central settings incrementally. New and refactored modules should use `universal_ai_studio.integrations.manager.IntegrationManager` to create shared SQLAlchemy, REST, GraphQL and Elasticsearch clients.

Disabling an integration removes its managed values from the process environment on the next Streamlit rerun. Modules must still handle unavailable integrations gracefully. The health page tests connectivity on demand; it does not continuously monitor services.

## Production cautions

The local JSON user store is a development/bootstrap mechanism, not enterprise SSO. Before production use, deploy an approved secrets manager, identity provider, backend-enforced authorization, audit logging, TLS, backup/restore, and operational monitoring. Never place credentials in `platform.json`, logs, source code or frontend-rendered output.


## Provider API keys via `.env`

Set `OPENAI_API_KEY` for OpenAI. Set `GOOGLE_API_KEY` for Google Gemini; `GEMINI_API_KEY` remains supported for compatibility. For Azure OpenAI, also set `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_VERSION`, and `AZURE_OPENAI_DEPLOYMENT`. Do not add these values to source code or commit the `.env` file. Legacy Streamlit pages prefer environment variables and only fall back to `.streamlit/secrets.toml` when an environment value is absent.
