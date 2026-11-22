"""Shared LangChain DataFrame-agent factory.

All application modules that ask an LLM to analyze pandas DataFrames should
use this factory so optional dependencies and initialization errors are
handled consistently.
"""
from __future__ import annotations

from typing import Any


class DataFrameAgentDependencyError(RuntimeError):
    """Raised when a dependency required for DataFrame-agent output is absent."""


def create_dataframe_agent(
    llm: Any,
    dataframe: Any,
    *,
    memory: Any = None,
    verbose: bool = False,
    allow_dangerous_code: bool = True,
) -> Any:
    """Create a LangChain pandas DataFrame agent with a consistent dependency check."""
    try:
        import tabulate  # noqa: F401 - required by LangChain's DataFrame prompt rendering
    except ImportError as exc:
        raise DataFrameAgentDependencyError(
            "The AI DataFrame analysis feature requires 'tabulate'. "
            "Install the platform dependencies with "
            "`python -m pip install -r requirements.txt`, then restart the app."
        ) from exc

    try:
        from langchain_experimental.agents import create_pandas_dataframe_agent
    except ImportError:
        try:
            from langchain.agents import create_pandas_dataframe_agent
        except ImportError as exc:
            raise DataFrameAgentDependencyError(
                "The LangChain pandas DataFrame agent is unavailable. "
                "Install the platform dependencies with "
                "`python -m pip install -r requirements.txt`."
            ) from exc

    kwargs = {
        "verbose": verbose,
        "allow_dangerous_code": allow_dangerous_code,
    }
    if memory is not None:
        kwargs["memory"] = memory

    return create_pandas_dataframe_agent(llm, dataframe, **kwargs)
