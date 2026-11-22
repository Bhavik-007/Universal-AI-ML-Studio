"""Per-module import dependency validation used before enabling applications."""
from __future__ import annotations

import importlib.util

# Names are Python import names, not necessarily their PyPI distribution names.
# Include dependencies imported by the page's local service modules as well.
MODULE_DEPENDENCIES: dict[str, tuple[str, ...]] = {
    "forecast": ("streamlit", "pandas", "numpy", "plotly", "sklearn"),
    "file_qa": ("streamlit", "pandas", "langchain", "langchain_experimental", "langchain_openai"),
    "api_analyzer": ("streamlit", "requests", "pandas", "langchain", "langchain_experimental", "langchain_openai"),
    "sentiment": ("streamlit", "pandas", "nltk", "transformers", "matplotlib"),
    "finance": ("streamlit", "plotly", "yfinance"),
    "sql_voice": ("streamlit", "openai", "pandas", "pyodbc", "pyttsx3", "speech_recognition", "yaml"),
    "voice_test": ("streamlit", "openai", "pandas", "psycopg2", "pymongo", "pymysql", "pyodbc", "pyttsx3", "speech_recognition"),
    "purchase": ("streamlit", "pandas", "numpy", "sklearn"),
    "mcp": ("streamlit", "requests", "plotly"),
    "fraud": ("streamlit", "pandas", "plotly", "sklearn"),
    "loan_tree": ("streamlit", "pandas", "numpy", "sklearn", "joblib", "matplotlib"),
    "marketing": ("streamlit", "pandas", "requests", "dotenv", "pyodbc", "pypdf", "docx", "PIL"),
    "graphql": ("streamlit", "pandas", "strawberry"),
    "agent_assist": ("streamlit", "ollama", "redis", "dotenv"),
    "market_intelligence": ("streamlit", "pandas", "plotly", "requests", "yfinance"),
    "svm_fraud": ("streamlit", "pandas", "sklearn", "matplotlib", "seaborn"),
    "nlp_sql": ("streamlit", "yaml", "dotenv", "pandas", "sqlalchemy", "pyodbc", "elasticsearch", "sentence_transformers", "langchain_ollama"),
    "rag_sql": ("streamlit", "yaml", "dotenv", "pandas", "sqlalchemy", "pyodbc", "elasticsearch", "sentence_transformers", "langchain_ollama", "pymongo", "pypdf", "docx", "PIL"),
}


def missing_dependencies(module_key: str, declared_dependencies: tuple[str, ...] | None = None) -> tuple[str, ...]:
    missing = []
    packages = declared_dependencies if declared_dependencies is not None else MODULE_DEPENDENCIES.get(module_key, ())
    for package in packages:
        try:
            available = importlib.util.find_spec(package) is not None
        except (ImportError, ModuleNotFoundError, ValueError):
            available = False
        if not available:
            missing.append(package)
    return tuple(missing)


def validate_module_dependencies(module_key: str, declared_dependencies: tuple[str, ...] | None = None) -> tuple[bool, tuple[str, ...]]:
    missing = missing_dependencies(module_key, declared_dependencies)
    return not missing, missing
