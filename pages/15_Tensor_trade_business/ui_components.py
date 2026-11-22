"""Shared visual system for every Market Intelligence section."""
import streamlit as st

DESIGN = {
    "content_max_width": "1440px",
    "section_min_height": "auto",
    "card_min_height": "116px",
    "radius": "14px",
    "gap": "16px",
}


def inject_design_system() -> None:
    st.markdown(
        """
        <style>
        :root {
          --mi-bg: #f5f7fb;
          --mi-surface: #ffffff;
          --mi-border: #e3e8ef;
          --mi-text: #172b4d;
          --mi-muted: #64748b;
          --mi-primary: #2457c5;
          --mi-positive: #138a56;
          --mi-negative: #c43d4b;
          --mi-radius: 14px;
        }
        [data-testid="stAppViewContainer"] { background: var(--mi-bg); }
        .block-container {
          max-width: 1440px;
          padding: 1.25rem clamp(1rem, 2vw, 2rem) 2.5rem;
        }
        [data-testid="stSidebar"] {
          background: #101f36;
          border-right: 1px solid #243852;
        }
        [data-testid="stSidebar"] * { color: #edf3ff; }
        [data-testid="stSidebar"] [data-testid="stRadio"] label {
          padding: .38rem .5rem; border-radius: 8px;
        }
        [data-testid="stSidebar"] [data-testid="stRadio"] label:hover {
          background: #203653;
        }
        .mi-brand { font-size: .72rem; letter-spacing: .13em; text-transform: uppercase;
          color: #a8bad3; font-weight: 800; margin: .2rem 0 .35rem; }
        .mi-side-title { color: white; font-size: 1.22rem; font-weight: 800; margin-bottom: .2rem; }
        .mi-side-copy { color: #b7c6da; font-size: .78rem; line-height: 1.45; }
        .mi-page-header {
          background: linear-gradient(120deg,#fff 0%,#f1f6ff 100%);
          border: 1px solid var(--mi-border); border-radius: var(--mi-radius);
          padding: 1.25rem 1.4rem; margin: 0 0 1rem 0;
          min-height: 126px; box-sizing: border-box;
        }
        .mi-eyebrow { color: var(--mi-primary); font-size: .68rem; font-weight: 800;
          letter-spacing: .12em; text-transform: uppercase; margin-bottom: .45rem; }
        .mi-page-title { color: var(--mi-text); font-size: clamp(1.4rem,2.2vw,2rem);
          line-height: 1.2; font-weight: 800; margin: 0; }
        .mi-page-description { color: var(--mi-muted); font-size: .88rem;
          line-height: 1.5; margin-top: .45rem; }
        .mi-section-heading { display:flex; align-items:center; gap:.55rem;
          color:var(--mi-text); font-size:1.05rem; font-weight:800;
          margin: .2rem 0 .65rem; min-height: 30px; }
        .mi-section-help { color:var(--mi-muted); font-size:.82rem; margin:0 0 .8rem; }
        div[data-testid="stMetric"] {
          background:var(--mi-surface); border:1px solid var(--mi-border);
          border-radius:var(--mi-radius); padding: .85rem 1rem;
          min-height:116px; box-sizing:border-box;
        }
        div[data-testid="stMetricLabel"] { color:var(--mi-muted); font-weight:650; }
        div[data-testid="stMetricValue"] { color:var(--mi-text); font-weight:800; }
        div[data-testid="stPlotlyChart"], div[data-testid="stDataFrame"] {
          background:#fff; border:1px solid var(--mi-border);
          border-radius:var(--mi-radius); overflow:hidden;
        }
        div[data-testid="stButton"] button, div[data-testid="stDownloadButton"] button {
          border-radius:9px; font-weight:700; min-height:42px;
        }
        div[data-testid="stTextInput"] input, div[data-testid="stSelectbox"] > div,
        div[data-testid="stNumberInput"] input { border-radius:9px; }
        div[data-testid="stExpander"] { background:#fff; border:1px solid var(--mi-border);
          border-radius:12px; }
        .mi-note { color:var(--mi-muted); font-size:.78rem; line-height:1.5; }
        @media (max-width: 900px) {
          .block-container { padding-left: .85rem; padding-right: .85rem; }
          .mi-page-header { min-height: 0; padding: 1rem; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def page_header(title: str, description: str, eyebrow: str = "Market Intelligence") -> None:
    st.markdown(
        f'<section class="mi-page-header"><div class="mi-eyebrow">{eyebrow}</div>'
        f'<h1 class="mi-page-title">{title}</h1>'
        f'<div class="mi-page-description">{description}</div></section>',
        unsafe_allow_html=True,
    )


def section_heading(title: str, description: str | None = None, icon: str = "▦") -> None:
    st.markdown(f'<div class="mi-section-heading">{icon} {title}</div>', unsafe_allow_html=True)
    if description:
        st.markdown(f'<div class="mi-section-help">{description}</div>', unsafe_allow_html=True)
