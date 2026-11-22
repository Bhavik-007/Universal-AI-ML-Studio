
# pages/1_Forecast_Model.py

import io
import logging

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from sklearn.linear_model import LinearRegression

from auth.ui_guard import apply_sidebar_visibility
from auth.login_manager import login_manager
from auth.auth_guard import protect_page


# ============================================================
# PAGE CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="Forecast Model",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

logger = logging.getLogger(__name__)


# ============================================================
# AUTHENTICATION
# ============================================================

login_manager()
protect_page()

apply_sidebar_visibility()


# ============================================================
# PAGE STYLING
# ============================================================

st.markdown(
    """
    <style>
        .forecast-header {
            font-size: 28px;
            font-weight: 700;
            margin-bottom: 4px;
        }

        .forecast-subtitle {
            color: #808495;
            font-size: 14px;
            margin-bottom: 20px;
        }

        div[data-testid="stMetric"] {
            background-color: var(--secondary-background-color);
            padding: 15px;
            border-radius: 10px;
            border: 1px solid rgba(128,128,128,0.15);
        }

        .section-header {
            font-size: 19px;
            font-weight: 600;
            margin-top: 12px;
            margin-bottom: 10px;
        }
    </style>
    """,
    unsafe_allow_html=True
)


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:

    st.markdown("## 📈 Forecast Model")
    st.caption("Time Series Forecasting")

    st.divider()

    st.markdown(
        f"👤 **{st.session_state.get('username', 'User')}**"
    )

    st.divider()

    st.caption("FORECASTING ENGINE")
    st.markdown("Linear Regression")

    st.caption("SUPPORTED FREQUENCIES")
    st.markdown("- Daily\n- Monthly")


# ============================================================
# DATA LOADING
# ============================================================

@st.cache_data(show_spinner=False)
def load_data(file_bytes: bytes, file_name: str):

    """Load and cache uploaded CSV data."""

    return pd.read_csv(io.BytesIO(file_bytes))


# ============================================================
# DATA PREPARATION
# ============================================================

def prepare_data(
    df,
    datetime_col,
    aggregation
):

    """Clean dates and aggregate numerical data."""

    df = df.copy()

    if df.empty:
        raise ValueError("The uploaded CSV file is empty.")

    if datetime_col not in df.columns:
        raise ValueError("Selected date column does not exist.")

    df[datetime_col] = pd.to_datetime(
        df[datetime_col],
        errors="coerce"
    )

    df = df.dropna(subset=[datetime_col])

    if df.empty:
        raise ValueError(
            "No valid date records found in the selected column."
        )

    df = df.sort_values(datetime_col)

    numeric_cols = df.select_dtypes(
        include=[np.number]
    ).columns.tolist()

    if not numeric_cols:
        raise ValueError(
            "No numerical columns found in the uploaded dataset."
        )

    df = df[
        [datetime_col] + numeric_cols
    ]

    df[numeric_cols] = df[numeric_cols].replace(
        [np.inf, -np.inf],
        np.nan
    )

    return df, numeric_cols


# ============================================================
# TIME SERIES AGGREGATION
# ============================================================

def aggregate_data(
    df,
    datetime_col,
    frequency,
    aggregation
):

    """Aggregate data using the selected frequency."""

    df = df.copy()

    df = df.set_index(datetime_col)

    if frequency == "Monthly":
        resample_frequency = "ME"
    else:
        resample_frequency = "D"

    resampler = df.resample(resample_frequency)

    if aggregation == "Sum":
        result = resampler.sum(min_count=1)

    elif aggregation == "Mean":
        result = resampler.mean()

    elif aggregation == "Max":
        result = resampler.max()

    else:
        raise ValueError("Unsupported aggregation method.")

    return result.reset_index()


# ============================================================
# FORECAST ENGINE
# ============================================================

def prepare_forecast(
    df,
    datetime_col,
    target,
    future_steps,
    frequency
):

    """Generate a linear regression forecast."""

    working_df = df.copy()

    working_df = working_df.sort_values(
        datetime_col
    ).reset_index(drop=True)

    if target not in working_df.columns:
        raise ValueError(
            f"Target column '{target}' was not found."
        )

    working_df["TimeIndex"] = np.arange(
        len(working_df)
    )

    working_df[target] = pd.to_numeric(
        working_df[target],
        errors="coerce"
    )

    valid_mask = np.isfinite(
        working_df[target].to_numpy(dtype=float)
    )

    training_df = working_df.loc[valid_mask].copy()

    if len(training_df) < 3:
        raise ValueError(
            f"{target}: At least 3 valid observations are "
            "required for forecasting."
        )

    X = training_df[["TimeIndex"]].to_numpy()

    y = training_df[target].to_numpy(dtype=float)

    model = LinearRegression()

    model.fit(X, y)

    future_index = np.arange(
        len(working_df),
        len(working_df) + future_steps
    ).reshape(-1, 1)

    predictions = model.predict(future_index)

    if frequency == "Monthly":
        freq = "ME"
    else:
        freq = "D"

    last_date = working_df[datetime_col].max()

    future_dates = pd.date_range(
        start=last_date,
        periods=future_steps + 1,
        freq=freq
    )[1:]

    forecast_df = pd.DataFrame({

        datetime_col: future_dates,

        f"Forecast_{target}": predictions

    })

    return forecast_df, training_df, model


# ============================================================
# CHART GENERATION
# ============================================================

def create_forecast_chart(
    training_df,
    forecast_df,
    datetime_col,
    target
):

    """Generate an interactive Plotly forecast chart."""

    forecast_column = f"Forecast_{target}"

    fig = go.Figure()

    # Historical actual data

    fig.add_trace(
        go.Scatter(
            x=training_df[datetime_col],
            y=training_df[target],
            mode="lines+markers",
            name="Actual",
            line=dict(
                color="#269B83",
                width=2.5
            ),
            hovertemplate=(
                "Date: %{x|%Y-%m-%d}<br>"
                "Actual: %{y:,.2f}"
                "<extra></extra>"
            )
        )
    )

    # Forecast data

    fig.add_trace(
        go.Scatter(
            x=forecast_df[datetime_col],
            y=forecast_df[forecast_column],
            mode="lines+markers",
            name="Forecast",
            line=dict(
                color="#4789D9",
                width=2.5,
                dash="dash"
            ),
            hovertemplate=(
                "Date: %{x|%Y-%m-%d}<br>"
                "Forecast: %{y:,.2f}"
                "<extra></extra>"
            )
        )
    )

    fig.update_layout(

        title=dict(
            text=f"Actual vs Forecast: {target}",
            x=0.02
        ),

        xaxis_title="Date",

        yaxis_title=target,

        template="plotly_white",

        height=420,

        hovermode="x unified",

        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        ),

        margin=dict(
            l=20,
            r=20,
            t=65,
            b=20
        )
    )

    fig.update_xaxes(
        showgrid=True,
        gridcolor="rgba(128,128,128,0.15)"
    )

    fig.update_yaxes(
        showgrid=True,
        gridcolor="rgba(128,128,128,0.15)"
    )

    return fig


# ============================================================
# MAIN PAGE HEADER
# ============================================================

st.markdown(
    '<div class="forecast-header">'
    '📈 Forecast Model'
    '</div>',
    unsafe_allow_html=True
)

st.markdown(
    '<div class="forecast-subtitle">'
    'Analyze historical trends and generate '
    'future projections using machine learning.'
    '</div>',
    unsafe_allow_html=True
)

st.divider()


# ============================================================
# FILE UPLOAD
# ============================================================

st.markdown(
    "### 📂 Dataset Upload"
)

uploaded_file = st.file_uploader(
    "Upload your CSV dataset",
    type=["csv"],
    help="Upload a CSV containing a date column and numerical metrics."
)


# ============================================================
# FORECAST PROCESSING
# ============================================================

if uploaded_file is not None:

    try:

        with st.spinner("Loading and validating dataset..."):

            file_bytes = uploaded_file.getvalue()

            df = load_data(
                file_bytes,
                uploaded_file.name
            )

        if df.empty:
            st.error("Uploaded CSV contains no records.")
            st.stop()

        # ----------------------------------------------------
        # DATE COLUMN SELECTION
        # ----------------------------------------------------

        date_candidates = [
            col for col in df.columns
            if (
                "date" in col.lower()
                or "time" in col.lower()
            )
        ]

        default_date = (
            date_candidates[0]
            if date_candidates
            else df.columns[0]
        )

        st.markdown("### ⚙️ Forecast Configuration")

        config1, config2, config3 = st.columns(3)

        with config1:

            datetime_col = st.selectbox(
                "Date / Datetime Column",
                options=df.columns.tolist(),
                index=df.columns.tolist().index(default_date)
            )

        with config2:

            frequency = st.selectbox(
                "Forecast Frequency",
                ["Monthly", "Daily"],
                index=0
            )

        with config3:

            aggregation = st.selectbox(
                "Aggregation Method",
                ["Sum", "Mean", "Max"],
                index=0
            )

        # ----------------------------------------------------
        # DATA VALIDATION
        # ----------------------------------------------------

        df, numeric_cols = prepare_data(
            df,
            datetime_col,
            aggregation
        )

        if not numeric_cols:

            st.error(
                "No numerical columns available."
            )

            st.stop()

        # ----------------------------------------------------
        # AGGREGATION
        # ----------------------------------------------------

        df = aggregate_data(
            df,
            datetime_col,
            frequency,
            aggregation
        )

        if df.empty:

            st.error(
                "No valid records available after aggregation."
            )

            st.stop()

        # ----------------------------------------------------
        # FORECAST SETTINGS
        # ----------------------------------------------------

        st.markdown("### 🔮 Forecast Settings")

        settings1, settings2 = st.columns(2)

        with settings1:

            selected_targets = st.multiselect(
                "Select Metrics to Forecast",
                options=numeric_cols,
                default=[numeric_cols[0]]
            )

        with settings2:

            if frequency == "Monthly":

                future_steps = st.slider(
                    "Forecast Horizon (Months)",
                    min_value=1,
                    max_value=36,
                    value=6
                )

            else:

                future_steps = st.slider(
                    "Forecast Horizon (Days)",
                    min_value=1,
                    max_value=365,
                    value=30
                )

        # ----------------------------------------------------
        # DATASET OVERVIEW
        # ----------------------------------------------------

        st.divider()

        st.markdown("### 📊 Dataset Overview")

        metric1, metric2, metric3 = st.columns(3)

        with metric1:

            st.metric(
                "Total Observations",
                f"{len(df):,}"
            )

        with metric2:

            st.metric(
                "Numerical Metrics",
                len(numeric_cols)
            )

        with metric3:

            st.metric(
                "Forecast Periods",
                future_steps
            )

        st.caption(
            f"Date range: "
            f"{df[datetime_col].min():%Y-%m-%d}"
            f" to "
            f"{df[datetime_col].max():%Y-%m-%d}"
        )

        # ----------------------------------------------------
        # FORECAST EXECUTION
        # ----------------------------------------------------

        if not selected_targets:

            st.info(
                "Please select at least one metric to forecast."
            )

        else:

            st.divider()

            st.markdown(
                "### 📈 Forecast Results"
            )

            for target in selected_targets:

                with st.container(border=True):

                    st.markdown(
                        f"#### 🔎 {target}"
                    )

                    try:

                        forecast_df, training_df, model = (
                            prepare_forecast(
                                df,
                                datetime_col,
                                target,
                                future_steps,
                                frequency
                            )
                        )

                        forecast_column = (
                            f"Forecast_{target}"
                        )

                        # ------------------------------------
                        # SUMMARY METRICS
                        # ------------------------------------

                        last_actual = float(
                            training_df[target].iloc[-1]
                        )

                        next_forecast = float(
                            forecast_df[
                                forecast_column
                            ].iloc[0]
                        )

                        final_forecast = float(
                            forecast_df[
                                forecast_column
                            ].iloc[-1]
                        )

                        if last_actual != 0:

                            growth = (
                                (
                                    next_forecast - last_actual
                                ) / abs(last_actual)
                            ) * 100

                            growth_value = f"{growth:+.2f}%"

                        else:

                            growth_value = "N/A"

                        col1, col2, col3 = st.columns(3)

                        with col1:

                            st.metric(
                                "Last Actual",
                                f"{last_actual:,.2f}"
                            )

                        with col2:

                            st.metric(
                                "Next Forecast",
                                f"{next_forecast:,.2f}"
                            )

                        with col3:

                            st.metric(
                                "Forecast Change",
                                growth_value
                            )

                        # ------------------------------------
                        # FORECAST CHART
                        # ------------------------------------

                        fig = create_forecast_chart(
                            training_df,
                            forecast_df,
                            datetime_col,
                            target
                        )

                        st.plotly_chart(
                            fig,
                            use_container_width=True,
                            key=f"forecast_chart_{target}"
                        )

                        # ------------------------------------
                        # FORECAST TABLE
                        # ------------------------------------

                        with st.expander(
                            "📋 View Forecast Data",
                            expanded=False
                        ):

                            st.dataframe(
                                forecast_df,
                                use_container_width=True,
                                hide_index=True
                            )

                            csv_data = (
                                forecast_df.to_csv(
                                    index=False
                                ).encode("utf-8")
                            )

                            st.download_button(

                                label="⬇️ Download Forecast CSV",

                                data=csv_data,

                                file_name=(
                                    f"forecast_{target}.csv"
                                ),

                                mime="text/csv",

                                key=f"download_{target}"
                            )

                    except Exception as target_error:

                        logger.exception(
                            "Forecast failed for %s",
                            target
                        )

                        st.warning(
                            f"Unable to forecast {target}: "
                            f"{target_error}"
                        )

    except Exception as e:

        logger.exception(
            "Forecast Model processing failed"
        )

        st.error(
            f"Unable to process uploaded dataset: {e}"
        )

else:

    st.info(
        "📥 Upload a CSV dataset to start generating forecasts."
    )

    st.markdown(
        """
        **Supported functionality**

        - Daily and monthly forecasting
        - Multiple numerical target columns
        - Configurable aggregation
        - Interactive historical vs forecast charts
        - Forecast data export
        """
    )
