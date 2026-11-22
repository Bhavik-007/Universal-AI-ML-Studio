from sklearn.model_selection import train_test_split
from sklearn.svm import SVC
from sklearn.metrics import accuracy_score, classification_report
from sklearn.preprocessing import LabelEncoder

def train_supervised_model(df):
    X = df.drop("fraud_flag", axis=1)
    y = df["fraud_flag"]

    # Encode categorical columns
    for col in X.select_dtypes(include=["object"]).columns:
        le = LabelEncoder()
        X[col] = le.fit_transform(X[col].astype(str))

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.3, random_state=42)

    model = SVC(kernel="rbf", probability=True)
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    acc = accuracy_score(y_test, y_pred)
    report = classification_report(y_test, y_pred, output_dict=True)

    # Attach predictions back to test set
    results = X_test.copy()
    results["Actual"] = y_test
    results["Predicted"] = y_pred

    return acc, report, results