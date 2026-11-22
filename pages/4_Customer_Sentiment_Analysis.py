
import io
import hashlib
import logging
import textwrap

import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

from auth.login_manager import login_manager
from auth.auth_guard import protect_page


# =========================================================
# 1. STREAMLIT CONFIGURATION
# =========================================================

st.set_page_config(
    page_title="Customer Sentiment Intelligence",
    page_icon="📝",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Existing authentication integrations
login_manager()
protect_page()

from auth.ui_guard import apply_sidebar_visibility

apply_sidebar_visibility()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)

MAX_FILE_SIZE_MB = 50
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024


# =========================================================
# 2. SESSION STATE INITIALIZATION
# =========================================================

SESSION_DEFAULTS = {
    "df_file": None,
    "analysis_results": None,
    "analysis_complete": False,
    "analysis_mode": None,
    "source_file_name": None,
    "source_file_hash": None,
    "analysis_column": None,
    "analysis_history": []
}


def initialize_session():

    for key, default_value in SESSION_DEFAULTS.items():

        if key not in st.session_state:

            if isinstance(default_value, list):
                st.session_state[key] = default_value.copy()
            else:
                st.session_state[key] = default_value


initialize_session()


# =========================================================
# 3. CENTRALIZED SESSION CLEANUP
# =========================================================

def clear_analysis_session(clear_upload_widget=False):
    """
    Clears all customer sentiment analysis state.

    clear_upload_widget=True must only be used before
    the file uploader widget is instantiated.
    """

    for key, default_value in SESSION_DEFAULTS.items():

        if isinstance(default_value, list):
            st.session_state[key] = default_value.copy()

        elif isinstance(default_value, dict):
            st.session_state[key] = default_value.copy()

        else:
            st.session_state[key] = default_value

    # Clear uploader only before widget initialization.
    if clear_upload_widget:

        if "customer_sentiment_upload" in st.session_state:
            st.session_state.customer_sentiment_upload = None

    logger.info(
        "Customer sentiment analysis session cleared."
    )


# =========================================================
# 4. EXECUTIVE DASHBOARD CSS
# =========================================================

st.markdown(
    textwrap.dedent("""
    <style>

    /* GLOBAL THEME */

    .stApp {
        background-color: #F7F9FC;
    }

    [data-testid="stHeader"] {
        background: transparent;
    }

    [data-testid="stSidebar"] {
        background-color: #FFFFFF;
        border-right: 1px solid #E8ECF2;
    }

    /* MAIN HEADER */

    .main-header {
        background: linear-gradient(
            120deg,
            #FFFFFF,
            #F0F5FF
        );

        border: 1px solid #E2E8F0;
        border-radius: 14px;

        padding: 24px 28px;
        margin-bottom: 22px;
    }

    .main-header h1 {
        color: #172B4D;
        font-size: 30px;
        font-weight: 700;
        margin: 0 0 5px 0;
    }

    .main-header p {
        color: #64748B;
        font-size: 14px;
        margin: 0;
    }

    /* KPI CARDS - UNIFORM ALIGNMENT */

    div[data-testid="stMetric"] {
        background-color: #FFFFFF;

        border: 1px solid #E5EAF1;
        border-radius: 12px;

        box-shadow: 0 2px 8px
            rgba(20, 40, 80, 0.03);

        height: 115px !important;
        min-height: 115px !important;
        max-height: 115px !important;

        width: 100%;
        box-sizing: border-box;

        padding: 15px !important;

        display: block !important;

        overflow: hidden !important;
    }

    /* KPI LABEL */

    div[data-testid="stMetricLabel"] {
        color: #64748B;
        min-height: 22px;
        margin-bottom: 5px;
    }

    /* KPI VALUE */

    div[data-testid="stMetricValue"] {
        color: #172B4D;
        font-weight: 700;
        line-height: 1.3;
        margin-bottom: 0;
    }

    /*
       No delta indicators.
       No green/red badges.
       No percentage arrows.
    */

    /* BUTTONS */

    div.stButton > button {
        border-radius: 8px;
        font-weight: 600;
    }

    div.stDownloadButton > button {
        border-radius: 8px;
        font-weight: 600;
    }

    /* FILE UPLOADER */

    div[data-testid="stFileUploader"] {
        background: #FFFFFF;
        border: 1px dashed #A8B8CC;
        border-radius: 12px;
        padding: 12px;
    }

    /* SECTION HEADINGS */

    .section-label {
        color: #172B4D;
        font-size: 19px;
        font-weight: 700;
        margin-top: 10px;
        margin-bottom: 12px;
    }

    .info-text {
        color: #64748B;
        font-size: 13px;
    }

    /* DATAFRAME */

    div[data-testid="stDataFrame"] {
        border: 1px solid #E5EAF1;
        border-radius: 10px;
        overflow: hidden;
    }

    </style>
    """),
    unsafe_allow_html=True
)


# =========================================================
# 5. CACHED MODEL LOADING
# =========================================================

@st.cache_resource(show_spinner=False)
def load_vader():

    import nltk

    from nltk.sentiment import SentimentIntensityAnalyzer

    try:
        nltk.data.find("sentiment/vader_lexicon.zip")

    except LookupError:
        nltk.download("vader_lexicon", quiet=True)

    return SentimentIntensityAnalyzer()


@st.cache_resource(show_spinner=False)
def load_transformer():

    import torch

    from transformers import pipeline

    device = 0 if torch.cuda.is_available() else -1

    logger.info(
        "Loading CardiffNLP Transformer model."
    )

    return pipeline(
        "sentiment-analysis",
        model="cardiffnlp/twitter-roberta-base-sentiment",
        framework="pt",
        device=device
    )


# =========================================================
# 6. FILE VALIDATION
# =========================================================

def validate_dataframe(df):

    if df is None or df.empty:
        raise ValueError(
            "The uploaded file contains no records."
        )

    if len(df.columns) == 0:
        raise ValueError(
            "No columns were found."
        )

    if len(df) > 500000:
        raise ValueError(
            "Maximum supported records: 500,000."
        )

    if len(df.columns) > 200:
        raise ValueError(
            "The file contains too many columns."
        )

    df = df.dropna(
        how="all"
    ).dropna(
        axis=1,
        how="all"
    )

    if df.empty:
        raise ValueError(
            "The uploaded file contains only empty records."
        )

    return df.reset_index(drop=True)


def read_uploaded_file(uploaded_file):

    file_name = uploaded_file.name.lower()

    file_bytes = uploaded_file.getvalue()

    if len(file_bytes) > MAX_FILE_SIZE_BYTES:
        raise ValueError(
            f"Maximum file size is {MAX_FILE_SIZE_MB} MB."
        )

    if not file_bytes:
        raise ValueError(
            "The uploaded file is empty."
        )

    if file_name.endswith(".csv"):

        df = pd.read_csv(
            io.BytesIO(file_bytes)
        )

    elif file_name.endswith(".xlsx"):

        df = pd.read_excel(
            io.BytesIO(file_bytes),
            engine="openpyxl"
        )

    else:

        raise ValueError(
            "Unsupported file format."
        )

    return validate_dataframe(df)


# =========================================================
# 7. VADER SENTIMENT ANALYSIS
# =========================================================

def run_vader_analysis(df, text_column):

    sia = load_vader()

    texts = (
        df[text_column]
        .fillna("")
        .astype(str)
        .tolist()
    )

    sentiments = []
    confidence_scores = []

    progress = st.progress(0)
    status = st.empty()

    total = len(texts)

    for index, text in enumerate(texts):

        if not text.strip():

            sentiments.append("NEUTRAL")
            confidence_scores.append(0.0)

        else:

            # Calculate polarity only once per record.
            score = sia.polarity_scores(text)["compound"]

            if score >= 0.05:
                sentiment = "POSITIVE"

            elif score <= -0.05:
                sentiment = "NEGATIVE"

            else:
                sentiment = "NEUTRAL"

            sentiments.append(sentiment)
            confidence_scores.append(abs(score))

        if (
            (index + 1) % 100 == 0
            or index + 1 == total
        ):

            progress.progress(
                (index + 1) / total
            )

    status.success(
        "VADER analysis completed."
    )

    result = df.copy()

    result["Sentiment"] = sentiments
    result["Confidence"] = confidence_scores
    result["Analysis_Model"] = "VADER"

    return result


# =========================================================
# 8. TRANSFORMER SENTIMENT ANALYSIS
# =========================================================

def run_transformer_analysis(
    df,
    text_column,
    batch_size
):

    sentiment_pipeline = load_transformer()

    texts = (
        df[text_column]
        .fillna("")
        .astype(str)
        .tolist()
    )

    total = len(texts)

    sentiments = ["NEUTRAL"] * total
    confidence_scores = [0.0] * total

    valid_indices = [
        index
        for index, text in enumerate(texts)
        if text.strip()
    ]

    total_valid = len(valid_indices)

    progress = st.progress(0)
    status = st.empty()

    label_mapping = {
        "LABEL_0": "NEGATIVE",
        "LABEL_1": "NEUTRAL",
        "LABEL_2": "POSITIVE"
    }

    if total_valid == 0:

        progress.progress(1.0)

        status.info(
            "No non-empty feedback records found."
        )

    else:

        for start in range(
            0,
            total_valid,
            batch_size
        ):

            batch_indices = valid_indices[
                start:start + batch_size
            ]

            batch_texts = [
                texts[index]
                for index in batch_indices
            ]

            predictions = sentiment_pipeline(
                batch_texts,
                truncation=True,
                max_length=512,
                batch_size=batch_size
            )

            for index, prediction in zip(
                batch_indices,
                predictions
            ):

                label = prediction["label"]

                sentiment = label_mapping.get(
                    label,
                    label.upper()
                )

                sentiments[index] = sentiment

                confidence_scores[index] = float(
                    prediction["score"]
                )

            completed = min(
                start + batch_size,
                total_valid
            )

            progress.progress(
                completed / total_valid
            )

            status.info(
                f"Processed {completed:,} of "
                f"{total_valid:,} feedback records."
            )

        status.success(
            "Transformer analysis completed."
        )

    result = df.copy()

    result["Sentiment"] = sentiments
    result["Confidence"] = confidence_scores
    result["Analysis_Model"] = "Transformer"

    return result


# =========================================================
# 9. EXCEL EXPORT
# =========================================================

def export_to_excel(df):

    output = io.BytesIO()

    with pd.ExcelWriter(
        output,
        engine="openpyxl"
    ) as writer:

        df.to_excel(
            writer,
            index=False,
            sheet_name="Sentiment Results"
        )

        worksheet = writer.sheets[
            "Sentiment Results"
        ]

        worksheet.freeze_panes = "A2"

        worksheet.auto_filter.ref = (
            worksheet.dimensions
        )

        for column_cells in worksheet.columns:

            max_length = max(
                len(str(cell.value or ""))
                for cell in column_cells
            )

            worksheet.column_dimensions[
                column_cells[0].column_letter
            ].width = min(
                max_length + 2,
                45
            )

    return output.getvalue()


# =========================================================
# 10. SIDEBAR
# =========================================================

with st.sidebar:

    st.markdown(
        "## 📝 Sentiment Intelligence"
    )

    st.caption(
        "Customer Analytics Platform"
    )

    st.divider()

    st.markdown(
        "### User Information"
    )

    st.write(
        f"👤 **{st.session_state.get('username', 'User')}**"
    )

    st.divider()

    st.markdown(
        "### Analysis Engines"
    )

    st.markdown(
        """
        - ⚡ **VADER:** Fast sentiment analysis
        - 🧠 **Transformer:** Context-aware analysis
        """
    )

    st.divider()

    st.markdown(
        "### Supported Files"
    )

    st.caption("CSV and XLSX")

    st.caption(
        f"Maximum file size: {MAX_FILE_SIZE_MB} MB"
    )

    st.divider()

    if st.button(
        "🗑️ Reset Analysis",
        use_container_width=True
    ):

        clear_analysis_session(
            clear_upload_widget=True
        )

        st.rerun()


# =========================================================
# 11. MAIN PAGE HEADER
# =========================================================

header_html = textwrap.dedent("""
<div class="main-header">
    <h1>Customer Sentiment Intelligence</h1>
    <p>
        Enterprise customer feedback analytics,
        sentiment classification and business insights.
    </p>
</div>
""").strip()

st.markdown(
    header_html,
    unsafe_allow_html=True
)


# =========================================================
# 12. FILE UPLOAD AND AUTOMATIC SESSION CLEANUP
# =========================================================

st.markdown(
    '<div class="section-label">📂 Data Management</div>',
    unsafe_allow_html=True
)

uploaded_file = st.file_uploader(
    "Upload customer feedback dataset",
    type=["csv", "xlsx"],
    help="Upload a CSV or Excel file.",
    key="customer_sentiment_upload"
)


# ---------------------------------------------------------
# DETECT FILE REMOVAL
# ---------------------------------------------------------

if uploaded_file is None:

    has_existing_session = (
        st.session_state.df_file is not None
        or st.session_state.analysis_results is not None
        or st.session_state.analysis_complete
        or st.session_state.source_file_hash is not None
    )

    if has_existing_session:

        logger.info(
            "Uploaded file removed. Clearing analysis session."
        )

        clear_analysis_session()

        st.rerun()


# ---------------------------------------------------------
# PROCESS NEW UPLOADED FILE
# ---------------------------------------------------------

else:

    try:

        file_bytes = uploaded_file.getvalue()

        file_hash = hashlib.sha256(
            file_bytes
        ).hexdigest()

        if file_hash != st.session_state.source_file_hash:

            # Clear previous dataset and analysis.
            clear_analysis_session()

            with st.spinner(
                "Loading and validating dataset..."
            ):

                df = read_uploaded_file(
                    uploaded_file
                )

                st.session_state.df_file = df

                st.session_state.source_file_name = (
                    uploaded_file.name
                )

                st.session_state.source_file_hash = (
                    file_hash
                )

            logger.info(
                "Dataset loaded: %s | Rows: %s | Columns: %s",
                uploaded_file.name,
                df.shape[0],
                df.shape[1]
            )

            st.success(
                f"Dataset loaded successfully: "
                f"{df.shape[0]:,} records and "
                f"{df.shape[1]} columns."
            )

    except Exception as error:

        logger.exception(
            "File loading failed."
        )

        clear_analysis_session()

        st.error(
            f"Unable to load dataset: {error}"
        )


# =========================================================
# 13. DATASET OVERVIEW
# =========================================================

if st.session_state.df_file is not None:

    df = st.session_state.df_file

    st.markdown(
        "### Dataset Overview"
    )

    col1, col2, col3, col4 = st.columns(4)

    col1.metric(
        "Total Records",
        f"{len(df):,}"
    )

    col2.metric(
        "Total Columns",
        len(df.columns)
    )

    col3.metric(
        "Empty Records",
        int(df.isna().all(axis=1).sum())
    )

    col4.metric(
        "Duplicate Records",
        int(df.duplicated().sum())
    )

    with st.expander(
        "View Uploaded Dataset",
        expanded=False
    ):

        preview_count = st.select_slider(
            "Records to display",
            options=[10, 25, 50, 100, 250],
            value=25
        )

        st.dataframe(
            df.head(preview_count),
            use_container_width=True,
            hide_index=True
        )


# =========================================================
# 14. ANALYSIS CONFIGURATION
# =========================================================

if st.session_state.df_file is not None:

    df = st.session_state.df_file

    st.divider()

    st.markdown(
        '<div class="section-label">⚙️ Analysis Configuration</div>',
        unsafe_allow_html=True
    )

    available_columns = [
        column
        for column in df.columns
        if df[column].notna().any()
    ]

    if not available_columns:

        st.warning(
            "No usable columns were found."
        )

    else:

        with st.form(
            "sentiment_analysis_form"
        ):

            col1, col2 = st.columns(2)

            with col1:

                text_column = st.selectbox(
                    "Select Customer Feedback Column",
                    options=available_columns
                )

            with col2:

                analysis_mode = st.radio(
                    "Select Analysis Engine",
                    options=[
                        "Fast (VADER)",
                        "Accurate (Transformers)"
                    ],
                    horizontal=True
                )

            batch_size = st.select_slider(
                "Transformer Batch Size",
                options=[8, 16, 32, 64],
                value=32,
                help=(
                    "Higher batch sizes may improve "
                    "throughput but require more memory."
                )
            )

            submitted = st.form_submit_button(
                "🔍 Run Sentiment Analysis",
                type="primary",
                use_container_width=True
            )

        if submitted:

            try:

                if analysis_mode == "Fast (VADER)":

                    with st.spinner(
                        "Running VADER analysis..."
                    ):

                        results = run_vader_analysis(
                            df.copy(),
                            text_column
                        )

                else:

                    with st.spinner(
                        "Initializing Transformer analysis..."
                    ):

                        results = run_transformer_analysis(
                            df.copy(),
                            text_column,
                            batch_size
                        )

                st.session_state.analysis_results = results

                st.session_state.analysis_complete = True

                st.session_state.analysis_mode = analysis_mode

                st.session_state.analysis_column = text_column

                st.session_state.analysis_history.append({
                    "file": st.session_state.source_file_name,
                    "model": analysis_mode,
                    "records": len(results),
                    "column": text_column
                })

                logger.info(
                    "Analysis completed | Model: %s | Records: %s",
                    analysis_mode,
                    len(results)
                )

                st.success(
                    "Sentiment analysis completed successfully!"
                )

            except Exception as error:

                logger.exception(
                    "Sentiment analysis failed."
                )

                st.error(
                    f"Sentiment analysis failed: {error}"
                )


# =========================================================
# 15. EXECUTIVE ANALYTICS DASHBOARD
# =========================================================

if (
    st.session_state.analysis_complete
    and st.session_state.analysis_results is not None
):

    results = st.session_state.analysis_results.copy()

    text_column = st.session_state.analysis_column

    st.divider()

    st.markdown(
        '<div class="section-label">📊 Executive Analytics Dashboard</div>',
        unsafe_allow_html=True
    )

    # -----------------------------------------------------
    # KPI CALCULATIONS
    # -----------------------------------------------------

    total_records = len(results)

    sentiment_counts = (
        results["Sentiment"]
        .value_counts()
        .reindex(
            ["POSITIVE", "NEGATIVE", "NEUTRAL"],
            fill_value=0
        )
    )

    positive = int(sentiment_counts["POSITIVE"])
    negative = int(sentiment_counts["NEGATIVE"])
    neutral = int(sentiment_counts["NEUTRAL"])

    positive_pct = (
        positive / total_records * 100
        if total_records else 0
    )

    negative_pct = (
        negative / total_records * 100
        if total_records else 0
    )

    neutral_pct = (
        neutral / total_records * 100
        if total_records else 0
    )

    avg_confidence = (
        results["Confidence"].mean() * 100
        if total_records else 0
    )

    # -----------------------------------------------------
    # KPI CARDS - NO COLORED INDICATORS
    # -----------------------------------------------------

    k1, k2, k3, k4, k5 = st.columns(
        5,
        gap="medium"
    )

    k1.metric(
        label="Total Feedback",
        value=f"{total_records:,}"
    )

    k2.metric(
        label=f"Positive ({positive_pct:.1f}%)",
        value=f"{positive:,}"
    )

    k3.metric(
        label=f"Negative ({negative_pct:.1f}%)",
        value=f"{negative:,}"
    )

    k4.metric(
        label=f"Neutral ({neutral_pct:.1f}%)",
        value=f"{neutral:,}"
    )

    k5.metric(
        label="Avg. Confidence",
        value=f"{avg_confidence:.1f}%"
    )

    # -----------------------------------------------------
    # CHART COLORS
    # -----------------------------------------------------

    chart_colors = {
        "POSITIVE": "#16A34A",
        "NEGATIVE": "#DC5252",
        "NEUTRAL": "#94A3B8"
    }

    # -----------------------------------------------------
    # SENTIMENT DISTRIBUTION
    # -----------------------------------------------------

    st.markdown(
        "### Sentiment Distribution"
    )

    chart1, chart2 = st.columns(2)

    with chart1:

        fig_donut = go.Figure(
            data=[
                go.Pie(
                    labels=sentiment_counts.index.tolist(),

                    values=sentiment_counts.values.tolist(),

                    hole=0.65,

                    marker=dict(
                        colors=[
                            chart_colors[label]
                            for label in sentiment_counts.index
                        ]
                    ),

                    textinfo="label+percent",

                    hovertemplate=(
                        "%{label}<br>"
                        "Records: %{value}<br>"
                        "Percentage: %{percent}"
                        "<extra></extra>"
                    )
                )
            ]
        )

        fig_donut.update_layout(
            title="Sentiment Composition",
            height=380,
            margin=dict(
                t=60,
                b=30,
                l=20,
                r=20
            ),
            paper_bgcolor="white",
            plot_bgcolor="white",
            showlegend=False
        )

        st.plotly_chart(
            fig_donut,
            use_container_width=True
        )

    with chart2:

        chart_df = pd.DataFrame({
            "Sentiment": sentiment_counts.index,
            "Count": sentiment_counts.values
        })

        fig_bar = px.bar(
            chart_df,
            x="Sentiment",
            y="Count",
            color="Sentiment",
            color_discrete_map=chart_colors,
            text="Count",
            title="Feedback Volume by Sentiment"
        )

        fig_bar.update_layout(
            height=380,
            showlegend=False,
            paper_bgcolor="white",
            plot_bgcolor="white",
            margin=dict(
                t=60,
                b=30,
                l=20,
                r=20
            )
        )

        fig_bar.update_traces(
            textposition="outside"
        )

        st.plotly_chart(
            fig_bar,
            use_container_width=True
        )

    # -----------------------------------------------------
    # CONFIDENCE ANALYSIS
    # -----------------------------------------------------

    st.markdown(
        "### Confidence Analysis"
    )

    fig_confidence = px.histogram(
        results,
        x="Confidence",
        color="Sentiment",
        nbins=20,
        color_discrete_map=chart_colors,
        title="Distribution of Sentiment Confidence Scores"
    )

    fig_confidence.update_layout(
        height=350,
        paper_bgcolor="white",
        plot_bgcolor="white",
        xaxis_title="Confidence Score",
        yaxis_title="Number of Feedback Records"
    )

    st.plotly_chart(
        fig_confidence,
        use_container_width=True
    )

    # -----------------------------------------------------
    # FEEDBACK EXPLORER
    # -----------------------------------------------------

    st.divider()

    st.markdown(
        '<div class="section-label">🔎 Feedback Explorer</div>',
        unsafe_allow_html=True
    )

    filter1, filter2 = st.columns([2, 1])

    with filter1:

        search_text = st.text_input(
            "Search Customer Feedback",
            placeholder="Search keywords or feedback..."
        )

    with filter2:

        selected_sentiments = st.multiselect(
            "Filter Sentiment",
            options=[
                "POSITIVE",
                "NEGATIVE",
                "NEUTRAL"
            ],
            default=[
                "POSITIVE",
                "NEGATIVE",
                "NEUTRAL"
            ]
        )

    filtered_results = results[
        results["Sentiment"].isin(
            selected_sentiments
        )
    ].copy()

    if search_text.strip():

        filtered_results = filtered_results[
            filtered_results[text_column]
            .fillna("")
            .astype(str)
            .str.contains(
                search_text,
                case=False,
                regex=False
            )
        ]

    st.caption(
        f"Displaying {len(filtered_results):,} "
        f"of {total_records:,} analyzed records."
    )

    st.dataframe(
        filtered_results,
        use_container_width=True,
        hide_index=True,
        height=450
    )

    # -----------------------------------------------------
    # EXPORT RESULTS
    # -----------------------------------------------------

    st.divider()

    st.markdown(
        "### 📥 Export Analysis Results"
    )

    st.caption(
        "Exports contain the records currently displayed "
        "after applying search and sentiment filters."
    )

    csv_data = filtered_results.to_csv(
        index=False
    ).encode("utf-8-sig")

    col_csv, col_excel = st.columns(2)

    with col_csv:

        st.download_button(
            label="📄 Download CSV",
            data=csv_data,
            file_name="customer_sentiment_results.csv",
            mime="text/csv",
            use_container_width=True
        )

    with col_excel:

        try:

            excel_data = export_to_excel(
                filtered_results
            )

            st.download_button(
                label="📊 Download Excel",
                data=excel_data,
                file_name="customer_sentiment_results.xlsx",
                mime=(
                    "application/vnd.openxmlformats-officedocument."
                    "spreadsheetml.sheet"
                ),
                use_container_width=True
            )

        except Exception:

            logger.exception(
                "Excel export failed."
            )

            st.error(
                "Unable to generate Excel export. "
                "Check the openpyxl installation."
            )


# =========================================================
# 16. EMPTY STATES
# =========================================================

elif st.session_state.df_file is None:

    st.info(
        "👋 Welcome! Upload a customer feedback CSV "
        "or Excel file to get started."
    )

elif not st.session_state.analysis_complete:

    st.info(
        "Your dataset is ready. Select the feedback column "
        "and analysis engine, then run sentiment analysis."
    )


# =========================================================
# 17. FOOTER
# =========================================================

footer_html = textwrap.dedent("""
<div style="
    text-align: center;
    color: #94A3B8;
    font-size: 12px;
    padding: 10px;
">
    Customer Sentiment Intelligence |
    Enterprise Analytics Platform
</div>
""").strip()

st.markdown(
    footer_html,
    unsafe_allow_html=True
)
