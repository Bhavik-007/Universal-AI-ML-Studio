import streamlit as st

from universal_ai_studio.core.env_config import get_api_key, get_config_value

from auth.login_manager import login_manager
from auth.auth_guard import protect_page




st.set_page_config(page_title="SQL Voice Chatbot", layout="wide")
login_manager()
protect_page()

from auth.ui_guard import apply_sidebar_visibility

import pandas as pd
import logging
import re
import os
import threading
import time
from datetime import datetime
from openai import AzureOpenAI
import speech_recognition as sr
import pyttsx3
import pyodbc
import psycopg2
import pymysql
from pymongo import MongoClient
import urllib

# =========================================================
# --- LOGIN + SIDEBAR GUARD ---
# =========================================================
apply_sidebar_visibility()


# --------------------------
# Config / UI header
# --------------------------
with st.sidebar:
    st.markdown("<h2>🎙️ SQL Voice Chatbot (Multi-DB)</h2>", unsafe_allow_html=True)
    st.markdown("Choose your DB, connect, select a table, then ask by voice.")

st.title("🎙️ Ask Your Database by Voice (10s capture)")

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# --- toggles controlled from secrets.toml ---
show_sql = get_config_value("app_settings", "show_sql", False)
log_shipping = get_config_value("log_settings", "log_shipping", False)

# --------------------------
# Azure OpenAI Client init
# --------------------------
try:
    azure_api_key = get_api_key("openai")
    if not azure_api_key:
        raise RuntimeError("OPENAI_API_KEY is missing. Add it to the project-root .env file and restart the app.")
    client = AzureOpenAI(
        api_key=azure_api_key,
        api_version=get_config_value("openai", "api_version"),
        azure_endpoint=get_config_value("openai", "api_base"),
    )
    deployment_name = get_config_value("openai", "deployment_name")
except Exception as e:
    st.error(f"❌ Azure OpenAI config error: {e}")
    st.stop()

# --------------------------
# DB Connection UI
# --------------------------
db_type = st.sidebar.selectbox(
    "Select Database Type",
    ["Azure SQL", "SQL Server (On-Premises)", "PostgreSQL", "MySQL", "MongoDB"]
)

st.sidebar.markdown("### Connection Parameters")
host = st.sidebar.text_input("Host / Server")
port = st.sidebar.text_input("Port", value="1433" if db_type in ["Azure SQL", "SQL Server (On-Premises)"] else "")
user = st.sidebar.text_input("Username")
password = st.sidebar.text_input("Password", type="password")
database = st.sidebar.text_input("Database Name")

connect_btn = st.sidebar.button("🔗 Connect to Database")

conn = None
mongo_client = None
schema_info = ""
tables = []
selected_table = None

if connect_btn:
    try:
        if db_type == "Azure SQL":
            conn = pyodbc.connect(
                f"DRIVER={{ODBC Driver 17 for SQL Server}};"
                f"SERVER={host},{port};"
                f"DATABASE={database};"
                f"UID={user};"
                f"PWD={password};"
                f"Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;"
            )

        elif db_type == "SQL Server (On-Premises)":
            if "\\" in host:
                server = host
            else:
                server = f"{host},{port}"

            conn = pyodbc.connect(
                f"DRIVER={{ODBC Driver 17 for SQL Server}};"
                f"SERVER={server};"
                f"DATABASE={database};"
                f"UID={user};"
                f"PWD={password};"
                f"Encrypt=no;TrustServerCertificate=yes;Connection Timeout=30;"
            )

        elif db_type == "PostgreSQL":
            conn = psycopg2.connect(
                host=host, port=port, dbname=database, user=user, password=password
            )

        elif db_type == "MySQL":
            conn = pymysql.connect(
                host=host, port=int(port), db=database, user=user, password=password
            )

        elif db_type == "MongoDB":
            mongo_client = MongoClient(f"mongodb://{user}:{password}@{host}:{port}/{database}")

        st.sidebar.success(f"✅ Connected to {db_type}")

    except Exception as e:
        st.sidebar.error(f"❌ Connection failed: {e}")

# --------------------------
# Schema & Table Visibility
# --------------------------
if conn:
    cursor = conn.cursor()
    if db_type in ["Azure SQL", "SQL Server (On-Premises)"]:
        cursor.execute("SELECT TABLE_SCHEMA, TABLE_NAME FROM INFORMATION_SCHEMA.TABLES")
        rows = cursor.fetchall()
        schemas = sorted(set([r[0] for r in rows]))
        schema = st.sidebar.selectbox("Select Schema", schemas)
        tables = [r[1] for r in rows if r[0] == schema]
        selected_table = st.sidebar.selectbox("Select Table", tables)

        if selected_table:
            cursor.execute(f"""
                SELECT COLUMN_NAME, DATA_TYPE 
                FROM INFORMATION_SCHEMA.COLUMNS 
                WHERE TABLE_SCHEMA='{schema}' AND TABLE_NAME='{selected_table}'
            """)
            cols = cursor.fetchall()
            schema_info = f"Table: {schema}.{selected_table}\n"
            for col in cols:
                schema_info += f"  - {col[0]} ({col[1]})\n"

    elif db_type == "PostgreSQL":
        cursor.execute("SELECT table_schema, table_name FROM information_schema.tables WHERE table_schema='public'")
        rows = cursor.fetchall()
        schemas = sorted(set([r[0] for r in rows]))
        schema = st.sidebar.selectbox("Select Schema", schemas)
        tables = [r[1] for r in rows if r[0] == schema]
        selected_table = st.sidebar.selectbox("Select Table", tables)

        if selected_table:
            cursor.execute(f"""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_schema='{schema}' AND table_name='{selected_table}'
            """)
            cols = cursor.fetchall()
            schema_info = f"Table: {schema}.{selected_table}\n"
            for col in cols:
                schema_info += f"  - {col[0]} ({col[1]})\n"

    elif db_type == "MySQL":
        cursor.execute("SHOW TABLES")
        tables = [r[0] for r in cursor.fetchall()]
        selected_table = st.sidebar.selectbox("Select Table", tables)

        if selected_table:
            cursor.execute(f"DESCRIBE {selected_table}")
            cols = cursor.fetchall()
            schema_info = f"Table: {selected_table}\n"
            for col in cols:
                schema_info += f"  - {col[0]} ({col[1]})\n"

elif mongo_client:
    db = mongo_client[database]
    collections = db.list_collection_names()
    selected_table = st.sidebar.selectbox("Select Collection", collections)

    if selected_table:
        sample_doc = db[selected_table].find_one()
        schema_info = f"Collection: {selected_table}\n"
        if sample_doc:
            for k, v in sample_doc.items():
                schema_info += f"  - {k} ({type(v).__name__})\n"

# --------------------------
# Speech recognizer and TTS helpers
# --------------------------
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
    except Exception as e:
        return None, str(e)

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

def run_query(user_question: str):
    """Generate query with LLM and execute."""
    sql_prompt = f"""
You are a {db_type} expert.
Only use the following schema/collection details:

{schema_info}

Write an optimized query to answer this question:
\"{user_question}\"

Only return the query. Do not explain or use markdown.
"""
    response = client.chat.completions.create(
        model=deployment_name,
        messages=[{"role": "user", "content": sql_prompt}],
        temperature=0,
        max_tokens=700,
    )
    sql_text = re.sub(r"(?i)^```(sql|json)?|```$", "", response.choices[0].message.content.strip())

    if mongo_client:
        db = mongo_client[database]
        collection = db[selected_table]
        df = pd.DataFrame(list(collection.find().limit(10)))  # simple fallback
    else:
        df = pd.read_sql(sql_text, conn)

    answer = f"✅ Retrieved {len(df)} rows." if not df.empty else "No data returned."
    return sql_text, df, answer

# --------------------------
# UI & main flow
# --------------------------
if "last_q" not in st.session_state:
    st.session_state.last_q = None
if "last_a" not in st.session_state:
    st.session_state.last_a = None

if selected_table:
    st.markdown("#### Steps\n1. Click **Start (Speak)**\n2. Ask your question\n3. Bot transcribes → runs query → answers")

    if st.button("🎤 Start (Speak)"):

        AUDIO_SLOT["audio"] = None
        t = threading.Thread(target=_record_thread, args=(10,), daemon=True)
        t.start()
        placeholder = st.empty()
        for remaining in range(10, 0, -1):
            placeholder.info(f"🎤 Recording... {remaining}s remaining. Speak now.")
            time.sleep(1)
        placeholder.info("⏳ Processing audio...")
        t.join()

        audio_obj = AUDIO_SLOT.get("audio", None)
        if audio_obj and not isinstance(audio_obj, Exception):
            text, err = transcribe_audio(audio_obj)
            if text:
                st.success(f"🗣️ You asked: {text}")
                st.session_state.last_q = text
                try:
                    sql_text, df, answer = run_query(text)
                    st.subheader("📊 Query Results")
                    st.dataframe(df, width="stretch")
                    if show_sql:
                        with st.expander("📄 View Query"):
                            st.code(sql_text, language="sql")
                    st.subheader("📝 Bot Answer")
                    st.write(answer)
                    st.session_state.last_a = answer
                    speak_text(answer)
                    log_prompt_to_csv(text, sql_text)
                except Exception as e:
                    st.error(f"❌ Processing error: {e}")
            else:
                st.error(err or "❌ Could not transcribe audio.")
        else:
            st.error("No audio captured.")

# Show last Q&A
if st.session_state.last_q:
    st.markdown("### Last Q&A")
    st.markdown(f"**Q:** {st.session_state.last_q}")
    if st.session_state.last_a:
        st.markdown(f"**A:** {st.session_state.last_a}")
