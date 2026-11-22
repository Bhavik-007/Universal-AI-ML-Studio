# auth/ui_guard.py

import streamlit as st

def apply_sidebar_visibility():
    """
    Hides sidebar completely until user logs in.
    Restores it automatically after successful login.
    """
    if not st.session_state.get("logged_in", False):
        # --- Hide entire sidebar + navigation before login ---
        st.markdown(
            """
            <style>
            [data-testid="stSidebar"],
            [data-testid="stSidebarNav"],
            [data-testid="stSidebarCollapsedControl"] {
                display: none !important;
            }
            [data-testid="stAppViewContainer"] {
                margin-left: 0 !important;
            }
            </style>
            """,
            unsafe_allow_html=True,
        )
    else:
        # --- Restore sidebar after login ---
        st.markdown(
            """
            <style>
            [data-testid="stSidebar"],
            [data-testid="stSidebarCollapsedControl"] {
                display: block !important;
            }
            </style>
            """,
            unsafe_allow_html=True,
        )
