"""Central catalogue for all Streamlit applications in the workspace."""
from __future__ import annotations

from dataclasses import dataclass
import json
import re
from pathlib import Path
import tempfile

from universal_ai_studio.core.configuration import load_platform_config
from universal_ai_studio.core.feature_manager import is_feature_enabled

ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Application:
    key: str
    name: str
    path: str
    category: str
    status: str = "registered"
    required_permission: str = "applications.use"
    default_enabled: bool = True
    discovered: bool = False
    dependencies: tuple[str, ...] = ()
    icon: str = "🧰"
    description: str = "Open this registered application workspace."
    sort_order: int = 100

    @property
    def url_path(self) -> str:
        return self.key

    @property
    def available(self) -> bool:
        target = (ROOT / self.path).resolve()
        return target.is_relative_to(ROOT) and target.is_file() and target.suffix.lower() == ".py"

    @property
    def enabled(self) -> bool:
        return is_feature_enabled(self.key, default=self.default_enabled)


class ApplicationRegistry:
    def __init__(self) -> None:
        self._applications: dict[str, Application] = {}
        self._discovered_keys: set[str] = set()
        self.manifest_errors: list[str] = []

    def register(self, application: Application) -> None:
        if application.key in self._applications:
            raise ValueError(f"Duplicate application key: {application.key}")
        if not re.fullmatch(r"[a-z][a-z0-9_]{1,63}", application.key):
            raise ValueError(f"Invalid application key: {application.key}")
        target = (ROOT / application.path).resolve()
        if not target.is_relative_to(ROOT):
            raise ValueError("Application entry point must be inside the repository root.")
        if any(existing.path == application.path for existing in self._applications.values()):
            raise ValueError(f"Application path is already registered: {application.path}")
        self._applications[application.key] = application

    def register_manifest(self, *, key: str, name: str, path: str, category: str = "Custom", required_permission: str = "applications.use", dependencies: tuple[str, ...] = ()) -> Application:
        """Register an existing, repository-local Streamlit page using a JSON manifest."""
        if not re.fullmatch(r"[a-z][a-z0-9_]{1,63}", key):
            raise ValueError("Module key must start with a lowercase letter and contain only lowercase letters, digits or underscores.")
        if not name.strip() or len(name) > 100:
            raise ValueError("Module name must contain 1–100 characters.")
        relative = Path(path.replace("\\", "/"))
        if relative.is_absolute() or ".." in relative.parts or relative.suffix.lower() != ".py" or not relative.parts or relative.parts[0].lower() != "pages":
            raise ValueError("Entry point must be a relative Python file path under the repository pages/ directory.")
        if any(not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]*", item) for item in dependencies):
            raise ValueError("Dependency names may contain only letters, numbers, dots, underscores and hyphens.")
        target = (ROOT / relative).resolve()
        if not target.is_relative_to(ROOT) or not target.is_file():
            raise ValueError("The selected Python entry point does not exist inside the repository.")
        application = Application(key=key, name=name.strip(), path=relative.as_posix(), category=category.strip() or "Custom", status="discovered", required_permission=required_permission, default_enabled=False, discovered=True, dependencies=tuple(sorted(set(("streamlit",) + tuple(dependencies)))), icon="🧩", description="Custom application registered from the module catalogue.")
        if key in self._applications:
            raise ValueError(f"Duplicate application key: {key}")
        if any(existing.path == application.path for existing in self._applications.values()):
            raise ValueError(f"Application path is already registered: {application.path}")
        manifest_dir = ROOT / "config" / "modules"
        manifest_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = manifest_dir / f"{key}.json"
        if manifest_path.exists():
            raise ValueError(f"A module manifest already exists for '{key}'.")
        payload = {"key": key, "name": application.name, "path": application.path, "category": application.category, "required_permission": required_permission, "dependencies": list(application.dependencies)}
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=manifest_dir, prefix=f".{key}.", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(payload, stream, indent=2)
            stream.flush()
        temporary.replace(manifest_path)
        self.refresh_discovered()
        return self._applications[key]

    def refresh_discovered(self) -> None:
        """Reload trusted module manifests; no Python code is executed during discovery."""
        for key in self._discovered_keys:
            self._applications.pop(key, None)
        self._discovered_keys.clear()
        self.manifest_errors.clear()
        manifest_dir = ROOT / "config" / "modules"
        if not manifest_dir.is_dir():
            return
        for manifest_path in sorted(manifest_dir.glob("*.json")):
            try:
                data = json.loads(manifest_path.read_text(encoding="utf-8"))
                application = Application(
                    key=str(data["key"]), name=str(data["name"]), path=str(data["path"]),
                    category=str(data.get("category", "Custom")), status="discovered",
                    required_permission=str(data.get("required_permission", "applications.use")),
                    default_enabled=False, discovered=True,
                    dependencies=tuple(data.get("dependencies", ["streamlit"])),
                    icon=str(data.get("icon", "🧩")),
                    description=str(data.get("description", "Custom application registered from the module catalogue.")),
                )
                if manifest_path.stem != application.key:
                    raise ValueError("Manifest filename must match its module key.")
                relative = Path(application.path)
                if relative.is_absolute() or ".." in relative.parts or not relative.parts or relative.parts[0].lower() != "pages":
                    raise ValueError("Manifest entry point must be a relative path under pages/.")
                if not isinstance(data.get("dependencies", ["streamlit"]), list) or any(not isinstance(item, str) for item in data.get("dependencies", ["streamlit"])):
                    raise ValueError("Manifest dependencies must be a list of Python import names.")
                if application.key in self._applications:
                    raise ValueError(f"Duplicate application key: {application.key}")
                if not re.fullmatch(r"[a-z][a-z0-9_]{1,63}", application.key):
                    raise ValueError("Invalid module key in manifest.")
                if not application.available:
                    raise ValueError("Manifest entry point is missing or outside the repository.")
                if any(existing.path == application.path for existing in self._applications.values()):
                    raise ValueError("Manifest entry point is already registered.")
                self._applications[application.key] = application
                self._discovered_keys.add(application.key)
            except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
                self.manifest_errors.append(f"{manifest_path.name}: {exc}")
                continue

    def list(self, *, enabled_only: bool = False, available_only: bool = False) -> tuple[Application, ...]:
        """Return a consistent catalogue snapshot with one config read per call."""
        self.refresh_discovered()
        applications = tuple(self._applications.values())
        if enabled_only:
            # Avoid re-reading/parsing platform.json once for every registered app.
            features = load_platform_config().get("features", {})
            applications = tuple(
                app for app in applications
                if bool(features.get(app.key, app.default_enabled))
            )
        if available_only:
            applications = tuple(app for app in applications if app.available)
        return tuple(sorted(applications, key=lambda app: (app.sort_order, app.name.casefold())))

    def get(self, key: str) -> Application | None:
        self.refresh_discovered()
        return self._applications.get(key)


registry = ApplicationRegistry()
_BUILTIN_APPLICATIONS = (
    Application("forecast", "Forecast Model", "pages/1_Forecast_Model.py", "Analytics", icon="📈", description="Build forecasts, compare scenarios and review prediction outputs.", sort_order=10),
    Application("file_qa", "CSV / Excel Q&A", "pages/2_File_QA_Chatbot.py", "Documents", icon="📄", description="Upload spreadsheets and ask questions across tabular data.", sort_order=20),
    Application("api_analyzer", "API Analyzer", "pages/3_API_Analyzer.py", "Integrations", icon="🔌", description="Inspect API endpoints, requests, responses and schemas.", sort_order=30),
    Application("sentiment", "Customer Sentiment Analysis", "pages/4_Customer_Sentiment_Analysis.py", "Analytics", icon="💬", description="Analyze customer feedback, sentiment and intent.", sort_order=40),
    Application("finance", "Finance Dashboard", "pages/5_Finance_dashboard.py", "Analytics", icon="💹", description="Explore financial indicators, metrics and dashboard insights.", sort_order=50),
    Application("sql_voice", "SQL Voice Chatbot", "pages/6_SQL_Voice_Chatbot.py", "Data", icon="🗄️", description="Query structured data using natural language and voice.", sort_order=60),
    Application("voice_test", "Voice Test", "pages/7_Voice_test.py", "Voice", icon="🎙️", description="Test speech recognition and voice interaction workflows.", sort_order=70),
    Application("purchase", "Universal Purchase Predictor", "pages/8_Universal_Purchase_Predictor.py", "Analytics", icon="🛒", description="Explore purchase propensity and prediction workflows.", sort_order=80),
    Application("mcp", "MCP Explorer", "pages/9_MCP_Model.py", "Platform Tools", icon="🧩", description="Browse repository structure and inspect application components (legacy explorer).", sort_order=90),
    Application("fraud", "Card Fraud Detection", "pages/10_Card_Fraud_Detection.py", "Risk", icon="🛡️", description="Review card transaction fraud detection workflows.", sort_order=100),
    Application("loan_tree", "Loan Decision Tree", "pages/11_Decision_tree.py", "Risk", icon="🌳", description="Explore decision-tree based loan decision workflows.", sort_order=110),
    Application("marketing", "Marketing Campaign Studio", "pages/12_marketing_campaign_studio/app.py", "Marketing", icon="📣", description="Create campaign content, review audiences and manage email campaign delivery.", sort_order=120),
    Application("graphql", "GraphQL Explorer", "pages/13_GraphQL_API/app.py", "Integrations", icon="🔗", description="Explore GraphQL schema, queries and data operations.", sort_order=130),
    Application("agent_assist", "Agent Assist", "pages/14_Fast_API_Intent_detaction/app.py", "AI", icon="🤖", description="Analyze intent and sentiment for assisted service workflows.", sort_order=140),
    Application("market_intelligence", "Market Intelligence", "pages/15_Tensor_trade_business/app.py", "Analytics", icon="📊", description="Explore market signals and technical analysis workflows.", sort_order=150),
    Application("svm_fraud", "SVM Fraud Detection", "pages/16_SVM_fraud_detection/app.py", "Risk", icon="🔐", description="Run SVM-based supervised and unsupervised fraud analysis.", sort_order=160),
    Application("nlp_sql", "NLP-to-SQL", "pages/17_NLP-to-SQL/nlp_to_sql_app/ui/main.py", "Data", icon="🧠", description="Translate natural-language questions into governed SQL queries.", sort_order=170),
    Application("rag_sql", "NLP-to-SQL + Document RAG", "pages/18_NLP-to-SQL_RAG_App/nlp_to_sql_rag_app/ui/main.py", "Data", icon="🔎", description="Combine natural-language SQL with document retrieval and RAG.", sort_order=180),
)
for _app in _BUILTIN_APPLICATIONS:
    registry.register(_app)
