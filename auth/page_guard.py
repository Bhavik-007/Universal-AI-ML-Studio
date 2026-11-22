# auth/page_guard.py
import streamlit as st
from auth.login_manager import login_manager
from auth.auth_guard import protect_page

def enforce_login(page_title="Protected Page"):
    """Universal login guard for all pages."""
    st.set_page_config(page_title=page_title, layout="wide")

    # Hide sidebar until login
    st.markdown("""
        <style>
        [data-testid="stSidebar"], [data-testid="stSidebarNav"], [data-testid="stSidebarCollapsedControl"] {
            display: none !important;
        }
        [data-testid="stAppViewContainer"] {
            margin-left: 0 !important;
        }
        </style>
    """, unsafe_allow_html=True)

    # Run login
    login_manager()

    # Block page if not logged in
    if not st.session_state.get("logged_in", False):
        protect_page()
        st.stop()

    # Re-enable sidebar after login
    st.markdown("""
        <style>
        [data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"] {
            display: block !important;
        }
        </style>
    """, unsafe_allow_html=True)
