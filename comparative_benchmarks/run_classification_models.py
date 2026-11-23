import json
import os
from pathlib import Path

import pandas as pd
import numpy as np
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.impute import SimpleImputer
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.svm import SVC
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    balanced_accuracy_score,
    f1_score,
    matthews_corrcoef,
    precision_score,
    recall_score,
)

from xgboost import XGBClassifier
from catboost import CatBoostClassifier


ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "NIFTY_EVENT_50" / "NiftyEvent50_enriched.csv"
OUTPUT_DIR = Path(__file__).resolve().parent / "outputs"
SEED = 42

CATEGORICAL = ["ticker", "sector", "event_type", "is_primary_filing"]
NUMERICAL = [
    "pre_event_price",
    "pre_event_return",
    "pre_event_volatility",
    "pre_event_volume_change",
    "nifty50_prev_day_return",
    "india_vix_pct_change",
]


def chronological_purged_split(df, embargo_days=5):
    df = df.sort_values(["effective_t0", "event_id"]).reset_index(drop=True)
    train_idx = int(len(df) * 0.70)
    val_idx = int(len(df) * 0.85)
    train_end = pd.to_datetime(df.iloc[train_idx]["effective_t0"])
    val_end = pd.to_datetime(df.iloc[val_idx]["effective_t0"])
    dates = pd.to_datetime(df["effective_t0"])
    train = df.loc[dates < train_end - pd.Timedelta(days=embargo_days)].copy()
    val = df.loc[
        (dates > train_end + pd.Timedelta(days=embargo_days))
        & (dates < val_end - pd.Timedelta(days=embargo_days))
    ].copy()
    test = df.loc[dates > val_end + pd.Timedelta(days=embargo_days)].copy()
    return train, val, test


def make_pipeline(estimator):
    preprocessor = ColumnTransformer([
        ("numerical", Pipeline([
            ("impute", SimpleImputer(strategy="median")),
            ("scale", StandardScaler()),
        ]), NUMERICAL),
        ("categorical", Pipeline([
            ("impute", SimpleImputer(strategy="most_frequent")),
            ("encode", OneHotEncoder(handle_unknown="ignore")),
        ]), CATEGORICAL),
    ])
    return Pipeline([("preprocessor", preprocessor), ("model", estimator)])


def run_task(task_name, target, train, val, test):
    X_train = train[CATEGORICAL + NUMERICAL]
    X_val = val[CATEGORICAL + NUMERICAL]
    X_test = test[CATEGORICAL + NUMERICAL]
    y_train = train[target].astype(str).str.strip().str.title()
    y_val = val[target].astype(str).str.strip().str.title()
    y_test = test[target].astype(str).str.strip().str.title()
    class_names = sorted(y_train.unique())
    class_mapping = {name: index for index, name in enumerate(class_names)}
    y_train = y_train.map(class_mapping)
    y_val = y_val.map(class_mapping)
    y_test = y_test.map(class_mapping)

    binary = class_names == ["No", "Yes"]
    xgb_objective = "binary:logistic" if binary else "multi:softprob"
    catboost_loss = "Logloss" if binary else "MultiClass"

    models = {
        "Majority Baseline": DummyClassifier(strategy="most_frequent"),
        "Random Forest": RandomForestClassifier(
            n_estimators=300,
            min_samples_leaf=3,
            class_weight="balanced",
            random_state=SEED,
            n_jobs=-1,
        ),
        "XGBoost": XGBClassifier(
            n_estimators=300,
            max_depth=6,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            objective=xgb_objective,
            eval_metric="logloss" if binary else "mlogloss",
            random_state=SEED,
            n_jobs=-1,
        ),
        "CatBoost": CatBoostClassifier(
            iterations=300,
            depth=6,
            learning_rate=0.05,
            loss_function=catboost_loss,
            random_seed=SEED,
            verbose=False,
        ),
        "SVM": SVC(
            kernel="rbf",
            class_weight="balanced",
            probability=True,
            random_state=SEED,
        ),
        "Logistic Regression": LogisticRegression(
            max_iter=3000,
            class_weight="balanced",
            random_state=SEED,
        ),
    }

    rows = []
    fitted = {}
    for name, estimator in models.items():
        pipeline = make_pipeline(estimator)
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
    comparison.to_csv(OUTPUT_DIR / f"{task_name.lower()}_classification_comparison.csv", index=False)

    best_name = comparison.iloc[0]["Model"]
    best = fitted[best_name]
    best.fit(pd.concat([X_train, X_val]), pd.concat([y_train, y_val]))
    prediction = best.predict(X_test)

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
    if binary:
        yes_precision = precision_score(y_test, prediction, pos_label=1, zero_division=0)
        yes_recall = recall_score(y_test, prediction, pos_label=1, zero_division=0)
        yes_f1 = f1_score(y_test, prediction, pos_label=1, zero_division=0)
        if hasattr(best, "predict_proba"):
            yes_index = list(best.classes_).index(1)
            probability = best.predict_proba(X_test)[:, yes_index]
            yes_ap = average_precision_score(y_test.eq(1).astype(int), probability)
        else:
            yes_ap = None
        summary.update({
            "test_yes_precision": yes_precision,
            "test_yes_recall": yes_recall,
            "test_yes_f1": yes_f1,
            "test_yes_average_precision": yes_ap,
        })

    return comparison, summary


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(DATA_PATH)
    df["effective_t0"] = pd.to_datetime(df["effective_t0"], errors="coerce")
    df = df.dropna(subset=["effective_t0", "direction_label", "volatility_label"])
    train, val, test = chronological_purged_split(df)

    direction_comparison, direction_summary = run_task(
        "Direction", "direction_label", train, val, test
    )

    available = df["volatility_label_status"].fillna("Unknown").eq("Available")
    ids = set(df.loc[available, "event_id"])
    volatility_comparison, volatility_summary = run_task(
        "Volatility",
        "volatility_label",
        train[train["event_id"].isin(ids)],
        val[val["event_id"].isin(ids)],
        test[test["event_id"].isin(ids)],
    )

    summary = {
        "direction": direction_summary,
        "volatility": volatility_summary,
        "models": [
            "Majority Baseline",
            "Random Forest",
            "XGBoost",
            "CatBoost",
            "SVM",
            "Logistic Regression",
        ],
    }
    with open(OUTPUT_DIR / "classification_models_summary.json", "w") as handle:
        json.dump(summary, handle, indent=2)
    print(direction_comparison.to_string(index=False))
    print(volatility_comparison.to_string(index=False))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
