import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_nlp_apps_use_distinct_import_package_names():
    sql_root = str(ROOT / "pages" / "17_NLP-to-SQL")
    rag_root = str(ROOT / "pages" / "18_NLP-to-SQL_RAG_App")
    for path in (rag_root, sql_root):
        if path not in sys.path:
            sys.path.insert(0, path)
    sql_config = importlib.import_module("nlp_to_sql_app.core.config")
    rag_config = importlib.import_module("nlp_to_sql_rag_app.core.config")
    assert sql_config.__name__ != rag_config.__name__
    assert sql_config.__package__.startswith("nlp_to_sql_app")
    assert rag_config.__package__.startswith("nlp_to_sql_rag_app")


def test_registered_nlp_page_paths_use_unique_package_names():
    from universal_ai_studio.applications import registry
    assert registry.get("nlp_sql").path.endswith("nlp_to_sql_app/ui/main.py")
    assert registry.get("rag_sql").path.endswith("nlp_to_sql_rag_app/ui/main.py")


def test_market_intelligence_uses_a_unique_service_package():
    import importlib
    module_root = str(ROOT / "pages" / "15_Tensor_trade_business")
    if module_root not in sys.path:
        sys.path.insert(0, module_root)
    package = importlib.import_module("market_intelligence_services")
    assert package.__name__ == "market_intelligence_services"


def test_svm_fraud_uses_a_namespaced_helper_package():
    import importlib
    module_root = str(ROOT / "pages" / "16_SVM_fraud_detection")
    if module_root not in sys.path:
        sys.path.insert(0, module_root)
    package = importlib.import_module("svm_fraud")
    assert package.__name__ == "svm_fraud"
