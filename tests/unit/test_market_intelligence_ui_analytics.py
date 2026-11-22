from __future__ import annotations

import pandas as pd
import pytest

from universal_ai_studio.applications.market_intelligence.market_analytics import (
    add_technical_indicators,
    support_resistance,
    validate_ohlcv,
    volume_summary,
)

ROOT = __import__('pathlib').Path(__file__).resolve().parents[2]
PACKAGE_DIR = ROOT / "universal_ai_studio" / "applications" / "market_intelligence"


@pytest.fixture
def sample_ohlcv() -> pd.DataFrame:
    timestamps = pd.date_range("2026-01-01", periods=80, freq="D")
    close = pd.Series([100 + i * 0.7 + ((-1) ** i) * 1.5 for i in range(80)])
    return pd.DataFrame({
        "timestamp": timestamps, "open": close - .4, "high": close + 1.2,
        "low": close - 1.1, "close": close,
        "volume": [1000 + i * 10 for i in range(80)],
    })


def test_valid_ohlcv_has_no_issues(sample_ohlcv):
    assert validate_ohlcv(sample_ohlcv) == []


def test_invalid_candle_is_reported(sample_ohlcv):
    sample_ohlcv.loc[3, "high"] = sample_ohlcv.loc[3, "low"] - 1
    assert any("High below Low" in issue for issue in validate_ohlcv(sample_ohlcv))


def test_duplicate_timestamp_is_reported(sample_ohlcv):
    sample_ohlcv.loc[1, "timestamp"] = sample_ohlcv.loc[0, "timestamp"]
    assert any("Duplicate timestamps" in issue for issue in validate_ohlcv(sample_ohlcv))


def test_indicators_are_added(sample_ohlcv):
    result = add_technical_indicators(sample_ohlcv, 10, 25)
    for column in ["sma_fast", "sma_slow", "rsi", "macd", "macd_signal", "macd_histogram"]:
        assert column in result.columns
    assert result["sma_fast"].notna().all()


def test_invalid_sma_windows_raise(sample_ohlcv):
    with pytest.raises(ValueError):
        add_technical_indicators(sample_ohlcv, 30, 20)


def test_support_resistance_and_volume(sample_ohlcv):
    levels = support_resistance(sample_ohlcv, 20)
    volume = volume_summary(sample_ohlcv, 20)
    assert levels["support"] <= levels["resistance"]
    assert volume["latest_volume"] > 0
    assert volume["relative_volume"] > 0


def test_demo_dataset_is_present_and_valid():
    sample = pd.read_csv(PACKAGE_DIR / "sample_data" / "demo_ohlcv.csv", parse_dates=["timestamp"])
    assert len(sample) == 180
    assert validate_ohlcv(sample) == []


def test_integrated_page_delegates_to_namespaced_renderer():
    source = (ROOT / "pages" / "15_Tensor_trade_business" / "app.py").read_text(encoding="utf-8")
    assert "from universal_ai_studio.applications.market_intelligence.render import render" in source
    assert "render()" in source
    assert "login_manager()" not in source
    assert "st.set_page_config" not in source


def test_market_intelligence_does_not_replace_global_platform_sidebar():
    source = (PACKAGE_DIR / "render.py").read_text(encoding="utf-8")
    assert "st.sidebar" not in source
    assert "horizontal=True" in source
    assert "Explore demo data" in source
    assert "Load market data" in source


def test_shared_shell_owns_authentication_and_page_route():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    assert "login_manager()" in source
    assert '"pages/15_Tensor_trade_business/app.py"' in (ROOT / "universal_ai_studio" / "applications" / "registry.py").read_text(encoding="utf-8")
    assert "selected_page.run()" in source
