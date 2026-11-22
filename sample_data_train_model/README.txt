# Universal Fraud Detection - Sample Test Data

These are synthetic datasets generated for testing only. They do not represent real people, customers, transactions, claims, or fraud cases.

## Files
- `sample_bfsi_transactions.csv` — labelled BFSI transaction sample.
- `sample_retail_orders.csv` — labelled retail/e-commerce order sample.
- `sample_insurance_claims.csv` — labelled insurance claim sample.
- `sample_unsupervised_events.csv` — unlabelled generic event sample for anomaly detection.

Each labelled dataset contains `fraud_flag` (0 = normal, 1 = synthetic positive example).
The unlabelled dataset intentionally has no target column.

## Suggested tests
1. Supervised: upload one of the first three files, select `fraud_flag` as the target, and select `1` as the positive/suspicious class.
2. Unsupervised: upload `sample_unsupervised_events.csv`, choose `No target (anomaly detection)`, and exclude `event_id` from features.
3. Business rule: enable the numeric threshold rule and choose an amount field, e.g. `transaction_amount`, `order_value`, `claim_amount`, or `event_amount`.
4. Data quality: inspect the preview and data quality profile.

All data is synthetic. Model scores and metrics are illustrative test outputs, not evidence of real-world fraud-detection performance.
