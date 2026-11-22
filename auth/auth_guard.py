"""Fail-closed access guard with an absolute/idle session lifetime."""
import os
import time
import streamlit as st


def protect_page() -> None:
    if not st.session_state.get("logged_in", False):
        st.error("Your session is not authenticated. Return to the login page to continue.")
        st.stop()

    now = int(time.time())
    ttl = max(300, int(os.getenv("UAS_SESSION_TTL_SECONDS", "28800")))
    last_activity = int(st.session_state.get("last_activity", st.session_state.get("auth_time", now)))
    if now - last_activity > ttl:
        st.session_state.clear()
        st.rerun()
    st.session_state["last_activity"] = now
