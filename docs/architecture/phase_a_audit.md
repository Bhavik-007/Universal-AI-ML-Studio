# Repository audit and correction report — 2026-11-15

## Repository inventory

The archive contains 18 Streamlit application entry points, a root Streamlit workspace, authentication utilities, a platform FastAPI foundation, a Strawberry GraphQL service, two NLP-to-SQL applications, SQL Server integrations, optional MongoDB metadata persistence, and local runtime logs/configuration.

## Verified issues found before correction

| Area | Finding | Severity |
|---|---|---|
| Authentication | Unsalted SHA-256 password hashes, hard-coded default administrator creation, and password-reset codes displayed in the UI | Critical |
| Page execution | Several Streamlit pages called `st.set_page_config` after other Streamlit commands; this can raise `StreamlitAPIException` | High |
| Navigation | The root app exposed only the data explorer while the enterprise dashboard and other verified apps were not registered centrally | High |
| Vector retrieval | Both NLP-to-SQL apps imported Qdrant directly and the RAG app silently fell back to in-memory vectors | High |
| Dependencies | Root `requirements.txt` was UTF-16 encoded; pytest autodiscovered manual connection scripts and failed collection when optional dependencies were absent | High |
| Secrets | Multiple nested `.env` files and a hard-coded API credential assignment were present in the archive | Critical |
| Observability | Local log files were included in the project archive and logging policies were fragmented | Medium |
| Readiness claims | Dashboard provider metrics were hard-coded and could imply configuration/health that had not been verified | Medium |

## Corrections applied in this delivery

- Replaced shared password hashing with salted PBKDF2-SHA256 and automatic upgrade of legacy SHA-256 hashes on successful login.
- Removed automatic creation of a known default administrator. First-admin bootstrap now requires explicit environment credentials.
- Removed password-reset code disclosure in the UI. Recovery now requires configured SMTP, uses a short-lived code, and limits attempts.
- Added session lifetime checks and a shared sign-out control.
- Registered the dashboard, data explorer and 18 verified application pages in the root Streamlit navigation.
- Standardized page configuration to occur before page rendering and added login guards to registered application pages.
- Replaced Qdrant vector-store code in both NLP-to-SQL applications with an Elasticsearch dense-vector implementation.
- Removed Qdrant client dependencies and in-memory vector fallback from those paths. Elasticsearch failures now surface explicitly.
- Updated NLP-to-SQL configuration and RAG documentation to use Elasticsearch indexes and embedding dimension validation.
- Converted root requirements to UTF-8, merged dependencies from all application folders into one repository-root `requirements.txt`, and removed duplicate/per-app requirements manifests.
- Added `pytest.ini` to restrict default test collection to the maintained `tests/` directory.
- Removed a hard-coded API credential from the connection test in favor of `OPENAI_API_KEY`.
- Added `.gitignore` rules and safe `.env.example` templates; actual `.env` files and runtime logs are excluded from the delivery archive.
- Rewrote the root README with setup, run, testing and security guidance.

## Validation performed

- Initial `python -m compileall -q .`: passed before modifications.
- Initial `python -m pytest -q`: collection failed because pytest discovered standalone scripts requiring unavailable optional packages (`streamlit`, `ollama`, `pyodbc`).
- Initial `python -m pytest -q tests`: 8 passed.
- Post-change `python -m compileall -q .`: passed.
- Post-change `python -m pytest -q`: 14 passed.
- Static scan: no Qdrant client imports remain in Python source; both NLP-to-SQL retrieval implementations now use the shared Elasticsearch dense-vector store.
- Static scan: all registered Streamlit page files exist and the maintained page scripts include authentication guards.

## Important migration and production limitations

- No live Elasticsearch cluster was available; index creation, dense-vector mapping compatibility, ingestion, semantic retrieval and hybrid retrieval were not integration-tested.
- No Qdrant service/data snapshot was supplied. Code paths and dependencies were migrated, but existing Qdrant collection data has not been exported or imported into Elasticsearch.
- No Gemini/OpenAI/Ollama credentials or external provider calls were used to claim provider connectivity.
- No SQL Server, MongoDB, MCP server, SMTP server or external APIs were available for end-to-end validation.
- The local JSON user store is a development compatibility layer. Existing local user-store files and hashes are intentionally excluded from the distributable archive; bootstrap a new administrator using environment variables. Production requires an enterprise identity provider, shared session management, backend RBAC and an approved secrets manager.
- The legacy application modules have not all been refactored to consume the shared AI provider manager, common database manager, centralized RAG service or policy-enforced authorization.
- No production deployment, HA, disaster recovery, backup restore, tenant isolation or compliance certification is claimed.

## Recommended next steps

1. Configure a non-production Elasticsearch 8.x cluster and verify both schema and document indexes.
2. Re-embed/re-index any required legacy Qdrant content after exporting and validating its metadata.
3. Integrate an enterprise identity provider and enforce RBAC in every API/service.
4. Run per-application integration tests with the required external services and OS dependencies.
5. Pin dependencies in a tested lockfile and add CI security/dependency scanning.


## Repository documentation consolidation

The repository now has one Python dependency manifest (`requirements.txt`). Application-specific dependency manifests and `requirements-enterprise.txt` were removed after their dependencies were reviewed and merged. The current architecture is documented in the root `APP_ARCHITECTURE.md`.


## Follow-on restructuring implemented

- Added `universal_ai_studio/core/configuration.py` for persistent non-secret settings and Fernet-encrypted integration secrets.
- Added `feature_manager.py` and per-module dependency validation; disabled modules are removed from Streamlit navigation and cannot be newly enabled when declared dependencies are missing.
- Added administrator-only Feature Management, Integration Management and Platform Health pages.
- Added centralized SQL Server, REST, GraphQL, Elasticsearch and Ollama connection probes plus shared SQLAlchemy, REST, GraphQL and Elasticsearch client factories.
- Applied saved integration settings after authentication so legacy modules can consume centrally managed values through process environment variables.
- Renamed the two nested generic `app` packages to `nlp_to_sql_app` and `nlp_to_sql_rag_app`, resolving a cross-module `sys.modules['app']` collision.
- Added explicit module path bootstraps for Marketing Campaign Studio, Market Intelligence and SVM Fraud Detection local imports.
- Renamed Market Intelligence's generic `services` package to `market_intelligence_services` and SVM Fraud Detection helper modules to a dedicated `svm_fraud` package to avoid cross-module import collisions.
- Added Windows `setup.bat` with supported Python version checks, pip repair, dependency installation and `pip check`.
- Expanded automated tests for encrypted secret storage, feature flag persistence and unique module namespaces.


## Final verification snapshot

- `python -m compileall -q .`: passed.
- `python -m pytest -q`: 36 passed.
- 105 Python files parsed via AST.
- 18 built-in registry paths verified present; package namespace collision fixes cover NLP-to-SQL, Market Intelligence and SVM Fraud Detection.
- Live Streamlit execution and real external integration connectivity remain pending on the Windows deployment environment.
