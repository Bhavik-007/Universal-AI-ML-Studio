from sklearn.svm import OneClassSVM
from sklearn.preprocessing import LabelEncoder

def train_unsupervised_model(df):
    X = df.drop("fraud_flag", axis=1)

    for col in X.select_dtypes(include=["object"]).columns:
        le = LabelEncoder()
        X[col] = le.fit_transform(X[col].astype(str))

    model = OneClassSVM(kernel="rbf", nu=0.05, gamma="scale")
    model.fit(X)

    preds = model.predict(X)  # -1 = anomaly, 1 = normal
    results = df.copy()
    results["AnomalyFlag"] = preds

    return results