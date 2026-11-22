"""Streamlit Agent Assist application using the in-process service layer."""
from __future__ import annotations

import sys
import time
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from auth.login_manager import login_manager
from auth.auth_guard import protect_page

st.set_page_config(page_title="AT&T Fiber | Agent Assist", page_icon="◉", layout="wide")
login_manager()
protect_page()

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
load_dotenv(dotenv_path=BASE_DIR / ".env")

import backend  # noqa: E402


def ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 1)


st.markdown("""<style>
.stApp {background: #f5f7fa;}
.brand {color:#0568ae;font-weight:800;letter-spacing:.04em}
div[data-testid="stMetric"] {background:white;border-left:4px solid #00a8e0;padding:12px;border-radius:6px}
</style>""", unsafe_allow_html=True)

st.markdown("<div class='brand'>AT&T FIBER</div>", unsafe_allow_html=True)
st.title("Agent Assist & Propensity Command Center")
st.caption("In-process Streamlit workflow — no separate FastAPI/Uvicorn service is required.")

sample_customers = backend.get_customers()
customer_ids = list(sample_customers)
customer_id = st.selectbox(
    "Select customer",
    customer_ids,
    format_func=lambda value: f"{sample_customers[value]['name']} · {value}",
)
profile = sample_customers[customer_id]

left, right = st.columns([1, 1.25], gap="large")
with left:
    st.subheader("Customer context")
    st.caption(f"{profile.get('name')} · {profile.get('plan')} · {profile.get('status')}")
    st.json(profile)
    message = st.text_area("Customer message", placeholder="Example: My internet keeps disconnecting and I am frustrated.", height=130)
    run = st.button("Analyse customer message", type="primary", width="stretch", disabled=not message.strip())

with right:
    st.subheader("Agent dashboard")
    if run:
        started = time.perf_counter()
        try:
            data = backend.process_chat(backend.ChatRequest(customer_id=customer_id, message=message.strip()))
            record = data["record"]
            metric1, metric2, metric3 = st.columns(3)
            metric1.metric("Intent", record["intent"].replace("_", " ").title())
            metric2.metric("Sentiment", record["sentiment"].title())
            metric3.metric("Processing", f"{ms(started)} ms")
            st.caption(f"Engine: {data['engine']} · Redis Pub/Sub: {data['pubsub_note']} · CSV audit: {data['csv_note']}")
            st.markdown("#### Next Best Offer (NBO)")
            offer_col, score_col = st.columns([2, 1])
            offer_col.info(f"**Recommended offer:** {record['offer']}")
            score_col.success(f"**Propensity:** {record['score']}")
            st.caption(f"**Rationale:** {data['rationale']}")
            st.markdown("#### AI response")
            st.info(record["response"])
            st.markdown("#### Suggested reply")
            st.success(record["reply"])
            st.markdown("#### Call summary")
            st.write(record["summary"])
        except Exception as exc:
            st.error(f"Unable to process this interaction: {exc}")
    else:
        st.info("Enter a customer message and select Analyse to generate agent guidance.")
