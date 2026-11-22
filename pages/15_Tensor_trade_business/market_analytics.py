"""Pure market analytics helpers shared by Market Intelligence views."""
from __future__ import annotations

import pandas as pd

REQUIRED_OHLCV = ("timestamp", "open", "high", "low", "close", "volume")


def validate_ohlcv(data: pd.DataFrame) -> list[str]:
    """Return data-quality issues without mutating the input frame."""
    issues: list[str] = []
    if data is None or data.empty:
        return ["No market data is available."]
    missing = [column for column in REQUIRED_OHLCV if column not in data.columns]
    if missing:
        return [f"Missing required columns: {', '.join(missing)}"]
    frame = data.copy()
    if frame["timestamp"].isna().any():
        issues.append("Some rows have invalid timestamps.")
    if frame["timestamp"].duplicated().any():
        issues.append("Duplicate timestamps were found.")
    numeric = ("open", "high", "low", "close", "volume")
    for column in numeric:
        values = pd.to_numeric(frame[column], errors="coerce")
        if values.isna().any():
            issues.append(f"{column.title()} contains missing or non-numeric values.")
    if (pd.to_numeric(frame["volume"], errors="coerce") < 0).any():
        issues.append("Volume contains negative values.")
    if (pd.to_numeric(frame["high"], errors="coerce") < pd.to_numeric(frame["low"], errors="coerce")).any():
        issues.append("One or more candles have High below Low.")
    high = pd.to_numeric(frame["high"], errors="coerce")
    low = pd.to_numeric(frame["low"], errors="coerce")
    open_ = pd.to_numeric(frame["open"], errors="coerce")
    close = pd.to_numeric(frame["close"], errors="coerce")
    if ((high < open_) | (high < close) | (low > open_) | (low > close)).any():
        issues.append("One or more candles have inconsistent OHLC prices.")
    return issues


def add_technical_indicators(
    data: pd.DataFrame,
    fast_window: int = 20,
    slow_window: int = 50,
    rsi_window: int = 14,
) -> pd.DataFrame:
    """Return a copy with SMA, RSI, MACD and rolling volatility columns."""
    if fast_window < 2 or slow_window <= fast_window or rsi_window < 2:
        raise ValueError("Use SMA windows >= 2, Slow SMA greater than Fast SMA, and RSI window >= 2.")
    frame = data.copy()
    close = pd.to_numeric(frame["close"], errors="coerce")
    frame["sma_fast"] = close.rolling(fast_window, min_periods=1).mean()
    frame["sma_slow"] = close.rolling(slow_window, min_periods=1).mean()
    frame["return"] = close.pct_change()
    frame["volatility"] = frame["return"].rolling(20, min_periods=2).std()

    delta = close.diff()
    gain = delta.clip(lower=0).rolling(rsi_window, min_periods=rsi_window).mean()
    loss = (-delta.clip(upper=0)).rolling(rsi_window, min_periods=rsi_window).mean()
    relative_strength = gain / loss.replace(0, pd.NA)
    frame["rsi"] = 100 - (100 / (1 + relative_strength))
    frame.loc[(loss == 0) & (gain > 0), "rsi"] = 100
    frame.loc[(gain == 0) & (loss > 0), "rsi"] = 0
    frame.loc[(gain == 0) & (loss == 0), "rsi"] = 50

    ema_fast = close.ewm(span=12, adjust=False, min_periods=1).mean()
    ema_slow = close.ewm(span=26, adjust=False, min_periods=1).mean()
    frame["macd"] = ema_fast - ema_slow
    frame["macd_signal"] = frame["macd"].ewm(span=9, adjust=False, min_periods=1).mean()
    frame["macd_histogram"] = frame["macd"] - frame["macd_signal"]
    return frame


def support_resistance(data: pd.DataFrame, window: int = 20) -> dict[str, float]:
    """Simple rolling-period support/resistance estimates, not trade advice."""
    if data is None or data.empty:
        raise ValueError("Market data is empty.")
    if window < 2:
        raise ValueError("Window must be at least 2.")
    sample = data.tail(window)
    return {
        "support": float(pd.to_numeric(sample["low"], errors="coerce").min()),
        "resistance": float(pd.to_numeric(sample["high"], errors="coerce").max()),
    }


def volume_summary(data: pd.DataFrame, window: int = 20) -> dict[str, float]:
    if data is None or data.empty:
        raise ValueError("Market data is empty.")
    volume = pd.to_numeric(data["volume"], errors="coerce")
    latest = float(volume.iloc[-1])
    average = float(volume.tail(window).mean())
    return {
        "latest_volume": latest,
        "average_volume": average,
        "relative_volume": latest / average if average > 0 else 0.0,
    }
