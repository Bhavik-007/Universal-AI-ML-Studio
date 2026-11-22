from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_tabulate_is_declared_for_dataframe_agent():
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    assert "tabulate>=0.9,<1.0" in requirements


def test_file_qa_uses_shared_dataframe_agent_factory():
    source = (ROOT / "pages" / "2_File_QA_Chatbot.py").read_text(encoding="utf-8")
    assert "create_dataframe_agent(" in source
    assert "Your file was loaded successfully, but the Q&A assistant" in source
    assert "Failed to read file" in source
