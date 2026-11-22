"""Universal, industry-agnostic AI/ML workbench.

Authentication, global navigation and platform configuration are owned by app.py.
This page only owns its dataset and analytical workflow state.
"""
from __future__ import annotations

import io
import json
import logging
from datetime import datetime, timezone

import pandas as pd
import plotly.express as px
import streamlit as st

from universal_ai_studio.data_platform.ingestion import DatasetIngestionError, read_dataset
from universal_ai_studio.data_platform.profiling import profile_dataset, recommend_objectives
from universal_ai_studio.ai_platform.ml.engine import (
    run_forecasting, run_recommendations, run_supervised, run_unsupervised,
)
from universal_ai_studio.ai_platform.ml.registry import algorithms_for, recommend_algorithm_keys



def _audit_workbench(event: str, details: dict) -> None:
    """Write metadata-only audit events; never log dataset rows or values."""
    try:
        from universal_ai_studio.core.logging import write_audit_event
        write_audit_event(actor=str(st.session_state.get("username", "unknown")),
                          event=event, details=details)
    except Exception:
        logging.exception("Universal AI/ML audit event could not be persisted")

st.title("✦ Universal AI/ML Workbench")
st.caption("Upload or connect structured data, define an analytical objective, and let the platform adapt its workflow to your dataset.")

st.info("Your uploaded dataset is processed within this application workflow. Data is not sent to an LLM by default. Choose an AI-assisted workflow separately if you want to use a configured provider.")

if "uas_ml_frame" not in st.session_state:
    st.session_state.uas_ml_frame = None
if "uas_ml_filename" not in st.session_state:
    st.session_state.uas_ml_filename = None
if "uas_ml_profile" not in st.session_state:
    st.session_state.uas_ml_profile = None
if "uas_ml_results" not in st.session_state:
    st.session_state.uas_ml_results = []

with st.container(border=True):
    st.subheader("1. Add or connect a dataset")
    source_mode = st.radio(
        "Dataset source",
        ["Upload file", "Configured SQL Server", "Configured REST API", "Synthetic demo"],
        horizontal=True,
        key="uas_ml_source_mode",
    )
    if source_mode == "Upload file":
        uploaded = st.file_uploader(
            "Upload CSV, Excel, JSON, JSONL or Parquet",
            type=["csv", "xlsx", "xls", "json", "jsonl", "ndjson", "parquet"],
            help="Maximum upload size: 100 MB. The workbench supports structured tabular datasets.",
            key="uas_ml_upload",
        )
        if uploaded is not None:
            try:
                frame = read_dataset(uploaded.name, uploaded.getvalue())
                st.session_state.uas_ml_frame = frame
                st.session_state.uas_ml_filename = uploaded.name
                st.session_state.uas_ml_profile = profile_dataset(frame)
                st.session_state.uas_ml_results = []
                st.session_state.uas_ml_recommendations = None
                _audit_workbench("universal_ai_ml.dataset_loaded", {"source": "file_upload", "rows": len(frame), "columns": len(frame.columns)})
                st.success(f"Dataset loaded: {len(frame):,} rows × {len(frame.columns):,} columns.")
            except DatasetIngestionError as exc:
                st.error(str(exc))
            except Exception as exc:
                st.error(f"Dataset loading failed: {type(exc).__name__}: {exc}")
    elif source_mode == "Configured SQL Server":
        st.caption("Uses the centrally configured SQL Server connection. Configure credentials under Platform Administration → Integrations; connection secrets are not requested or stored on this page.")
        if st.button("Connect and list tables", key="uas_ml_sql_list"):
            try:
                from universal_ai_studio.data_platform.connectors import list_sql_server_tables
                st.session_state.uas_ml_sql_tables = list_sql_server_tables()
            except Exception as exc:
                st.error(str(exc))
        sql_tables = st.session_state.get("uas_ml_sql_tables", [])
        if sql_tables:
            selected_table = st.selectbox("Available table", sql_tables, key="uas_ml_sql_table")
            if st.button("Load selected table", type="primary", key="uas_ml_sql_load"):
                try:
                    from universal_ai_studio.data_platform.connectors import load_sql_server_table
                    frame = load_sql_server_table(selected_table)
                    st.session_state.uas_ml_frame = frame
                    st.session_state.uas_ml_filename = f"sql_server:{selected_table}"
                    st.session_state.uas_ml_profile = profile_dataset(frame)
                    st.session_state.uas_ml_results = []
                    st.session_state.uas_ml_recommendations = None
                    _audit_workbench("universal_ai_ml.dataset_loaded", {"source": "configured_sql_server", "rows": len(frame), "columns": len(frame.columns)})
                    st.success(f"Loaded up to {len(frame):,} rows from {selected_table}.")
                except Exception as exc:
                    st.error(str(exc))
        else:
            st.info("No table list is available yet. Connect using the button above.")
    elif source_mode == "Configured REST API":
        st.caption("Uses the centrally configured REST API base URL and encrypted authentication settings.")
        endpoint_path = st.text_input("Relative JSON endpoint path", placeholder="/v1/records", key="uas_ml_rest_path")
        if st.button("Load API dataset", type="primary", disabled=not endpoint_path.strip(), key="uas_ml_rest_load"):
            try:
                from universal_ai_studio.data_platform.connectors import load_rest_dataset
                frame = load_rest_dataset(endpoint_path)
                st.session_state.uas_ml_frame = frame
                st.session_state.uas_ml_filename = f"rest_api:{endpoint_path}"
                st.session_state.uas_ml_profile = profile_dataset(frame)
                st.session_state.uas_ml_results = []
                st.session_state.uas_ml_recommendations = None
                _audit_workbench("universal_ai_ml.dataset_loaded", {"source": "configured_rest_api", "rows": len(frame), "columns": len(frame.columns)})
                st.success(f"API dataset loaded: {len(frame):,} rows × {len(frame.columns):,} columns.")
            except Exception as exc:
                st.error(str(exc))
    elif source_mode == "Synthetic demo":
        st.caption("Demonstration data is synthetic and does not represent a real organization or customer.")
        if st.button("Load synthetic dataset", type="primary", key="uas_ml_demo"):
            demo = pd.DataFrame({
                "record_date": pd.date_range("2025-01-01", periods=240, freq="D"),
                "segment": ["A", "B", "C", "D"] * 60,
                "feature_alpha": [((i * 7) % 31) + (i % 5) for i in range(240)],
                "feature_beta": [((i * 11) % 43) / 3 for i in range(240)],
                "feature_gamma": [float((i % 17) * 2 + (i % 3)) for i in range(240)],
            })
            demo["outcome_value"] = 2.4 * demo["feature_alpha"] - 1.3 * demo["feature_beta"] + demo["feature_gamma"] * 0.7
            demo.loc[::19, "feature_beta"] = None
            st.session_state.uas_ml_frame = demo
            st.session_state.uas_ml_filename = "synthetic_universal_demo.csv"
            st.session_state.uas_ml_profile = profile_dataset(demo)
            st.session_state.uas_ml_results = []
            st.session_state.uas_ml_recommendations = None
            _audit_workbench("universal_ai_ml.dataset_loaded", {"source": "synthetic_demo", "rows": len(demo), "columns": len(demo.columns)})
            st.success("Synthetic demonstration dataset loaded.")

frame: pd.DataFrame | None = st.session_state.uas_ml_frame
profile = st.session_state.uas_ml_profile
if frame is None or profile is None:
    st.markdown("### Start with your data")
    st.write("The workbench detects data types, profiles quality, recommends analytical objectives and exposes only the controls relevant to the selected objective.")
    st.caption("Supported now: CSV, XLSX/XLS, JSON, JSONL/NDJSON and Parquet. Large-scale distributed execution and database connectors are extension points, not enabled by this local workbench yet.")
    st.stop()

st.divider()
st.subheader("2. Understand your dataset")
metric_cols = st.columns(5)
metric_cols[0].metric("Rows", f"{profile['rows']:,}")
metric_cols[1].metric("Columns", f"{profile['columns']:,}")
metric_cols[2].metric("Duplicate rows", f"{profile['duplicate_rows']:,}")
metric_cols[3].metric("Missing cells", f"{sum(item['missing'] for item in profile['columns']):,}")
metric_cols[4].metric("Memory", f"{profile['memory_mb']:.1f} MB")

with st.expander("Preview data", expanded=True):
    st.dataframe(frame.head(100), use_container_width=True, height=300)

profile_tab, explore_tab, workflow_tab, output_tab = st.tabs([
    "Dataset Profile", "Explore & Statistics", "Analysis & Modeling", "Results & Downloads"
])

with profile_tab:
    left, right = st.columns([1.4, 1])
    with left:
        st.markdown("#### Column profile")
        profile_frame = pd.DataFrame([
            {"Column": c["name"], "Detected type": c["kind"], "Storage dtype": c["dtype"],
             "Missing": c["missing"], "Missing %": c["missing_pct"], "Unique": c["unique"]}
            for c in profile["columns"]
        ])
        st.dataframe(profile_frame, use_container_width=True, hide_index=True)
    with right:
        st.markdown("#### Data quality checks")
        if profile["quality_issues"]:
            for issue in profile["quality_issues"][:30]:
                severity = issue["severity"]
                label = issue.get("column", issue["issue"].replace("_", " ").title())
                st.write(f"{'⚠️' if severity == 'warning' else 'ℹ️'} **{label}** — {issue['recommendation']}")
        else:
            st.success("No basic missing-value, duplicate-row or constant-column issues detected.")
    st.markdown("#### Potential target variables")
    if profile["potential_targets"]:
        st.dataframe(pd.DataFrame(profile["potential_targets"]), use_container_width=True, hide_index=True)
        st.caption("These are statistical candidates only. Select a target only when it matches your real business question.")
    else:
        st.info("No obvious target candidate was detected. EDA and unsupervised objectives are still available.")
    st.markdown("#### Objective recommendations")
    for recommendation in recommend_objectives(profile):
        st.write(f"**{recommendation['objective']}** — {recommendation['reason']}")

with explore_tab:
    st.markdown("#### Distributions")
    numeric_cols = profile["numeric_columns"]
    if numeric_cols:
        selected_numeric = st.selectbox("Numeric column", numeric_cols, key="uas_ml_eda_numeric")
        chart = px.histogram(frame, x=selected_numeric, marginal="box", title=f"Distribution of {selected_numeric}")
        st.plotly_chart(chart, use_container_width=True)
        if len(numeric_cols) >= 2:
            st.markdown("#### Numeric correlations")
            corr = frame[numeric_cols].corr(numeric_only=True)
            st.plotly_chart(px.imshow(corr, text_auto=True, aspect="auto", title="Correlation matrix"), use_container_width=True)
        st.markdown("#### Statistical summary")
        st.dataframe(frame[numeric_cols].describe().T, use_container_width=True)
    else:
        st.info("No numeric columns were detected. Use the column profile to inspect categorical and text fields.")
    if profile["categorical_columns"]:
        category = st.selectbox("Categorical column", profile["categorical_columns"], key="uas_ml_eda_cat")
        counts = frame[category].astype("string").fillna("(missing)").value_counts().head(20).rename_axis(category).reset_index(name="count")
        st.plotly_chart(px.bar(counts, x=category, y="count", title=f"Top values: {category}"), use_container_width=True)

with workflow_tab:
    st.markdown("#### 3. Choose an analytical objective")
    objective_labels = {
        "Exploratory Data Analysis": "eda",
        "Classification": "classification",
        "Regression": "regression",
        "Clustering": "clustering",
        "Anomaly Detection": "anomaly_detection",
        "Forecasting": "forecasting",
        "Recommendation": "recommendation",
    }
    objective_label = st.selectbox("What are you trying to understand or predict?", list(objective_labels), key="uas_ml_objective")
    objective = objective_labels[objective_label]
    st.caption({
        "eda": "Summarize distributions, quality and relationships without training a predictive model.",
        "classification": "Predict a categorical outcome, such as a class or status.",
        "regression": "Predict a continuous numeric value.",
        "clustering": "Discover groups without a predefined target label.",
        "anomaly_detection": "Identify observations that differ from the broader data pattern.",
        "forecasting": "Estimate future values using a time column and historical numeric target.",
        "recommendation": "Recommend similar items from entity-item interaction data.",
    }[objective])

    if objective == "eda":
        st.success("EDA is available in the Explore & Statistics tab. No model training is required.")
    elif objective in {"classification", "regression"}:
        target_options = profile["potential_targets"]
        suggested = target_options[0]["column"] if target_options else frame.columns[-1]
        target = st.selectbox("Target variable", list(frame.columns), index=list(frame.columns).index(suggested), key="uas_ml_target")
        feature_candidates = [column for column in frame.columns if column != target]
        features = st.multiselect("Features to use", feature_candidates, default=feature_candidates, key="uas_ml_features")
        specs = algorithms_for(objective)
        algorithm_labels = {spec.key: f"{spec.label} — {spec.description}" for spec in specs}
        recommended_keys = list(recommend_algorithm_keys(frame[[c for c in frame.columns if c != target]], objective))
        st.caption("Recommended starting algorithms based on the selected objective and dataset shape: " + ", ".join(recommended_keys))
        chosen_algorithms = st.multiselect("Algorithms to compare", list(algorithm_labels), default=recommended_keys, format_func=lambda key: algorithm_labels[key], key="uas_ml_algorithms")
        test_fraction = st.slider("Holdout test fraction", 0.1, 0.4, 0.2, 0.05, key="uas_ml_test_fraction")
        enable_selection = st.checkbox("Apply automatic feature selection", value=False, key="uas_ml_feature_selection")
        selection_percentile = st.slider("Retain top feature percentile", 20, 100, 80, 5,
                                         disabled=not enable_selection, key="uas_ml_selection_percentile")
        if st.button("Train and compare models", type="primary", disabled=not features or not chosen_algorithms, key="uas_ml_train"):
            try:
                model_frame = frame[features + [target]].copy()
                with st.spinner("Preprocessing data, training models and evaluating holdout performance..."):
                    results = run_supervised(model_frame, target=target, objective=objective,
                                             algorithms=chosen_algorithms, test_size=test_fraction,
                                             feature_selection_percentile=selection_percentile if enable_selection else None)
                st.session_state.uas_ml_results = results
                _audit_workbench("universal_ai_ml.model_run_completed", {"objective": objective, "runs": [result.summary() for result in results]})
                st.success(f"Completed {len(results)} model run(s). Best result: {results[0].algorithm}.")
            except Exception as exc:
                st.error(f"Model execution failed: {type(exc).__name__}: {exc}")
    elif objective in {"clustering", "anomaly_detection"}:
        feature_candidates = profile["numeric_columns"] + profile["categorical_columns"]
        features = st.multiselect("Features to analyze", feature_candidates, default=feature_candidates, key="uas_ml_unsup_features")
        if objective == "clustering":
            n_clusters = st.slider("Number of clusters", 2, 12, 3, key="uas_ml_n_clusters")
        else:
            contamination = st.slider("Expected anomaly proportion", 0.01, 0.30, 0.05, 0.01, key="uas_ml_contamination")
        if st.button("Run unsupervised analysis", type="primary", disabled=not features, key="uas_ml_unsup"):
            try:
                with st.spinner("Preparing features and fitting the unsupervised model..."):
                    result = run_unsupervised(frame[features], objective=objective,
                                              contamination=contamination if objective == "anomaly_detection" else 0.05,
                                              n_clusters=n_clusters if objective == "clustering" else 3)
                st.session_state.uas_ml_results = [result]
                _audit_workbench("universal_ai_ml.model_run_completed", {"objective": objective, "algorithm": result.algorithm, "metrics": result.metrics})
                st.success("Unsupervised analysis completed.")
            except Exception as exc:
                st.error(f"Analysis failed: {type(exc).__name__}: {exc}")
    elif objective == "forecasting":
        time_options = profile["datetime_columns"] + [c["name"] for c in profile["columns"] if c["kind"] == "datetime-like"]
        if not time_options or not profile["numeric_columns"]:
            st.warning("Forecasting requires at least one date/time column and one numeric column. Choose another objective or add the required fields.")
        else:
            time_column = st.selectbox("Time/date column", time_options, key="uas_ml_time")
            target = st.selectbox("Numeric value to forecast", profile["numeric_columns"], key="uas_ml_forecast_target")
            horizon = st.number_input("Forecast horizon (observations)", min_value=1, max_value=90, value=7, key="uas_ml_horizon")
            lags = st.number_input("Lag observations", min_value=2, max_value=30, value=7, key="uas_ml_lags")
            if st.button("Build forecast", type="primary", key="uas_ml_forecast"):
                try:
                    with st.spinner("Training chronological lag baseline and generating forecast..."):
                        result = run_forecasting(frame, time_column=time_column, target=target, horizon=int(horizon), lags=int(lags))
                    st.session_state.uas_ml_results = [result]
                    _audit_workbench("universal_ai_ml.model_run_completed", {"objective": objective, "algorithm": result.algorithm, "metrics": result.metrics})
                    st.success("Forecast completed. Review holdout metrics before relying on future estimates.")
                except Exception as exc:
                    st.error(f"Forecast failed: {type(exc).__name__}: {exc}")
    elif objective == "recommendation":
        if len(profile["categorical_columns"]) < 2:
            st.warning("Recommendation requires at least two categorical columns: an entity/user field and an item/object field.")
        else:
            entity_column = st.selectbox("Entity / user column", profile["categorical_columns"], key="uas_ml_entity")
            item_column = st.selectbox("Item / object column", [c for c in profile["categorical_columns"] if c != entity_column], key="uas_ml_item")
            rating_options = ["(implicit interaction)"] + profile["numeric_columns"]
            rating_choice = st.selectbox("Optional rating / interaction strength", rating_options, key="uas_ml_rating")
            if st.button("Generate similar-item recommendations", type="primary", key="uas_ml_recommend"):
                try:
                    recommendations = run_recommendations(frame, entity_column=entity_column, item_column=item_column,
                                                          rating_column=None if rating_choice.startswith("(") else rating_choice)
                    st.session_state.uas_ml_recommendations = recommendations
                    _audit_workbench("universal_ai_ml.recommendations_generated", {"rows": len(recommendations)})
                    st.success("Recommendation table generated.")
                except Exception as exc:
                    st.error(f"Recommendation workflow failed: {type(exc).__name__}: {exc}")

with output_tab:
    st.markdown("#### 4. Results and downloads")
    results = st.session_state.uas_ml_results
    if results:
        comparison = pd.DataFrame([{"Algorithm": result.algorithm, **result.metrics} for result in results])
        st.dataframe(comparison, use_container_width=True, hide_index=True)
        for index, result in enumerate(results):
            with st.expander(f"{result.algorithm} — run details", expanded=index == 0):
                st.json(result.summary())
                if result.output_frame is not None:
                    st.dataframe(result.output_frame.head(100), use_container_width=True)
                    st.download_button("Download result CSV", result.output_frame.to_csv(index=False).encode("utf-8"),
                                       file_name=f"{result.objective}_results.csv", mime="text/csv",
                                       key=f"uas_ml_result_csv_{index}")
                if result.model is not None:
                    try:
                        import joblib
                        buffer = io.BytesIO()
                        joblib.dump({"model": result.model, "metadata": result.summary(),
                                     "created_at": datetime.now(timezone.utc).isoformat()}, buffer)
                        st.download_button("Download model artifact", buffer.getvalue(),
                                           file_name=f"{result.objective}_{result.algorithm}.joblib",
                                           mime="application/octet-stream", key=f"uas_ml_model_{index}")
                    except Exception as exc:
                        st.warning(f"Model artifact could not be serialized: {exc}")
        report = {"dataset": st.session_state.uas_ml_filename, "profile": profile,
                  "results": [result.summary() for result in results]}
        st.download_button("Download analysis report (JSON)", json.dumps(report, indent=2, default=str).encode("utf-8"),
                           file_name="universal_ai_ml_report.json", mime="application/json")
    else:
        st.info("No model results yet. Select an objective in Analysis & Modeling and run the workflow.")
    recommendations = st.session_state.get("uas_ml_recommendations")
    if recommendations is not None:
        st.markdown("#### Similar-item recommendations")
        st.dataframe(recommendations, use_container_width=True, hide_index=True)
        st.download_button("Download recommendations", recommendations.to_csv(index=False).encode("utf-8"),
                           file_name="recommendations.csv", mime="text/csv")

st.divider()
st.caption("Universal core: industry-neutral ingestion, profiling and task-oriented analytics. Model recommendations are technical suggestions—not business decisions. Validate data suitability, leakage, fairness, and deployment requirements before production use.")

from universal_ai_studio.mcp_platform.streamlit_ui import render_shared_mcp_tools
render_shared_mcp_tools("universal_ai_ml")
