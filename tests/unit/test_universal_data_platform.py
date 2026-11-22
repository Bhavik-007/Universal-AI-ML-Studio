import io
import json

import numpy as np
import pandas as pd
import pytest

from universal_ai_studio.data_platform.ingestion import DatasetIngestionError, read_dataset
from universal_ai_studio.data_platform.profiling import profile_dataset, recommend_objectives
from universal_ai_studio.ai_platform.ml.engine import (
    run_forecasting, run_recommendations, run_supervised, run_unsupervised,
)
from universal_ai_studio.ai_platform.ml.registry import AlgorithmSpec, algorithms_for, recommend_algorithm_keys, register_algorithm


def test_csv_ingestion_and_duplicate_column_normalization():
    data = b"name,name,value\na,b,1\nc,d,2\n"
    frame = read_dataset("sample.csv", data)
    assert len(set(frame.columns)) == 3
    assert frame.shape == (2, 3)


def test_json_records_are_flattened():
    payload = json.dumps([{"user": {"id": 1}, "score": 4}, {"user": {"id": 2}, "score": 5}]).encode()
    frame = read_dataset("records.json", payload)
    assert "user.id" in frame.columns
    assert frame["score"].tolist() == [4, 5]


def test_json_wrapped_records_are_supported():
    payload = json.dumps({"records": [{"x": 1}, {"x": 2}]}).encode()
    frame = read_dataset("records.json", payload)
    assert frame["x"].tolist() == [1, 2]


def test_unsupported_file_type_is_rejected():
    with pytest.raises(DatasetIngestionError, match="Unsupported file type"):
        read_dataset("script.py", b"print('not data')")


def test_profile_detects_types_quality_and_target_candidates():
    frame = pd.DataFrame({"target_label": [0, 1, 0, 1], "amount": [1.0, 2.0, None, 4.0],
                          "category": ["a", "b", "a", "b"]})
    profile = profile_dataset(frame)
    assert profile["rows"] == 4
    assert profile["numeric_columns"] == ["target_label", "amount"]
    assert profile["categorical_columns"] == ["category"]
    assert profile["quality_issues"]
    assert any(item["column"] == "target_label" for item in profile["potential_targets"])
    assert recommend_objectives(profile)


def test_classification_pipeline_trains_and_evaluates():
    rng = np.random.default_rng(42)
    x = rng.normal(size=160)
    frame = pd.DataFrame({"x": x, "group": np.where(x > 0, "high", "low"),
                          "target": np.where(x > 0, "positive", "negative")})
    results = run_supervised(frame, target="target", objective="classification",
                             algorithms=["logistic_regression"])
    assert results[0].metrics["accuracy"] > 0.8
    assert results[0].model is not None


def test_regression_pipeline_trains_and_evaluates():
    rng = np.random.default_rng(7)
    x = rng.normal(size=140)
    frame = pd.DataFrame({"x": x, "category": np.where(x > 0, "a", "b"), "target": 3 * x + 2})
    results = run_supervised(frame, target="target", objective="regression", algorithms=["ridge"])
    assert results[0].metrics["rmse"] < 0.5


def test_clustering_and_anomaly_workflows_return_labeled_data():
    rng = np.random.default_rng(4)
    frame = pd.DataFrame({"x": np.r_[rng.normal(0, .2, 50), rng.normal(4, .2, 50)],
                          "y": np.r_[rng.normal(0, .2, 50), rng.normal(4, .2, 50)]})
    clustered = run_unsupervised(frame, objective="clustering", n_clusters=2)
    anomalous = run_unsupervised(frame, objective="anomaly_detection", contamination=0.05)
    assert len(clustered.output_frame) == len(frame)
    assert "model_label" in clustered.output_frame
    assert "is_anomaly" in anomalous.output_frame


def test_forecasting_baseline_returns_holdout_metrics_and_future_values():
    frame = pd.DataFrame({"date": pd.date_range("2024-01-01", periods=100, freq="D"),
                          "value": np.linspace(10, 40, 100) + np.sin(np.arange(100))})
    result = run_forecasting(frame, time_column="date", target="value", horizon=5, lags=5)
    assert len(result.output_frame) == 5
    assert result.metrics["mae"] >= 0


def test_item_similarity_recommendations_are_generated():
    frame = pd.DataFrame({"entity": ["u1", "u1", "u2", "u2", "u3", "u3"],
                          "item": ["a", "b", "a", "b", "b", "c"],
                          "rating": [5, 4, 4, 5, 3, 5]})
    result = run_recommendations(frame, entity_column="entity", item_column="item", rating_column="rating")
    assert not result.empty
    assert {"item", "recommended_item", "similarity"}.issubset(result.columns)


def test_algorithm_registry_accepts_extensions():
    spec = AlgorithmSpec("test_extension", "Test Extension", "classification", lambda: object(), "test")
    register_algorithm(spec)
    assert any(item.key == "test_extension" for item in algorithms_for("classification"))


def test_feature_selection_can_be_added_to_supervised_pipeline():
    rng = np.random.default_rng(18)
    frame = pd.DataFrame({f"feature_{i}": rng.normal(size=180) for i in range(6)})
    frame["target"] = 2 * frame["feature_0"] - frame["feature_1"]
    results = run_supervised(frame, target="target", objective="regression",
                             algorithms=["ridge"], feature_selection_percentile=60)
    assert results[0].model is not None


def test_rest_connector_rejects_absolute_or_traversal_paths():
    from universal_ai_studio.data_platform.connectors import DatasetConnectionError, load_rest_dataset
    with pytest.raises(DatasetConnectionError, match="relative endpoint"):
        load_rest_dataset("https://example.com/data")
    with pytest.raises(DatasetConnectionError, match="relative endpoint"):
        load_rest_dataset("../admin")


def test_algorithm_recommendations_adapt_to_dataset_shape():
    frame = pd.DataFrame({"x": range(600), "category": ["a", "b"] * 300})
    recommended = recommend_algorithm_keys(frame, "regression")
    assert "ridge" in recommended
    assert "random_forest" in recommended
    assert "extra_trees" in recommended
