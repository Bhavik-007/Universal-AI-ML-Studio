"""Render Market Intelligence inside the Universal AI Studio application shell.

Authentication, page configuration and global navigation are owned by app.py.
This module owns only Market Intelligence content and never creates a second
platform sidebar or a second login flow.
"""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from universal_ai_studio.applications.market_intelligence.market_analytics import (
    add_technical_indicators,
    support_resistance,
    validate_ohlcv,
    volume_summary,
)
from universal_ai_studio.applications.market_intelligence.market_intelligence_services.market_data import YahooMarketData
from universal_ai_studio.applications.market_intelligence.market_intelligence_services.tensortrade_adapter import get_tensortrade_runtime_status
from universal_ai_studio.applications.market_intelligence.ui_components import (
    inject_design_system,
    page_header,
    section_heading,
)

logger = logging.getLogger(__name__)
PACKAGE_DIR = Path(__file__).resolve().parent
VIEWS = [
    "Market Overview",
    "Technical Analysis",
    "Price & Volume",
    "Historical Data & Export",
    "Data Quality",
]


@st.cache_resource
def get_market_service() -> YahooMarketData:
    return YahooMarketData()


@st.cache_data(ttl=300, show_spinner=False)
def load_market_frame(query: str, period: str, interval: str) -> tuple[pd.DataFrame, dict]:
    service = get_market_service()
    resolution = service.resolve_ticker(query)
    if not resolution.success:
        raise ValueError(resolution.error or "The instrument could not be resolved.")
    ticker = str(resolution.context.get("ticker") or "").strip().upper()
    if not ticker:
        raise ValueError("Ticker resolution returned an empty ticker.")
    result = service.get_history(ticker=ticker, period=period, interval=interval)
    if not result.success or result.data is None or result.data.empty:
        raise RuntimeError(result.error or "The data provider returned no historical prices.")
    normalized = service.normalize_ohlcv(result.data)
    if normalized.empty:
        raise ValueError("The returned market data could not be normalized to OHLCV.")
    return normalized, {
        **resolution.context,
        **result.context,
        "ticker": ticker,
        "company_name": resolution.context.get("company_name") or query,
    }


def _chart(frame: pd.DataFrame, *, title: str, include_volume: bool = True) -> None:
    if include_volume:
        fig = make_subplots(
            rows=2, cols=1, shared_xaxes=True, vertical_spacing=.055,
            row_heights=[.76, .24],
        )
        fig.add_trace(go.Candlestick(
            x=frame["timestamp"], open=frame["open"], high=frame["high"],
            low=frame["low"], close=frame["close"], name="OHLC",
        ), row=1, col=1)
        for key, label in (("sma_fast", "Fast SMA"), ("sma_slow", "Slow SMA")):
            if key in frame:
                fig.add_trace(go.Scatter(x=frame["timestamp"], y=frame[key], name=label), row=1, col=1)
        fig.add_trace(go.Bar(x=frame["timestamp"], y=frame["volume"], name="Volume", opacity=.5), row=2, col=1)
        fig.update_yaxes(title_text="Price", row=1, col=1)
        fig.update_yaxes(title_text="Volume", row=2, col=1)
    else:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=frame["timestamp"], y=frame["close"], name="Close"))
        for key, label in (("sma_fast", "Fast SMA"), ("sma_slow", "Slow SMA")):
            if key in frame:
                fig.add_trace(go.Scatter(x=frame["timestamp"], y=frame[key], name=label))
    fig.update_layout(
        title=title, template="plotly_white", height=470, autosize=True,
        hovermode="x unified", xaxis_rangeslider_visible=False,
        margin=dict(l=12, r=12, t=58, b=18),
        legend=dict(orientation="h", y=1.08, x=.5, xanchor="center"),
    )
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(showgrid=True, gridcolor="#edf1f6", zeroline=False)
    st.plotly_chart(fig, use_container_width=True, config={"responsive": True, "displaylogo": False})


def _set_demo() -> None:
    st.session_state.update({
        "mi_demo_mode": True,
        "mi_query": "",
        "mi_period": "6mo",
        "mi_interval": "1d",
        "mi_fast": 20,
        "mi_slow": 50,
        "mi_data_requested": True,
    })


def render() -> None:
    inject_design_system()
    page_header(
        "Enterprise Market Intelligence",
        "Explore market movements, technical indicators and historical OHLCV data. Research only — no broker connection or order execution.",
        "Universal AI Studio · Analytics",
    )

    # Feature navigation lives in the page content. The persistent platform
    # sidebar remains exclusively owned by st.navigation in the app shell.
    selected_view = st.radio(
        "Market Intelligence sections", VIEWS, horizontal=True,
        label_visibility="collapsed", key="mi_view_selector",
    )

    with st.container(border=True):
        section_heading("Instrument & analysis controls", "Load live NSE market data or explore the bundled synthetic demonstration dataset.", "⌕")
        with st.form("mi_market_controls", clear_on_submit=False):
            c1, c2, c3 = st.columns([3.2, 1, 1])
            with c1:
                query_input = st.text_input(
                    "Company / NSE ticker", value=st.session_state.get("mi_query", ""),
                    placeholder="TCS, INFY, RELIANCE or Tata Consultancy Services",
                    disabled=bool(st.session_state.get("mi_demo_mode", False)),
                    help="Enter an NSE-listed company name or ticker. Example: TCS.",
                )
            with c2:
                period_input = st.selectbox("History period", ["1d", "5d", "1mo", "3mo", "6mo", "1y", "2y"], index=4)
            with c3:
                interval_input = st.selectbox("Candle interval", ["1m", "5m", "15m", "30m", "60m", "1h", "1d"], index=6)
            s1, s2, s3 = st.columns([1, 1, 1.3])
            with s1:
                fast_input = st.number_input("Fast SMA", min_value=2, max_value=200, value=int(st.session_state.get("mi_fast", 20)))
            with s2:
                slow_input = st.number_input("Slow SMA", min_value=3, max_value=300, value=int(st.session_state.get("mi_slow", 50)))
            with s3:
                st.markdown("<div style='height:1.75rem'></div>", unsafe_allow_html=True)
                load_clicked = st.form_submit_button("Load market data", type="primary", use_container_width=True)

        action_demo, action_clear, source_col = st.columns([1.25, .8, 2.2])
        with action_demo:
            if st.button("Explore demo data", use_container_width=True):
                _set_demo()
                st.rerun()
        with action_clear:
            if st.button("Clear", use_container_width=True):
                for key in ("mi_data_requested", "mi_demo_mode", "mi_query", "mi_loaded_frame", "mi_loaded_meta"):
                    st.session_state.pop(key, None)
                st.rerun()
        with source_col:
            st.caption("Demo records are synthetic and are clearly labelled. Live data requires internet access to Yahoo Finance.")

    if load_clicked:
        if fast_input >= slow_input:
            st.error("Fast SMA must be smaller than Slow SMA.")
        elif not query_input.strip():
            st.warning("Enter an NSE company/ticker or choose Explore demo data.")
        else:
            st.session_state.update({
                "mi_demo_mode": False, "mi_query": query_input.strip(),
                "mi_period": period_input, "mi_interval": interval_input,
                "mi_fast": int(fast_input), "mi_slow": int(slow_input),
                "mi_data_requested": True,
            })
            st.rerun()

    if not st.session_state.get("mi_data_requested", False):
        with st.container(border=True):
            section_heading("Start exploring market data", "You can preview every section immediately using the bundled sample dataset.", "▦")
            st.info("Select **Explore demo data** to load 180 synthetic daily candles, or enter an NSE company/ticker and select **Load market data**.")
            st.markdown("**Available views** · Market Overview · Technical Analysis · Price & Volume · Historical Data & Export · Data Quality")
        return

    demo_mode = bool(st.session_state.get("mi_demo_mode", False))
    query = str(st.session_state.get("mi_query", ""))
    period = str(st.session_state.get("mi_period", "6mo"))
    interval = str(st.session_state.get("mi_interval", "1d"))
    fast_window = int(st.session_state.get("mi_fast", 20))
    slow_window = int(st.session_state.get("mi_slow", 50))

    try:
        if demo_mode:
            demo_path = PACKAGE_DIR / "sample_data" / "demo_ohlcv.csv"
            base_frame = pd.read_csv(demo_path, parse_dates=["timestamp"])
            metadata = {
                "ticker": "DEMO.NS", "company_name": "Synthetic demonstration dataset",
                "exchange": "Sample data", "source": "Synthetic demonstration data",
            }
            source_label = "Synthetic demonstration data · not live market data"
        else:
            with st.spinner(f"Loading {query} from Yahoo Finance…"):
                base_frame, metadata = load_market_frame(query, period, interval)
            source_label = "Yahoo Finance"
        issues = validate_ohlcv(base_frame)
        if issues:
            st.warning("Data quality checks found issues. Review the Data Quality section before using exports.")
        frame = add_technical_indicators(base_frame, fast_window, slow_window)
        levels = support_resistance(frame)
        volume = volume_summary(frame)
        latest = frame.iloc[-1]
        first_close, last_close = float(frame["close"].iloc[0]), float(latest["close"])
        change_pct = ((last_close / first_close) - 1) * 100 if first_close else 0.0
        ticker = str(metadata.get("ticker", "DEMO.NS" if demo_mode else query.upper()))
        instrument = str(metadata.get("company_name", query or "Synthetic demonstration dataset"))
    except Exception as exc:
        logger.exception("Market Intelligence data load failed")
        st.error("Market data could not be loaded. Check the ticker, selected period, network access and Yahoo Finance availability.")
        with st.expander("Technical details"):
            st.code(f"{type(exc).__name__}: {exc}")
        return

    st.caption(f"**{instrument} ({ticker})** · {source_label} · {len(frame):,} rows · Latest candle: {latest['timestamp']}")

    if selected_view == "Market Overview":
        section_heading("Market snapshot", "Summary values are calculated from the selected historical window.", "▦")
        cols = st.columns(4)
        cols[0].metric("Last close", f"{last_close:,.2f}")
        cols[1].metric("Period change", f"{change_pct:+.2f}%")
        cols[2].metric("Period high", f"{frame['high'].max():,.2f}")
        cols[3].metric("Period low", f"{frame['low'].min():,.2f}")
        _chart(frame, title=f"{ticker} · Price, moving averages and volume")
        c1, c2, c3 = st.columns(3)
        c1.metric("Trend", "Bullish" if latest["sma_fast"] > latest["sma_slow"] else "Bearish" if latest["sma_fast"] < latest["sma_slow"] else "Neutral")
        c2.metric("Relative volume", f"{volume['relative_volume']:.2f}×")
        c3.metric("Data source", "Synthetic demo" if demo_mode else "Yahoo Finance")

    elif selected_view == "Technical Analysis":
        section_heading("Technical indicators", "Indicators are descriptive calculations, not investment recommendations.", "⌁")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric(f"SMA {fast_window}", f"{latest['sma_fast']:,.2f}")
        c2.metric(f"SMA {slow_window}", f"{latest['sma_slow']:,.2f}")
        c3.metric("RSI (14)", f"{latest['rsi']:.1f}" if pd.notna(latest["rsi"]) else "N/A")
        c4.metric("MACD", f"{latest['macd']:.3f}")
        _chart(frame, title=f"{ticker} · Moving averages", include_volume=False)
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=frame["timestamp"], y=frame["rsi"], name="RSI (14)"))
        fig.add_hline(y=70, line_dash="dash", line_color="#c43d4b")
        fig.add_hline(y=30, line_dash="dash", line_color="#138a56")
        fig.update_layout(title="Relative Strength Index", template="plotly_white", height=300, margin=dict(l=12, r=12, t=48, b=12))
        st.plotly_chart(fig, use_container_width=True, config={"responsive": True})
        st.caption(f"MACD latest: {latest['macd']:.4f} · Signal: {latest['macd_signal']:.4f} · Support: {levels['support']:.2f} · Resistance: {levels['resistance']:.2f}")

    elif selected_view == "Price & Volume":
        section_heading("Price action and volume", "Candlestick ranges and volume help describe historical market behaviour.", "▥")
        _chart(frame, title=f"{ticker} · Candlestick and volume")
        a, b, c = st.columns(3)
        a.metric("Latest volume", f"{volume['latest_volume']:,.0f}")
        b.metric("20-period average", f"{volume['average_volume']:,.0f}")
        c.metric("Relative volume", f"{volume['relative_volume']:.2f}×")

    elif selected_view == "Historical Data & Export":
        section_heading("Historical OHLCV records", "Download the normalized historical candles or a TensorTrade-compatible OHLCV file.", "▤")
        display_cols = ["timestamp", "open", "high", "low", "close", "volume", "sma_fast", "sma_slow"]
        st.dataframe(frame[display_cols].tail(250), use_container_width=True, hide_index=True)
        st.download_button("Download OHLCV + indicators", frame[display_cols].to_csv(index=False).encode("utf-8"), file_name=f"{ticker}_ohlcv_indicators.csv", mime="text/csv")
        export_frame = get_market_service().tensortrade_ohlcv(frame)
        export_issues = validate_ohlcv(export_frame)
        if export_issues:
            st.warning("TensorTrade-format export is disabled until OHLCV validation passes: " + "; ".join(export_issues))
        else:
            st.download_button("Download TensorTrade-ready OHLCV", export_frame.to_csv(index=False).encode("utf-8"), file_name=f"{ticker}_tensortrade_ohlcv.csv", mime="text/csv")
        runtime = get_tensortrade_runtime_status()
        st.caption("TensorTrade package: installed" if runtime.installed else "TensorTrade package: not installed. This export is a data-format handoff only; it does not run a simulator or trading agent.")

    else:
        section_heading("Data quality diagnostics", "Review source completeness and OHLCV consistency before exporting or using the data downstream.", "✓")
        quality = validate_ohlcv(base_frame)
        q1, q2, q3, q4 = st.columns(4)
        q1.metric("Rows", f"{len(base_frame):,}")
        q2.metric("Missing values", f"{int(base_frame.isna().sum().sum()):,}")
        q3.metric("Duplicate timestamps", f"{int(base_frame['timestamp'].duplicated().sum()):,}")
        q4.metric("OHLCV checks", "PASS" if not quality else "REVIEW")
        if quality:
            for issue in quality:
                st.warning(issue)
        else:
            st.success("No OHLCV validation issues were detected.")
        st.caption(f"Source: {source_label} · Ticker: {ticker} · Latest timestamp: {latest['timestamp']}")

    st.caption("Market research and data analysis only. No investment advice, broker connection, order placement or trading execution.")
