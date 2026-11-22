
"""
8_Universal_Purchase_Predictor.py

Universal Purchase Predictor
Single-file Streamlit ML application.

Features:
- Main-screen CSV upload
- Dataset profiling and quality checks
- Automatic target suggestion
- Classification and regression
- Automatic model comparison
- Best model recommendation
- Model performance dashboard
- Batch predictions and CSV export
- Single-record prediction

No feature-specific sidebar controls.
The application-wide sidebar/navigation is preserved.

Dependencies:
    pip install streamlit pandas numpy scikit-learn
"""

from __future__ import annotations

import hashlib
import logging
import warnings
from io import BytesIO
from typing import Any

import numpy as np
import pandas as pd
import streamlit as st

from sklearn.base import clone
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import (
    ExtraTreesClassifier,
    ExtraTreesRegressor,
    RandomForestClassifier,
    RandomForestRegressor,
)
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
    mean_absolute_error,
    mean_squared_error,
    r2_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import (
    LabelEncoder,
    OneHotEncoder,
    StandardScaler,
)
from sklearn.tree import (
    DecisionTreeClassifier,
    DecisionTreeRegressor,
)

warnings.filterwarnings("ignore", category=FutureWarning)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

LOGGER = logging.getLogger("universal_purchase_predictor")


# ================================================================
# INTERNAL DEFAULTS
# These are not exposed as user-facing configuration controls.
# ================================================================

TEST_SIZE = 0.20
RANDOM_STATE = 42
ENSEMBLE_TREES = 150


# ================================================================
# PAGE CONFIGURATION
# ================================================================

st.set_page_config(
    page_title="Universal Purchase Predictor",
    page_icon="🔮",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ================================================================
# UI STYLING
# IMPORTANT:
# Do not hide or modify the application-wide sidebar here.
# The parent application owns global navigation.
# ================================================================

st.markdown(
    """
    <style>
    .block-container {
        max-width: 1500px;
        padding-top: 1.5rem;
        padding-bottom: 3rem;
    }

    .app-header {
        font-size: 2rem;
        font-weight: 750;
        letter-spacing: -0.7px;
        margin-bottom: 0.2rem;
    }

    .app-subtitle {
        color: #8490a0;
        font-size: 0.95rem;
        margin-bottom: 1.5rem;
    }

    .section-heading {
        font-size: 1.15rem;
        font-weight: 650;
        margin-top: 0.5rem;
        margin-bottom: 0.8rem;
    }

    [data-testid="stMetric"] {
        border: 1px solid rgba(128,128,128,.20);
        border-radius: 12px;
        padding: 14px 16px;
        background: rgba(128,128,128,.045);
    }

    [data-testid="stMetricLabel"] {
        font-size: 0.83rem;
    }

    [data-testid="stMetricValue"] {
        font-weight: 700;
    }

    div[data-testid="stDataFrame"] {
        border: 1px solid rgba(128,128,128,.15);
        border-radius: 10px;
        overflow: hidden;
    }

    div[data-testid="stFileUploader"] {
        border: 1px dashed rgba(128,128,128,.40);
        border-radius: 12px;
        padding: 12px;
    }

    div.stButton > button {
        border-radius: 9px;
        font-weight: 600;
        min-height: 2.6rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ================================================================
# SESSION STATE
# ================================================================

DEFAULT_STATE = {
    "source_fingerprint": None,
    "trained_config": None,
    "trained_pipeline": None,
    "trained_target": None,
    "trained_features": None,
    "trained_problem_type": None,
    "trained_model_name": None,
    "trained_metrics": None,
    "trained_label_encoder": None,
    "trained_feature_schema": None,
    "training_results": None,
    "model_artifacts": {},
}

for key, default_value in DEFAULT_STATE.items():
    if key not in st.session_state:
        st.session_state[key] = default_value


def clear_trained_state() -> None:
    """Invalidate trained artifacts when the dataset/configuration changes."""

    for key, default_value in DEFAULT_STATE.items():
        if key != "source_fingerprint":
            st.session_state[key] = default_value


# ================================================================
# DATA LOADING
# ================================================================

def dataframe_fingerprint(file_bytes: bytes) -> str:
    return hashlib.sha256(file_bytes).hexdigest()


def read_csv_safely(file_bytes: bytes) -> pd.DataFrame:
    """Read CSV using common encodings."""

    errors = []

    for encoding in ("utf-8-sig", "utf-8", "latin-1"):

        try:

            frame = pd.read_csv(
                BytesIO(file_bytes),
                encoding=encoding,
            )

            if frame.empty:
                raise ValueError("The uploaded CSV contains no records.")

            frame.columns = [
                str(column).strip()
                for column in frame.columns
            ]

            if frame.columns.duplicated().any():

                duplicates = frame.columns[
                    frame.columns.duplicated()
                ].tolist()

                raise ValueError(
                    f"Duplicate column names found: {duplicates}"
                )

            return frame

        except Exception as exc:
            errors.append(f"{encoding}: {exc}")

    raise ValueError(
        "Unable to read the CSV file. " + " | ".join(errors)
    )


# ================================================================
# DATASET PROFILING
# ================================================================

def detect_target_column(
    frame: pd.DataFrame,
) -> str | None:

    preferred_names = {
        "target",
        "label",
        "class",
        "outcome",
        "result",
        "status",
        "purchase",
        "purchased",
        "converted",
        "conversion",
        "churn",
        "response",
        "prediction",
        "y",
    }

    candidates = []

    for column in frame.columns:

        values = frame[column].dropna()

        if values.empty or values.nunique() <= 1:
            continue

        name = str(column).strip().lower()

        score = 5 if name in preferred_names else 0

        if values.nunique() == 2:
            score += 2

        if values.nunique() <= 10:
            score += 1

        candidates.append((score, column))

    if not candidates:
        return None

    candidates.sort(
        key=lambda item: item[0],
        reverse=True,
    )

    return candidates[0][1]


def infer_problem_type(
    target: pd.Series,
) -> str:

    values = target.dropna()

    if values.empty:
        return "Classification"

    if (
        pd.api.types.is_object_dtype(values)
        or pd.api.types.is_bool_dtype(values)
        or isinstance(values.dtype, pd.CategoricalDtype)
    ):
        return "Classification"

    if values.nunique() <= 15:
        return "Classification"

    return "Regression"


def build_data_profile(
    frame: pd.DataFrame,
) -> pd.DataFrame:

    return pd.DataFrame(
        {
            "Column": frame.columns,
            "Data Type": frame.dtypes.astype(str).values,
            "Missing Values": frame.isna().sum().values,
            "Missing %": (
                frame.isna().mean() * 100
            ).round(2).values,
            "Unique Values": frame.nunique(
                dropna=True
            ).values,
        }
    )


# ================================================================
# FEATURE ENGINEERING
# ================================================================

def prepare_features(
    frame: pd.DataFrame,
    forced_date_columns: list[str] | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:

    data = frame.copy()

    forced_dates = set(
        forced_date_columns or []
    )

    schema = {
        "original_columns": list(frame.columns),
        "date_columns": [],
        "dropped_columns": [],
    }

    for column in list(data.columns):

        series = data[column]

        is_datetime = (
            column in forced_dates
            or pd.api.types.is_datetime64_any_dtype(series)
        )

        if not is_datetime and (
            pd.api.types.is_object_dtype(series)
            or pd.api.types.is_string_dtype(series)
        ):

            non_null = series.dropna()

            if len(non_null) >= 3:

                parsed = pd.to_datetime(
                    non_null,
                    errors="coerce",
                )

                date_ratio = float(
                    parsed.notna().mean()
                )

                numeric_ratio = float(
                    pd.to_numeric(
                        non_null,
                        errors="coerce",
                    ).notna().mean()
                )

                if (
                    date_ratio >= 0.85
                    and numeric_ratio < 0.5
                ):
                    is_datetime = True

        if is_datetime:

            parsed = pd.to_datetime(
                series,
                errors="coerce",
            )

            data[f"{column}__year"] = parsed.dt.year
            data[f"{column}__month"] = parsed.dt.month
            data[f"{column}__day"] = parsed.dt.day
            data[f"{column}__weekday"] = parsed.dt.dayofweek
            data[f"{column}__hour"] = parsed.dt.hour

            data.drop(
                columns=[column],
                inplace=True,
            )

            schema["date_columns"].append(column)

    data.replace(
        [np.inf, -np.inf],
        np.nan,
        inplace=True,
    )

    for column in data.columns:

        if pd.api.types.is_bool_dtype(data[column]):

            data[column] = data[column].map(
                {
                    True: "True",
                    False: "False",
                }
            )

        elif not pd.api.types.is_numeric_dtype(data[column]):

            data[column] = data[column].map(
                lambda value: (
                    np.nan
                    if pd.isna(value)
                    else str(value)
                )
            )

    empty_columns = [
        column
        for column in data.columns
        if data[column].isna().all()
    ]

    if empty_columns:

        data.drop(
            columns=empty_columns,
            inplace=True,
        )

        schema["dropped_columns"].extend(
            empty_columns
        )

    constant_columns = [
        column
        for column in data.columns
        if data[column].nunique(dropna=False) <= 1
    ]

    if constant_columns:

        data.drop(
            columns=constant_columns,
            inplace=True,
        )

        schema["dropped_columns"].extend(
            constant_columns
        )

    if data.shape[1] == 0:
        raise ValueError(
            "No useful predictor columns remain after preprocessing."
        )

    return data, schema


# ================================================================
# TARGET VALIDATION
# ================================================================

def validate_target(
    target: pd.Series,
    problem_type: str,
) -> tuple[pd.Series, LabelEncoder | None]:

    if target.isna().any():

        raise ValueError(
            f"Target column contains {int(target.isna().sum())} "
            "missing values. Resolve missing target values before training."
        )

    if target.nunique() < 2:

        raise ValueError(
            "The target column must contain at least two distinct values."
        )

    if problem_type == "Regression":

        numeric_target = pd.to_numeric(
            target,
            errors="coerce",
        )

        if numeric_target.isna().any():

            raise ValueError(
                "Regression requires a numeric target. "
                "Select Classification or choose a numeric target column."
            )

        return numeric_target.astype(float), None

    encoder = LabelEncoder()

    encoded = pd.Series(
        encoder.fit_transform(
            target.astype(str)
        ),
        index=target.index,
        name=target.name,
    )

    return encoded, encoder


# ================================================================
# PREPROCESSING PIPELINE
# ================================================================

def make_one_hot_encoder() -> OneHotEncoder:

    try:

        return OneHotEncoder(
            handle_unknown="ignore",
            sparse_output=True,
        )

    except TypeError:

        return OneHotEncoder(
            handle_unknown="ignore",
            sparse=True,
        )


def build_preprocessor(
    features: pd.DataFrame,
) -> ColumnTransformer:

    numeric_columns = features.select_dtypes(
        include=[np.number]
    ).columns.tolist()

    categorical_columns = [
        column
        for column in features.columns
        if column not in numeric_columns
    ]

    transformers = []

    if numeric_columns:

        numeric_pipeline = Pipeline(
            steps=[
                (
                    "imputer",
                    SimpleImputer(strategy="median"),
                ),
                (
                    "scaler",
                    StandardScaler(),
                ),
            ]
        )

        transformers.append(
            (
                "numeric",
                numeric_pipeline,
                numeric_columns,
            )
        )

    if categorical_columns:

        categorical_pipeline = Pipeline(
            steps=[
                (
                    "imputer",
                    SimpleImputer(strategy="most_frequent"),
                ),
                (
                    "encoder",
                    make_one_hot_encoder(),
                ),
            ]
        )

        transformers.append(
            (
                "categorical",
                categorical_pipeline,
                categorical_columns,
            )
        )

    if not transformers:

        raise ValueError(
            "No numeric or categorical features were detected."
        )

    return ColumnTransformer(
        transformers=transformers,
        remainder="drop",
        verbose_feature_names_out=False,
    )


def build_pipeline(
    estimator: Any,
    training_features: pd.DataFrame,
) -> Pipeline:

    return Pipeline(
        steps=[
            (
                "preprocessor",
                build_preprocessor(training_features),
            ),
            (
                "model",
                clone(estimator),
            ),
        ]
    )


# ================================================================
# MODEL LIBRARY
# ================================================================

def get_model_candidates(
    problem_type: str,
) -> dict[str, Any]:

    if problem_type == "Classification":

        return {

            "Random Forest": RandomForestClassifier(
                n_estimators=ENSEMBLE_TREES,
                random_state=RANDOM_STATE,
                class_weight="balanced",
                n_jobs=-1,
            ),

            "Extra Trees": ExtraTreesClassifier(
                n_estimators=ENSEMBLE_TREES,
                random_state=RANDOM_STATE,
                class_weight="balanced",
                n_jobs=-1,
            ),

            "Logistic Regression": LogisticRegression(
                max_iter=1500,
                class_weight="balanced",
            ),

            "Decision Tree": DecisionTreeClassifier(
                random_state=RANDOM_STATE,
                class_weight="balanced",
            ),

        }

    return {

        "Random Forest": RandomForestRegressor(
            n_estimators=ENSEMBLE_TREES,
            random_state=RANDOM_STATE,
            n_jobs=-1,
        ),

        "Extra Trees": ExtraTreesRegressor(
            n_estimators=ENSEMBLE_TREES,
            random_state=RANDOM_STATE,
            n_jobs=-1,
        ),

        "Ridge Regression": Ridge(),

        "Decision Tree": DecisionTreeRegressor(
            random_state=RANDOM_STATE,
        ),

    }


# ================================================================
# MODEL EVALUATION
# ================================================================

def calculate_metrics(
    y_true,
    y_pred,
    problem_type: str,
    probabilities=None,
    class_count=None,
) -> dict[str, float]:

    if problem_type == "Regression":

        return {

            "MAE": float(
                mean_absolute_error(
                    y_true,
                    y_pred,
                )
            ),

            "RMSE": float(
                np.sqrt(
                    mean_squared_error(
                        y_true,
                        y_pred,
                    )
                )
            ),

            "R²": float(
                r2_score(
                    y_true,
                    y_pred,
                )
            ),

        }

    metrics = {

        "Accuracy": float(
            accuracy_score(
                y_true,
                y_pred,
            )
        ),

        "Precision": float(
            precision_score(
                y_true,
                y_pred,
                average="weighted",
                zero_division=0,
            )
        ),

        "Recall": float(
            recall_score(
                y_true,
                y_pred,
                average="weighted",
                zero_division=0,
            )
        ),

        "F1 Score": float(
            f1_score(
                y_true,
                y_pred,
                average="weighted",
                zero_division=0,
            )
        ),

    }

    if probabilities is not None:

        try:

            if class_count == 2:

                metrics["ROC-AUC"] = float(
                    roc_auc_score(
                        y_true,
                        probabilities[:, 1],
                    )
                )

            elif class_count and class_count > 2:

                metrics["ROC-AUC"] = float(
                    roc_auc_score(
                        y_true,
                        probabilities,
                        multi_class="ovr",
                        average="weighted",
                    )
                )

        except Exception:
            pass

    return metrics


def render_metrics(
    metrics: dict[str, float],
) -> None:

    columns = st.columns(
        min(4, max(1, len(metrics)))
    )

    for index, (name, value) in enumerate(
        metrics.items()
    ):

        with columns[index % len(columns)]:

            st.metric(
                name,
                f"{value:.4f}",
            )


# ================================================================
# MAIN SCREEN HEADER
# ================================================================

st.markdown(
    '<div class="app-header">🔮 Universal Purchase Predictor</div>',
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="app-subtitle">
    A universal machine learning workspace for structured datasets.
    Explore data, train classification or regression models,
    compare performance and generate predictions.
    </div>
    """,
    unsafe_allow_html=True,
)


# ================================================================
# MAIN SCREEN DATA UPLOAD
# ================================================================

st.markdown(
    '<div class="section-heading">1. Upload your dataset</div>',
    unsafe_allow_html=True,
)

upload_col, upload_info_col = st.columns(
    [2, 1]
)

with upload_col:

    uploaded_file = st.file_uploader(
        "Choose a CSV dataset",
        type=["csv"],
        key="purchase_predictor_dataset",
        help="Upload a structured CSV file to start your analysis.",
    )

with upload_info_col:

    st.info(
        """
        **Supported format: CSV**

        Upload your dataset to automatically
        begin data profiling and preparation.
        """
    )


if uploaded_file is None:

    st.divider()

    st.markdown("### Your machine learning workflow")

    workflow_columns = st.columns(5)

    workflow = [
        ("01", "Upload", "Load your dataset"),
        ("02", "Explore", "Review data quality"),
        ("03", "Train", "Compare ML models"),
        ("04", "Evaluate", "Review performance"),
        ("05", "Predict", "Generate predictions"),
    ]

    for column, item in zip(workflow_columns, workflow):

        with column:

            st.markdown(
                f"**{item[0]} · {item[1]}**"
            )

            st.caption(item[2])

    st.stop()


# ================================================================
# LOAD DATASET
# ================================================================

try:

    file_bytes = uploaded_file.getvalue()

    fingerprint = dataframe_fingerprint(
        file_bytes
    )

    if st.session_state.source_fingerprint != fingerprint:

        clear_trained_state()

        st.session_state.source_fingerprint = fingerprint

    df = read_csv_safely(file_bytes)

except Exception as exc:

    st.error(
        f"Dataset loading failed: {exc}"
    )

    st.stop()


if df.shape[1] < 2:

    st.error(
        "The dataset must contain at least two columns: "
        "one or more predictors and one target."
    )

    st.stop()


# ================================================================
# DATASET OVERVIEW
# ================================================================

st.divider()

st.markdown(
    '<div class="section-heading">2. Dataset overview</div>',
    unsafe_allow_html=True,
)

metric_columns = st.columns(4)

metric_columns[0].metric(
    "Total records",
    f"{df.shape[0]:,}",
)

metric_columns[1].metric(
    "Total columns",
    f"{df.shape[1]:,}",
)

metric_columns[2].metric(
    "Numeric columns",
    len(
        df.select_dtypes(
            include=[np.number]
        ).columns
    ),
)

metric_columns[3].metric(
    "Missing cells",
    f"{int(df.isna().sum().sum()):,}",
)


with st.expander(
    "Dataset preview",
    expanded=True,
):

    st.dataframe(
        df.head(20),
        use_container_width=True,
    )


with st.expander(
    "Data quality profile",
):

    profile = build_data_profile(df)

    st.dataframe(
        profile,
        use_container_width=True,
        hide_index=True,
    )

    missing_columns = profile[
        profile["Missing Values"] > 0
    ]

    if missing_columns.empty:

        st.success(
            "No missing values detected."
        )

    else:

        st.warning(
            f"{len(missing_columns)} columns contain missing values. "
            "Missing predictor values will be handled by preprocessing."
        )


# ================================================================
# TARGET CONFIGURATION
# ================================================================

st.divider()

st.markdown(
    '<div class="section-heading">3. Define prediction objective</div>',
    unsafe_allow_html=True,
)

suggested_target = detect_target_column(df)

target_options = list(df.columns)

default_target_index = (
    target_options.index(suggested_target)
    if suggested_target in target_options
    else 0
)

target_col, problem_col = st.columns(2)

with target_col:

    target_column = st.selectbox(
        "What should the model predict?",
        options=target_options,
        index=default_target_index,
        key="predictor_target_column",
    )

with problem_col:

    inferred_type = infer_problem_type(
        df[target_column]
    )

    problem_type = st.selectbox(
        "Prediction type",
        options=[
            "Classification",
            "Regression",
        ],
        index=(
            0 if inferred_type == "Classification" else 1
        ),
        key="predictor_problem_type",
    )


if suggested_target:

    st.caption(
        f"Suggested target: **{suggested_target}**. "
        "Change the selection if another column is your intended outcome."
    )


# ================================================================
# RESET MODEL WHEN CONFIGURATION CHANGES
# ================================================================

current_config = (
    fingerprint,
    target_column,
    problem_type,
)

if st.session_state.trained_config != current_config:

    if st.session_state.trained_config is not None:

        clear_trained_state()

    st.session_state.trained_config = current_config


# ================================================================
# TARGET DISTRIBUTION
# ================================================================

with st.expander(
    "Explore target distribution",
):

    target_values = df[target_column].dropna()

    if target_values.empty:

        st.warning(
            "The selected target contains no valid values."
        )

    elif target_values.nunique() <= 30:

        distribution = (
            target_values.astype(str)
            .value_counts()
            .head(30)
        )

        st.bar_chart(distribution)

    else:

        st.info(
            "The target has many distinct values. "
            "A categorical distribution chart is not displayed."
        )


# ================================================================
# PREPARE FEATURES AND TARGET
# ================================================================

try:

    X_raw = df.drop(
        columns=[target_column]
    ).copy()

    y, label_encoder = validate_target(
        df[target_column],
        problem_type,
    )

    X_prepared, feature_schema = prepare_features(
        X_raw
    )

    X_prepared = X_prepared.loc[y.index]

except Exception as exc:

    st.error(
        f"Data preparation failed: {exc}"
    )

    st.stop()


if len(X_prepared) < 6:

    st.error(
        "At least 6 usable records are recommended for model training."
    )

    st.stop()


# ================================================================
# TRAIN / TEST SPLIT
# Internal defaults; no configuration controls are displayed.
# ================================================================

stratify_values = None

if problem_type == "Classification":

    class_counts = y.value_counts()

    test_rows = int(
        np.ceil(len(y) * TEST_SIZE)
    )

    train_rows = len(y) - test_rows

    if (
        class_counts.min() >= 2
        and test_rows >= len(class_counts)
        and train_rows >= len(class_counts)
    ):

        stratify_values = y


try:

    X_train, X_test, y_train, y_test = train_test_split(
        X_prepared,
        y,
        test_size=TEST_SIZE,
        random_state=RANDOM_STATE,
        stratify=stratify_values,
    )

except Exception as exc:

    st.error(
        f"Unable to prepare training data: {exc}"
    )

    st.stop()


if (
    problem_type == "Classification"
    and y_train.nunique() < 2
):

    st.error(
        "Training data contains only one target class. "
        "Please provide more representative data."
    )

    st.stop()


# ================================================================
# MODEL TRAINING
# ================================================================

st.divider()

st.markdown(
    '<div class="section-heading">4. Model training and comparison</div>',
    unsafe_allow_html=True,
)

st.write(
    "The application automatically evaluates suitable algorithms "
    "and recommends the strongest model using holdout performance."
)

train_button = st.button(
    "🚀 Train and compare models",
    type="primary",
    use_container_width=True,
)


if train_button:

    model_candidates = get_model_candidates(
        problem_type
    )

    leaderboard = []
    trained_artifacts = {}

    progress = st.progress(
        0,
        text="Preparing model training...",
    )

    model_items = list(
        model_candidates.items()
    )

    for index, (model_name, estimator) in enumerate(
        model_items
    ):

        try:

            pipeline = build_pipeline(
                estimator,
                X_train,
            )

            pipeline.fit(
                X_train,
                y_train,
            )

            predictions = pipeline.predict(
                X_test
            )

            probabilities = None

            if (
                problem_type == "Classification"
                and hasattr(pipeline, "predict_proba")
            ):

                probabilities = pipeline.predict_proba(
                    X_test
                )

            metrics = calculate_metrics(
                np.asarray(y_test),
                np.asarray(predictions),
                problem_type,
                probabilities,
                (
                    int(y.nunique())
                    if problem_type == "Classification"
                    else None
                ),
            )

            leaderboard.append(
                {
                    "Model": model_name,
                    **metrics,
                    "Status": "Successful",
                }
            )

            trained_artifacts[model_name] = {
                "pipeline": pipeline,
                "metrics": metrics,
            }

        except Exception as exc:

            LOGGER.exception(
                "Model training failed: %s",
                model_name,
            )

            leaderboard.append(
                {
                    "Model": model_name,
                    "Status": f"Failed: {str(exc)[:150]}",
                }
            )

        progress.progress(
            (index + 1) / len(model_items),
            text=f"Evaluating {model_name}",
        )

    progress.empty()

    if not trained_artifacts:

        st.error(
            "All models failed to train. "
            "Please review your dataset and target column."
        )

    else:

        primary_metric = (
            "F1 Score"
            if problem_type == "Classification"
            else "RMSE"
        )

        reverse_sort = (
            problem_type == "Classification"
        )

        best_name = sorted(
            trained_artifacts,
            key=lambda name: trained_artifacts[name][
                "metrics"
            ].get(
                primary_metric,
                (
                    float("-inf")
                    if reverse_sort
                    else float("inf")
                ),
            ),
            reverse=reverse_sort,
        )[0]

        best_artifact = trained_artifacts[best_name]

        st.session_state.model_artifacts = trained_artifacts

        st.session_state.training_results = pd.DataFrame(
            leaderboard
        )

        st.session_state.trained_pipeline = (
            best_artifact["pipeline"]
        )

        st.session_state.trained_target = target_column

        st.session_state.trained_features = list(
            X_prepared.columns
        )

        st.session_state.trained_problem_type = (
            problem_type
        )

        st.session_state.trained_model_name = best_name

        st.session_state.trained_metrics = (
            best_artifact["metrics"]
        )

        st.session_state.trained_label_encoder = (
            label_encoder
        )

        st.session_state.trained_feature_schema = (
            feature_schema
        )

        st.success(
            f"Model comparison completed. Recommended model: {best_name}"
        )


# ================================================================
# MODEL COMPARISON RESULTS
# ================================================================

if st.session_state.training_results is not None:

    st.markdown("#### Model comparison results")

    st.dataframe(
        st.session_state.training_results,
        use_container_width=True,
        hide_index=True,
    )

    successful_models = list(
        st.session_state.model_artifacts.keys()
    )

    if successful_models:

        selected_model = st.selectbox(
            "Select model for predictions",
            options=successful_models,
            index=(
                successful_models.index(
                    st.session_state.trained_model_name
                )
                if st.session_state.trained_model_name
                in successful_models
                else 0
            ),
            key="predictor_selected_model",
        )

        selected_artifact = (
            st.session_state.model_artifacts[
                selected_model
            ]
        )

        st.session_state.trained_pipeline = (
            selected_artifact["pipeline"]
        )

        st.session_state.trained_model_name = selected_model

        st.session_state.trained_metrics = (
            selected_artifact["metrics"]
        )


# ================================================================
# MODEL PERFORMANCE
# ================================================================

if st.session_state.trained_pipeline is None:

    st.info(
        "Upload your dataset, select the prediction objective, "
        "and train the models to continue."
    )

    st.stop()


if (
    st.session_state.trained_target != target_column
    or st.session_state.trained_problem_type != problem_type
    or st.session_state.trained_features != list(X_prepared.columns)
):

    st.warning(
        "The dataset or prediction configuration has changed. "
        "Please train the models again."
    )

    st.stop()


st.divider()

st.markdown(
    '<div class="section-heading">5. Model performance</div>',
    unsafe_allow_html=True,
)

st.write(
    f"**Selected model:** {st.session_state.trained_model_name}"
)

render_metrics(
    st.session_state.trained_metrics or {}
)

st.caption(
    "Performance metrics are calculated on the held-out test dataset."
)


# ================================================================
# PREDICTION WORKSPACE
# ================================================================

st.divider()

st.markdown(
    '<div class="section-heading">6. Prediction workspace</div>',
    unsafe_allow_html=True,
)

batch_tab, single_tab = st.tabs(
    [
        "📦 Batch prediction",
        "🔍 Single-record prediction",
    ]
)

active_pipeline = st.session_state.trained_pipeline


# ================================================================
# BATCH PREDICTION
# ================================================================

with batch_tab:

    st.write(
        "Generate predictions for the uploaded dataset "
        "and export the results."
    )

    try:

        batch_predictions = active_pipeline.predict(
            X_prepared
        )

        batch_output = df.copy()

        if problem_type == "Classification":

            encoder = st.session_state.trained_label_encoder

            if encoder is not None:

                batch_output["predicted_value"] = (
                    encoder.inverse_transform(
                        np.asarray(
                            batch_predictions,
                            dtype=int,
                        )
                    )
                )

            else:

                batch_output["predicted_value"] = (
                    batch_predictions
                )

            if hasattr(active_pipeline, "predict_proba"):

                probabilities = active_pipeline.predict_proba(
                    X_prepared
                )

                batch_output["prediction_confidence"] = (
                    probabilities.max(axis=1)
                )

                batch_output["confidence_level"] = pd.cut(
                    batch_output["prediction_confidence"],
                    bins=[
                        -0.001,
                        0.60,
                        0.80,
                        1.001,
                    ],
                    labels=[
                        "Low",
                        "Medium",
                        "High",
                    ],
                )

        else:

            batch_output["predicted_value"] = (
                batch_predictions
            )

        st.dataframe(
            batch_output.head(50),
            use_container_width=True,
        )

        st.download_button(
            "⬇️ Download prediction results",
            data=batch_output.to_csv(
                index=False
            ).encode("utf-8"),
            file_name="purchase_prediction_results.csv",
            mime="text/csv",
            use_container_width=True,
        )

        st.caption(
            "These are predictions on the uploaded dataset. "
            "They are not independent test-set evaluation metrics."
        )

    except Exception as exc:

        LOGGER.exception(
            "Batch prediction failed"
        )

        st.error(
            f"Batch prediction failed: {exc}"
        )


# ================================================================
# SINGLE-RECORD PREDICTION
# ================================================================

with single_tab:

    st.write(
        "Enter the values for a new record to generate an individual prediction."
    )

    with st.form(
        "single_record_prediction",
        clear_on_submit=False,
    ):

        live_input: dict[str, Any] = {}

        input_columns = st.columns(2)

        for index, column in enumerate(X_raw.columns):

            source_series = X_raw[column]

            with input_columns[index % 2]:

                if pd.api.types.is_bool_dtype(source_series):

                    live_input[column] = st.selectbox(
                        str(column),
                        [True, False],
                        key=f"live_bool_{column}",
                    )

                elif pd.api.types.is_numeric_dtype(source_series):

                    numeric_values = pd.to_numeric(
                        source_series,
                        errors="coerce",
                    ).dropna()

                    default_value = (
                        float(numeric_values.median())
                        if not numeric_values.empty
                        else 0.0
                    )

                    live_input[column] = st.number_input(
                        str(column),
                        value=default_value,
                        key=f"live_numeric_{column}",
                    )

                else:

                    choices = (
                        source_series.dropna()
                        .astype(str)
                        .unique()
                        .tolist()
                    )

                    if 0 < len(choices) <= 100:

                        live_input[column] = st.selectbox(
                            str(column),
                            choices,
                            key=f"live_category_{column}",
                        )

                    else:

                        sample = (
                            source_series.dropna()
                            .astype(str)
                        )

                        default_text = (
                            sample.iloc[0]
                            if not sample.empty
                            else ""
                        )

                        live_input[column] = st.text_input(
                            str(column),
                            value=default_text,
                            key=f"live_text_{column}",
                        )

        predict_clicked = st.form_submit_button(
            "Generate prediction",
            type="primary",
            use_container_width=True,
        )

    if predict_clicked:

        try:

            live_frame = pd.DataFrame(
                [live_input],
                columns=X_raw.columns,
            )

            forced_dates = (
                st.session_state.trained_feature_schema or {}
            ).get(
                "date_columns",
                [],
            )

            live_prepared, _ = prepare_features(
                live_frame,
                forced_date_columns=forced_dates,
            )

            live_prepared = live_prepared.reindex(
                columns=st.session_state.trained_features,
                fill_value=np.nan,
            )

            prediction = active_pipeline.predict(
                live_prepared
            )[0]

            if problem_type == "Classification":

                encoder = st.session_state.trained_label_encoder

                display_prediction = (
                    encoder.inverse_transform(
                        [int(prediction)]
                    )[0]
                    if encoder is not None
                    else prediction
                )

                st.success(
                    f"Predicted outcome: **{display_prediction}**"
                )

                if hasattr(active_pipeline, "predict_proba"):

                    probabilities = active_pipeline.predict_proba(
                        live_prepared
                    )[0]

                    confidence = float(
                        np.max(probabilities)
                    )

                    st.metric(
                        "Prediction confidence",
                        f"{confidence:.1%}",
                    )

            else:

                st.success(
                    f"Predicted value: **{float(prediction):,.4f}**"
                )

        except Exception as exc:

            LOGGER.exception(
                "Single-record prediction failed"
            )

            st.error(
                f"Prediction failed: {exc}"
            )


# ================================================================
# FOOTER
# ================================================================

st.divider()

st.caption(
    "Universal Purchase Predictor | "
    "Classification and Regression | "
    "Single-file implementation"
)
