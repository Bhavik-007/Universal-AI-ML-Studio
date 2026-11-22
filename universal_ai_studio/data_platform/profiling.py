"""Dataset profiling and task recommendations independent of industry semantics."""
from __future__ import annotations

from collections import Counter
from typing import Any

import numpy as np
import pandas as pd


def _column_kind(series: pd.Series) -> str:
    dtype = series.dtype
    if pd.api.types.is_datetime64_any_dtype(dtype):
        return "datetime"
    if pd.api.types.is_bool_dtype(dtype):
        return "boolean"
    if pd.api.types.is_numeric_dtype(dtype):
        return "numeric"
    sample = series.dropna().astype(str).head(100)
    if not sample.empty:
        parsed = pd.to_datetime(sample, errors="coerce", utc=False, format="mixed")
        if parsed.notna().mean() >= 0.85:
            return "datetime-like"
    if series.nunique(dropna=True) <= min(50, max(10, int(len(series) * 0.05))):
        return "categorical"
    return "text_or_identifier"


def profile_dataset(frame: pd.DataFrame) -> dict[str, Any]:
    if frame is None or frame.empty:
        raise ValueError("A non-empty dataset is required for profiling.")
    columns = []
    for name in frame.columns:
        series = frame[name]
        missing = int(series.isna().sum())
        kind = _column_kind(series)
        item: dict[str, Any] = {
            "name": str(name), "dtype": str(series.dtype), "kind": kind,
            "missing": missing, "missing_pct": round(missing / len(frame) * 100, 2),
            "unique": int(series.nunique(dropna=True)),
        }
        if kind == "numeric":
            numeric = pd.to_numeric(series, errors="coerce")
            item.update({
                "mean": _safe_float(numeric.mean()), "std": _safe_float(numeric.std()),
                "min": _safe_float(numeric.min()), "median": _safe_float(numeric.median()),
                "max": _safe_float(numeric.max()),
            })
        else:
            top = series.dropna().astype(str).value_counts().head(3)
            item["top_values"] = [{"value": str(key)[:120], "count": int(value)} for key, value in top.items()]
        columns.append(item)

    duplicate_rows = int(frame.duplicated().sum())
    numeric_columns = [item["name"] for item in columns if item["kind"] == "numeric"]
    categorical_columns = [item["name"] for item in columns if item["kind"] in {"categorical", "boolean"}]
    datetime_columns = [item["name"] for item in columns if item["kind"] in {"datetime", "datetime-like"}]
    text_columns = [item["name"] for item in columns if item["kind"] == "text_or_identifier"]
    quality_issues = []
    if duplicate_rows:
        quality_issues.append({"severity": "warning", "issue": "duplicate_rows", "count": duplicate_rows,
                               "recommendation": "Review duplicate records before training or aggregation."})
    for item in columns:
        if item["missing"]:
            quality_issues.append({"severity": "warning", "issue": "missing_values", "column": item["name"],
                                   "count": item["missing"], "recommendation": "Use imputation or exclude the column if missingness is not informative."})
        if item["unique"] <= 1:
            quality_issues.append({"severity": "info", "issue": "constant_column", "column": item["name"],
                                   "count": item["unique"], "recommendation": "Consider excluding this column from modeling."})

    return {
        "rows": int(frame.shape[0]), "columns": int(frame.shape[1]),
        "memory_mb": round(float(frame.memory_usage(deep=True).sum()) / (1024 * 1024), 2),
        "duplicate_rows": duplicate_rows,
        "numeric_columns": numeric_columns, "categorical_columns": categorical_columns,
        "datetime_columns": datetime_columns, "text_columns": text_columns,
        "columns": columns, "quality_issues": quality_issues,
        "potential_targets": infer_target_candidates(frame, columns),
    }


def infer_target_candidates(frame: pd.DataFrame, column_profile: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    profile = column_profile or profile_dataset(frame)["columns"]
    candidates = []
    n_rows = len(frame)
    for item in profile:
        name, kind, unique = item["name"], item["kind"], item["unique"]
        if kind not in {"numeric", "categorical", "boolean"} or unique < 2 or unique >= max(2, n_rows * 0.95):
            continue
        score = 0.35
        if kind in {"categorical", "boolean"} and 2 <= unique <= 20:
            score += 0.35
        if kind == "numeric" and unique >= 10:
            score += 0.25
        lowered = name.lower()
        if any(token in lowered for token in ("target", "label", "outcome", "result", "class", "status")):
            score += 0.25
        candidates.append({"column": name, "kind": kind, "unique": unique, "score": round(min(score, 0.95), 2)})
    return sorted(candidates, key=lambda item: (-item["score"], item["column"]))[:10]


def recommend_objectives(profile: dict[str, Any]) -> list[dict[str, str]]:
    rows = profile["rows"]
    recommendations = [{"objective": "Exploratory Data Analysis", "reason": "Understand distributions, missingness, outliers and relationships before modeling."}]
    if profile["numeric_columns"]:
        recommendations.append({"objective": "Clustering", "reason": "Numeric features are available for unsupervised segmentation."})
        recommendations.append({"objective": "Anomaly Detection", "reason": "Numeric features are available for identifying unusual observations."})
    target_kinds = {item["kind"] for item in profile["potential_targets"]}
    if target_kinds.intersection({"categorical", "boolean"}):
        recommendations.append({"objective": "Classification", "reason": "Categorical or boolean target candidates are available; confirm the target represents the outcome you want to predict."})
    if "numeric" in target_kinds:
        recommendations.append({"objective": "Regression", "reason": "Numeric target candidates are available; confirm the target is a continuous value relevant to your objective."})
    if profile["datetime_columns"] and profile["numeric_columns"]:
        recommendations.append({"objective": "Forecasting", "reason": "Date/time and numeric columns are available for a time-series workflow."})
    if len(profile["categorical_columns"]) >= 2:
        recommendations.append({"objective": "Recommendation", "reason": "Categorical columns may form user-item or entity-item interactions; identify the relevant fields."})
    return recommendations


def _safe_float(value: Any) -> float | None:
    try:
        number = float(value)
        return number if np.isfinite(number) else None
    except (TypeError, ValueError):
        return None
