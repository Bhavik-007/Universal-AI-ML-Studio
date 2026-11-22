"""Extensible, objective-driven machine-learning algorithm catalogue."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Any


@dataclass(frozen=True)
class AlgorithmSpec:
    key: str
    label: str
    objective: str
    estimator_factory: Callable[[], Any]
    description: str
    requirements: str = "general tabular data"


_EXTENSIONS: dict[str, AlgorithmSpec] = {}


def register_algorithm(spec: AlgorithmSpec, *, replace: bool = False) -> None:
    """Register an additional algorithm without changing the core workflow."""
    key = f"{spec.objective}:{spec.key}"
    if key in _EXTENSIONS and not replace:
        raise ValueError(f"Algorithm already registered: {key}")
    if spec.objective not in {"classification", "regression", "clustering", "anomaly_detection"}:
        raise ValueError(f"Unsupported registry objective: {spec.objective}")
    _EXTENSIONS[key] = spec


# Imports are lazy at call time so platform navigation does not require every
# optional ML backend to be imported during application startup.
def algorithms_for(objective: str) -> tuple[AlgorithmSpec, ...]:
    from sklearn.cluster import KMeans
    from sklearn.ensemble import (ExtraTreesClassifier, ExtraTreesRegressor,
                                  IsolationForest, RandomForestClassifier,
                                  RandomForestRegressor)
    from sklearn.linear_model import LogisticRegression, Ridge

    catalog = {
        "classification": (
            AlgorithmSpec("logistic_regression", "Logistic Regression", objective,
                          lambda: LogisticRegression(max_iter=1000, class_weight="balanced"),
                          "Interpretable linear baseline for classification."),
            AlgorithmSpec("random_forest", "Random Forest", objective,
                          lambda: RandomForestClassifier(n_estimators=250, random_state=42, n_jobs=-1,
                                                         class_weight="balanced_subsample"),
                          "Non-linear ensemble suitable for mixed tabular features."),
            AlgorithmSpec("extra_trees", "Extra Trees", objective,
                          lambda: ExtraTreesClassifier(n_estimators=250, random_state=42, n_jobs=-1,
                                                       class_weight="balanced"),
                          "Randomized tree ensemble for tabular classification."),
        ),
        "regression": (
            AlgorithmSpec("ridge", "Ridge Regression", objective, lambda: Ridge(),
                          "Regularized linear regression baseline."),
            AlgorithmSpec("random_forest", "Random Forest Regressor", objective,
                          lambda: RandomForestRegressor(n_estimators=250, random_state=42, n_jobs=-1),
                          "Non-linear ensemble for tabular regression."),
            AlgorithmSpec("extra_trees", "Extra Trees Regressor", objective,
                          lambda: ExtraTreesRegressor(n_estimators=250, random_state=42, n_jobs=-1),
                          "Randomized tree ensemble for regression."),
        ),
        "clustering": (
            AlgorithmSpec("kmeans", "K-Means", objective, lambda: KMeans(n_clusters=3, n_init="auto", random_state=42),
                          "Centroid-based segmentation; scales best to compact feature spaces."),
        ),
        "anomaly_detection": (
            AlgorithmSpec("isolation_forest", "Isolation Forest", objective,
                          lambda: IsolationForest(contamination="auto", random_state=42, n_estimators=250, n_jobs=-1),
                          "Tree-based unsupervised outlier detection."),
        ),
    }
    defaults = list(catalog.get(objective, ()))
    defaults.extend(spec for spec in _EXTENSIONS.values() if spec.objective == objective)
    return tuple(defaults)


def recommend_algorithm_keys(frame, objective: str) -> tuple[str, ...]:
    """Return objective- and data-shape-aware default algorithms for comparison."""
    available = {spec.key for spec in algorithms_for(objective)}
    rows, columns = frame.shape
    categorical = len(frame.select_dtypes(exclude=["number", "bool"]).columns)
    if objective == "classification":
        ranked = ["logistic_regression"]
        if rows >= 80 and (categorical > 0 or columns >= 3):
            ranked.append("random_forest")
        if rows >= 500:
            ranked.append("extra_trees")
    elif objective == "regression":
        ranked = ["ridge"]
        if rows >= 80 and (categorical > 0 or columns >= 3):
            ranked.append("random_forest")
        if rows >= 500:
            ranked.append("extra_trees")
    else:
        ranked = [spec.key for spec in algorithms_for(objective)]
    selected = tuple(key for key in ranked if key in available)
    return selected or tuple(available)
