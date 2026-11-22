# Market Intelligence integration fix

## What was wrong

The Market Intelligence page was written as a standalone Streamlit application, then registered as a page inside the Universal AI Studio `st.navigation` shell. That created several ownership conflicts:

1. The page repeated `st.set_page_config`, `login_manager()` and `protect_page()` even though the main `app.py` already owns page configuration and authentication.
2. The page created another `st.sidebar` for its own controls. In the combined app this competes with the platform's persistent navigation sidebar.
3. The previous page stopped rendering when no ticker was entered. The initial screen therefore showed only the instrument controls and no usable preview.
4. The page used generic top-level imports (`market_analytics`, `ui_components`) after modifying `sys.path`, which can collide with same-named modules from other applications.

## What changed

- The main Universal AI Studio shell remains the single owner of authentication, page configuration, global sidebar navigation and workspace switching.
- `pages/15_Tensor_trade_business/app.py` is now a small adapter that calls the namespaced Market Intelligence renderer.
- Market Intelligence implementation modules now live under `universal_ai_studio/applications/market_intelligence/` and use explicit package imports.
- The Market Intelligence page no longer creates a second platform sidebar. Its five feature views are selected within the page content.
- Instrument controls are presented in a clear form with an explicit **Load market data** action.
- **Explore demo data** loads the bundled 180-row synthetic OHLCV dataset without requiring Yahoo Finance credentials or network access.
- Existing Yahoo/NSE resolution, historical data retrieval, OHLCV normalization, technical analytics and TensorTrade-compatible CSV export are retained.
- TensorTrade remains a data-format handoff only; no trading simulator, agent training, broker connection or order execution is claimed.
- The legacy page folder and original service files are retained for traceability/backward compatibility; the integrated runtime uses the namespaced package as the canonical implementation.

## Files

- `pages/15_Tensor_trade_business/app.py` — integrated page adapter
- `universal_ai_studio/applications/market_intelligence/render.py` — integrated UI and workflow
- `universal_ai_studio/applications/market_intelligence/market_analytics.py` — indicators and validation
- `universal_ai_studio/applications/market_intelligence/market_intelligence_services/market_data.py` — Yahoo Finance/NSE data service
- `universal_ai_studio/applications/market_intelligence/market_intelligence_services/tensortrade_adapter.py` — TensorTrade capability status
- `universal_ai_studio/applications/market_intelligence/sample_data/demo_ohlcv.csv` — clearly synthetic demo data

## Run

From the repository root:

```powershell
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Open **Analytics → Market Intelligence**. Select **Explore demo data** to confirm that the dashboard, indicators, charts, historical table and data-quality view render without a live market-data connection. Then enter an NSE ticker such as `TCS` and choose **Load market data** to test Yahoo Finance.

## Validation

- `python -m compileall` completed successfully for the modified page, package and tests.
- `pytest -q`: 80 tests passed.
- Streamlit and yfinance were not installed in the build environment; browser rendering and live Yahoo Finance requests therefore remain to be verified in the deployment environment.
