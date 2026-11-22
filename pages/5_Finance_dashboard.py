import streamlit as st

from auth.login_manager import login_manager
from auth.auth_guard import protect_page




st.set_page_config(page_title="Stock Price Dashboard", layout="wide")
login_manager()
protect_page()

from auth.ui_guard import apply_sidebar_visibility

import yfinance as yf
import logging
import plotly.graph_objects as go
import os

# =========================================================
# --- LOGIN + SIDEBAR GUARD ---
# =========================================================
apply_sidebar_visibility()


# =========================================================
# --- STREAMLIT CONFIG ---
# =========================================================
st.cache_resource.show_spinner = False  # Disable spinner globally
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# =========================================================
# --- SIDEBAR ---
# =========================================================
with st.sidebar:
    st.markdown("<h2>📊 Stock Price Dashboard</h2>", unsafe_allow_html=True)
    st.markdown("Track the latest **stock price trends** for your favorite companies.")
    st.markdown("---")
    st.markdown(f"👤 Logged in as **{st.session_state.get('username', 'User')}**")

    st.markdown("---")
# --- PAGE HEADER ---
# =========================================================
col1, col2, col3 = st.columns([1, 2, 1])
with col2:
    image_path = os.path.join("assets", "05_finance_dashboard.jpg")
    if os.path.exists(image_path):
        st.image(image_path, width=200)
st.title("📊 Stock Market Trends")

# =========================================================
# --- POPULAR COMPANIES ---
# =========================================================
companies = {
    "Apple (AAPL)": "AAPL",
    "Microsoft (MSFT)": "MSFT",
    "Tesla (TSLA)": "TSLA",
    "Amazon (AMZN)": "AMZN",
    "Google (GOOGL)": "GOOGL",
    "Meta (META)": "META",
    "Netflix (NFLX)": "NFLX",
    "NVIDIA (NVDA)": "NVDA",
}

# =========================================================
# --- USER INPUTS ---
# =========================================================
st.subheader("📌 Choose a Company or Enter Ticker Symbol")

company_name = st.selectbox("Choose from popular companies:", list(companies.keys()))
stock_symbol = companies[company_name]

manual_search = st.text_input("Or enter another ticker symbol manually (e.g., IBM, ORCL)")
if manual_search:
    stock_symbol = manual_search.upper()

period = st.selectbox(
    "Select Time Range", ["1mo", "3mo", "6mo", "1y", "5y", "max"], index=0
)

# =========================================================
# --- STOCK DATA FETCH ---
# =========================================================
@st.cache_resource
def get_stock_data(symbol, period="1mo"):
    stock = yf.Ticker(symbol)
    return stock.history(period=period)

# =========================================================
# --- DISPLAY STOCK DATA ---
# =========================================================
if stock_symbol:
    try:
        hist = get_stock_data(stock_symbol, period)
        if not hist.empty:
            latest_price = hist["Close"].iloc[-1]
            st.metric(label=f"Latest Closing Price ({stock_symbol})", value=f"${latest_price:.2f}")

            # --- Plotly Chart ---
            fig = go.Figure()
            fig.add_trace(
                go.Scatter(
                    x=hist.index,
                    y=hist["Close"],
                    mode="lines",
                    line=dict(color="royalblue", width=2),
                    name="Close Price",
                )
            )

            fig.update_layout(
                title=f"{stock_symbol} Stock Price Trend ({period})",
                xaxis_title="Date",
                yaxis_title="Price (USD)",
                template="plotly_white",
                hovermode="x unified",
                margin=dict(l=40, r=40, t=60, b=40),
            )

            st.plotly_chart(fig, width="stretch")

        else:
            st.warning("⚠️ No stock data found for this symbol.")
    except Exception as e:
        st.error(f"❌ Failed to fetch stock data: {e}")
