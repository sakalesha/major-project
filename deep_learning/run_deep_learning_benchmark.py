import copy
import json
import os
import random
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    balanced_accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    matthews_corrcoef,
    precision_score,
    recall_score,
)


SEED = 42
random.seed(SEED)
np.random.seed(SEED)
torch.manual_seed(SEED)

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "NIFTY_EVENT_50" / "NiftyEvent50_enriched.csv"
OUTPUT_DIR = Path(__file__).resolve().parent / "outputs"

CATEGORICAL = ["ticker", "sector", "event_type", "is_primary_filing"]
NUMERICAL = [
    "pre_event_price",
    "pre_event_return",
    "pre_event_volatility",
    "pre_event_volume_change",
    "nifty50_prev_day_return",
    "india_vix_pct_change",
]


class MLP(nn.Module):
    def __init__(self, input_size, output_size, hidden_sizes=(128, 64), dropout=0.25):
        super().__init__()
        layers = []
        previous = input_size
        for hidden_size in hidden_sizes:
            layers.extend([
                nn.Linear(previous, hidden_size),
                nn.BatchNorm1d(hidden_size),
                nn.GELU(),
                nn.Dropout(dropout),
            ])
            previous = hidden_size
        layers.append(nn.Linear(previous, output_size))
        self.network = nn.Sequential(*layers)

    def forward(self, x):
        return self.network(x)


class ResidualMLP(nn.Module):
    def __init__(self, input_size, output_size, hidden_size=128, dropout=0.25):
        super().__init__()
        self.input = nn.Sequential(
            nn.Linear(input_size, hidden_size),
            nn.BatchNorm1d(hidden_size),
            nn.GELU(),
        )
        self.block1 = self._block(hidden_size, dropout)
        self.block2 = self._block(hidden_size, dropout)
        self.output = nn.Linear(hidden_size, output_size)

    @staticmethod
    def _block(hidden_size, dropout):
        return nn.Sequential(
            nn.Linear(hidden_size, hidden_size),
            nn.BatchNorm1d(hidden_size),
            nn.GELU(),
            nn.Dropout(dropout),
        )

    def forward(self, x):
        x = self.input(x)
        x = x + self.block1(x)
        x = x + self.block2(x)
        return self.output(x)


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


def fit_preprocessor(train):
    preprocessor = ColumnTransformer([
        ("numerical", Pipeline([(
            "impute", SimpleImputer(strategy="median")
        ), (
            "scale", StandardScaler()
        )]), NUMERICAL),
        ("categorical", Pipeline([(
            "impute", SimpleImputer(strategy="most_frequent")
        ), (
            "encode", OneHotEncoder(handle_unknown="ignore")
        )]), CATEGORICAL),
    ])
    preprocessor.fit(train[CATEGORICAL + NUMERICAL])
    return preprocessor


def to_tensors(preprocessor, train, val, test, target):
    train_labels = train[target].astype(str).str.strip().str.title()
    val_labels = val[target].astype(str).str.strip().str.title()
    test_labels = test[target].astype(str).str.strip().str.title()

    classes = sorted(train_labels.unique())
    class_to_index = {label: index for index, label in enumerate(classes)}
    y_train = train_labels.map(class_to_index).to_numpy(dtype=np.int64)
    y_val = val_labels.map(class_to_index).to_numpy(dtype=np.int64)
    y_test = test_labels.map(class_to_index).to_numpy(dtype=np.int64)

    X_train = preprocessor.transform(train[CATEGORICAL + NUMERICAL])
    X_val = preprocessor.transform(val[CATEGORICAL + NUMERICAL])
    X_test = preprocessor.transform(test[CATEGORICAL + NUMERICAL])
    X_train = X_train.toarray() if hasattr(X_train, "toarray") else np.asarray(X_train)
    X_val = X_val.toarray() if hasattr(X_val, "toarray") else np.asarray(X_val)
    X_test = X_test.toarray() if hasattr(X_test, "toarray") else np.asarray(X_test)

    tensors = {
        "train": (torch.tensor(X_train, dtype=torch.float32), torch.tensor(y_train, dtype=torch.long)),
        "val": (torch.tensor(X_val, dtype=torch.float32), torch.tensor(y_val, dtype=torch.long)),
        "test": (torch.tensor(X_test, dtype=torch.float32), torch.tensor(y_test, dtype=torch.long)),
    }
    return tensors, classes, y_test


def train_model(model_name, model, train_data, val_data, classes, y_train, epochs=120, patience=15):
    X_train, y_train_tensor = train_data
    X_val, y_val_tensor = val_data

    counts = torch.bincount(y_train_tensor, minlength=len(classes)).float()
    weights = counts.sum() / torch.clamp(counts, min=1)
    weights = weights / weights.sum() * len(classes)
    criterion = nn.CrossEntropyLoss(weight=weights)
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-3)

    loader = DataLoader(
        TensorDataset(X_train, y_train_tensor),
        batch_size=64,
        shuffle=True,
        drop_last=True,
        generator=torch.Generator().manual_seed(SEED),
    )

    best_state = copy.deepcopy(model.state_dict())
    best_f1 = -1.0
    wait = 0

    for epoch in range(epochs):
        model.train()
        for X_batch, y_batch in loader:
            optimizer.zero_grad(set_to_none=True)
            loss = criterion(model(X_batch), y_batch)
            loss.backward()
            optimizer.step()

        model.eval()
        with torch.no_grad():
            logits = model(X_val)
            probabilities = torch.softmax(logits, dim=1).numpy()
            predictions = probabilities.argmax(axis=1)

        val_labels = y_val_tensor.numpy()
        macro_f1 = f1_score(val_labels, predictions, average="macro", zero_division=0)
        if macro_f1 > best_f1:
            best_f1 = macro_f1
            best_state = copy.deepcopy(model.state_dict())
            wait = 0
        else:
            wait += 1
            if wait >= patience:
                break

    model.load_state_dict(best_state)
    model.eval()
    return model, best_f1


def predict(model, X):
    with torch.no_grad():
        logits = model(torch.tensor(X, dtype=torch.float32))
        return torch.softmax(logits, dim=1).numpy()


def fit_retrained_model(model, train_data, classes, epochs=80):
    X_train, y_train_tensor = train_data
    counts = torch.bincount(y_train_tensor, minlength=len(classes)).float()
    weights = counts.sum() / torch.clamp(counts, min=1)
    weights = weights / weights.sum() * len(classes)
    criterion = nn.CrossEntropyLoss(weight=weights)
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-3)
    loader = DataLoader(
        TensorDataset(X_train, y_train_tensor),
        batch_size=64,
        shuffle=True,
        drop_last=True,
        generator=torch.Generator().manual_seed(SEED),
    )
    model.train()
    for _ in range(epochs):
        for X_batch, y_batch in loader:
            optimizer.zero_grad(set_to_none=True)
            loss = criterion(model(X_batch), y_batch)
            loss.backward()
            optimizer.step()
    model.eval()
    return model


def select_volatility_threshold(probabilities, y_val, yes_index):
    best = {"threshold": 0.5, "macro_f1": -1.0}
    for threshold in np.arange(0.20, 0.81, 0.02):
        predictions = np.where(probabilities[:, yes_index] >= threshold, yes_index, 1 - yes_index)
        score = f1_score(y_val, predictions, average="macro", zero_division=0)
        if score > best["macro_f1"]:
            best = {"threshold": float(threshold), "macro_f1": float(score)}
    return best


def run_task(task_name, target, train, val, test, output_dir):
    preprocessor = fit_preprocessor(train)
    tensors, classes, y_test = to_tensors(preprocessor, train, val, test, target)
    X_train, y_train_tensor = tensors["train"]
    X_val, y_val_tensor = tensors["val"]
    X_test, y_test_tensor = tensors["test"]

    architectures = {
        "MLP": lambda: MLP(X_train.shape[1], len(classes), hidden_sizes=(128, 64), dropout=0.25),
        "ResidualMLP": lambda: ResidualMLP(X_train.shape[1], len(classes), hidden_size=128, dropout=0.25),
    }

    rows = []
    best_model_name = None
    best_model = None
    best_validation_f1 = -1.0

    for model_name, factory in architectures.items():
        model = factory()
        model, val_f1 = train_model(
            model_name, model, tensors["train"], tensors["val"], classes, y_train_tensor
        )
        val_probabilities = predict(model, X_val.numpy())
        val_predictions = val_probabilities.argmax(axis=1)

        row = {
            "Model": model_name,
            "Validation Accuracy": accuracy_score(y_val_tensor.numpy(), val_predictions),
            "Validation Balanced Accuracy": balanced_accuracy_score(y_val_tensor.numpy(), val_predictions),
            "Validation Precision Macro": precision_score(y_val_tensor.numpy(), val_predictions, average="macro", zero_division=0),
            "Validation Recall Macro": recall_score(y_val_tensor.numpy(), val_predictions, average="macro", zero_division=0),
            "Validation F1 Macro": f1_score(y_val_tensor.numpy(), val_predictions, average="macro", zero_division=0),
        }
        rows.append(row)

        if val_f1 > best_validation_f1:
            best_validation_f1 = val_f1
            best_model_name = model_name
            best_model = copy.deepcopy(model)

    comparison = pd.DataFrame(rows).sort_values("Validation F1 Macro", ascending=False)
    comparison.to_csv(output_dir / f"{task_name.lower()}_deep_learning_validation.csv", index=False)

    X_retrain = torch.cat([X_train, X_val])
    y_retrain = torch.cat([y_train_tensor, y_val_tensor])
    retrained_model = architectures[best_model_name]()
    retrained_model = fit_retrained_model(
        retrained_model, (X_retrain, y_retrain), classes, epochs=80
    )

    test_probabilities = predict(retrained_model, X_test.numpy())

    threshold = None
    if task_name == "Volatility":
        yes_index = classes.index("Yes")
        val_probabilities = predict(best_model, X_val.numpy())
        threshold = select_volatility_threshold(
            val_probabilities,
            y_val_tensor.numpy(),
            yes_index,
        )
        test_predictions = np.where(
            test_probabilities[:, yes_index] >= threshold["threshold"],
            yes_index,
            1 - yes_index,
        )
    else:
        test_predictions = test_probabilities.argmax(axis=1)

    y_test_array = y_test_tensor.numpy()
    class_names = classes
    cm = confusion_matrix(y_test_array, test_predictions, labels=list(range(len(classes))))
    pd.DataFrame(cm, index=class_names, columns=class_names).to_csv(
        output_dir / f"{task_name.lower()}_deep_learning_test_confusion_matrix.csv"
    )
    pd.DataFrame(
        classification_report(
            y_test_array,
            test_predictions,
            target_names=class_names,
            output_dict=True,
            zero_division=0,
        )
    ).transpose().to_csv(output_dir / f"{task_name.lower()}_deep_learning_test_report.csv")

    summary = {
        "selected_model": best_model_name,
        "primary_metric": "macro_f1",
        "test_accuracy": accuracy_score(y_test_array, test_predictions),
        "test_balanced_accuracy": balanced_accuracy_score(y_test_array, test_predictions),
        "test_mcc": matthews_corrcoef(y_test_array, test_predictions),
        "test_macro_f1": f1_score(y_test_array, test_predictions, average="macro", zero_division=0),
        "test_precision_macro": precision_score(y_test_array, test_predictions, average="macro", zero_division=0),
        "test_recall_macro": recall_score(y_test_array, test_predictions, average="macro", zero_division=0),
        "n_train": len(train),
        "n_validation": len(val),
        "n_test": len(test),
        "class_names": class_names,
    }

    if task_name == "Volatility":
        yes_index = classes.index("Yes")
        yes_labels = (y_test_array == yes_index).astype(int)
        yes_predictions = (test_predictions == yes_index).astype(int)
        summary.update({
            "selected_threshold": threshold["threshold"],
            "validation_threshold_macro_f1": threshold["macro_f1"],
            "test_yes_precision": precision_score(yes_labels, yes_predictions, zero_division=0),
            "test_yes_recall": recall_score(yes_labels, yes_predictions, zero_division=0),
            "test_yes_f1": f1_score(yes_labels, yes_predictions, zero_division=0),
            "test_yes_average_precision": average_precision_score(
                yes_labels,
                test_probabilities[:, yes_index],
            ),
        })

    with open(output_dir / f"{task_name.lower()}_deep_learning_test_summary.json", "w") as handle:
        json.dump(summary, handle, indent=2)

    return comparison, summary


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(DATA_PATH)
    df["effective_t0"] = pd.to_datetime(df["effective_t0"], errors="coerce")
    df = df.dropna(subset=["effective_t0", "direction_label", "volatility_label"])
    train, val, test = chronological_purged_split(df)

    direction_comparison, direction_summary = run_task(
        "Direction", "direction_label", train, val, test, OUTPUT_DIR
    )

    available = df["volatility_label_status"].fillna("Unknown").eq("Available")
    volatility_ids = set(df.loc[available, "event_id"])
    volatility_train = train[train["event_id"].isin(volatility_ids)]
    volatility_val = val[val["event_id"].isin(volatility_ids)]
    volatility_test = test[test["event_id"].isin(volatility_ids)]
    volatility_comparison, volatility_summary = run_task(
        "Volatility",
        "volatility_label",
        volatility_train,
        volatility_val,
        volatility_test,
        OUTPUT_DIR,
    )

    summary = {
        "direction": direction_summary,
        "volatility": volatility_summary,
        "dataset": str(DATA_PATH),
        "seed": SEED,
        "device": "cpu",
        "splits": {
            "train": len(train),
            "validation": len(val),
            "test": len(test),
            "embargo_days": 5,
        },
    }
    with open(OUTPUT_DIR / "deep_learning_summary.json", "w") as handle:
        json.dump(summary, handle, indent=2)

    print(direction_comparison.to_string(index=False))
    print(volatility_comparison.to_string(index=False))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
