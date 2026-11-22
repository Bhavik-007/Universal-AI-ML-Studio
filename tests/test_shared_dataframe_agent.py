from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_all_dataframe_agent_call_sites_use_shared_factory():
    file_qa = (ROOT / "pages" / "2_File_QA_Chatbot.py").read_text(encoding="utf-8")
    api_analyzer = (ROOT / "pages" / "3_API_Analyzer.py").read_text(encoding="utf-8")
    assert "create_dataframe_agent(" in file_qa
    assert "create_dataframe_agent(" in api_analyzer
    assert "create_pandas_dataframe_agent(" not in file_qa
    assert "create_pandas_dataframe_agent(" not in api_analyzer


def test_shared_factory_checks_tabulate_and_reports_install_command():
    factory = (ROOT / "universal_ai_studio" / "ai_platform" / "dataframe_agent.py").read_text(encoding="utf-8")
    assert "import tabulate" in factory
    assert "pip install -r requirements.txt" in factory


def test_api_analyzer_does_not_misreport_agent_failure_as_request_failure():
    source = (ROOT / "pages" / "3_API_Analyzer.py").read_text(encoding="utf-8")
    assert "The API request succeeded and its response is displayed" in source
