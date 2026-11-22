
import hashlib
import io
import logging

import pandas as pd
import streamlit as st

from langchain.memory import ConversationBufferMemory

from universal_ai_studio.core.env_config import get_config_value
from universal_ai_studio.ai_platform.providers import get_langchain_llm

from universal_ai_studio.ai_platform.dataframe_agent import (
    create_dataframe_agent,
    DataFrameAgentDependencyError,
)

from auth.login_manager import login_manager
from auth.auth_guard import protect_page
from auth.ui_guard import apply_sidebar_visibility


# =========================================================
# PAGE CONFIGURATION
# =========================================================

st.set_page_config(
    page_title="File Q&A Chatbot",
    page_icon="📂",
    layout="wide",
    initial_sidebar_state="expanded",
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


# =========================================================
# AUTHENTICATION & ACCESS CONTROL
# =========================================================

login_manager()
protect_page()
apply_sidebar_visibility()


# =========================================================
# SESSION STATE INITIALIZATION
# =========================================================

SESSION_DEFAULTS = {
    "chat_log_file": [],
    "df_file": None,
    "agent": None,
    "memory": None,
    "file_hash": None,
    "file_name": None,
    "llm": None,
    "llm_initialized": False,
}

for key, default_value in SESSION_DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = default_value

if st.session_state.memory is None:
    st.session_state.memory = ConversationBufferMemory(
        memory_key="chat_history",
        return_messages=True,
    )


# =========================================================
# SIDEBAR
# =========================================================

with st.sidebar:
    st.markdown("## 📂 File Q&A Chatbot")

    st.markdown(
        f"👤 Logged in as **{st.session_state.get('username', 'User')}**"
    )

    st.divider()

    if st.session_state.file_name:
        st.caption("Current document")
        st.markdown(f"📄 **{st.session_state.file_name}**")

    if st.session_state.df_file is not None:
        df = st.session_state.df_file

        st.caption("Document information")
        st.write(f"Rows: {df.shape[0]:,}")
        st.write(f"Columns: {df.shape[1]:,}")

    st.divider()

    if st.button("🗑️ Clear Chat", use_container_width=True):
        st.session_state.chat_log_file = []

        st.session_state.memory = ConversationBufferMemory(
            memory_key="chat_history",
            return_messages=True,
        )

        if st.session_state.df_file is not None and st.session_state.llm:
            try:
                st.session_state.agent = create_dataframe_agent(
                    st.session_state.llm,
                    st.session_state.df_file,
                    verbose=False,
                    memory=st.session_state.memory,
                    allow_dangerous_code=True,
                )
            except Exception:
                logger.exception("Failed to recreate DataFrame agent")

        st.rerun()


# =========================================================
# MAIN HEADER
# =========================================================

st.title("📂 Chat with Your File (CSV / Excel)")

st.caption(
    "Upload your CSV or Excel file, explore your data, "
    "and ask questions using AI."
)

st.divider()


# =========================================================
# AI PROVIDER INITIALIZATION
# =========================================================

try:

    if not st.session_state.llm_initialized:

        st.session_state.llm = get_langchain_llm()
        st.session_state.llm_initialized = True

        logger.info("AI provider initialized successfully.")

    llm = st.session_state.llm

    if get_config_value(
        "app_settings",
        "show_status_messages",
        True,
    ):
        st.success(
            "🟢 AI provider initialized through "
            "Universal AI Studio Provider Management."
        )
    else:
        logger.info("AI provider is ready.")

except Exception as e:

    logger.exception("AI provider initialization failed")

    st.error(
        f"AI provider initialization failed: {e}"
    )

    st.stop()


# =========================================================
# FILE UPLOAD SECTION
# =========================================================

st.markdown("### 📁 Upload your CSV or Excel file")

uploaded_file = st.file_uploader(
    "Choose a file",
    type=["csv", "xlsx"],
    help="Supported formats: CSV and Excel (.xlsx).",
    key="file_qa_uploader",
)

# =========================================================
# FILE PROCESSING
# =========================================================

if uploaded_file is not None:

    try:

        file_bytes = uploaded_file.getvalue()

        current_file_hash = hashlib.sha256(
            file_bytes
        ).hexdigest()

        # Process only when a new or different file is uploaded.
        if current_file_hash != st.session_state.file_hash:

            logger.info(
                "Processing uploaded file: %s",
                uploaded_file.name,
            )

            with st.spinner("Reading and processing your file..."):

                file_extension = uploaded_file.name.lower()

                if file_extension.endswith(".csv"):

                    df = pd.read_csv(
                        io.BytesIO(file_bytes)
                    )

                elif file_extension.endswith(".xlsx"):

                    df = pd.read_excel(
                        io.BytesIO(file_bytes)
                    )

                else:
                    raise ValueError(
                        "Unsupported file format."
                    )

                if df.empty:
                    raise ValueError(
                        "The uploaded file contains no data."
                    )

                # Store processed DataFrame.
                st.session_state.df_file = df
                st.session_state.file_hash = current_file_hash
                st.session_state.file_name = uploaded_file.name

                # Reset previous conversation for the new file.
                st.session_state.chat_log_file = []

                st.session_state.memory = ConversationBufferMemory(
                    memory_key="chat_history",
                    return_messages=True,
                )

                # Reset previous agent.
                st.session_state.agent = None

                logger.info(
                    "File loaded successfully: %s rows, %s columns",
                    df.shape[0],
                    df.shape[1],
                )

                # Initialize the agent only once per new file.
                try:

                    st.session_state.agent = create_dataframe_agent(
                        llm,
                        df,
                        verbose=False,
                        memory=st.session_state.memory,
                        allow_dangerous_code=True,
                    )

                    logger.info(
                        "DataFrame Q&A agent initialized successfully."
                    )

                except DataFrameAgentDependencyError as agent_error:

                    logger.exception(
                        "DataFrame agent dependency error"
                    )

                    st.warning(
                        "Your file was loaded successfully, "
                        "but the Q&A agent could not start. "
                        "Please install the required dependencies "
                        "using requirements.txt and restart the app. "
                        f"Details: {agent_error}"
                    )

                except Exception as agent_error:

                    logger.exception(
                        "DataFrame agent initialization failed"
                    )

                    st.warning(
                        "Your file was loaded, but the Q&A agent "
                        "could not be initialized. Please check "
                        "your AI provider configuration and logs. "
                        f"Details: {agent_error}"
                    )

            st.rerun()

        # =================================================
        # FILE INFORMATION
        # =================================================

        if st.session_state.df_file is not None:

            df = st.session_state.df_file

            st.success(
                f"File loaded: {st.session_state.file_name}"
            )

            col1, col2, col3 = st.columns(3)

            col1.metric(
                "Total Rows",
                f"{df.shape[0]:,}",
            )

            col2.metric(
                "Total Columns",
                f"{df.shape[1]:,}",
            )

            col3.metric(
                "Memory Usage",
                f"{df.memory_usage(deep=True).sum() / (1024 * 1024):.2f} MB",
            )

            # =============================================
            # DATA PREVIEW
            # =============================================

            with st.expander(
                "📊 Preview uploaded data",
                expanded=False,
            ):

                st.dataframe(
                    df.head(50),
                    use_container_width=True,
                )

                st.caption(
                    "Showing the first 50 rows."
                )

    except Exception as e:

        logger.exception(
            "Uploaded file processing failed"
        )

        st.error(
            f"Failed to process uploaded file: {e}"
        )

        st.session_state.df_file = None
        st.session_state.agent = None
        st.session_state.file_hash = None
        st.session_state.file_name = None


# =========================================================
# Q&A CHAT SECTION
# =========================================================

if (
    st.session_state.df_file is not None
    and st.session_state.agent is not None
):

    st.divider()

    st.markdown("### 💬 Ask Questions About Your File")

    st.caption(
        "Ask questions about your uploaded data "
        "using natural language."
    )

    # Display previous conversations.
    for chat in st.session_state.chat_log_file:

        with st.chat_message("user"):
            st.write(chat["question"])

        with st.chat_message("assistant"):
            st.write(chat["answer"])

    # Use a form to avoid processing the same question
    # on unrelated Streamlit reruns.
    with st.form(
        key="file_qa_question_form",
        clear_on_submit=True,
    ):

        user_question = st.text_input(
            "Enter your question",
            placeholder="Example: What are the top 10 records?",
        )

        submit_question = st.form_submit_button(
            "🔍 Ask AI",
            use_container_width=True,
        )

    if submit_question and user_question.strip():

        try:

            with st.spinner(
                "🤖 AI is analyzing your data..."
            ):

                answer = st.session_state.agent.run(
                    user_question.strip()
                )

            # Save conversation.
            st.session_state.chat_log_file.append(
                {
                    "question": user_question.strip(),
                    "answer": answer,
                }
            )

            st.rerun()

        except Exception as e:

            logger.exception(
                "DataFrame Q&A execution failed"
            )

            st.error(
                f"Unable to process your question: {e}"
            )

elif st.session_state.df_file is not None:

    st.info(
        "Your file is loaded, but the Q&A agent is unavailable. "
        "Please check the application logs."
    )

else:

    st.info(
        "👆 Upload a CSV or Excel file to get started."
    )


# =========================================================
# SHARED MCP INTEGRATION
# =========================================================

try:

    from universal_ai_studio.mcp_platform.streamlit_ui import (
        render_shared_mcp_tools,
    )

    render_shared_mcp_tools("file_qa")

except Exception:

    logger.exception(
        "Shared MCP tools could not be rendered."
    )
