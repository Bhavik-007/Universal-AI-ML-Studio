# Session Navigation and Performance Assessment

## Findings from the supplied codebase

- The platform is a Streamlit application using `st.navigation`, `st.Page`, `st.switch_page`, and `st.session_state`.
- Authentication state (`logged_in`, username, role, timestamps) is held in Streamlit session state. Streamlit associates this state with the browser's active WebSocket session; it is not a durable cross-process session store.
- The shared entry point previously called `registry.list()` repeatedly while building navigation, quick-switch routes, and workspace guidance. Each call refreshed module manifests and, for enabled filtering, the feature manager re-read and parsed `config/platform.json` for each application.
- The File Q&A page used a relative logo path (`assets/01_firstwatchlogo.jpg`). This depends on the process working directory and can fail when launched through a service/container with a different working directory. The asset itself in the supplied archive is a valid JPEG.
- Redis is already a declared dependency and is used by the FastAPI intent-detection backend. No Redis-backed Streamlit login/session implementation was found in the reviewed entry point. No RabbitMQ implementation was found.

## Changes implemented

1. The File Q&A logo is now resolved relative to the page's own file path. A small text fallback and warning are rendered if the image is absent.
2. The main entry point builds one enabled/available application catalogue snapshot per Streamlit rerun and reuses it for page registration, category navigation, quick-switch options, and workspace guidance.
3. `ApplicationRegistry.list()` now reads platform feature configuration once per call instead of causing one platform-config read per application.
4. The dashboard reuses its enabled-app and all-available-app snapshots rather than refreshing the registry again for its metric.
5. Small, targeted visual refinements were added for alerts, upload controls, typography, and the logo fallback. The existing page layout and workflows are retained.

## Architecture recommendation

### Keep Streamlit session state for the current single-instance deployment

Do not add Redis or RabbitMQ to the Streamlit navigation path as a first response. `st.session_state` is already the low-latency state mechanism for the active browser session. A message broker does not make `st.switch_page()` or a Streamlit rerun faster.

### Redis

Use Redis only when a demonstrated requirement exists for shared ephemeral state across application instances, shared caching, rate limiting, or distributed coordination. For multi-instance Streamlit deployments, first ensure load-balancer affinity/sticky sessions because the Streamlit WebSocket owns the in-memory session. Store durable business/session records in the existing database. If the application must restore state after a worker restart or move between instances without affinity, design an explicit serializable session snapshot store; do not attempt to serialize arbitrary Streamlit objects, uploaded file handles, open clients, or LangChain agents.

Redis Streams are not needed for ordinary session retrieval. Introduce them only if a real event-consumer workflow (replayable session lifecycle events, audit/event fan-out) is required.

### RabbitMQ

RabbitMQ is appropriate for durable asynchronous jobs such as long-running document ingestion, model training, bulk processing, or outbound delivery. It should not be in the synchronous page-navigation or session-read path. No evidence in the inspected entry point establishes a need for RabbitMQ for session switching.

### Hybrid

A Redis + RabbitMQ hybrid is not recommended for this issue. It adds two operational dependencies without addressing the current Streamlit rerun/navigation mechanism. Revisit only when measured workload requirements justify both systems.

## Performance evidence and limitations

A reproducible before/after wall-clock benchmark was not possible from static source inspection alone: it requires running the application with representative user sessions, data, providers, and deployment infrastructure. No fabricated latency numbers are reported.

The deterministic code-path reduction is:

- Main entry point: repeated catalogue refresh/config reads consolidated to one catalogue snapshot per rerun.
- Enabled-feature filtering: platform configuration parsing reduced from once per registered app to once per `registry.list(enabled_only=True)` call.
- Dashboard: app catalogue snapshots are reused for metrics and page cards.

Measure real latency in the target deployment using browser navigation timings and server-side timings around authentication, registry construction, page startup, and first useful render. Compare p50/p95 across at least 30 switches per route and test with representative concurrent users. Record app version, instance count, CPU/memory, cache state, and dataset size.

## Multi-instance deployment notes

- Keep the current local JSON user store only for single-instance/local use. A multi-instance deployment needs a shared identity provider or transactional shared user store.
- Configure sticky sessions for Streamlit WebSockets, or implement a carefully scoped external state model for the subset of state that must survive instance changes.
- Persist durable user data in the database; keep transient UI state in Streamlit session state.
- Add Redis only for a specific measured shared-cache/session-snapshot use case. Add RabbitMQ only for asynchronous job processing.

## Validation

The complete repository test suite passed after the changes: **85 passed**. Python compilation checks passed for the changed entry point, dashboard, File Q&A page, and registry module. Runtime latency and multi-user load tests remain deployment validation tasks, not claims made by this source-level change.


## Authentication and navigation revision

The current entry point now initializes a hidden Streamlit navigation page before rendering the login flow. This prevents Streamlit's automatic `pages/` discovery from exposing the application catalogue to unauthenticated users. After successful authentication, the normal role-filtered sidebar navigation is built.

The redundant top-level workspace selectbox has been removed. Sign out is rendered in the authenticated sidebar and anchored to its footer. The action clears the complete Streamlit session state (including widget state, route state and uploaded-file references) and reruns the app, which returns to the unauthenticated login flow. Session expiry follows the same clear-and-rerun path.

The existing shared-resource caches are intentionally not globally cleared during logout: `st.cache_resource` objects may be shared across users and clearing them on one user's sign-out could disrupt other active sessions. No explicit user-keyed cache invalidation contract was identified in the reviewed app shell. User-specific transient state remains in `st.session_state` and is cleared on sign-out.

Validation in this environment: the focused login/navigation test module passes (11 tests). The full repository suite reports 100 passing tests and 2 failures in pre-existing File Q&A assertions that expect source text absent from the supplied `pages/2_File_QA_Chatbot.py`. A runtime browser test and navigation latency benchmark require the target Streamlit environment and were not claimed here.
