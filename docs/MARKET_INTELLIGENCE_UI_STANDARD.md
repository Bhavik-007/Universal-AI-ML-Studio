# Market Intelligence UI Standard

## Navigation model

Market Intelligence is a workspace inside Universal AI Studio. The platform-level left sidebar navigation remains owned by the Universal AI Studio entry point. Market Intelligence feature navigation and shared instrument controls are grouped below the platform route tree in the same collapsible sidebar, avoiding a second independent navigation rail.

Feature views are:

1. Market Overview
2. Technical Analysis
3. Price & Volume
4. Historical Data & Export
5. Data Quality

The sidebar also exposes a direct return action to the main dashboard. Feature selection uses Streamlit session state, so the selected instrument, interval, period and moving-average windows are retained while users move between views.

## Shared layout contract

All Market Intelligence views import the same `ui_components.py` design system. Do not define per-view content widths, card radii, typography or chart heights.

| Element | Shared rule |
|---|---|
| Main content maximum width | 1440px |
| Main content padding | `1.25rem clamp(1rem, 2vw, 2rem) 2.5rem` |
| Header minimum height | 126px on desktop; content-driven on narrow screens |
| Metric card minimum height | 116px |
| Card and panel radius | 14px |
| Chart height | 470px |
| History table height | 470px |
| Data-quality table height | 360px |
| Section heading minimum height | 30px |
| Responsive breakpoint | 900px |

The sidebar is provided by Streamlit and can be collapsed using its native control. Charts use responsive Plotly configuration and fill their parent container. Tables have explicit viewport heights to reduce layout movement when row counts vary.

## Shared data workflow

- Live mode resolves the company/ticker through the existing Yahoo/NSE market-data service and retrieves historical OHLCV.
- Demonstration mode loads `sample_data/demo_ohlcv.csv`, a bundled 180-row synthetic dataset. It is explicitly labelled as synthetic and never presented as live market data.
- Both modes use the same normalization, analytics and validation stages before rendering.
- SMA, RSI, MACD, support/resistance and volume summaries are calculated from the loaded OHLCV frame.
- TensorTrade export uses the existing service validation method and exports only validated timestamp/open/high/low/close/volume columns.

## TensorTrade scope boundary

The current integration prepares and validates TensorTrade-compatible OHLCV data. The optional runtime status reports whether the `tensortrade` package is installed. This workspace does not currently create TensorTrade environments, train reinforcement-learning agents, backtest strategies or submit broker orders. The UI states this explicitly; no simulated result is fabricated.

## Extension rules

New Market Intelligence features must:

- Add a navigation item to `NAV_ITEMS` and `NAV_TO_KEY`.
- Reuse `page_header`, `section_heading`, `DESIGN` and the shared CSS in `ui_components.py`.
- Use the shared sidebar controls and session-state keys for instrument settings.
- Keep Plotly chart height and data-table height within the shared layout contract.
- Include data provenance and user-facing errors.
- Add unit tests for calculations or validation logic; avoid network-dependent tests in the unit suite.
