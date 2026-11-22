# Universal AI Studio

Universal AI Studio is a unified Streamlit workspace for 18 existing analytics, AI/ML, data, integration and business applications. The root `app.py` is the single supported launcher, and the central application registry drives the main navigation.

## Documentation

- [Application architecture](APP_ARCHITECTURE.md) — current architecture, all 18 application entry points, service boundaries, security notes and known limitations.
- [Marketing Campaign Studio guide](pages/12_marketing_campaign_studio/MARKETING_CAMPAIGN_STUDIO.md)
- [GraphQL Explorer guide](pages/13_GraphQL_API/GRAPHQL_EXPLORER.md)
- [Market Intelligence guide](pages/15_Tensor_trade_business/MARKET_INTELLIGENCE_GUIDE.md)
- [NLP-to-SQL + Document RAG guide](pages/18_NLP-to-SQL_RAG_App/NLP_TO_SQL_RAG_GUIDE.md)
- [Module registration guide](docs/MODULE_REGISTRATION.md)
- [Configuration and integrations guide](docs/CONFIGURATION_GUIDE.md)
- `docs/architecture/` contains the implementation audit and delivery notes.

There is exactly **one Python dependency manifest**: the repository-root `requirements.txt`. There is exactly **one repository README**: this file. Application-specific guides use descriptive filenames and are not separate README files.

## Prerequisites

- Python 3.11 or 3.12.
- Access to any external services required by the particular application you want to use.
- Elasticsearch 8.x for the NLP-to-SQL vector retrieval and RAG features.
- Kibana 8.12.2 is included in the supplied Docker Compose configuration for local Elasticsearch administration and monitoring. Keep Kibana and Elasticsearch versions aligned.
- Market Intelligence retrieves Yahoo Finance data, calculates technical indicators and exports validated TensorTrade-format OHLCV. It does **not** currently create TensorTrade environments, train reinforcement-learning agents, backtest strategies or execute trades; the TensorTrade runtime is not included in the root dependency manifest.
- Optional: Ollama, Redis, SQL Server, MongoDB, SMTP and MCP services depending on the selected application.

The main Streamlit workspace does not require a separately running FastAPI/Uvicorn server. GraphQL Explorer executes its Strawberry schema in-process. Agent Assist invokes its Python service in-process.

## Install and run

### Windows / VS Code

Open the project folder in VS Code, open **Terminal → New Terminal**, and run:

```powershell
.\setup.bat
```

The script creates or reuses `.venv`, checks/repairs pip, installs the root `requirements.txt`, runs `pip check`, creates `.env` from `.env.example` when needed, generates a local encryption key if one is missing, and optionally launches Streamlit. This project currently targets Python 3.11 or 3.12; Python 3.14 is not assumed compatible with every AI/ML dependency. If the existing `.venv` uses an unsupported version, the script asks before recreating only that virtual-environment folder.

After setup, edit `.env` with the endpoints and settings required by your services. The setup script preserves an existing `.env` and existing encryption key. Back up `UAS_CONFIG_ENCRYPTION_KEY` separately from the encrypted credentials file.

Launch manually at any time with:

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```

### Linux / macOS

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cp .env.example .env
# Edit .env and configure only the providers/services you plan to use.
streamlit run app.py
```

Open the local URL printed by Streamlit, normally `http://localhost:8501`. Stop the application with `Ctrl+C`.

**If you already created `.venv` or see `ModuleNotFoundError`:** open PowerShell in the repository root, activate that environment with ` .\\.venv\\Scripts\\Activate.ps1 `, then run `python -m pip install --upgrade pip` and `python -m pip install -r requirements.txt` again. Start Streamlit from that same activated terminal using `python -m streamlit run app.py`. Do not install packages with a different Python interpreter. The dependency names corresponding to common imports are `scikit-learn` for `sklearn`, `langchain-openai` for `langchain_openai`, `python-dotenv` for `dotenv`, and `strawberry-graphql` for `strawberry`.

### Test login

A development-only test account is included in `auth/users.json` so you can sign in immediately:

| Field | Value |
|---|---|
| Username | `demo` |
| Password | `demo123` |
| Role | `admin` (full application navigation) |

The JSON file stores a salted PBKDF2-SHA256 password hash, not the plaintext password. For local testing, any non-empty password is accepted when creating an account or resetting a password; the 12-character, mixed-case, number and symbol complexity rule has been removed. You may optionally replace the demo account with your own credentials using `UAS_BOOTSTRAP_ADMIN_USERNAME` and `UAS_BOOTSTRAP_ADMIN_PASSWORD` when the user store is empty. **Change or remove the demo account before exposing the app to other users or deploying it.** Existing legacy SHA-256 hashes are upgraded to salted PBKDF2-SHA256 after successful login.

## Dynamic platform administration

Administrator users see **Platform Administration first** in the persistent left sidebar navigation and at the top of the dashboard:

- **Application Management:** enable or disable registered modules, validate dependencies, and register an existing repository-local Streamlit page through a manifest. Newly discovered modules start disabled.
- **Integration Management:** configure SQL Server, REST, GraphQL, Elasticsearch, Kibana and LLM provider endpoints; connection tests are available for supported external services.
- **AI Provider Management:** manage Gemini, OpenAI and Ollama defaults and credentials.
- **MCP Management:** register MCP servers, discover tools/resources/prompts and govern tool execution.
- **Platform Health:** run on-demand connectivity checks, including Elasticsearch and Kibana reachability.

Non-secret settings are persisted in `config/platform.json`; custom module manifests are stored in `config/modules/` and contain only validated relative page paths. Integration credentials are encrypted in `config/secrets.enc` using Fernet. The encryption key must be supplied separately as `UAS_CONFIG_ENCRYPTION_KEY` in the local `.env` or an approved secret manager; it is never written to the configuration files. The Windows `setup.bat` generates this key automatically when it initializes a new `.env` or finds the setting empty. For manual setup on Linux/macOS, generate one with:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Store the value in `.env` as `UAS_CONFIG_ENCRYPTION_KEY=...`. Back up the key separately from `config/secrets.enc`; losing the key makes saved credentials unrecoverable. Runtime configuration is loaded after authentication and exposed to legacy modules through process environment variables to support incremental migration.

## Navigation and user guidance

- The root application shell uses Streamlit native **left sidebar navigation**, with **Platform Administration first** for administrators, followed by Home and grouped application categories.
- Home is always available as a route in the left sidebar, and a compact workspace switcher is rendered by the shared shell on every registered application page. Streamlit owns route transitions and browser history; application session state is not cleared during switching.
- The dashboard uses equal-column, minimum-height application cards and separates administrator tools from end-user workspaces.
- Every registered application has a contextual **Getting started** panel with an overview, steps, input guidance, an example prompt, expected output and common troubleshooting advice. These examples are guidance, not promises of identical output.
- Market Intelligence includes a bundled synthetic OHLCV demo dataset, visibly labelled as demonstration data. It must not be used for investment decisions.

## Architecture decisions

- **Frontend:** Streamlit remains the primary UI.
- **Application navigation:** all 18 applications are registered in `universal_ai_studio/applications/registry.py` and exposed through root `app.py`.
- **API runtime:** no standalone FastAPI/Uvicorn server is started or required for the Streamlit workspace. There is no separately hosted REST or GraphQL HTTP endpoint in this configuration.
- **GraphQL:** Strawberry query execution is in-process.
- **Vector database:** Elasticsearch is the only vector database. No Qdrant, Chroma, Pinecone, FAISS or in-memory vector-store fallback is used in the migrated NLP-to-SQL retrieval paths.
- **Operational databases:** SQL Server, SQLite and optional MongoDB remain available for application/business data; they are not vector databases.
- **AI providers:** Gemini, OpenAI and Ollama are used by application-specific workflows where configured. Provider selection is not yet centralized across all legacy applications.

## Elasticsearch configuration

Configure the endpoint and authentication required by your Elasticsearch deployment:

```dotenv
ELASTICSEARCH_URL=http://localhost:9200
ELASTICSEARCH_VERIFY_CERTS=true
# Use either an API key or username/password:
ELASTICSEARCH_API_KEY=
ELASTICSEARCH_USERNAME=
ELASTICSEARCH_PASSWORD=
```

The NLP-to-SQL applications use Elasticsearch `dense_vector` indexes. The default embedding model is `sentence-transformers/all-MiniLM-L6-v2` (384 dimensions). Existing indexes must have a compatible mapping. Changing the embedding model or dimension requires a planned re-embedding/re-indexing migration. Existing Qdrant data was not migrated because no source collection export was supplied.

Elasticsearch is an external service; it is not started by `streamlit run app.py`. If it is unavailable, vector retrieval and document RAG cannot operate.

## Kibana configuration

Kibana is the management and visualization interface for Elasticsearch; it is **not** a separate database or vector store. Universal AI Studio continues to use Elasticsearch as its only vector database. Use Kibana to inspect indexes, mappings, indexed documents, cluster status and queries.

The integration patch adds Kibana settings to the root `.env.example` and the administrator integration configuration:

```dotenv
# Browser-facing Kibana URL when Streamlit runs directly on Windows/Linux/macOS:
KIBANA_URL=http://localhost:5601

# Elasticsearch URL as seen from the Kibana Docker container when Elasticsearch
# is running on the host or in a separate container with port 9200 published:
KIBANA_ELASTICSEARCH_HOSTS=http://host.docker.internal:9200
```

Use the URL that is reachable **from the application runtime** in Integration Management:

| Where Streamlit runs | Kibana URL configured in Universal AI Studio |
|---|---|
| Directly on the host | `http://localhost:5601` |
| In the supplied Docker Compose network | `http://kibana:5601` |

The supplied Compose file overrides `KIBANA_URL` for the `universal-ai-studio` container to `http://kibana:5601`. Your browser still opens Kibana at `http://localhost:5601` because Compose publishes port 5601 on the host. The Kibana container uses `KIBANA_ELASTICSEARCH_HOSTS` to reach Elasticsearch. If Elasticsearch is on a different host or port, update this variable in `.env` to the URL reachable from the Kibana container.

### Start Kibana with an existing Elasticsearch container (Windows PowerShell)

If your existing Elasticsearch Docker container is named `elasticsearch` and publishes port 9200, start it first:

```powershell
docker start elasticsearch
Invoke-RestMethod http://localhost:9200
```

Then start only Kibana from the project root (use this when Streamlit is already running directly on your Windows machine):

```powershell
Copy-Item .env.example .env -ErrorAction SilentlyContinue
# Edit .env and preserve your existing credentials and encryption key.
docker compose up -d kibana
docker compose logs -f kibana
```

Open Kibana at `http://localhost:5601`. Check container status with `docker compose ps` and stop the Compose-managed Kibana service with `docker compose stop kibana`.

If you want to run the Streamlit application in Docker as well, start the complete Compose stack instead:

```powershell
docker compose up -d --build
docker compose ps
docker compose logs -f kibana
```

The complete stack publishes Streamlit at `http://localhost:8501` and Kibana at `http://localhost:5601`. Avoid running a second standalone Kibana container on port 5601 at the same time. If you previously created one with `docker run --name kibana`, stop and remove that old container before starting the Compose-managed Kibana:

```powershell
docker stop kibana
docker rm kibana
```

Only run those last two commands if that standalone container exists and you intend to replace it with the Compose-managed service. They do not delete Elasticsearch data.

### Kibana connection validation

1. Confirm Elasticsearch responds at `http://localhost:9200` from the host.
2. Confirm the Kibana container is running: `docker compose ps`.
3. Open `http://localhost:5601` and wait for Kibana to finish starting.
4. In Universal AI Studio, open **Integration Management**, set the Kibana URL appropriate to the Streamlit runtime (`http://localhost:5601` for host-run Streamlit or `http://kibana:5601` for the Compose application container), save, and run **Test Connection**.
5. The **Platform Health** page can then check Kibana's `/api/status` endpoint.

A successful HTTP health check confirms Kibana is reachable; it does not by itself prove that every Elasticsearch index, mapping or vector-search workflow is healthy.

## Configuration and secrets

- Copy `.env.example` to `.env` and populate only the variables required by the selected features.
- Never commit `.env`, API keys, database passwords, SMTP credentials, local user stores or runtime logs.
- Keep `SEND_EMAIL=false` while testing. Enable email delivery only after reviewing the configured recipient and approving the send in the application.
- Use least-privilege, read-only SQL credentials for natural-language SQL features.
- Validate generated SQL before execution and treat retrieved documents as untrusted content.
- The local JSON user store is a single-instance development/bootstrap mechanism, not enterprise SSO or shared identity management.

## Tests

Run from the repository root:

```bash
python -m compileall -q .
python -m pytest -q
```

The default pytest configuration collects the maintained `tests/` suite. Unit tests do not certify live connectivity to Elasticsearch, SQL Server, Redis, Ollama, Gemini, OpenAI, SMTP, Yahoo Finance or MCP servers.

## Current limitations

The 18 applications are centrally registered and feature-toggle controlled, but their internal implementations remain partly independent. Shared configuration and encrypted credential persistence are implemented; not every legacy service has yet been migrated to consume a typed shared database/API/provider client. The GraphQL integration test page is in-process and therefore does not use the remote GraphQL health probe unless an external endpoint is configured. The local JSON authentication store and Streamlit page guards are not a substitute for enterprise SSO and service-layer authorization. Integration tests still require reachable external services and valid credentials.

Before production rollout, complete per-application integration tests, security review, SSO and backend authorization, centralized secrets management, observability, deployment hardening, backup/restore validation, performance testing and tenant-isolation testing.


## Docker deployment

The repository includes a root `Dockerfile`, `.dockerignore`, and `docker-compose.yml` for the Streamlit application and Kibana. The Compose file assumes Elasticsearch is already running separately and reachable from Docker through the host-published port 9200. It does not create, replace or migrate the Elasticsearch container or its data.

### Run Streamlit locally and Kibana in Docker

This is useful when developing with `streamlit run app.py` on Windows while keeping Kibana containerized:

```powershell
# Start the existing Elasticsearch container (if it is not already running).
docker start elasticsearch

# Start only Kibana; do not start a second Streamlit container.
docker compose up -d kibana
docker compose ps
```

Configure the host-run Streamlit application with `KIBANA_URL=http://localhost:5601` in `.env` or in **Integration Management**. Open Streamlit at `http://localhost:8501` and Kibana at `http://localhost:5601`.

### Run Streamlit and Kibana in Docker

Copy `.env.example` to `.env` only if `.env` does not already exist. Do not overwrite an existing `.env`; it may contain API keys, database credentials and the encryption key. Populate the required values, then run:

```powershell
Copy-Item .env.example .env -ErrorAction SilentlyContinue
# Edit .env; preserve existing secrets and UAS_CONFIG_ENCRYPTION_KEY.
docker compose build
docker compose up -d
docker compose ps
docker compose logs -f universal-ai-studio kibana
```

Open Streamlit at `http://localhost:8501` and Kibana at `http://localhost:5601`. Inside the Compose network, the Streamlit container reaches Kibana using `http://kibana:5601`; the browser reaches the published Kibana port using `http://localhost:5601`. The Kibana container reaches the separately running Elasticsearch service using `KIBANA_ELASTICSEARCH_HOSTS`, which defaults to `http://host.docker.internal:9200`.

If Elasticsearch is hosted elsewhere, change `KIBANA_ELASTICSEARCH_HOSTS` to an address reachable from the Kibana container. For the Streamlit container, `DOCKER_ELASTICSEARCH_URL` controls its Elasticsearch endpoint. Do not use `localhost` inside a container to refer to a service running on the Windows host or in another container.

Stop the Compose services with `docker compose down`. This stops/removes the Compose-managed containers but does not remove the separately managed Elasticsearch container or its data. For production, use authenticated TLS endpoints, a secret manager and a hardened network configuration; the local development defaults are not production security settings.

## API credentials

The application reads API credentials from the project-root `.env` file. Set `OPENAI_API_KEY` for OpenAI and `GOOGLE_API_KEY` (or the backwards-compatible `GEMINI_API_KEY`) for Google Gemini. Azure OpenAI deployments may additionally use `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_VERSION`, and `AZURE_OPENAI_DEPLOYMENT`. Legacy pages now prefer `.env` and use `.streamlit/secrets.toml` only as a backwards-compatible fallback; a `secrets.toml` file is no longer required for OpenAI/Gemini API keys. Restart Streamlit after changing `.env`.

### AI Provider Management

Administrators can open **AI Provider Management** from Platform Administration to enable/disable Google Gemini, OpenAI and Ollama, choose the default provider/model, and set generation defaults. API credentials entered in the UI are stored in the encrypted credential store; alternatively, credentials can be supplied in the root `.env` file (`GOOGLE_API_KEY` or `GEMINI_API_KEY`, `OPENAI_API_KEY`, and `OLLAMA_BASE_URL`). Ollama is intended for locally hosted models and must be reachable from the application runtime (inside Docker, use `host.docker.internal` when Ollama runs on the host).

The shared provider service is implemented in `universal_ai_studio/ai_platform/providers.py`. File Q&A, API Analyzer and SQL Voice Chatbot use this provider abstraction, so their chat-generation provider can be changed in AI Provider Management without editing those modules. New modules should use `ProviderManager.complete()` or `get_langchain_llm()` rather than importing a vendor SDK directly. A few legacy modules, including Azure-specific Voice Test and specialized intent-detection paths, still use their own provider integration and require migration before they can be switched centrally. Embedding providers are configured separately from chat providers; changing an embedding model may require rebuilding Elasticsearch vector indexes when dimensions or embedding semantics differ.

## Unified application navigation (November 2026)

The application entry point now uses Streamlit's native multipage navigation in the persistent top position. The navigation is grouped by workspace type and backed by the central application registry. A global **Switch workspace** selector is rendered above every page, providing direct access to the dashboard, every enabled application, and (for administrators) platform management routes. The Dashboard remains available from the left sidebar and the switcher.

Navigation uses stable route slugs and Streamlit-managed URL/history handling. Switching pages does not clear `st.session_state`; app state held there remains available while the same user session is active. Logout is centralized in the global application header. Module-specific sidebars are retained for their existing workflow controls, but their duplicate logout buttons were removed.

The dashboard is the application discovery catalogue. Application identity, icon, description, category, route and sort order are owned by `universal_ai_studio/applications/registry.py`. New modules should be registered there (or through the trusted module manifest workflow) rather than hard-coded into dashboard UI code.

**Mail application note:** this repository does not contain a standalone Mail client. Email composition and campaign delivery workflows are part of Marketing Campaign Studio. A separate Mail application should only be added when its actual implementation and requirements are available.

## Market Intelligence workspace redesign

Market Intelligence now uses a dedicated, collapsible left sidebar for its five feature views and shared instrument controls. The platform-level application navigation remains in the Universal AI Studio shell. All five views use one shared design system and layout contract documented in `docs/MARKET_INTELLIGENCE_UI_STANDARD.md`.

The workspace supports both Yahoo Finance live data and the bundled synthetic demonstration dataset. Demonstration data is clearly labelled and is not represented as live market data. TensorTrade functionality remains validated OHLCV preparation/export; this does not imply environment construction, agent training, backtesting or order execution.


### Troubleshooting: integration credentials cannot be saved

`GOOGLE_API_KEY` (or `GEMINI_API_KEY`) authenticates requests to Google Gemini. `UAS_CONFIG_ENCRYPTION_KEY` is a separate local Fernet key used only to encrypt credentials saved through the Integrations UI. The app now generates the encryption key automatically on first startup when it is missing, while preserving all existing `.env` values. Restart the app from the repository root if you see the old warning. Do not replace your Google API key with the encryption key.
