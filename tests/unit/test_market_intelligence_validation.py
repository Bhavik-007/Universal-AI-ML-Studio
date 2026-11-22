from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
MODULE_DIR = ROOT / "pages" / "15_Tensor_trade_business"


def _load_market_data_module():
    sys.path.insert(0, str(MODULE_DIR))
    sys.modules.setdefault("yfinance", types.SimpleNamespace())
    module_path = MODULE_DIR / "market_intelligence_services" / "market_data.py"
    spec = importlib.util.spec_from_file_location("uas_market_data_test_module", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def valid_ohlcv(rows: int = 3) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01", periods=rows, freq="D"),
            "open": [100.0] * rows,
            "high": [105.0] * rows,
            "low": [95.0] * rows,
            "close": [102.0] * rows,
            "volume": [1000] * rows,
        }
    )


def test_valid_ohlcv_exports_in_required_order():
    module = _load_market_data_module()
    service = module.YahooMarketData()
    source = valid_ohlcv()
    source["extra"] = "ignored"
    result = service.tensortrade_ohlcv(source)
    assert list(result.columns) == ["timestamp", "open", "high", "low", "close", "volume"]
    assert result["timestamp"].is_monotonic_increasing


def test_invalid_ohlcv_is_rejected_before_export():
    module = _load_market_data_module()
    service = module.YahooMarketData()
    source = valid_ohlcv()
    source.loc[1, "high"] = 90.0
    report = service.validate_ohlcv(source)
    assert report["valid"] is False
    assert any("High must be" in issue for issue in report["issues"])
    with pytest.raises(ValueError, match="OHLCV validation failed"):
        service.tensortrade_ohlcv(source)


def test_duplicate_timestamps_and_negative_volume_are_rejected():
    module = _load_market_data_module()
    service = module.YahooMarketData()
    source = valid_ohlcv()
    source.loc[1, "timestamp"] = source.loc[0, "timestamp"]
    source.loc[2, "volume"] = -1
    report = service.validate_ohlcv(source)
    assert report["valid"] is False
    assert any("Duplicate timestamps" in issue for issue in report["issues"])
    assert any("Volume cannot be negative" in issue for issue in report["issues"])


def test_bundled_demo_dataset_is_valid_and_explicitly_synthetic():
    module = _load_market_data_module()
    service = module.YahooMarketData()
    sample_path = MODULE_DIR / "sample_data" / "demo_ohlcv.csv"
    sample = pd.read_csv(sample_path, parse_dates=["timestamp"])
    report = service.validate_ohlcv(sample)
    assert report["valid"] is True
    assert report["rows"] == 180
    assert "demo" in sample_path.name


def test_every_builtin_application_has_contextual_guidance():
    import ast
    guidance_path = ROOT / "universal_ai_studio" / "ui" / "guidance.py"
    tree = ast.parse(guidance_path.read_text(encoding="utf-8"))
    assignment = next(node for node in tree.body if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "GUIDANCE" for t in node.targets))
    guidance = ast.literal_eval(assignment.value)
    registry_source = (ROOT / "universal_ai_studio" / "applications" / "registry.py").read_text(encoding="utf-8")
    keys = set()
    for node in ast.walk(ast.parse(registry_source)):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "Application" and node.args and isinstance(node.args[0], ast.Constant):
            keys.add(node.args[0].value)
    assert keys <= set(guidance)


def test_normalization_preserves_duplicate_timestamps_for_diagnostics():
    module = _load_market_data_module()
    service = module.YahooMarketData()
    source = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(["2026-01-01", "2026-01-01"]),
            "Open": [100, 101],
            "High": [105, 106],
            "Low": [95, 96],
            "Close": [102, 103],
            "Volume": [1000, 1100],
        }
    )
    normalized = service.normalize_ohlcv(source)
    assert len(normalized) == 2
    assert service.validate_ohlcv(normalized)["valid"] is False
