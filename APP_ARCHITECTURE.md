# Universal AI Studio — Application Architecture

**Document purpose:** describe the current repository architecture, how the 18 applications are exposed through one Streamlit workspace, the main runtime/data boundaries, and what is and is not provided by this delivery. This document describes the implementation in this repository; it is not a target-state design or a production-readiness certification.

## 1. Architecture at a glance

Universal AI Studio is a **single-process Streamlit workspace**. The root `app.py` is the only supported application launcher. It authenticates the user, builds navigation from the central application registry, and renders the selected application page in the Streamlit process.

```text
                         User / Browser
                               |
                               v
                    Streamlit server process
                         streamlit run app.py
                               |
                 +-------------+-------------+
                 |                           |
                 v                           v
          Authentication              Streamlit navigation
          auth/login_manager.py       enterprise_dashboard.py
          auth/auth_guard.py                  |
                                             v
                                Application registry (18 apps)
                                             |
            +----------------+---------------+------------------+
            |                |               |                  |
            v                v               v                  v
       Analytics         Integration       AI / RAG          Business
       and ML pages      and GraphQL       applications      workflows
            |                |               |                  |
            +----------------+---------------+------------------+
                                             |
                                             v
                              Application-specific Python services
                                             |
             +---------------+---------------+----------------+
             |               |               |                |
             v               v               v                v
        LLM providers   Elasticsearch     Operational DBs   External APIs
        Gemini/OpenAI   dense_vector      SQL Server         Yahoo Finance
        Ollama          keyword + vector  SQLite             SMTP
                                         MongoDB (optional)  MCP endpoints
                                             |
                                             v
                                Results returned to Streamlit
```

### Runtime decisions

- **One launcher:** `streamlit run app.py`.
- **No separate Uvicorn process:** the main workspace does not start FastAPI/Uvicorn and does not require a second API terminal.
- **GraphQL:** the GraphQL Explorer invokes the Strawberry schema in-process. It is an embedded query interface, not a separately hosted GraphQL HTTP endpoint.
- **Agent Assist:** the Streamlit page calls its local Python backend directly. Redis and Ollama are optional supporting services depending on the configured processing path.
- **No separate Data Explorer launcher:** the duplicate `analyse_app.py` entry was removed. The Enterprise Dashboard is the landing page; the 18 registered applications are the navigation catalogue.

## 2. Repository entry points and shared platform modules

| Path | Responsibility |
|---|---|
| `app.py` | Single Streamlit entry point, authentication bootstrap, sign-out and navigation |
| `enterprise_dashboard.py` | Landing page and application catalogue/readiness overview |
| `universal_ai_studio/applications/registry.py` | Single source of truth for the 18 application names, categories, page paths and runtime availability |
| `universal_ai_studio/core/configuration.py` | Persistent non-secret platform configuration and Fernet-encrypted integration secrets |
| `universal_ai_studio/core/feature_manager.py` | Central feature flag access and persistence |
| `universal_ai_studio/core/dependency_manager.py` | Per-module Python dependency validation |
| `universal_ai_studio/integrations/health.py` | On-demand SQL Server, REST, GraphQL, Elasticsearch and Ollama connectivity probes |
| `universal_ai_studio/integrations/manager.py` | Shared SQLAlchemy, REST session, GraphQL request and Elasticsearch client factories |
| `universal_ai_studio/ui/admin_pages.py` | Administrator-only feature, integration and platform health pages |
| `universal_ai_studio/core/logging.py` | Structured logging and secret-redacted administrator audit events |
| `auth/login_manager.py` | Local login, password hashing, bootstrap administrator and password recovery |
| `auth/auth_guard.py` | Page-level session and access guard |
| `universal_ai_studio/data_platform/elasticsearch.py` | Shared Elasticsearch dense-vector index/search implementation used by NLP-to-SQL RAG paths |
| `.env.example` | Names and safe defaults for environment-based configuration; contains no credentials |
| `requirements.txt` | The only Python dependency manifest for the repository |
| `tests/` | Maintained unit tests |

The registry drives the persistent left sidebar navigation and global workspace switcher dynamically. Persisted feature flags control which registered modules appear in navigation. The administrator feature page validates declared Python dependencies before enabling a currently disabled module. Legacy module internals are being migrated incrementally and do not yet all use shared service abstractions.

## 3. The 18 registered applications

All 18 entries below are registered in `universal_ai_studio/applications/registry.py` and are reachable from the main Streamlit navigation after login.

| # | Navigation name | Page entry point | Area |
|---:|---|---|---|
| 1 | Forecast Model | `pages/1_Forecast_Model.py` | Forecasting / analytics |
| 2 | CSV / Excel Q&A | `pages/2_File_QA_Chatbot.py` | File and document Q&A |
| 3 | API Analyzer | `pages/3_API_Analyzer.py` | API analysis |
| 4 | Customer Sentiment Analysis | `pages/4_Customer_Sentiment_Analysis.py` | NLP / analytics |
| 5 | Finance Dashboard | `pages/5_Finance_dashboard.py` | Finance analytics |
| 6 | SQL Voice Chatbot | `pages/6_SQL_Voice_Chatbot.py` | Natural-language data access / voice |
| 7 | Voice Test | `pages/7_Voice_test.py` | Speech input/output testing |
| 8 | Universal Purchase Predictor | `pages/8_Universal_Purchase_Predictor.py` | Predictive analytics |
| 9 | MCP Explorer | `pages/9_MCP_Model.py` | MCP integration exploration |
| 10 | Card Fraud Detection | `pages/10_Card_Fraud_Detection.py` | Fraud analytics |
| 11 | Loan Decision Tree | `pages/11_Decision_tree.py` | Decision support / ML |
| 12 | Marketing Campaign Studio | `pages/12_marketing_campaign_studio/app.py` | Campaign content and delivery workflow |
| 13 | GraphQL Explorer | `pages/13_GraphQL_API/app.py` | In-process Strawberry GraphQL exploration |
| 14 | Agent Assist | `pages/14_Fast_API_Intent_detaction/app.py` | Intent, sentiment and agent guidance |
| 15 | Market Intelligence | `pages/15_Tensor_trade_business/app.py` | Market data and technical analytics |
| 16 | SVM Fraud Detection | `pages/16_SVM_fraud_detection/app.py` | Supervised / unsupervised fraud models |
| 17 | NLP-to-SQL | `pages/17_NLP-to-SQL/nlp_to_sql_app/ui/main.py` | Natural-language SQL and schema retrieval; namespaced package avoids generic `app` collisions |
| 18 | NLP-to-SQL + Document RAG | `pages/18_NLP-to-SQL_RAG_App/nlp_to_sql_rag_app/ui/main.py` | Natural-language SQL and document retrieval; namespaced package avoids generic `app` collisions |

The Enterprise Dashboard is the default landing page and is not counted as one of the 18 application entries.

## 4. Dynamic feature and integration management

The platform now has an administrator-only management layer:

- `Feature Management` controls each registered application through persisted feature flags. Disabled applications are removed from Streamlit navigation. Declared module dependencies are checked before a disabled application can be enabled.
- `Integration Management` stores non-secret endpoint and behavior settings in `config/platform.json`, including Elasticsearch schema and document index names.
- Credentials are stored separately in `config/secrets.enc`, encrypted using Fernet. The key is supplied through `UAS_CONFIG_ENCRYPTION_KEY` in `.env` or an approved secret manager. The key is not persisted alongside ciphertext.
- Runtime integration values are applied after successful authentication and exposed to existing modules through process environment variables, supporting incremental migration.
- `Platform Health` provides on-demand probes for SQL Server, REST, GraphQL, Elasticsearch and Ollama. A configured endpoint is not represented as healthy until a probe succeeds.

The configuration files are runtime state and are excluded from source control. Back up the Fernet key separately from the encrypted secret file. If the key is lost, encrypted credentials cannot be recovered.

## 5. AI provider and model integration

The repository includes dependencies and application-specific code for these provider paths:

- **Google Gemini** through the Google Gen AI SDK.
- **OpenAI** through the OpenAI SDK and LangChain integration.
- **Ollama** for local model execution where an application is configured to use it.
- **Sentence Transformers** for local embedding generation in the Elasticsearch RAG applications.

Provider availability is configuration-dependent. Installing the package does not configure credentials, download local models, or prove connectivity. Provider selection and fallback behavior are not yet centralized across all 18 legacy applications.

## 6. Elasticsearch and retrieval architecture

**Elasticsearch is the only vector database in this application.** The two NLP-to-SQL applications use Elasticsearch `dense_vector` indexes for vector retrieval. The shared implementation is in `universal_ai_studio/data_platform/elasticsearch.py`.

The retrieval pattern is:

```text
Source content / database schema
             |
             v
       Text chunking
             |
             v
     Sentence Transformer
       embedding model
             |
             v
    Elasticsearch index
    - dense_vector field
    - text / keyword fields
    - metadata fields
             |
             v
 User question -> embedding + keyword query
             |
             v
      Hybrid retrieval
             |
             v
 Retrieved context -> LLM -> Streamlit response
```

Current defaults documented by the NLP-to-SQL applications:

- Embedding model: `sentence-transformers/all-MiniLM-L6-v2`.
- Vector dimension: 384.
- Indexes: `uas_schema_metadata` and `uas_document_chunks` (configured in the corresponding application YAML files).
- Elasticsearch 8.x Python client compatibility is specified in `requirements.txt`.

Do not switch embedding models or vector dimensions against an existing index without a planned re-indexing migration. Existing Qdrant data was not migrated because no source collection export was part of this delivery. Elasticsearch must be reachable for vector indexing/retrieval; these paths must fail explicitly rather than silently switching to an in-memory vector store.

Operational databases are separate from the vector database. SQL Server, SQLite and optional MongoDB may store business or application records; none is used as a substitute vector store.

## 7. Data and integration boundaries

| System | Role in the repository | Notes |
|---|---|---|
| Elasticsearch | Vector and document retrieval | Only vector database; requires external Elasticsearch service |
| SQL Server | Relational business data / campaign delivery tracking / SQL workflows | Requires SQL Server and a compatible ODBC driver where used |
| SQLite | Local GraphQL Explorer data source | Approved tables are controlled by the local GraphQL configuration |
| MongoDB | Optional application metadata/history in selected modules | Not used for vector storage |
| Redis | Optional cache/pub-sub support in Agent Assist | External service; not required to open the main Streamlit workspace |
| Ollama | Local LLM inference in selected applications | Must be installed and the requested model pulled before use |
| SMTP | Optional campaign email delivery and password recovery | Sending must remain disabled until deliberately configured and approved |
| Yahoo Finance | Market data source for Market Intelligence | Network/API availability and upstream limits apply |
| MCP servers | Tool integration for MCP Explorer | Requires separately configured MCP endpoints and permissions |

A connection setting in `.env.example` is only a configuration placeholder. It does not mean the corresponding service is bundled, running, healthy or reachable.

## 7. Authentication and security boundaries

- Local password hashing uses salted PBKDF2-SHA256; successful legacy SHA-256 logins are upgraded.
- A development demo administrator is supplied in `auth/users.json`; optional environment bootstrap credentials are used only when the JSON user store is empty. The demo account must be changed or removed before deployment.
- Password recovery depends on configured SMTP and uses time-limited, attempt-limited reset codes.
- Local user data is stored in a JSON file for this single-instance setup. It is not a shared identity platform.
- Page guards provide a UI-level access check. Sensitive operations must also enforce authorization in their service/data layer.
- Keep `.env`, user stores, logs, API keys and database credentials out of source control.
- Use least-privilege and read-only database credentials for natural-language SQL features. Validate generated SQL before execution.
- Treat retrieved documents and user-provided content as untrusted data, not as instructions to the model.

**Production requirement:** replace local JSON authentication with enterprise SSO/OIDC, shared session management, backend RBAC, centralized secrets management, TLS, audit logging and deployment-level network controls before exposing the workspace to multiple users or the public internet.

## 8. Configuration and startup

### Install

Use Python 3.11 or 3.12 and install all Python packages from the repository root. On Windows, run the included setup script from PowerShell or the VS Code integrated terminal:

```powershell
.\setup.bat
```

The script creates/reuses `.venv`, checks pip, installs the single root requirements file, validates dependencies, and optionally launches Streamlit. On Linux/macOS, create a virtual environment and install `requirements.txt` manually.

Copy `.env.example` to `.env` and fill only the settings needed by the applications you intend to run. The repository includes a local demo login in `auth/users.json` (`demo` / `demo123`), so bootstrap variables are optional for local testing. Change or remove this account before deployment. Then launch:

```bash
streamlit run app.py
```

Open the local Streamlit URL printed by the command (normally `http://localhost:8501`). **Do not start Uvicorn for this workspace.**

### Important environment variables

| Variable | Purpose |
|---|---|
| `UAS_BOOTSTRAP_ADMIN_USERNAME` | Initial local administrator name, used only when the user store is empty |
| `UAS_BOOTSTRAP_ADMIN_PASSWORD` | Optional initial local administrator password; any non-empty value is accepted |
| `ELASTICSEARCH_URL` | Elasticsearch endpoint |
| `ELASTICSEARCH_API_KEY` | Optional Elasticsearch API key |
| `ELASTICSEARCH_USERNAME` / `ELASTICSEARCH_PASSWORD` | Alternative Elasticsearch authentication |
| `ELASTICSEARCH_VERIFY_CERTS` | TLS certificate verification setting |
| `ELASTICSEARCH_SCHEMA_INDEX` / `ELASTICSEARCH_DOCUMENT_INDEX` / `ELASTICSEARCH_MARKETING_INDEX` | Module-specific Elasticsearch index selection |
| `UAS_CONFIG_ENCRYPTION_KEY` | Fernet key for encrypted UI-managed integration credentials |
| `OPENAI_API_KEY` | OpenAI-backed features, where used |
| `GEMINI_API_KEY` | Gemini-backed features, where used (check app configuration for the expected key name) |
| `OLLAMA_BASE_URL` / `OLLAMA_MODEL` / `USE_OLLAMA` | Local Ollama endpoint and model, where used |
| `REDIS_HOST` / `REDIS_PORT` | Optional Redis endpoint for Agent Assist |
| SQL Server variables | SQL workflows and campaign delivery; see `.env.example` and the relevant application config |
| SMTP variables | Password recovery and approved campaign email delivery |

The environment template is the source for exact shared variable names supported by the current configuration. Agent Assist also reads `REDIS_HOST`, `REDIS_PORT`, `OLLAMA_MODEL` and `USE_OLLAMA`. Some legacy applications also retain their own YAML/configuration files; do not assume every module reads every variable above.

## 9. Dependency management

`requirements.txt` is the **only** Python dependency manifest. Install it once from the repository root. Application-specific requirements files and the duplicate `requirements-enterprise.txt` have been consolidated and removed.

Some dependencies are needed only by optional application features (for example voice, market-data, Redis, database drivers or local LLM integrations). Their Python packages can be installed together, but their native system prerequisites and external services must be configured separately. In particular, `pyodbc` requires an installed SQL Server ODBC driver; `pyttsx3` may require OS audio components; Elasticsearch, Redis and Ollama are separate services.

## 10. Tests and operational checks

Run from the repository root:

```bash
python -m compileall -q .
python -m pytest -q
```

The default pytest configuration collects the maintained `tests/` suite and excludes manual connectivity scripts. Unit tests do not prove live connectivity to SQL Server, Elasticsearch, Redis, Ollama, Gemini, OpenAI, SMTP, Yahoo Finance or MCP servers. Run integration tests in an environment where those systems are configured.

## 11. Current limitations and production-readiness status

This repository is a consolidated Streamlit workspace with a first-stage shared administration layer. It is not yet certified as a fully unified enterprise platform.

- The 18 applications are centrally registered and feature-toggle controlled, but their internal business services remain partly independent.
- Shared configuration, encrypted credential persistence, on-demand connectivity probes and shared client factories are implemented. Not every legacy module has yet migrated to typed shared clients.
- Package namespaces for the two NLP-to-SQL applications are unique, preventing the generic `app` package collision. Market Intelligence and SVM Fraud Detection also use dedicated helper package names; Marketing Campaign Studio, Market Intelligence and SVM Fraud Detection explicitly resolve their module-local imports when launched from the central workspace.
- GraphQL Explorer remains an in-process Strawberry application; the remote GraphQL health check is only applicable when an external endpoint is configured.
- The local JSON authentication store and Streamlit page guards are not a substitute for enterprise SSO and service-layer authorization.
- Live SQL Server, Elasticsearch, REST/GraphQL, Redis, Ollama, SMTP, LLM, MCP, external API, performance/load, HA, disaster recovery, backup/restore, tenant isolation and compliance have not been certified by unit tests.
- Encrypted credentials require `UAS_CONFIG_ENCRYPTION_KEY`. The key must be backed up separately from `config/secrets.enc`; losing the key makes stored credentials unrecoverable.

Before production rollout, complete per-application integration tests, security review, SSO and backend authorization, centralized observability, deployment hardening, backup/restore validation, performance testing, tenant-isolation testing and a disaster-recovery exercise.

## 12. Modernization changes in this delivery

This delivery adds persisted module feature flags, controlled JSON-manifest module discovery, administrator-only feature/integration/health pages, Fernet-encrypted integration credential storage, shared integration client factories, module dependency checks, secret-redacted audit logging, and runtime configuration bridging for legacy modules. It removes ambiguous generic package names from both NLP-to-SQL applications, Market Intelligence and SVM Fraud Detection, and fixes Marketing Campaign Studio's module-local import resolution. The Windows setup script initializes `.env` and a local encryption key. These changes are covered by the maintained unit suite; external connection behavior still requires environment-specific integration testing.

## Central AI provider management

`AI Provider Management` is an administrator page for Google Gemini, OpenAI and Ollama. It stores non-secret defaults (default provider, temperature, token limit and timeout) in `config/platform.json`; API credentials entered in the UI are stored in Fernet-encrypted `config/secrets.enc`. Root `.env` credentials are also supported. `universal_ai_studio/ai_platform/providers.py` exposes a common completion interface and a LangChain LLM adapter. File Q&A, API Analyzer and SQL Voice Chatbot currently consume this shared abstraction. Modules that directly instantiate vendor SDKs must be migrated before central switching applies to them. Chat model selection does not automatically change embedding models or rewrite existing Elasticsearch vectors.


## Centralized MCP control plane (enhancement)

A shared MCP platform now lives under `universal_ai_studio/mcp_platform/`. It includes a
validated server registry, STDIO and Streamable HTTP client sessions, tools/resources/prompts
discovery, JSON Schema input validation, role/application/server/tool authorization, and
JSONL execution audit. Application modules integrate through `mcp_platform.api`; they should
not maintain separate MCP clients or registries. The administrator page is available as
**MCP Management**. The legacy `pages/9_MCP_Model.py` page is retained unchanged and remains
a repository structure explorer; it is not relabeled as an MCP protocol client.

The home page uses card-based application and administration sections alongside persistent Streamlit native left sidebar navigation. Existing application entry points and module registry paths remain unchanged. The new MCP registry stores configuration only; secret values are referenced by
environment-variable name and remain outside the JSON registry. See `docs/MCP_PLATFORM.md`
for implementation details and known production-hardening limitations.

## Application navigation and lifecycle

- `app.py` is the single Streamlit entry point and authentication boundary for the multipage workspace.
- `universal_ai_studio/applications/registry.py` is the source of truth for application keys, page paths, categories, icons, descriptions, enablement and stable URL slugs.
- `st.navigation(..., position="sidebar")` provides persistent, grouped native navigation. Administrator-only Platform Administration is the first group for administrators, followed by Home and application categories. Streamlit owns URL transitions and browser history.
- Home is a persistent route in the shared sidebar navigation, and the global workspace switcher appears in the shared shell on registered application routes. The Home route opens `enterprise_dashboard.py`.
- The global workspace selector in `app.py` offers direct switching to the Dashboard, enabled applications and administrator routes. It uses `st.switch_page` with repository-relative page paths.
- `enterprise_dashboard.py` is the discovery and launch surface; it is not the only navigation mechanism.
- `pages/platform/` contains thin file-based route wrappers for platform management pages so each administrative destination has a stable URL and can be linked from the dashboard and global switcher.
- Shared session state is not cleared during application switching. Logout and session expiry remain the only intentional full-session reset paths.
- Application-specific sidebars are retained where they contain workflow controls; global application navigation and logout are no longer duplicated in those sidebars.

A standalone Mail client is not present in this repository. The Marketing Campaign Studio includes email campaign functionality, which remains registered as part of that application rather than being represented as a separate mail client.


## Contextual guidance and Market Intelligence scope

- The shared shell renders an application-specific Getting started panel for all 18 built-in applications. Guidance includes purpose, steps, expected inputs, an example prompt, expected output and troubleshooting.
- Dashboard application cards use a consistent minimum height and description spacing; responsive column stacking is delegated to Streamlit's layout engine.
- Market Intelligence retrieves Yahoo Finance OHLCV data, calculates SMA/return/volatility indicators, renders charts and exports a validated TensorTrade-compatible CSV. It does not implement TensorTrade environments, reinforcement-learning agents, strategy backtesting or order execution. The optional package presence check is diagnostic only.
- A synthetic 180-row OHLCV dataset supports a clearly labelled no-network demo mode. Synthetic prices are not real market data and are not suitable for investment decisions.
