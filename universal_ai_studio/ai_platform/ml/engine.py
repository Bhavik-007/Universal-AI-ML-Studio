"""Dataset-driven tabular ML engine with explicit objective and evaluation."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.metrics import (accuracy_score, f1_score, mean_absolute_error,
                             mean_squared_error, precision_score, recall_score,
                             r2_score, silhouette_score)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.feature_selection import SelectPercentile, f_classif, f_regression
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from universal_ai_studio.ai_platform.ml.registry import algorithms_for


@dataclass
class ModelRunResult:
    objective: str
    algorithm: str
    metrics: dict[str, float]
    predictions: list[Any]
    model: Any
    feature_columns: list[str]
    target_column: str | None = None
    output_frame: pd.DataFrame | None = None

    def summary(self) -> dict[str, Any]:
        return {"objective": self.objective, "algorithm": self.algorithm,
                "metrics": self.metrics, "feature_columns": self.feature_columns,
                "target_column": self.target_column}


def _preprocessor(frame: pd.DataFrame) -> ColumnTransformer:
    numeric = frame.select_dtypes(include=["number", "bool"]).columns.tolist()
    categorical = [column for column in frame.columns if column not in numeric]
    transformers = []
    if numeric:
        transformers.append(("numeric", Pipeline([
            ("imputer", SimpleImputer(strategy="median", keep_empty_features=True)),
            ("scaler", StandardScaler()),
        ]), numeric))
    if categorical:
        transformers.append(("categorical", Pipeline([
            ("imputer", SimpleImputer(strategy="most_frequent")),
            ("onehot", OneHotEncoder(handle_unknown="ignore", min_frequency=2)),
        ]), categorical))
    if not transformers:
        raise ValueError("No usable feature columns remain after selecting the target.")
    return ColumnTransformer(transformers, remainder="drop", sparse_threshold=0.3)


def _clean_features(frame: pd.DataFrame, target: str | None = None) -> pd.DataFrame:
    features = frame.drop(columns=[target], errors="ignore").copy()
    # Convert parseable date columns into stable numeric calendar features.
    for column in list(features.columns):
        values = None
        if pd.api.types.is_datetime64_any_dtype(features[column]):
            values = pd.to_datetime(features[column], errors="coerce")
        elif not (pd.api.types.is_numeric_dtype(features[column]) or pd.api.types.is_bool_dtype(features[column])):
            sample = features[column].dropna().astype(str).head(100)
            date_like = not sample.empty and sample.str.contains(r"[-/:T]", regex=True).mean() >= 0.70
            if date_like:
                parsed = pd.to_datetime(sample, errors="coerce", format="mixed")
                if parsed.notna().mean() >= 0.85:
                    values = pd.to_datetime(features[column], errors="coerce", format="mixed")
        if values is not None:
            features[f"{column}__year"] = values.dt.year
            features[f"{column}__month"] = values.dt.month
            features[f"{column}__day"] = values.dt.day
            features = features.drop(columns=[column])
    features = features.replace([np.inf, -np.inf], np.nan)
    # Drop obvious unique identifiers and free-text columns to avoid accidental
    # high-cardinality expansion; users can explicitly select a curated subset.
    drop = []
    for column in features.columns:
        unique_ratio = features[column].nunique(dropna=True) / max(len(features), 1)
        # Numeric continuous variables are usually informative, even when
        # nearly every observation is unique. Only apply the identifier/text
        # heuristic to non-numeric high-cardinality columns.
        is_non_numeric = not (pd.api.types.is_numeric_dtype(features[column]) or
                              pd.api.types.is_bool_dtype(features[column]))
        if is_non_numeric and (unique_ratio > 0.98 or
                               features[column].nunique(dropna=True) > min(500, len(features) * 0.5)):
            drop.append(column)
    return features.drop(columns=drop, errors="ignore")


def run_supervised(
    frame: pd.DataFrame, *, target: str, objective: str,
    algorithms: list[str] | None = None, test_size: float = 0.2,
    feature_selection_percentile: int | None = None,
    max_training_rows: int = 100_000,
) -> list[ModelRunResult]:
    if objective not in {"classification", "regression"}:
        raise ValueError("Supervised objective must be classification or regression.")
    if target not in frame.columns:
        raise ValueError(f"Target column '{target}' does not exist.")
    data = frame.dropna(subset=[target]).copy()
    if len(data) < 20:
        raise ValueError("At least 20 non-null target rows are required for a train/test evaluation.")
    if len(data) > max_training_rows:
        data = data.sample(max_training_rows, random_state=42)
    y = data[target]
    if objective == "classification":
        if y.nunique() < 2:
            raise ValueError("Classification requires at least two target classes.")
        if y.nunique() > max(50, int(len(y) * 0.2)):
            raise ValueError("The selected target has too many unique values for classification. Consider regression or a different target.")
        stratify = y if y.value_counts().min() >= 2 else None
    else:
        y = pd.to_numeric(y, errors="coerce")
        valid = y.notna()
        data, y = data.loc[valid], y.loc[valid]
        if len(data) < 20:
            raise ValueError("Regression requires at least 20 numeric, non-null target rows.")
        stratify = None
    X = _clean_features(data, target)
    if X.shape[1] == 0:
        raise ValueError("No usable feature columns remain. Select more suitable features or remove identifier columns.")
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_size, random_state=42, stratify=stratify
    )
    requested = set(algorithms or [])
    specs = [spec for spec in algorithms_for(objective) if not requested or spec.key in requested]
    results = []
    for spec in specs:
        steps = [("preprocess", _preprocessor(X))]
        if feature_selection_percentile is not None:
            score_function = f_classif if objective == "classification" else f_regression
            steps.append(("feature_selection", SelectPercentile(score_func=score_function,
                                                                  percentile=int(feature_selection_percentile))))
        steps.append(("model", spec.estimator_factory()))
        pipeline = Pipeline(steps)
        pipeline.fit(X_train, y_train)
        predicted = pipeline.predict(X_test)
        if objective == "classification":
            metrics = {"accuracy": float(accuracy_score(y_test, predicted)),
                       "precision_weighted": float(precision_score(y_test, predicted, average="weighted", zero_division=0)),
                       "recall_weighted": float(recall_score(y_test, predicted, average="weighted", zero_division=0)),
                       "f1_weighted": float(f1_score(y_test, predicted, average="weighted", zero_division=0))}
        else:
            rmse = float(np.sqrt(mean_squared_error(y_test, predicted)))
            metrics = {"mae": float(mean_absolute_error(y_test, predicted)),
                       "rmse": rmse, "r2": float(r2_score(y_test, predicted))}
        prediction_output = data.loc[X_test.index].copy()
        prediction_output["actual"] = y_test
        prediction_output["prediction"] = predicted
        results.append(ModelRunResult(objective, spec.key, metrics, predicted.tolist(), pipeline,
                                      list(X.columns), target, prediction_output))
    if not results:
        raise ValueError("No algorithms were selected for this objective.")
    return sorted(results, key=lambda item: item.metrics.get("f1_weighted", item.metrics.get("r2", 0.0)), reverse=True)


def run_unsupervised(
    frame: pd.DataFrame, *, objective: str, algorithm: str | None = None,
    contamination: float = 0.05, n_clusters: int = 3,
    max_training_rows: int = 100_000,
) -> ModelRunResult:
    if objective not in {"clustering", "anomaly_detection"}:
        raise ValueError("Unsupervised objective must be clustering or anomaly_detection.")
    data = frame.copy()
    if len(data) > max_training_rows:
        data = data.sample(max_training_rows, random_state=42)
    X = _clean_features(data)
    if len(X) < 10 or X.shape[1] == 0:
        raise ValueError("At least 10 rows and one usable feature are required.")
    spec = next((item for item in algorithms_for(objective) if algorithm is None or item.key == algorithm), None)
    if spec is None:
        raise ValueError(f"Algorithm '{algorithm}' is not available for {objective}.")
    estimator = spec.estimator_factory()
    if objective == "anomaly_detection":
        estimator.set_params(contamination=contamination)
    elif objective == "clustering":
        estimator.set_params(n_clusters=int(n_clusters))
    pipeline = Pipeline([("preprocess", _preprocessor(X)), ("model", estimator)])
    labels = pipeline.fit_predict(X)
    metrics: dict[str, float] = {"records_processed": float(len(X)),
                                 "groups_or_outliers": float(len(set(labels)))}
    transformed = pipeline.named_steps["preprocess"].transform(X)
    if objective == "clustering" and len(set(labels)) > 1 and len(set(labels)) < len(labels):
        sample_size = min(5000, len(labels))
        metrics["silhouette"] = float(silhouette_score(transformed, labels, sample_size=sample_size, random_state=42))
    output = data.loc[X.index].copy()
    output["model_label"] = labels
    if objective == "anomaly_detection":
        output["is_anomaly"] = labels == -1
    return ModelRunResult(objective, spec.key, metrics, labels.tolist(), pipeline,
                          list(X.columns), output_frame=output)


def run_forecasting(
    frame: pd.DataFrame, *, time_column: str, target: str, horizon: int = 7,
    lags: int = 7, max_training_rows: int = 100_000,
) -> ModelRunResult:
    """Univariate recursive forecasting baseline using chronological lag features."""
    from sklearn.ensemble import RandomForestRegressor
    if time_column not in frame or target not in frame:
        raise ValueError("Select an existing time column and numeric target column.")
    data = frame[[time_column, target]].copy()
    data[time_column] = pd.to_datetime(data[time_column], errors="coerce")
    data[target] = pd.to_numeric(data[target], errors="coerce")
    data = data.dropna().sort_values(time_column).drop_duplicates(time_column)
    if len(data) < max(30, lags + 10):
        raise ValueError(f"Forecasting needs at least {max(30, lags + 10)} valid time-ordered observations.")
    if len(data) > max_training_rows:
        data = data.tail(max_training_rows)
    values = data[target].astype(float).to_numpy()
    X = pd.DataFrame({f"lag_{i}": pd.Series(values).shift(i) for i in range(1, lags + 1)}).dropna()
    y = pd.Series(values[lags:])
    split = max(1, int(len(X) * 0.8))
    if len(X) - split < 2:
        raise ValueError("Not enough holdout observations; reduce lag count or provide more data.")
    model = RandomForestRegressor(n_estimators=250, random_state=42, n_jobs=-1)
    model.fit(X.iloc[:split], y.iloc[:split])
    predicted = model.predict(X.iloc[split:])
    metrics = {"mae": float(mean_absolute_error(y.iloc[split:], predicted)),
               "rmse": float(np.sqrt(mean_squared_error(y.iloc[split:], predicted))),
               "holdout_rows": float(len(predicted))}
    final_model = RandomForestRegressor(n_estimators=250, random_state=42, n_jobs=-1)
    final_model.fit(X, y)
    history = list(values[-lags:])
    forecast_values = []
    for _ in range(int(horizon)):
        row = pd.DataFrame([{f"lag_{i}": history[-i] for i in range(1, lags + 1)}])
        next_value = float(final_model.predict(row)[0])
        forecast_values.append(next_value)
        history.append(next_value)
    last_time = data[time_column].iloc[-1]
    frequency = pd.infer_freq(data[time_column])
    future_dates = pd.date_range(start=last_time, periods=horizon + 1, freq=frequency or "D")[1:]
    output = pd.DataFrame({time_column: future_dates, "forecast": forecast_values})
    return ModelRunResult("forecasting", "random_forest_lag_baseline", metrics,
                          forecast_values, final_model, [f"lag_{i}" for i in range(1, lags + 1)],
                          target, output)


def run_recommendations(
    frame: pd.DataFrame, *, entity_column: str, item_column: str,
    rating_column: str | None = None, top_n: int = 5,
) -> pd.DataFrame:
    """Generic item-item collaborative filtering from user/entity-item interactions."""
    from sklearn.metrics.pairwise import cosine_similarity
    for column in (entity_column, item_column):
        if column not in frame:
            raise ValueError(f"Column '{column}' does not exist.")
    if rating_column and rating_column not in frame:
        raise ValueError(f"Rating column '{rating_column}' does not exist.")
    work = frame[[entity_column, item_column] + ([rating_column] if rating_column else [])].dropna()
    if work.empty:
        raise ValueError("No valid entity-item interactions remain after removing missing values.")
    work["_weight"] = pd.to_numeric(work[rating_column], errors="coerce") if rating_column else 1.0
    work = work.dropna(subset=["_weight"])
    matrix = work.pivot_table(index=entity_column, columns=item_column, values="_weight", aggfunc="mean", fill_value=0)
    if matrix.shape[0] < 2 or matrix.shape[1] < 2:
        raise ValueError("Recommendation requires at least two entities and two distinct items.")
    similarity = cosine_similarity(matrix.T)
    items = list(matrix.columns)
    rows = []
    for index, item in enumerate(items):
        similar = np.argsort(similarity[index])[::-1]
        for candidate in similar:
            if candidate == index:
                continue
            rows.append({"item": str(item), "recommended_item": str(items[candidate]),
                         "similarity": float(similarity[index, candidate])})
            if sum(1 for row in rows if row["item"] == str(item)) >= top_n:
                break
    return pd.DataFrame(rows)
