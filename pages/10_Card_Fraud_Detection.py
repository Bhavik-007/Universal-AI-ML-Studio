
import json
import logging
import hashlib
from pathlib import Path
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier, IsolationForest
from sklearn.impute import SimpleImputer
from sklearn.neighbors import LocalOutlierFactor
from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    roc_auc_score,
    confusion_matrix,
    classification_report,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from auth.login_manager import login_manager
from auth.auth_guard import protect_page
from auth.ui_guard import apply_sidebar_visibility


# =========================================================
# 1. APPLICATION CONFIGURATION
# =========================================================

st.set_page_config(
    page_title="Universal Fraud Intelligence",
    page_icon="🛡️",
    layout="wide",
)

login_manager()
protect_page()
apply_sidebar_visibility()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
FEEDBACK_DIR = BASE_DIR / "data"
FEEDBACK_FILE = FEEDBACK_DIR / "fraud_investigation_feedback.csv"

INDUSTRY_USE_CASES = {
    "BFSI": [
        "Card / payment fraud",
        "Banking transaction fraud",
        "Account takeover",
        "Identity fraud",
        "Suspicious transaction monitoring",
        "Custom scenario",
    ],
    "Retail & E-commerce": [
        "Refund / return abuse",
        "Fake orders",
        "Payment fraud",
        "Coupon / promotion abuse",
        "Account abuse",
        "Custom scenario",
    ],
    "Insurance": [
        "False / duplicate claims",
        "Suspicious policy applications",
        "Claim manipulation",
        "Provider / claimant anomaly",
        "Custom scenario",
    ],
    "Healthcare": [
        "Medical billing irregularities",
        "Suspicious provider billing",
        "Prescription abuse",
        "Custom scenario",
    ],
    "Telecommunications": [
        "SIM-swap indicators",
        "Subscription fraud",
        "Identity misuse",
        "Abnormal usage",
        "Custom scenario",
    ],
    "Government & Public Sector": [
        "Benefit / subsidy fraud",
        "Document manipulation indicators",
        "Identity fraud",
        "Suspicious claims",
        "Custom scenario",
    ],
    "Manufacturing & Supply Chain": [
        "Procurement fraud",
        "Invoice manipulation",
        "Vendor risk",
        "Inventory discrepancy",
        "Custom scenario",
    ],
    "Other / Custom": [
        "Custom fraud detection scenario",
    ],
}

FEEDBACK_OPTIONS = [
    "Confirmed Fraud",
    "Legitimate Activity",
    "False Positive",
    "Requires Further Investigation",
]


# =========================================================
# 2. SESSION MANAGEMENT
# =========================================================

def clear_fraud_session():

    keys = [
        key for key in list(st.session_state.keys())
        if key.startswith("fraud_")
    ]

    for key in keys:
        st.session_state.pop(key, None)

    st.session_state.pop(
        "_fraud_dataset_fingerprint", None
    )

    st.session_state.pop(
        "_fraud_page_initialized", None
    )


def remove_dataset_callback():
    clear_fraud_session()


# Detect when Streamlit has cleaned up the uploader
# after navigation to another multipage application page.

if (
    st.session_state.get("_fraud_page_initialized", False)
    and "fraud_dataset_upload" not in st.session_state
):
    clear_fraud_session()


# =========================================================
# 3. FEEDBACK PERSISTENCE
# =========================================================

def load_feedback():

    if not FEEDBACK_FILE.exists():
        return pd.DataFrame()

    try:
        return pd.read_csv(FEEDBACK_FILE)

    except Exception:
        logger.exception("Unable to read feedback file.")
        return pd.DataFrame()


def save_feedback(record):

    FEEDBACK_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    new_df = pd.DataFrame([record])

    if FEEDBACK_FILE.exists():

        new_df.to_csv(
            FEEDBACK_FILE,
            mode="a",
            header=False,
            index=False,
        )

    else:

        new_df.to_csv(
            FEEDBACK_FILE,
            index=False,
        )


def get_reviewed_training_data(fingerprint):

    feedback = load_feedback()

    if feedback.empty:
        return pd.DataFrame()

    required = {
        "dataset_fingerprint",
        "outcome",
        "features_json",
    }

    if not required.issubset(feedback.columns):
        return pd.DataFrame()

    feedback = feedback[
        feedback["dataset_fingerprint"] == fingerprint
    ].copy()

    # Only verified binary outcomes are used for learning.
    feedback = feedback[
        feedback["outcome"].isin(
            ["Confirmed Fraud", "Legitimate Activity", "False Positive"]
        )
    ]

    if feedback.empty:
        return pd.DataFrame()

    records = []

    for _, row in feedback.iterrows():

        try:

            features = json.loads(row["features_json"])

            features["reviewed_label"] = (
                1
                if row["outcome"] == "Confirmed Fraud"
                else 0
            )

            records.append(features)

        except (ValueError, TypeError, json.JSONDecodeError):
            continue

    return pd.DataFrame(records)


# =========================================================
# 4. DATA LOADING
# =========================================================

def load_dataset(uploaded_file):

    filename = uploaded_file.name.lower()

    if filename.endswith(".csv"):
        return pd.read_csv(uploaded_file)

    if filename.endswith((".xlsx", ".xls")):
        return pd.read_excel(uploaded_file)

    if filename.endswith(".json"):

        raw = json.load(uploaded_file)

        if isinstance(raw, list):
            return pd.json_normalize(raw)

        if isinstance(raw, dict):

            records = raw.get("data", raw)

            if isinstance(records, (list, dict)):
                return pd.json_normalize(records)

        raise ValueError(
            "JSON must contain an array of records "
            "or an object containing records."
        )

    raise ValueError("Unsupported file format.")


def get_fingerprint(uploaded_file):

    return hashlib.sha256(
        uploaded_file.getvalue()
    ).hexdigest()


# =========================================================
# 5. DYNAMIC DATA PROFILING
# =========================================================

def detect_datetime_series(series):

    if pd.api.types.is_datetime64_any_dtype(series):
        return True

    if not (
        pd.api.types.is_object_dtype(series)
        or pd.api.types.is_string_dtype(series)
    ):
        return False

    values = series.dropna()

    if values.empty:
        return False

    try:

        parsed = pd.to_datetime(
            values.head(500),
            errors="coerce",
            format="mixed",
            utc=True,
        )

        return parsed.notna().mean() >= 0.90

    except (ValueError, TypeError, OverflowError):

        return False


def profile_dataset(df):

    profile = []

    binary_candidates = []
    identifier_candidates = []
    constant_columns = []
    datetime_columns = []

    for column in df.columns:

        series = df[column]
        values = series.dropna()

        unique_count = values.nunique()

        unique_ratio = (
            unique_count / len(values)
            if len(values)
            else 0
        )

        missing_pct = series.isna().mean() * 100

        is_datetime = detect_datetime_series(series)

        is_numeric = pd.api.types.is_numeric_dtype(series)

        is_boolean = pd.api.types.is_bool_dtype(series)

        role = "Categorical Feature"

        if unique_count <= 1:

            role = "Constant"
            constant_columns.append(column)

        elif is_datetime:

            role = "Date / Time"
            datetime_columns.append(column)

        elif (
            unique_ratio >= 0.98
            and unique_count > 20
            and not is_numeric
            and not is_boolean
        ):

            role = "Potential Identifier"
            identifier_candidates.append(column)

        elif is_numeric:

            role = "Numerical Feature"

        else:

            role = "Categorical Feature"

        if (
            unique_count == 2
            and role not in [
                "Constant",
                "Date / Time",
                "Potential Identifier",
            ]
        ):

            role = "Binary Feature / Possible Target"

            binary_candidates.append({
                "column": column,
                "values": list(values.unique()),
                "distribution": values.value_counts(
                    normalize=True
                ).to_dict(),
            })

        profile.append({
            "Column": column,
            "Data Type": str(series.dtype),
            "Detected Role": role,
            "Unique Values": int(unique_count),
            "Uniqueness Ratio": round(unique_ratio, 4),
            "Missing %": round(missing_pct, 2),
        })

    return {
        "profile": pd.DataFrame(profile),
        "binary_candidates": binary_candidates,
        "identifiers": identifier_candidates,
        "constants": constant_columns,
        "datetime_columns": datetime_columns,
    }


# =========================================================
# 6. FEATURE PREPARATION
# =========================================================

def prepare_features(df, columns, profile):

    X = df[columns].copy()

    for column in X.columns:

        if column in profile["datetime_columns"]:

            parsed = pd.to_datetime(
                X[column],
                errors="coerce",
                format="mixed",
                utc=True,
            )

            X[column] = (
                parsed.astype("int64").astype(float)
                .where(parsed.notna(), np.nan)
                / 1_000_000_000
            )

        elif pd.api.types.is_bool_dtype(X[column]):

            X[column] = X[column].astype(float)

        elif pd.api.types.is_object_dtype(X[column]):

            X[column] = X[column].astype(object)
            X[column] = X[column].where(
                X[column].notna(), np.nan
            )

    all_missing = [
        column for column in X.columns
        if X[column].isna().all()
    ]

    X = X.drop(columns=all_missing)

    if X.empty:
        raise ValueError("No usable feature columns available.")

    return X, all_missing


# =========================================================
# 7. DYNAMIC PREPROCESSING
# =========================================================

def build_preprocessor(X):

    numeric_columns = X.select_dtypes(
        include=["number"]
    ).columns.tolist()

    categorical_columns = [
        column for column in X.columns
        if column not in numeric_columns
    ]

    transformers = []

    if numeric_columns:

        numeric_pipeline = Pipeline([
            (
                "imputer",
                SimpleImputer(strategy="median"),
            ),
            (
                "scaler",
                StandardScaler(),
            ),
        ])

        transformers.append((
            "numeric",
            numeric_pipeline,
            numeric_columns,
        ))

    if categorical_columns:

        categorical_pipeline = Pipeline([
            (
                "imputer",
                SimpleImputer(strategy="most_frequent"),
            ),
            (
                "encoder",
                OneHotEncoder(handle_unknown="ignore"),
            ),
        ])

        transformers.append((
            "categorical",
            categorical_pipeline,
            categorical_columns,
        ))

    if not transformers:
        raise ValueError("No usable model features.")

    return ColumnTransformer(
        transformers=transformers,
        remainder="drop",
    )


# =========================================================
# 8. MODEL FACTORY
# =========================================================

def create_supervised_model(X):

    return Pipeline([
        ("preprocessor", build_preprocessor(X)),
        (
            "detector",
            RandomForestClassifier(
                n_estimators=300,
                class_weight="balanced",
                random_state=42,
                n_jobs=-1,
            ),
        ),
    ])


def create_isolation_model(X, contamination):

    return Pipeline([
        ("preprocessor", build_preprocessor(X)),
        (
            "detector",
            IsolationForest(
                n_estimators=250,
                contamination=contamination,
                random_state=42,
                n_jobs=-1,
            ),
        ),
    ])


# =========================================================
# 9. ANOMALY ENSEMBLE
# =========================================================

def percentile_scores(values):

    values = np.asarray(values, dtype=float)

    ranks = pd.Series(values).rank(
        pct=True,
        method="average",
    ).to_numpy()

    return ranks * 100


def calculate_anomaly_scores(X, contamination):

    preprocessor = build_preprocessor(X)

    transformed = preprocessor.fit_transform(X)

    isolation = IsolationForest(
        n_estimators=250,
        contamination=contamination,
        random_state=42,
        n_jobs=-1,
    )

    isolation.fit(transformed)

    isolation_raw = -isolation.decision_function(
        transformed
    )

    isolation_scores = percentile_scores(
        isolation_raw
    )

    # LOF operates on a bounded-size sample to avoid
    # excessive memory and computation for large datasets.
    max_lof_rows = 10000

    if transformed.shape[0] > max_lof_rows:

        rng = np.random.default_rng(42)

        lof_indices = np.sort(
            rng.choice(
                transformed.shape[0],
                size=max_lof_rows,
                replace=False,
            )
        )

        sample = transformed[lof_indices]

    else:

        lof_indices = np.arange(
            transformed.shape[0]
        )

        sample = transformed

    if hasattr(sample, "toarray"):
        sample = sample.toarray()

    if sample.shape[0] >= 3:

        neighbors = min(
            20,
            sample.shape[0] - 1,
        )

        lof = LocalOutlierFactor(
            n_neighbors=neighbors,
            contamination=contamination,
        )

        lof.fit_predict(sample)

        lof_raw = -lof.negative_outlier_factor_

        lof_sample_scores = percentile_scores(
            lof_raw
        )

        lof_scores = np.interp(
            np.arange(len(X)),
            lof_indices,
            lof_sample_scores,
        )

    else:

        lof_scores = isolation_scores.copy()

    combined_scores = (
        0.60 * isolation_scores
        + 0.40 * lof_scores
    )

    return {
        "scores": combined_scores,
        "isolation_scores": isolation_scores,
        "lof_scores": lof_scores,
        "isolation_predictions": isolation.predict(
            transformed
        ),
    }


# =========================================================
# 10. RISK CLASSIFICATION
# =========================================================

def risk_band(score):

    if score >= 85:
        return "Critical"

    if score >= 65:
        return "High"

    if score >= 35:
        return "Medium"

    return "Low"


# =========================================================
# 11. SUPERVISED MODEL USING VERIFIED FEEDBACK
# =========================================================

def train_feedback_model(
    feedback_data,
    current_features,
):

    if feedback_data.empty:
        return None

    if "reviewed_label" not in feedback_data.columns:
        return None

    if feedback_data["reviewed_label"].nunique() != 2:
        return None

    # Require sufficient reviewed examples per class.
    counts = feedback_data["reviewed_label"].value_counts()

    if counts.min() < 10:
        return None

    feature_columns = list(current_features.columns)

    training_X = feedback_data.reindex(
        columns=feature_columns
    )

    training_y = feedback_data["reviewed_label"]

    # Recreate the current preprocessing schema.
    training_X = training_X.copy()

    for column in training_X.columns:

        if pd.api.types.is_numeric_dtype(
            current_features[column]
        ):
            training_X[column] = pd.to_numeric(
                training_X[column],
                errors="coerce",
            )

        else:
            training_X[column] = (
                training_X[column].astype(object)
            )

    model = create_supervised_model(
        training_X
    )

    model.fit(
        training_X,
        training_y,
    )

    return model


# =========================================================
# 12. BUSINESS RULES
# =========================================================

def apply_business_rule(
    results,
    source_df,
    rule_column,
    threshold,
    direction,
    row_positions,
):

    values = pd.to_numeric(
        source_df.iloc[row_positions][rule_column],
        errors="coerce",
    ).reset_index(drop=True)

    if direction == "Above threshold":

        triggered = values > threshold

    else:

        triggered = values < threshold

    results["Business rule triggered"] = (
        triggered.fillna(False).to_numpy()
    )

    results.loc[
        results["Business rule triggered"],
        "Detection status",
    ] = "Flagged by rule"

    # Transparent rule contribution to the combined score.
    results["Final risk score"] = np.maximum(
        results["Risk score"].to_numpy(),
        np.where(
            triggered.fillna(False).to_numpy(),
            85,
            0,
        ),
    )

    results["Risk level"] = [
        risk_band(score)
        for score in results["Final risk score"]
    ]

    return results, int(
        triggered.fillna(False).sum()
    )


# =========================================================
# 13. FEEDBACK EXPORT
# =========================================================

def csv_download(data):

    return data.to_csv(
        index=False
    ).encode("utf-8")


# =========================================================
# 14. MAIN HEADER
# =========================================================

left, right = st.columns(
    [3, 1],
    vertical_alignment="center",
)

with left:

    st.title("🛡️ Fraud Intelligence")

    st.caption(
        "Universal fraud detection and investigation workspace"
    )

with right:

    st.markdown(
        f"""
        <div style="text-align:right;padding-top:12px">
        <span style="color:#64748b">Signed in</span><br>
        <strong>{st.session_state.get('username', 'User')}</strong>
        </div>
        """,
        unsafe_allow_html=True,
    )


# =========================================================
# 15. INDUSTRY CONTEXT
# =========================================================

with st.container(border=True):

    st.markdown("#### Detection context")

    c1, c2 = st.columns(2)

    with c1:

        industry = st.selectbox(
            "Industry",
            list(INDUSTRY_USE_CASES.keys()),
            key="fraud_industry_selector",
        )

    with c2:

        use_case = st.selectbox(
            "Use case",
            INDUSTRY_USE_CASES[industry],
            key="fraud_use_case_selector",
        )


# =========================================================
# 16. APPLICATION TABS
# =========================================================

overview_tab, detection_tab, feedback_tab, guidance_tab = (
    st.tabs([
        "Data & Overview",
        "Detection Workbench",
        "Investigation Feedback",
        "Methodology",
    ])
)


# =========================================================
# TAB 1 - DATA & OVERVIEW
# =========================================================

with overview_tab:

    st.markdown("### Dataset ingestion")

    uploaded_file = st.file_uploader(
        "Upload CSV, Excel or JSON",
        type=["csv", "xlsx", "xls", "json"],
        key="fraud_dataset_upload",
    )

    if uploaded_file is None:

        clear_fraud_session()

        st.info(
            "Upload a dataset to begin."
        )

    else:

        try:

            fingerprint = get_fingerprint(
                uploaded_file
            )

            old_fingerprint = st.session_state.get(
                "_fraud_dataset_fingerprint"
            )

            if fingerprint != old_fingerprint:

                clear_fraud_session()

                df_loaded = load_dataset(
                    uploaded_file
                )

                if df_loaded.empty:
                    raise ValueError("Dataset is empty.")

                if not df_loaded.columns.is_unique:
                    raise ValueError(
                        "Duplicate column names detected."
                    )

                st.session_state["fraud_source_df"] = (
                    df_loaded.copy()
                )

                st.session_state["fraud_source_name"] = (
                    uploaded_file.name
                )

                st.session_state[
                    "_fraud_dataset_fingerprint"
                ] = fingerprint

            st.session_state[
                "_fraud_page_initialized"
            ] = True

        except Exception as exc:

            logger.exception(
                "Dataset ingestion error."
            )

            clear_fraud_session()

            st.error(
                f"Unable to load dataset: {exc}"
            )

    df = st.session_state.get(
        "fraud_source_df"
    )

    if df is not None:

        st.success(
            f"Loaded: {st.session_state['fraud_source_name']}"
        )

        missing = int(
            df.isna().sum().sum()
        )

        duplicates = int(
            df.duplicated().sum()
        )

        k1, k2, k3, k4 = st.columns(4)

        k1.metric("Records", f"{len(df):,}")
        k2.metric("Columns", f"{len(df.columns):,}")
        k3.metric("Missing cells", f"{missing:,}")
        k4.metric("Duplicate rows", f"{duplicates:,}")

        st.markdown("#### Dataset preview")

        st.dataframe(
            df.head(100),
            use_container_width=True,
        )

        profile = profile_dataset(df)

        with st.expander("Dynamic schema profile"):

            st.dataframe(
                profile["profile"],
                use_container_width=True,
                hide_index=True,
            )

        if duplicates:
            st.warning(
                f"{duplicates:,} duplicate rows found."
            )

        st.divider()

        st.button(
            "Remove dataset and reset session",
            on_click=remove_dataset_callback,
            use_container_width=True,
        )


# =========================================================
# TAB 2 - DETECTION WORKBENCH
# =========================================================

with detection_tab:

    df = st.session_state.get(
        "fraud_source_df"
    )

    fingerprint = st.session_state.get(
        "_fraud_dataset_fingerprint"
    )

    if df is None:

        st.info(
            "Upload a dataset in Data & Overview first."
        )

    else:

        profile = profile_dataset(df)

        st.markdown("### 1. Intelligent data profiling")

        c1, c2, c3, c4 = st.columns(4)

        c1.metric("Total columns", len(df.columns))

        c2.metric(
            "Binary candidates",
            len(profile["binary_candidates"]),
        )

        c3.metric(
            "Potential identifiers",
            len(profile["identifiers"]),
        )

        c4.metric(
            "Constant columns",
            len(profile["constants"]),
        )

        with st.expander("Review column classification"):

            st.dataframe(
                profile["profile"],
                use_container_width=True,
                hide_index=True,
            )

        # ---------------------------------------------
        # TARGET DETECTION
        # ---------------------------------------------

        st.markdown("### 2. Detection mode")

        st.caption(
            "A binary column is only a target candidate. "
            "It is not automatically considered a fraud label."
        )

        binary_columns = [
            item["column"]
            for item in profile["binary_candidates"]
        ]

        target_options = [
            "No confirmed label - Automatic detection"
        ] + binary_columns

        target_column = st.selectbox(
            "Ground-truth fraud label (if available)",
            target_options,
            key="fraud_target_selector",
        )

        supervised = (
            target_column !=
            "No confirmed label - Automatic detection"
        )

        if supervised:

            selected_target = target_column

            positive_class = st.selectbox(
                "Select confirmed fraud class",
                df[selected_target].dropna().unique().tolist(),
                key="fraud_positive_class",
            )

            st.success(
                f"Supervised detection selected: {selected_target}"
            )

        else:

            selected_target = None
            positive_class = None

            st.info(
                "No confirmed fraud label selected. "
                "The platform will use unsupervised anomaly detection."
            )

        # ---------------------------------------------
        # FEATURE SELECTION
        # ---------------------------------------------

        st.markdown("### 3. Feature configuration")

        available = [
            c for c in df.columns
            if c != selected_target
        ]

        defaults = list(dict.fromkeys(
            profile["identifiers"] + profile["constants"]
        ))

        defaults = [
            c for c in defaults
            if c in available
        ]

        excluded = st.multiselect(
            "Exclude identifiers and other columns",
            available,
            default=defaults,
            key="fraud_excluded_columns",
        )

        feature_columns = [
            c for c in available
            if c not in excluded
        ]

        if not feature_columns:

            st.error("No usable features selected.")

            st.stop()

        # ---------------------------------------------
        # DETECTION SETTINGS
        # ---------------------------------------------

        st.markdown("### 4. Detection configuration")

        if supervised:

            st.info(
                "Random Forest classification will be used."
            )

            test_size = st.slider(
                "Test dataset (%)",
                10,
                40,
                20,
                5,
            ) / 100

            contamination = 0.05

        else:

            st.info(
                "Hybrid anomaly detection will combine "
                "Isolation Forest and Local Outlier Factor."
            )

            contamination = st.slider(
                "Expected anomaly proportion (%)",
                1,
                30,
                5,
            ) / 100

            test_size = 0.20

        # ---------------------------------------------
        # BUSINESS RULES
        # ---------------------------------------------

        st.markdown("### 5. Business rules")

        numeric_features = [
            c for c in feature_columns
            if pd.api.types.is_numeric_dtype(df[c])
        ]

        enable_rule = st.checkbox(
            "Enable numeric threshold rule"
        )

        rule_column = None
        rule_threshold = None
        rule_direction = None

        if enable_rule and numeric_features:

            rule_column = st.selectbox(
                "Rule field",
                numeric_features,
            )

            values = pd.to_numeric(
                df[rule_column],
                errors="coerce",
            ).dropna()

            if not values.empty:

                rule_direction = st.radio(
                    "Condition",
                    [
                        "Above threshold",
                        "Below threshold",
                    ],
                    horizontal=True,
                )

                rule_threshold = st.number_input(
                    "Threshold",
                    value=float(values.median()),
                    format="%.4f",
                )

        elif enable_rule:

            st.warning(
                "No numeric features are available for rules."
            )

        # ---------------------------------------------
        # RUN DETECTION
        # ---------------------------------------------

        if st.button(
            "Run Fraud Detection",
            type="primary",
            use_container_width=True,
        ):

            try:

                X, removed = prepare_features(
                    df,
                    feature_columns,
                    profile,
                )

                if removed:
                    st.warning(
                        f"All-missing columns excluded: {removed}"
                    )

                if supervised:

                    y = df[selected_target]

                    valid = y.notna()

                    X = X.loc[valid].reset_index(drop=True)
                    y = y.loc[valid].reset_index(drop=True)

                    if y.nunique() != 2:
                        raise ValueError(
                            "Supervised target must have exactly two classes."
                        )

                    if y.value_counts().min() < 2:
                        raise ValueError(
                            "Each class needs at least two observations."
                        )

                    X_train, X_test, y_train, y_test = (
                        train_test_split(
                            X,
                            y,
                            test_size=test_size,
                            random_state=42,
                            stratify=y,
                        )
                    )

                    model = create_supervised_model(
                        X_train
                    )

                    model.fit(
                        X_train,
                        y_train,
                    )

                    predictions = model.predict(
                        X_test
                    )

                    probabilities = model.predict_proba(
                        X_test
                    )

                    classes = list(
                        model.named_steps["detector"].classes_
                    )

                    positive_index = classes.index(
                        positive_class
                    )

                    scores = (
                        probabilities[:, positive_index] * 100
                    )

                    actual_binary = (
                        y_test == positive_class
                    ).astype(int)

                    predicted_binary = (
                        predictions == positive_class
                    ).astype(int)

                    metrics = {
                        "Accuracy": accuracy_score(
                            y_test,
                            predictions,
                        ),
                        "Precision": precision_score(
                            actual_binary,
                            predicted_binary,
                            zero_division=0,
                        ),
                        "Recall": recall_score(
                            actual_binary,
                            predicted_binary,
                            zero_division=0,
                        ),
                        "F1-score": f1_score(
                            actual_binary,
                            predicted_binary,
                            zero_division=0,
                        ),
                    }

                    if actual_binary.nunique() == 2:

                        metrics["ROC-AUC"] = roc_auc_score(
                            actual_binary,
                            probabilities[:, positive_index],
                        )

                    result_df = X_test.reset_index(
                        drop=True
                    ).copy()

                    result_df["Actual outcome"] = (
                        y_test.reset_index(drop=True).astype(str)
                    )

                    result_df["Predicted outcome"] = (
                        pd.Series(predictions).astype(str)
                    )

                    result_df["Risk score"] = np.round(
                        scores, 2
                    )

                    result_df["Risk level"] = [
                        risk_band(float(s))
                        for s in scores
                    ]

                    result_df["Detection status"] = np.where(
                        predicted_binary == 1,
                        "Flagged",
                        "Not flagged",
                    )

                    result = {
                        "mode": "Supervised",
                        "model": "Random Forest",
                        "results": result_df,
                        "metrics": metrics,
                        "confusion_matrix": confusion_matrix(
                            y_test,
                            predictions,
                            labels=classes,
                        ),
                        "classes": [str(x) for x in classes],
                        "report": classification_report(
                            y_test,
                            predictions,
                            output_dict=True,
                            zero_division=0,
                        ),
                        "row_positions": X_test.index.to_numpy(),
                    }

                else:

                    anomaly = calculate_anomaly_scores(
                        X,
                        contamination,
                    )

                    scores = anomaly["scores"]

                    threshold = np.quantile(
                        scores,
                        1 - contamination,
                    )

                    flagged = scores >= threshold

                    result_df = X.reset_index(
                        drop=True
                    ).copy()

                    result_df["Isolation Forest score"] = np.round(
                        anomaly["isolation_scores"], 2
                    )

                    result_df["Local Outlier Factor score"] = np.round(
                        anomaly["lof_scores"], 2
                    )

                    result_df["Risk score"] = np.round(
                        scores, 2
                    )

                    result_df["Risk level"] = [
                        risk_band(float(s))
                        for s in scores
                    ]

                    result_df["Detection status"] = np.where(
                        flagged,
                        "Flagged",
                        "Not flagged",
                    )

                    result = {
                        "mode": "Unsupervised",
                        "model": "Isolation Forest + LOF",
                        "results": result_df,
                        "metrics": {
                            "Records analyzed": len(X),
                            "Flagged records": int(flagged.sum()),
                            "Flagged proportion": float(flagged.mean()),
                        },
                        "row_positions": np.arange(len(X)),
                    }

                # -------------------------------------
                # OPTIONAL BUSINESS RULE
                # -------------------------------------

                if (
                    enable_rule
                    and rule_column is not None
                    and rule_threshold is not None
                ):

                    positions = result["row_positions"]

                    result_df, rule_count = apply_business_rule(
                        result["results"],
                        df,
                        rule_column,
                        rule_threshold,
                        rule_direction,
                        positions,
                    )

                    result["results"] = result_df

                    result["rule_count"] = rule_count

                    result["rule_description"] = (
                        f"{rule_column} {rule_direction.lower()} "
                        f"{rule_threshold}"
                    )

                # -------------------------------------
                # FEEDBACK-BASED LEARNING
                # -------------------------------------

                reviewed = get_reviewed_training_data(
                    fingerprint
                )

                result["reviewed_feedback_count"] = len(
                    reviewed
                )

                result["feedback_model_available"] = False

                if not supervised and not reviewed.empty:

                    feedback_model = train_feedback_model(
                        reviewed,
                        X,
                    )

                    if feedback_model is not None:

                        feedback_probabilities = (
                            feedback_model.predict_proba(X)
                        )

                        feedback_classes = list(
                            feedback_model.named_steps[
                                "detector"
                            ].classes_
                        )

                        if 1 in feedback_classes:

                            feedback_scores = (
                                feedback_probabilities[
                                    :,
                                    feedback_classes.index(1),
                                ] * 100
                            )

                            result["results"][
                                "Feedback model score"
                            ] = np.round(
                                feedback_scores, 2
                            )

                            result["feedback_model_available"] = True

                            # Add verified feedback model signal
                            # to the anomaly ensemble.
                            combined = (
                                0.70 * result["results"][
                                    "Risk score"
                                ].to_numpy()
                                + 0.30 * feedback_scores
                            )

                            result["results"][
                                "Risk score"
                            ] = np.round(combined, 2)

                            result["results"][
                                "Risk level"
                            ] = [
                                risk_band(float(s))
                                for s in combined
                            ]

                st.session_state["fraud_result"] = result

                st.success(
                    "Detection completed successfully."
                )

            except Exception as exc:

                logger.exception(
                    "Fraud detection failed."
                )

                st.error(
                    f"Detection failed: {exc}"
                )

        # ---------------------------------------------
        # DISPLAY RESULTS
        # ---------------------------------------------

        result = st.session_state.get(
            "fraud_result"
        )

        if result is not None:

            st.divider()

            st.markdown("### Detection results")

            st.caption(
                f"{result['model']} | {result['mode']}"
            )

            if result["mode"] == "Supervised":

                columns = st.columns(
                    len(result["metrics"])
                )

                for col, (name, value) in zip(
                    columns,
                    result["metrics"].items(),
                ):

                    col.metric(
                        name,
                        f"{value:.3f}",
                    )

            else:

                columns = st.columns(3)

                columns[0].metric(
                    "Records analyzed",
                    result["metrics"]["Records analyzed"],
                )

                columns[1].metric(
                    "Flagged records",
                    result["metrics"]["Flagged records"],
                )

                columns[2].metric(
                    "Flagged proportion",
                    f"{result['metrics']['Flagged proportion']:.1%}",
                )

            if result.get("rule_count") is not None:

                st.info(
                    f"Business rule: {result['rule_description']} | "
                    f"Triggered records: {result['rule_count']}"
                )

            if result.get("feedback_model_available"):

                st.success(
                    "Verified investigator feedback was incorporated "
                    "into the anomaly risk scoring."
                )

            elif result.get("reviewed_feedback_count", 0):

                st.info(
                    f"{result['reviewed_feedback_count']} reviewed "
                    "feedback records available. More confirmed "
                    "examples from both classes are required before "
                    "feedback-based supervised learning can activate."
                )

            results_df = result["results"]

            flagged_count = int(
                results_df["Detection status"]
                .astype(str)
                .str.startswith("Flagged")
                .sum()
            )

            high_risk = int(
                results_df["Risk level"]
                .isin(["High", "Critical"])
                .sum()
            )

            c1, c2, c3 = st.columns(3)

            c1.metric(
                "Scored records",
                len(results_df),
            )

            c2.metric(
                "Flagged records",
                flagged_count,
            )

            c3.metric(
                "High / critical risk",
                high_risk,
            )

            # -----------------------------------------
            # RISK DISTRIBUTION
            # -----------------------------------------

            left, right = st.columns(2)

            with left:

                counts = (
                    results_df["Risk level"]
                    .value_counts()
                    .reindex(
                        ["Low", "Medium", "High", "Critical"],
                        fill_value=0,
                    )
                    .rename_axis("Risk")
                    .reset_index(name="Records")
                )

                fig = px.bar(
                    counts,
                    x="Risk",
                    y="Records",
                    color="Risk",
                    title="Risk distribution",
                    text="Records",
                )

                st.plotly_chart(
                    fig,
                    use_container_width=True,
                )

            with right:

                counts = (
                    results_df["Detection status"]
                    .value_counts()
                    .rename_axis("Status")
                    .reset_index(name="Records")
                )

                fig = px.pie(
                    counts,
                    names="Status",
                    values="Records",
                    title="Detection outcomes",
                    hole=0.45,
                )

                st.plotly_chart(
                    fig,
                    use_container_width=True,
                )

            fig = px.histogram(
                results_df,
                x="Risk score",
                color="Risk level",
                nbins=20,
                title="Risk score distribution",
            )

            st.plotly_chart(
                fig,
                use_container_width=True,
            )

            if result["mode"] == "Supervised":

                st.markdown("#### Confusion matrix")

                cm = pd.DataFrame(
                    result["confusion_matrix"],
                    index=[
                        f"Actual {x}"
                        for x in result["classes"]
                    ],
                    columns=[
                        f"Predicted {x}"
                        for x in result["classes"]
                    ],
                )

                st.dataframe(
                    cm,
                    use_container_width=True,
                )

                with st.expander("Classification report"):

                    st.dataframe(
                        pd.DataFrame(
                            result["report"]
                        ).transpose(),
                        use_container_width=True,
                    )

            st.markdown("#### Scored records")

            st.dataframe(
                results_df,
                use_container_width=True,
                height=400,
            )

            st.download_button(
                "Download detection results",
                data=csv_download(results_df),
                file_name="fraud_detection_results.csv",
                mime="text/csv",
                use_container_width=True,
            )

            st.warning(
                "An anomaly or model alert is not proof of fraud. "
                "Investigate and validate before taking action."
            )


# =========================================================
# TAB 3 - INVESTIGATION FEEDBACK
# =========================================================

with feedback_tab:

    st.markdown(
        "### Investigator feedback"
    )

    st.caption(
        "Record reviewed outcomes to build a verified historical "
        "feedback dataset for future model learning."
    )

    df = st.session_state.get(
        "fraud_source_df"
    )

    result = st.session_state.get(
        "fraud_result"
    )

    fingerprint = st.session_state.get(
        "_fraud_dataset_fingerprint"
    )

    if df is None or result is None:

        st.info(
            "Upload a dataset and run detection before recording feedback."
        )

    else:

        results_df = result["results"]

        row_number = st.selectbox(
            "Select scored record",
            options=list(range(len(results_df))),
            format_func=lambda x: (
                f"Record {x + 1} | "
                f"Risk: {results_df.iloc[x]['Risk level']} | "
                f"Score: {results_df.iloc[x]['Risk score']}"
            ),
            key="fraud_feedback_row",
        )

        selected_record = results_df.iloc[row_number]

        st.markdown("#### Selected record")

        st.dataframe(
            selected_record.to_frame("Value"),
            use_container_width=True,
        )

        outcome = st.selectbox(
            "Investigation outcome",
            FEEDBACK_OPTIONS,
            key="fraud_feedback_outcome",
        )

        if st.button(
            "Save investigation feedback",
            type="primary",
            use_container_width=True,
        ):

            try:

                feature_columns = [
                    c for c in results_df.columns
                    if c not in [
                        "Actual outcome",
                        "Predicted outcome",
                        "Detection status",
                        "Risk score",
                        "Risk level",
                        "Business rule triggered",
                        "Isolation Forest score",
                        "Local Outlier Factor score",
                        "Final risk score",
                        "Feedback model score",
                    ]
                ]

                feature_data = {}

                for column in feature_columns:

                    value = selected_record[column]

                    if pd.isna(value):
                        value = None

                    elif isinstance(value, np.generic):
                        value = value.item()

                    feature_data[column] = value

                feedback_record = {

                    "dataset_fingerprint": fingerprint,

                    "dataset_name": st.session_state.get(
                        "fraud_source_name",
                        "",
                    ),

                    "row_number": row_number,

                    "outcome": outcome,

                    "features_json": json.dumps(
                        feature_data,
                        default=str,
                    ),

                    "reviewed_by": st.session_state.get(
                        "username",
                        "User",
                    ),

                    "reviewed_at": datetime.now(
                        timezone.utc
                    ).isoformat(),

                }

                save_feedback(
                    feedback_record
                )

                st.success(
                    "Investigation feedback saved successfully."
                )

            except Exception as exc:

                logger.exception(
                    "Unable to save investigation feedback."
                )

                st.error(
                    f"Feedback could not be saved: {exc}"
                )

        # ---------------------------------------------
        # FEEDBACK HISTORY
        # ---------------------------------------------

        feedback = load_feedback()

        if not feedback.empty:

            dataset_feedback = feedback[
                feedback["dataset_fingerprint"] == fingerprint
            ]

            st.divider()

            st.markdown(
                "#### Current dataset feedback history"
            )

            st.dataframe(
                dataset_feedback.drop(
                    columns=["features_json"],
                    errors="ignore",
                ),
                use_container_width=True,
            )

            st.markdown(
                "#### Feedback summary"
            )

            summary = (
                dataset_feedback["outcome"]
                .value_counts()
                .rename_axis("Outcome")
                .reset_index(name="Records")
            )

            st.dataframe(
                summary,
                use_container_width=True,
                hide_index=True,
            )

            st.download_button(
                "Download feedback history",
                data=csv_download(dataset_feedback),
                file_name="investigation_feedback.csv",
                mime="text/csv",
            )


# =========================================================
# TAB 4 - METHODOLOGY
# =========================================================

with guidance_tab:

    st.markdown(
        "### Universal detection methodology"
    )

    st.markdown(
        """
        **1. Dynamic data profiling**

        - Runtime data type identification.
        - Binary target candidate identification.
        - Potential identifier detection.
        - Date/time identification.
        - Missing value and uniqueness profiling.

        **2. Supervised detection**

        - Explicitly confirmed target selection.
        - Random Forest classification.
        - Minority class identification for risk scoring.
        - Accuracy, precision, recall, F1 and ROC-AUC.

        **3. Unsupervised detection**

        - Isolation Forest.
        - Local Outlier Factor.
        - Combined anomaly scores.
        - No historical fraud label required.

        **4. Hybrid risk intelligence**

        - Anomaly scores.
        - Configurable numeric business rules.
        - Transparent rule-triggered alerts.

        **5. Feedback-based learning**

        - Investigator-confirmed fraud.
        - Legitimate activity.
        - False positive.
        - Further investigation.
        - Reviewed outcomes stored separately.
        - Feedback model activates after sufficient examples
          from both verified classes are available.
        """
    )

    st.markdown(
        "### Important limitations"
    )

    st.markdown(
        """
        - Unsupervised detection identifies unusual records,
          not confirmed fraudulent records.
        - LOF and Isolation Forest scores are relative anomaly
          indicators, not calibrated probabilities.
        - The combined anomaly score is a ranking signal.
        - A minority target class is not necessarily fraud;
          the business meaning must be confirmed.
        - Feedback learning requires sufficient representative
          reviewed examples and validation before production use.
        - Feedback is persisted in a local CSV file and is not
          a multi-user transactional database.
        - Dataset fingerprinting restricts feedback reuse to the
          exact uploaded file.
        - Automatic feature profiling does not guarantee
          prevention of target leakage.
        - This implementation performs batch detection.
        - Production deployment should add audit logging,
          access controls, drift monitoring and model validation.
        """
    )
