"""Legacy login entry point retained for backward compatibility."""
import streamlit as st
from auth.login_manager import login_manager
from auth.auth_guard import protect_page

st.set_page_config(page_title="Universal AI Studio | Login", page_icon="🔐", layout="centered")
login_manager()
protect_page()
st.success("You are signed in. Launch the application using `streamlit run app.py`.")
