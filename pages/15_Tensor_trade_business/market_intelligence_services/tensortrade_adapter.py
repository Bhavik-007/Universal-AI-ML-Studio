"""Optional TensorTrade runtime diagnostics.

The current Market Intelligence application exports validated OHLCV data only.
It intentionally does not claim to construct environments, train agents, backtest
strategies or execute orders.
"""
from __future__ import annotations

import importlib.util
from dataclasses import dataclass


@dataclass(frozen=True)
class TensorTradeRuntimeStatus:
    installed: bool
    package_name: str = "tensortrade"
    supported_workflows: tuple[str, ...] = ("validated OHLCV preparation and CSV export",)
    unavailable_workflows: tuple[str, ...] = (
        "TensorTrade environment construction",
        "reinforcement-learning agent training",
        "strategy backtesting and order execution",
    )


def get_tensortrade_runtime_status() -> TensorTradeRuntimeStatus:
    """Report whether the optional TensorTrade package is importable."""
    try:
        installed = importlib.util.find_spec("tensortrade") is not None
    except (ImportError, ValueError):
        installed = False
    return TensorTradeRuntimeStatus(installed=installed)
