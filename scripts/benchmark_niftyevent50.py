import os
import json
import argparse
import joblib
import pandas as pd
import numpy as np

from sklearn.base import clone
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.impute import SimpleImputer
from sklearn.dummy import DummyClassifier
from sklearn.linear_model import LogisticRegression, RidgeClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.svm import SVC
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    balanced_accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    matthews_corrcoef,
    confusion_matrix,
    classification_report,
)


def chronological_purged_split(df, embargo_days=5):
    df = df.sort_values(["effective_t0", "event_id"]).reset_index(drop=True)
    n = len(df)
    train_idx = int(n * 0.70)
    val_idx = int(n * 0.85)
    train_end = pd.to_datetime(df.iloc[train_idx]["effective_t0"])
    val_end = pd.to_datetime(df.iloc[val_idx]["effective_t0"])
    dates = pd.to_datetime(df["effective_t0"])

    train_mask = dates < train_end - pd.Timedelta(days=embargo_days)
    val_mask = (
        (dates > train_end + pd.Timedelta(days=embargo_days)) &
        (dates < val_end - pd.Timedelta(days=embargo_days))
    )
    test_mask = dates > val_end + pd.Timedelta(days=embargo_days)

    train = df.loc[train_mask].copy()
    val = df.loc[val_mask].copy()
    test = df.loc[test_mask].copy()

    same_date_groups = set(train["effective_t0"]).intersection(set(val["effective_t0"]))
    same_date_groups |= set(val["effective_t0"]).intersection(set(test["effective_t0"]))
    same_date_groups |= set(train["effective_t0"]).intersection(set(test["effective_t0"]))
    if same_date_groups:
        remove = pd.to_datetime(list(same_date_groups)).strftime("%Y-%m-%d").tolist()
        train = train[~train["effective_t0"].isin(remove)]
        val = val[~val["effective_t0"].isin(remove)]
        test = test[~test["effective_t0"].isin(remove)]

    return train, val, test


def make_pipeline(estimator, categorical, numerical):
    numerical_pipeline = Pipeline([
        ("impute", SimpleImputer(strategy="median")),
        ("scale", StandardScaler()),
    ])
    categorical_pipeline = Pipeline([
        ("impute", SimpleImputer(strategy="most_frequent")),
        ("encode", OneHotEncoder(handle_unknown="ignore")),
    ])
    preprocessor = ColumnTransformer([
        ("numerical", numerical_pipeline, numerical),
        ("categorical", categorical_pipeline, categorical),
    ])
    return Pipeline([("preprocessor", preprocessor), ("model", clone(estimator))])


def run_task(task_name, target, train, val, test, categorical, numerical, output_dir, models_dir):
    X_train = train[categorical + numerical]
    X_val = val[categorical + numerical]
    X_test = test[categorical + numerical]
    y_train = train[target].astype(str).str.strip().str.title()
    y_val = val[target].astype(str).str.strip().str.title()
    y_test = test[target].astype(str).str.strip().str.title()

    estimators = {
        "Majority Baseline": DummyClassifier(strategy="most_frequent"),
        "Stratified Baseline": DummyClassifier(strategy="stratified", random_state=42),
        "Logistic Regression": LogisticRegression(max_iter=3000, class_weight="balanced", random_state=42),
        "Ridge Classifier": RidgeClassifier(class_weight="balanced", random_state=42),
        "Random Forest": RandomForestClassifier(n_estimators=300, min_samples_leaf=3, class_weight="balanced", random_state=42, n_jobs=-1),
        "SVM": SVC(kernel="rbf", class_weight="balanced", probability=True, random_state=42),
    }

    rows = []
    fitted = {}
    for name, estimator in estimators.items():
        pipeline = make_pipeline(estimator, categorical, numerical)
        pipeline.fit(X_train, y_train)
        prediction = pipeline.predict(X_val)
        rows.append({
            "Model": name,
            "Validation Accuracy": accuracy_score(y_val, prediction),
            "Validation Balanced Accuracy": balanced_accuracy_score(y_val, prediction),
            "Validation Precision Macro": precision_score(y_val, prediction, average="macro", zero_division=0),
            "Validation Recall Macro": recall_score(y_val, prediction, average="macro", zero_division=0),
            "Validation F1 Macro": f1_score(y_val, prediction, average="macro", zero_division=0),
        })
        fitted[name] = pipeline

    comparison = pd.DataFrame(rows).sort_values("Validation F1 Macro", ascending=False)
    comparison.to_csv(os.path.join(output_dir, f"{task_name.lower()}_validation_comparison.csv"), index=False)
    best_name = comparison.iloc[0]["Model"]
    best = fitted[best_name]
    best.fit(
        pd.concat([X_train, X_val]),
        pd.concat([y_train, y_val]),
    )
    prediction = best.predict(X_test)

    classes = sorted(y_test.unique().tolist())
    cm = confusion_matrix(y_test, prediction, labels=classes)
    pd.DataFrame(cm, index=classes, columns=classes).to_csv(
        os.path.join(output_dir, f"{task_name.lower()}_test_confusion_matrix.csv")
    )
    pd.DataFrame(classification_report(y_test, prediction, output_dict=True, zero_division=0)).transpose().to_csv(
        os.path.join(output_dir, f"{task_name.lower()}_test_classification_report.csv")
    )

    summary = {
        "selected_model": best_name,
        "primary_metric": "macro_f1",
        "test_accuracy": accuracy_score(y_test, prediction),
        "test_balanced_accuracy": balanced_accuracy_score(y_test, prediction),
        "test_mcc": matthews_corrcoef(y_test, prediction),
        "test_macro_f1": f1_score(y_test, prediction, average="macro", zero_division=0),
        "test_precision_macro": precision_score(y_test, prediction, average="macro", zero_division=0),
        "test_recall_macro": recall_score(y_test, prediction, average="macro", zero_division=0),
        "n_train": len(train),
        "n_validation": len(val),
        "n_test": len(test),
    }
    if set(y_test.unique()).issubset({"Yes", "No"}):
        positive = "Yes"
        positive_index = list(best.classes_).index(positive)
        positive_probability = best.predict_proba(X_test)[:, positive_index]
        positive_labels = y_test.eq(positive).astype(int)
        summary.update({
            "test_yes_precision": precision_score(y_test, prediction, pos_label=positive, zero_division=0),
            "test_yes_recall": recall_score(y_test, prediction, pos_label=positive, zero_division=0),
            "test_yes_f1": f1_score(y_test, prediction, pos_label=positive, zero_division=0),
            "test_yes_average_precision": average_precision_score(positive_labels, positive_probability),
        })
    with open(os.path.join(output_dir, f"{task_name.lower()}_test_summary.json"), "w") as handle:
        json.dump(summary, handle, indent=2)
    joblib.dump(best, os.path.join(models_dir, f"{task_name.lower()}_best_pipeline.joblib"))
    return comparison, summary


def main():
    parser = argparse.ArgumentParser()
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    parser.add_argument("--input", default=os.path.join(root, "NIFTY_EVENT_50", "NiftyEvent50_enriched.csv"))
    parser.add_argument("--output", default=os.path.join(root, "outputs", "benchmark"))
    args = parser.parse_args()

    df = pd.read_csv(args.input)
    df["effective_t0"] = pd.to_datetime(df["effective_t0"], errors="coerce")
    df = df.dropna(subset=["effective_t0", "direction_label", "volatility_label"]).sort_values("effective_t0").reset_index(drop=True)

    train, val, test = chronological_purged_split(df)
    os.makedirs(args.output, exist_ok=True)
    os.makedirs(os.path.join(args.output, "splits"), exist_ok=True)
    os.makedirs(os.path.join(args.output, "models"), exist_ok=True)
    train.to_csv(os.path.join(args.output, "splits", "train_purged.csv"), index=False)
    val.to_csv(os.path.join(args.output, "splits", "validation_purged.csv"), index=False)
    test.to_csv(os.path.join(args.output, "splits", "test_purged.csv"), index=False)

    categorical = ["ticker", "sector", "event_type", "is_primary_filing"]
    numerical = [
        "pre_event_price",
        "pre_event_return",
        "pre_event_volatility",
        "pre_event_volume_change",
        "nifty50_prev_day_return",
        "india_vix_pct_change",
    ]

    direction_comparison, direction_summary = run_task(
        "Direction", "direction_label", train, val, test, categorical, numerical,
        args.output, os.path.join(args.output, "models")
    )

    available = df["volatility_label_status"].fillna("Unknown").eq("Available")
    volatility_train = train.loc[train["event_id"].isin(df.loc[available, "event_id"])]
    volatility_val = val.loc[val["event_id"].isin(df.loc[available, "event_id"])]
    volatility_test = test.loc[test["event_id"].isin(df.loc[available, "event_id"])]
    volatility_comparison, volatility_summary = run_task(
        "Volatility", "volatility_label", volatility_train, volatility_val, volatility_test,
        categorical, numerical, args.output, os.path.join(args.output, "models")
    )

    with open(os.path.join(args.output, "benchmark_summary.json"), "w") as handle:
        json.dump({
            "direction": direction_summary,
            "volatility": volatility_summary,
            "splits": {
                "train": len(train),
                "validation": len(val),
                "test": len(test),
                "embargo_days": 5,
            },
        }, handle, indent=2)

    print(direction_comparison.to_string(index=False))
    print(volatility_comparison.to_string(index=False))
    print(json.dumps({"direction": direction_summary, "volatility": volatility_summary}, indent=2))


if __name__ == "__main__":
    main()
