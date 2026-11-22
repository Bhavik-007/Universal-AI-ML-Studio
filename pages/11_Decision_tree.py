import streamlit as st

from auth.login_manager import login_manager
from auth.auth_guard import protect_page




st.set_page_config(page_title="Loan Management — Decision Tree", layout="wide")
login_manager()
protect_page()

import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.tree import DecisionTreeClassifier, plot_tree
from sklearn.pipeline import Pipeline
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.impute import SimpleImputer
from sklearn.metrics import accuracy_score, confusion_matrix, classification_report
import matplotlib.pyplot as plt
import io
import joblib


# -------------------- Utilities --------------------
@st.cache_data
def generate_synthetic_data(n_samples=1000, random_state=42):
    rng = np.random.RandomState(random_state)
    age = rng.randint(21, 70, n_samples)
    income = rng.normal(50000, 20000, n_samples).clip(8000, None)
    loan_amount = rng.normal(15000, 10000, n_samples).clip(1000, None)
    loan_term = rng.choice([12, 24, 36, 48, 60], n_samples, p=[0.05,0.1,0.3,0.3,0.25])
    credit_history = rng.choice([0,1], n_samples, p=[0.2,0.8])
    education = rng.choice(['Graduate','Not Graduate'], n_samples, p=[0.6,0.4])
    employment_years = rng.poisson(5, n_samples)
    property_area = rng.choice(['Urban','Semiurban','Rural'], n_samples, p=[0.4,0.35,0.25])

    score = (
        (income/10000) * 0.4
        + (credit_history*2.0)
        - (loan_amount/10000) * 0.6
        + (employment_years * 0.1)
        + (age/50)*0.05
    )
    prob = 1 / (1 + np.exp(-score))
    approved = rng.binomial(1, prob*0.6 + 0.2)

    return pd.DataFrame({
        'age': age,
        'income': income.round(2),
        'loan_amount': loan_amount.round(2),
        'loan_term': loan_term,
        'credit_history': credit_history,
        'education': education,
        'employment_years': employment_years,
        'property_area': property_area,
        'approved': approved
    })

def build_preprocessing_pipeline(X):
    numeric_features = X.select_dtypes(include=['int64', 'float64', 'int32', 'float32']).columns.tolist()
    categorical_features = X.select_dtypes(include=['object', 'category', 'bool']).columns.tolist()

    numeric_transformer = Pipeline([
        ('imputer', SimpleImputer(strategy='median')),
        ('scaler', StandardScaler())
    ])
    categorical_transformer = Pipeline([
        ('imputer', SimpleImputer(strategy='most_frequent')),
        ('onehot', OneHotEncoder(handle_unknown='ignore'))
    ])

    preprocessor = ColumnTransformer([
        ('num', numeric_transformer, numeric_features),
        ('cat', categorical_transformer, categorical_features)
    ])
    return preprocessor, numeric_features, categorical_features

# -------------------- UI --------------------
st.title("🏦 Loan Management — Decision Tree Classifier")
st.markdown("Upload your loan CSV or use the synthetic dataset (demo). Target column must be `approved` (0/1).")

with st.sidebar:
    st.header("Data & Model")
    upload = st.file_uploader("Upload CSV (optional)", type=['csv'])
    use_demo = st.checkbox("Use demo synthetic dataset", value=not bool(upload))
    n_demo = st.slider("Demo sample size", 200, 5000, 1000, step=100)
    criterion = st.selectbox('Criterion', ['gini', 'entropy'])

# Internal defaults
test_size = 0.2
random_state = 42

# Load data
if upload is not None and not use_demo:
    try:
        df = pd.read_csv(upload)
    except Exception as e:
        st.error(f"Error reading CSV: {e}")
        st.stop()
else:
    df = generate_synthetic_data(n_samples=n_demo, random_state=random_state)

st.subheader("Preview Data")
st.dataframe(df.head())

if 'approved' not in df.columns:
    st.error("Dataset must contain `approved` column with 0/1 values.")
    st.stop()

# Feature selection
all_features = [c for c in df.columns if c != 'approved']
selected_features = st.multiselect('Select features', options=all_features, default=all_features)

X = df[selected_features].copy()
y = df['approved'].copy()

# Auto-detect types & build preprocessing
preprocessor, numeric_features, categorical_features = build_preprocessing_pipeline(X)
st.write(f"Numeric: {numeric_features}")
st.write(f"Categorical: {categorical_features}")

# Train/test split
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=test_size, random_state=random_state, stratify=y)

# Pipeline
pipe = Pipeline([
    ('preprocessor', preprocessor),
    ('classifier', DecisionTreeClassifier(criterion=criterion, random_state=random_state))
])

# Train
with st.spinner('Training model...'):
    pipe.fit(X_train, y_train)

# Predictions
y_pred = pipe.predict(X_test)
acc = accuracy_score(y_test, y_pred)
cm = confusion_matrix(y_test, y_pred)
report = classification_report(y_test, y_pred, output_dict=True)

# -------------------- Results --------------------
st.subheader("Model performance")
col1, col2 = st.columns([1,2])
with col1:
    st.metric('Accuracy', f"{acc:.3f}")
with col2:
    st.write('Confusion matrix:')
    fig_cm, ax_cm = plt.subplots(figsize=(6, 6))
    cax = ax_cm.matshow(cm, cmap=plt.cm.Blues)
    fig_cm.colorbar(cax)

    # Annotate values
    for i in range(cm.shape[0]):
        for j in range(cm.shape[1]):
            ax_cm.text(j, i, str(cm[i, j]), ha='center', va='center')

    # Replace axis ticks with friendly names
    classes = ["Rejected Loan", "Approved Loan"]
    ax_cm.set_xticks([0, 1])
    ax_cm.set_xticklabels(classes, rotation=20)
    ax_cm.set_yticks([0, 1])
    ax_cm.set_yticklabels(classes)

    # Add user-friendly labels
    ax_cm.set_xlabel('Predicted (Model’s Guess)')
    ax_cm.set_ylabel('Actual (True Result)')
    st.pyplot(fig_cm)

# Classification report
st.write("### Classification Report")
report_df = pd.DataFrame(report).transpose()
report_df = report_df.rename(columns={
    "precision": "precision (accuracy for positives / exactness)",
    "recall": "recall (sensitivity)",
    "f1-score": "f1-score (balance)",
    "support": "support (frequency)"
})
report_df = report_df.rename(index={
    "0": "Rejected Loan",
    "1": "Approved Loan"
})
st.dataframe(report_df)

# -------------------- Tree plot --------------------
st.subheader('Decision Tree visualization (top 3 levels)')
try:
    ohe = pipe.named_steps['preprocessor'].named_transformers_['cat'].named_steps['onehot']
    ohe_features = list(ohe.get_feature_names_out(categorical_features))
    feature_names = numeric_features + ohe_features
except Exception:
    feature_names = selected_features

fig, ax = plt.subplots(figsize=(12,6))
plot_tree(pipe.named_steps['classifier'], feature_names=feature_names, filled=True, ax=ax, max_depth=3)
st.pyplot(fig)

# -------------------- Feature importances --------------------
st.subheader('Feature importances')
try:
    importances = pipe.named_steps['classifier'].feature_importances_
    fi = pd.Series(importances, index=feature_names).sort_values(ascending=False).head(15)
    st.bar_chart(fi)
except Exception as e:
    st.write('Could not compute feature importances:', e)

# -------------------- Single prediction --------------------
st.subheader('Predict for a single applicant')
with st.form('single_predict'):
    input_data = {}
    for col in selected_features:
        if col in numeric_features:
            input_data[col] = st.number_input(col, value=float(X[col].median()))
        else:
            vals = X[col].dropna().unique().tolist()
            input_data[col] = st.selectbox(col, options=vals)
    submit = st.form_submit_button('Predict')
    if submit:
        inp_df = pd.DataFrame([input_data])
        pred = pipe.predict(inp_df)[0]
        pred_proba = pipe.predict_proba(inp_df).max()
        st.write(f'Prediction: **{"Approved Loan" if pred==1 else "Rejected Loan"}** (confidence {pred_proba:.2f})')

# -------------------- Export --------------------
buf = io.BytesIO()
joblib.dump(pipe, buf)
buf.seek(0)
st.download_button('Download model (joblib)', data=buf, file_name='loan_tree.pkl')

csv_buf = io.StringIO()
pd.concat([X, y.rename('approved')], axis=1).to_csv(csv_buf, index=False)
st.download_button('Download training dataset', data=csv_buf.getvalue(), file_name='processed_dataset.csv', mime='text/csv')
