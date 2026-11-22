# Universal AI/ML Workbench

## Purpose

The Universal AI/ML Workbench is the platform's industry-neutral analytical entry point. It adapts ingestion, profiling and available workflows to the uploaded or connected dataset and the objective selected by the user. Industry labels, domain rules and domain-specific target assumptions are not used by the core engine.

## Architecture

```text
Streamlit application shell / authentication / RBAC
                 |
        Application Registry
                 |
       Universal AI/ML Workbench
                 |
       Dataset Source Adapters
       |          |          |
    Upload    SQL Server   REST API
       |          |          |
       +---- Canonical pandas DataFrame ----+
                         |
                Dataset Profiler
        schema / types / quality / candidates
                         |
                Objective Selection
        EDA / classification / regression /
        clustering / anomaly / forecasting /
                  recommendation
                         |
             Preprocessing / Feature Work
       imputation / scaling / one-hot / date parts /
                   optional selection
                         |
             Algorithm Registry + Engine
                         |
             Evaluation / Results / Exports
          metrics / predictions / model / JSON / CSV
```

Shared platform authentication, application registry, integration manager, encrypted secrets, AI providers, MCP and audit services remain in the existing platform packages. The Workbench does not introduce another authentication, provider, vector database or configuration manager.

## Supported dataset inputs

| Source | Supported behaviour |
|---|---|
| CSV | pandas CSV parser |
| Excel | `.xlsx` and `.xls` via openpyxl/xlrd |
| JSON | JSON arrays/objects; common single-list wrappers; nested records flattened |
| JSON Lines | `.jsonl` and `.ndjson` |
| Parquet | pandas Parquet reader via PyArrow |
| Configured SQL Server | Browse tables from the existing centrally configured SQL Server integration; load a bounded sample |
| Configured REST API | GET a relative endpoint from the centrally configured REST base URL; parse JSON records |
| Synthetic demo | Generated, clearly labelled synthetic data; never represented as production data |

Upload size is limited to 100 MB by the ingestion service. File ingestion currently caps a dataset at 1,000,000 rows. SQL Server reads are capped at 100,000 rows and REST responses at 100 MB. These are safety defaults for this Streamlit deployment, not claims of distributed big-data processing.

## Profiling

The profiler reports row/column counts, memory footprint, duplicate rows, missing values, unique counts, storage dtypes, inferred numeric/categorical/boolean/datetime-like/text-or-identifier types, numeric summaries, categorical top values and potential target candidates. Candidate targets are suggestions only; users must confirm that a column represents the intended outcome.

## Analytical objectives

| Objective | Current implementation |
|---|---|
| Exploratory Data Analysis | Numeric distributions, summary statistics, categorical top values and numeric correlation matrix |
| Classification | Logistic Regression, Random Forest and Extra Trees; imputation, scaling, one-hot encoding, optional SelectPercentile; holdout accuracy, weighted precision/recall/F1 and predictions |
| Regression | Ridge, Random Forest and Extra Trees; same preprocessing and optional feature selection; holdout MAE, RMSE, R² and predictions |
| Clustering | K-Means with configurable cluster count; encoded/imputed/scaled features; labels and silhouette score when valid |
| Anomaly Detection | Isolation Forest with configurable contamination; labels and anomaly flags |
| Forecasting | Chronological univariate lag-feature Random Forest baseline; holdout MAE/RMSE and recursive future horizon |
| Recommendation | Item-item collaborative similarity from entity-item interactions, with optional numeric rating/strength |

The algorithm registry supports runtime registration of additional algorithm specifications. Dataset-shape heuristics recommend a starting subset of algorithms; users can change the selection.

## Preprocessing and feature work

- Numeric values: median imputation and standard scaling.
- Categorical values: most-frequent imputation and one-hot encoding with unknown-category handling.
- Datetime values: year/month/day feature extraction in supervised and unsupervised tabular workflows.
- Optional supervised feature selection: SelectPercentile with ANOVA F-score or regression F-score.
- Obvious high-cardinality non-numeric identifiers/free-text columns are excluded by a conservative heuristic; users should curate feature columns and inspect the resulting feature list.

## Results and artifacts

- Supervised: comparison metrics, holdout predictions with actual values, fitted pipeline model artifact and JSON analysis report.
- Clustering/anomaly: labelled output CSV and fitted pipeline artifact.
- Forecasting: future values CSV and fitted lag model artifact.
- Recommendation: item-similarity CSV.
- The model artifact is a Joblib file. Only load artifacts from trusted sources because Joblib/pickle-based formats can execute code during deserialization.

## Security and data handling

- Uploaded data is not sent to an LLM by default.
- SQL Server and REST credentials are sourced from the existing platform Integration Manager and encrypted secret store; the Workbench does not ask users to paste credentials into its UI.
- REST access is restricted to relative endpoint paths on the administrator-configured base URL; absolute URLs and traversal paths are rejected.
- No arbitrary Python code from uploaded datasets is executed.
- Dataset load and model-run events write metadata-only audit entries (source type, row/column counts, objective, algorithm and metrics); dataset row values are not written to the audit log.
- Model training is bounded to a 100,000-row sample when larger inputs are supplied; forecasts use the latest bounded observations.
- The current page stores the active DataFrame and run results in Streamlit session state. Durable multi-user dataset/model storage, background jobs, distributed compute, governance approvals and lineage storage are future platform capabilities.

## Preserved specialized applications

The existing domain-specific applications remain in the repository and registry for backward compatibility. They are grouped under **Specialized Workflows** rather than defining the universal platform's core navigation or processing assumptions. They have not been silently deleted or rewritten as generic equivalents.

## Known limitations / next production phases

1. Only SQL Server and the centrally configured REST API have dataset connector adapters in this release. Other SQLAlchemy-supported databases can be added behind the same adapter interface.
2. Forecasting is a transparent lag-feature baseline, not a seasonal/holiday-aware forecasting suite. Frequency inference falls back to daily periods for irregular time series; users should validate the output frequency.
3. Recommendation is item-item similarity; it does not yet provide implicit-feedback ALS, content-based hybrid ranking, cold-start handling or online serving.
4. Text columns are profiled but not automatically embedded or used as NLP features in this release.
5. No distributed execution engine, model registry server, experiment tracking backend, hyperparameter optimization service or scheduled retraining service is included.
6. Fairness, explainability, leakage checks, drift monitoring and deployment approvals require additional domain-appropriate governance before production decisions.
7. Streamlit runtime and live SQL Server/REST connections must be tested in the target deployment environment.

## Add a new algorithm

Implement an estimator factory and register it with `register_algorithm(AlgorithmSpec(...))` in an application startup hook or a trusted extension package. The estimator must support the input representation produced by the shared preprocessing pipeline and return standard scikit-learn-compatible fit/predict or fit_predict methods. Add objective-specific tests and metrics before enabling it for users.
