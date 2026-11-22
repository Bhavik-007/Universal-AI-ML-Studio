from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_file_qa_logo_is_resolved_relative_to_page_file():
    source = (ROOT / "pages/2_File_QA_Chatbot.py").read_text(encoding="utf-8")
    assert 'Path(__file__).resolve().parents[1] / "assets" / "01_firstwatchlogo.jpg"' in source
    assert "logo_path.is_file()" in source


def test_entrypoint_reuses_one_application_catalogue_snapshot():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    assert source.count("registry.list(enabled_only=True, available_only=True)") == 1
    assert "for item in applications:" in source


def test_registry_reads_feature_config_once_for_enabled_filtering():
    source = (ROOT / "universal_ai_studio/applications/registry.py").read_text(encoding="utf-8")
    assert 'features = load_platform_config().get("features", {})' in source
    assert 'features.get(app.key, app.default_enabled)' in source
