import streamlit as st

from universal_ai_studio.core.env_config import get_config_value
from universal_ai_studio.ai_platform.providers import get_langchain_llm

from auth.login_manager import login_manager
from auth.auth_guard import protect_page




st.set_page_config(page_title="API Analyzer", layout="wide", page_icon="🌐")
login_manager()
protect_page()

from auth.ui_guard import apply_sidebar_visibility

import requests
import json
import pandas as pd
import logging
from universal_ai_studio.ai_platform.dataframe_agent import (
    create_dataframe_agent,
    DataFrameAgentDependencyError,
)
from langchain.memory import ConversationBufferMemory

# =========================================================
# --- LOGIN + SIDEBAR GUARD ---
# =========================================================
apply_sidebar_visibility()


# =========================================================
# --- STREAMLIT CONFIG ---
# =========================================================
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# =========================================================
# --- SIDEBAR (Visible after login) ---
# =========================================================
with st.sidebar:
    st.markdown("<h2>🌐 API Analyzer</h2>", unsafe_allow_html=True)
    st.markdown(f"👤 Logged in as **{st.session_state.get('username', 'User')}**")

    st.markdown("---")
    # API Inputs
    base_url = st.text_input("Base API URL", "https://jsonplaceholder.typicode.com")
    endpoint = st.text_input("Endpoint (without base)", "/posts")

    request_type = st.selectbox(
        "Select GET Request Type",
        ["Simple GET", "GET with Path Parameter", "GET with Query Parameters", "GET with Multiple Path Levels"]
    )

    # Authentication
    auth_method = st.radio("Authentication Method", ["None", "Basic Auth", "Bearer Token"])
    username, password, token = None, None, None
    headers = {}

    if auth_method == "Basic Auth":
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
    elif auth_method == "Bearer Token":
        token = st.text_input("Auth Token")
        if token:
            headers["Authorization"] = f"Bearer {token}"

    params, path_param, extra_path = {}, None, None
    if request_type == "GET with Path Parameter":
        path_param = st.text_input("Path Parameter (e.g., ID)")
    elif request_type == "GET with Query Parameters":
        query_str = st.text_area("Query Params (key=value, one per line)")
        if query_str:
            for line in query_str.split("\n"):
                if "=" in line:
                    k, v = line.split("=", 1)
                    params[k.strip()] = v.strip()
    elif request_type == "GET with Multiple Path Levels":
        extra_path = st.text_input("Additional Path (e.g., users/1/posts)")

    st.markdown("---")
# --- MAIN PAGE HEADER ---
# =========================================================
col1, col2, col3 = st.columns([1, 2, 1])
with col2:
    st.image("assets/01_firstwatchlogo.jpg", width=220)
st.title("🌐 API Analyzer")

# =========================================================
# --- BUILD FINAL REQUEST URL ---
# =========================================================
url = base_url.rstrip("/") + endpoint
if path_param:
    url = f"{url}/{path_param.strip()}"
elif extra_path:
    url = f"{url}/{extra_path.strip()}"

st.code(f"Request URL → {url}")

# =========================================================
# --- OPENAI LangChain CONFIG ---
# =========================================================
try:
    llm = get_langchain_llm()
    if get_config_value("app_settings", "show_status_messages", True):
        st.success("AI provider initialized through Universal AI Studio Provider Management.")
    else:
        logging.info("AI provider initialized through the central provider manager.")

except Exception as e:
    st.error(f"❌ OpenAI config error: {e}")
    st.stop()

# =========================================================
# --- SESSION STATE ---
# =========================================================
if "api_data" not in st.session_state:
    st.session_state.api_data = None
if "agent" not in st.session_state:
    st.session_state.agent = None
if "memory" not in st.session_state:
    st.session_state.memory = ConversationBufferMemory(memory_key="chat_history", return_messages=True)
if "chat_log" not in st.session_state:
    st.session_state.chat_log = []

# =========================================================
# --- SEND GET REQUEST ---
# =========================================================
if st.button("🚀 Send Request"):
    try:
        if auth_method == "Basic Auth" and username and password:
            response = requests.get(url, params=params, auth=(username, password), headers=headers)
        else:
            response = requests.get(url, params=params, headers=headers)

        st.subheader("Response Status")
        st.write(f"{response.status_code} - {response.reason}")

        st.subheader("Response Headers")
        st.json(dict(response.headers))

        st.subheader("Response Body")
        try:
            data = response.json()
            st.session_state.api_data = data
            st.json(data)

            if isinstance(data, list):
                df = pd.DataFrame(data)
                st.dataframe(df, width="stretch")
            elif isinstance(data, dict):
                df = pd.DataFrame([data])
                st.dataframe(df, width="stretch")
            else:
                df = None

            if df is not None:
                try:
                    st.session_state.agent = create_dataframe_agent(
                        llm,
                        df,
                        verbose=False,
                        memory=st.session_state.memory,
                        allow_dangerous_code=True
                    )
                except DataFrameAgentDependencyError as agent_error:
                    logging.exception("API response DataFrame agent dependency is missing")
                    st.session_state.agent = None
                    st.warning(
                        "The API request succeeded and its response is displayed, "
                        "but AI analysis could not start. " + str(agent_error)
                    )
                except Exception as agent_error:
                    logging.exception("API response DataFrame agent initialization failed")
                    st.session_state.agent = None
                    st.warning(
                        "The API request succeeded and its response is displayed, "
                        "but the AI analysis agent could not be initialized: "
                        + str(agent_error)
                    )

        except json.JSONDecodeError:
            st.text(response.text)

    except Exception as e:
        logging.exception("API request or response processing failed")
        st.error(f"❌ API request/response processing failed: {e}")

# =========================================================
# --- AI-POWERED ANALYSIS ---
# =========================================================
if st.session_state.api_data is not None and st.session_state.agent:
    st.subheader("🤖 Ask AI about the API Response")
    user_question = st.text_input("💬 Enter your question")

    if user_question:
        try:
            with st.spinner("AI analyzing API response..."):
                answer = st.session_state.agent.run(user_question)

            st.markdown("### 📝 Answer")
            st.write(answer)

            st.session_state.chat_log.append({"question": user_question, "answer": answer})
        except Exception as e:
            st.error(f"❌ LangChain Agent Error: {e}")
