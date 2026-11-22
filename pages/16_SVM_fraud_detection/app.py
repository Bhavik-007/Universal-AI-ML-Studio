import sys
from pathlib import Path

MODULE_DIR = Path(__file__).resolve().parent
if str(MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE_DIR))

import streamlit as st

from auth.login_manager import login_manager
from auth.auth_guard import protect_page




st.set_page_config(page_title="Universal AI Studio Application", layout="wide")
login_manager()
protect_page()

import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from svm_fraud.utils import load_large_file
from svm_fraud.model_supervised import train_supervised_model
from svm_fraud.model_unsupervised import train_unsupervised_model

st.title("BFSI Fraud Detection Dashboard")

uploaded_file = st.file_uploader("Upload CSV/XLSX file", type=["csv", "xlsx"])

if uploaded_file:
    df = load_large_file(uploaded_file)

    # Tabs for navigation
    tab1, tab2, tab3, tab4 = st.tabs(["Overview", "Fraud Cases", "Visualizations", "Download"])

    with tab1:  # Overview
        st.subheader("Data Preview")
        st.write(df.head())

        st.subheader("Fraud Flag Distribution")
        fig, ax = plt.subplots()
        sns.countplot(x="fraud_flag", data=df, ax=ax)
        st.pyplot(fig)

    with tab2:  # Fraud Cases
        option = st.selectbox("Choose Model Type", ["Supervised SVM", "Unsupervised One-Class SVM"])
        if st.button("Train Model"):
            if option == "Supervised SVM":
                acc, report, results = train_supervised_model(df)
                st.write(f"Model Accuracy: {acc*100:.2f}%")
                st.dataframe(pd.DataFrame(report).transpose())
                st.subheader("Transactions Predicted as Fraud")
                st.dataframe(results[results["Predicted"] == 1])
            else:
                results = train_unsupervised_model(df)
                st.subheader("Transactions Flagged as Anomalies")
                st.dataframe(results[results["AnomalyFlag"] == -1])

    with tab3:  # Visualizations
        st.subheader("Fraud vs Non-Fraud Predictions")
        if 'results' in locals():
            fig, ax = plt.subplots()
            if "Predicted" in results.columns:
                sns.countplot(x="Predicted", data=results, ax=ax, palette="Set2")
            else:
                sns.countplot(x="AnomalyFlag", data=results, ax=ax, palette="Set2")
            st.pyplot(fig)

            st.subheader("Transaction Amounts by Prediction")
            if "Predicted" in results.columns:
                fig, ax = plt.subplots()
                sns.boxplot(x="Predicted", y="amount", data=results, ax=ax, palette="Set1")
                st.pyplot(fig)

            st.subheader("Fraud Predictions by Location")
            if "location" in results.columns:
                fig, ax = plt.subplots(figsize=(8,4))
                sns.countplot(x="location", hue="Predicted" if "Predicted" in results.columns else "AnomalyFlag", data=results, ax=ax)
                ax.tick_params(axis="x", rotation=45)
                st.pyplot(fig)

    with tab4:  # Download
        if 'results' in locals():
            if "Predicted" in results.columns:
                fraud_cases = results[results["Predicted"] == 1]
            else:
                fraud_cases = results[results["AnomalyFlag"] == -1]

            st.download_button(
                label="Download Fraud Cases as CSV",
                data=fraud_cases.to_csv(index=False),
                file_name="fraud_cases.csv",
                mime="text/csv"
            )
