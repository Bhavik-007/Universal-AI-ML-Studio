import streamlit as st

from universal_ai_studio.core.env_config import get_config_value, get_sqlserver_legacy_config
from universal_ai_studio.ai_platform.providers import ProviderManager

from auth.login_manager import login_manager
from auth.auth_guard import protect_page




st.set_page_config(page_title="SQL Voice Chatbot", layout="wide")
login_manager()
protect_page()

from auth.ui_guard import apply_sidebar_visibility

import pyodbc
import pandas as pd
import logging
import re
import yaml
import os
import threading
import time
from datetime import datetime
import speech_recognition as sr
import pyttsx3

# =========================================================
# --- LOGIN + SIDEBAR GUARD ---
# =========================================================
apply_sidebar_visibility()


# =========================================================
# --- STREAMLIT CONFIG ---
# =========================================================
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# =========================================================
# --- SIDEBAR ---
# =========================================================
with st.sidebar:
    st.markdown("<h2>🎙️ SQL Voice Chatbot (Local Demo)</h2>", unsafe_allow_html=True)
    st.markdown("Click Start, speak for up to 10s, wait for reply, then repeat.")
    st.markdown("---")
    st.markdown(f"👤 Logged in as **{st.session_state.get('username', 'User')}**")
    st.markdown("---")
# --- PAGE HEADER ---
# =========================================================
st.title("🎙️ Ask Your Database by Voice (10s capture)")
st.markdown("""
#### How it works
1. Click **Start (Speak)**  
2. Speak within the 10 second window  
3. The bot transcribes, generates SQL, and fetches results  
4. Click again to ask another question
""")

# =========================================================
# --- APP SETTINGS ---
# =========================================================
show_sql = get_config_value("app_settings", "show_sql", False)
show_status = get_config_value("app_settings", "show_status_messages", False)
log_shipping = get_config_value("log_settings", "log_shipping", False)

# =========================================================
# --- OPENAI CLIENT INIT ---
# =========================================================
try:
    ai_provider_manager = ProviderManager()
    if show_status:
        st.success("AI provider initialized through Universal AI Studio Provider Management.")
except Exception as e:
    st.error(f"AI provider configuration error: {e}")
    st.stop()

# =========================================================
# --- SQL SERVER INIT ---
# =========================================================
try:
    env, db_cfg = get_sqlserver_legacy_config()
    conn_str = db_cfg.get("connection_string") or (
        f"DRIVER={{{db_cfg.get('driver', 'ODBC Driver 18 for SQL Server')}}};"
        f"SERVER={db_cfg['server']};DATABASE={db_cfg['database']};"
        f"UID={db_cfg['username']};PWD={db_cfg['password']};"
        f"Encrypt={'yes' if db_cfg.get('encrypt', True) else 'no'};"
        f"TrustServerCertificate={os.getenv('SQL_TRUST_SERVER_CERTIFICATE', 'no')};"
    )
    if show_status:
        st.success(f"✅ Using '{env}' SQL environment.")
except Exception as e:
    st.error(f"❌ SQL Server config error: {e}")
    st.stop()

# =========================================================
# --- LOAD table_config.yaml ---
# =========================================================
try:
    with open("table_config.yaml", "r") as file:
        table_config = yaml.safe_load(file)
        allowed_tables = [t for t in table_config.get("allowed_tables", []) if t]
        join_conditions = table_config.get("joins", [])
except Exception as e:
    st.error(f"❌ Failed to load table_config.yaml: {e}")
    st.stop()

# =========================================================
# --- SCHEMA INFO BUILDER ---
# =========================================================
schema_info = ""
try:
    with pyodbc.connect(conn_str) as conn:
        for tbl in allowed_tables:
            if isinstance(tbl, str) and "." in tbl:
                schema, table = tbl.split(".", 1)
                full_name = tbl
            elif isinstance(tbl, dict):
                schema, table = tbl.get("schema"), tbl.get("name")
                full_name = f"{schema}.{table}"
            else:
                continue

            cursor = conn.cursor()
            cursor.execute("""
                SELECT COLUMN_NAME, DATA_TYPE
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ?
            """, (schema, table))
            cols = cursor.fetchall()

            schema_info += f"Table: {full_name}\n" + "\n".join(f"  - {c[0]} ({c[1]})" for c in cols) + "\n\n"

        if join_conditions:
            schema_info += "Joins:\n" + "\n".join(
                f"  - {j['type']} JOIN {j['left']} = {j['right']}" for j in join_conditions
            )
except Exception as e:
    st.error(f"❌ Failed to build schema info: {e}")
    st.stop()

# =========================================================
# --- SPEECH RECOGNITION SETUP ---
# =========================================================
recognizer = sr.Recognizer()
recognizer.energy_threshold = 300
recognizer.pause_threshold = 0.8
AUDIO_SLOT = {"audio": None}

def _record_thread(duration_seconds: int = 10):
    try:
        with sr.Microphone() as source:
            recognizer.adjust_for_ambient_noise(source, duration=0.5)
            audio = recognizer.record(source, duration=duration_seconds)
        AUDIO_SLOT["audio"] = audio
    except Exception as e:
        AUDIO_SLOT["audio"] = e

def transcribe_audio(audio):
    try:
        text = recognizer.recognize_google(audio)
        return text, None
    except sr.UnknownValueError:
        return None, "Could not understand audio (try speaking more clearly)."
    except sr.RequestError as e:
        return None, f"Speech recognition API error: {e}"
    except Exception as e:
        return None, f"Unexpected transcription error: {e}"

def speak_text(text):
    try:
        engine = pyttsx3.init()
        engine.say(text)
        engine.runAndWait()
    except Exception as e:
        logging.warning(f"TTS failed: {e}")

def log_prompt_to_csv(user_question, sql, status="success", filename="logs/prompt_logs.csv"):
    if not log_shipping:
        return
    entry = {
        "timestamp": datetime.now().isoformat(),
        "user_question": user_question,
        "sql": sql,
        "status": status,
    }
    try:
        os.makedirs("logs", exist_ok=True)
        pd.DataFrame([entry]).to_csv(filename, mode="a", header=not os.path.isfile(filename), index=False)
    except Exception as e:
        logging.warning(f"Could not write log: {e}")

# =========================================================
# --- LLM SQL QUERY RUNNER ---
# =========================================================
def run_sql_query_from_llm(user_question: str):
    sql_prompt = f"""
You are a SQL Server expert.
Only use the following tables, columns, and joins:

{schema_info}

Write an optimized SQL query to answer this question:
\"{user_question}\"

Only return the SQL. Do not explain or use markdown.
"""
    generated_sql = ai_provider_manager.complete(sql_prompt, max_tokens=700, temperature=0)
    sql_text = re.sub(r"(?i)^```sql|```$", "", generated_sql.strip())
    with pyodbc.connect(conn_str) as conn:
        df = pd.read_sql(sql_text, conn)

    answer = "✅ Retrieved {} rows.".format(len(df)) if not df.empty else "No data returned for your query."
    return sql_text, df, answer

# =========================================================
# --- MAIN UI LOGIC ---
# =========================================================
if "is_recording" not in st.session_state:
    st.session_state.is_recording = False
if "last_q" not in st.session_state:
    st.session_state.last_q = None
if "last_a" not in st.session_state:
    st.session_state.last_a = None

if st.button("🎤 Start (Speak)"):
    AUDIO_SLOT["audio"] = None
    st.session_state.is_recording = True

    t = threading.Thread(target=_record_thread, args=(10,), daemon=True)
    t.start()

    placeholder = st.empty()
    for remaining in range(10, 0, -1):
        placeholder.info(f"🎤 Recording... {remaining}s remaining. Speak now.")
        time.sleep(1)
    placeholder.info("⏳ Processing audio...")

    t.join()
    st.session_state.is_recording = False

    audio_obj = AUDIO_SLOT.get("audio", None)
    if audio_obj is None:
        st.error("No audio captured — try again.")
    elif isinstance(audio_obj, Exception):
        st.error(f"Recording error: {audio_obj}")
    else:
        text, err = transcribe_audio(audio_obj)
        if text is None:
            st.error(err or "❌ Could not transcribe audio.")
        else:
            st.success(f"🗣️ You asked: {text}")
            st.session_state.last_q = text
            try:
                with st.spinner("🤖 Generating SQL and querying database..."):
                    sql_text, df, answer = run_sql_query_from_llm(text)

                st.subheader("📊 Query Results")
                st.dataframe(df, width="stretch")

                if show_sql:
                    with st.expander("📄 View SQL Query"):
                        st.code(sql_text, language="sql")

                st.subheader("📝 Bot Answer")
                st.write(answer)
                st.session_state.last_a = answer

                speak_text(answer)
                log_prompt_to_csv(text, sql_text)

            except Exception as e:
                st.error(f"❌ Processing error: {e}")
                log_prompt_to_csv(text, "", status=f"Error: {e}")

# =========================================================
# --- LAST Q&A DISPLAY ---
# =========================================================
if st.session_state.last_q:
    st.markdown("### Last Q&A")
    st.markdown(f"**Q:** {st.session_state.last_q}")
    if st.session_state.last_a:
        st.markdown(f"**A:** {st.session_state.last_a}")
