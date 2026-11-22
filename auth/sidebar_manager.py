# auth/sidebar_manager.py
import streamlit as st

def hide_sidebar():
    """Completely hides the sidebar using CSS."""
    st.markdown(
        """
        <style>
        [data-testid="stSidebar"] {
            display: none;
        }
        </style>
        """,
        unsafe_allow_html=True
    )

def render_sidebar():
    """Shows the sidebar only after successful login."""
    with st.sidebar:
        st.image("assets/01_firstwatchlogo.jpg", width="stretch")
        st.markdown("<h2>💬 Live BOT NLP-to-SQL</h2>", unsafe_allow_html=True)

        username = st.session_state.get("username", "Unknown User")
        st.markdown(f"👤 Logged in as **{username}**")

        if st.button("🚪 Logout"):
            st.session_state.clear()
            st.success("You’ve been logged out.")
            st.markdown(
                """
                <meta http-equiv="refresh" content="0;url=/login_app">
                """,
                unsafe_allow_html=True
            )
            st.stop()

        st.markdown("---")
