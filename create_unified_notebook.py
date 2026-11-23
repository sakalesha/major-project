from pathlib import Path

import nbformat as nbf


notebook = nbf.v4.new_notebook()
notebook.metadata = {
    "kernelspec": {
        "display_name": "NiftyEvent50 Python 3.11",
        "language": "python",
        "name": "niftyevent50",
    },
    "language_info": {
        "name": "python",
        "version": "3",
    },
}

cells = []


def markdown(source):
    cells.append(nbf.v4.new_markdown_cell(source))


def code(source):
    cells.append(nbf.v4.new_code_cell(source))


markdown("""# NiftyEvent-50: Unified Machine-Learning and Statistical Pipeline

This notebook compares all implemented model families using one documented evaluation protocol:

- 3,199 NiftyEvent-50 observations
- Chronological 70/15/15 train-validation-test split
- Five-calendar-day embargo around partition boundaries
- Training-only preprocessing fit
- Macro-F1 for model selection
- Untouched final test set
- Separate treatment of event-classification and time-series forecasting tasks

**Historical experimental notebooks are not used as evidence.** They contain random fallback features in some exploratory cells.
""")

code("""from pathlib import Path
import copy
import json
import random
import warnings

import numpy as np
import pandas as pd
import torch
import torch.nn as nn

from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.metrics import (
    accuracy_score, balanced_accuracy_score, f1_score,
    matthews_corrcoef, precision_score, recall_score,
    average_precision_score, mean_absolute_error, mean_squared_error,
    confusion_matrix, classification_report
)
from sklearn.dummy import DummyClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.svm import SVC

warnings.filterwarnings("ignore")
SEED = 42
random.seed(SEED)
np.random.seed(SEED)
torch.manual_seed(SEED)

ROOT = Path.cwd()
DATA_PATH = ROOT / "NIFTY_EVENT_50" / "NiftyEvent50_enriched.csv"
WINDOW_DIR = ROOT / "NIFTY_EVENT_50" / "ohlcv_windows"
CACHE_DIR = ROOT / "NIFTY_EVENT_50" / "cache"
OUTPUT_DIR = ROOT / "outputs" / "unified_notebook"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

print("PyTorch:", torch.__version__)
print("CUDA available:", torch.cuda.is_available())
print("Dataset:", DATA_PATH)
""")

markdown("""## 1. Dataset loading and quality audit

The canonical [NiftyEvent50_final.csv](NIFTY_EVENT_50/NiftyEvent50_final.csv) remains a 10-column public dataset.
This notebook uses the enriched release for verified market features and cumulative abnormal returns.
""")

code("""df = pd.read_csv(DATA_PATH)
df["effective_t0"] = pd.to_datetime(df["effective_t0"], errors="coerce")
df = df.dropna(subset=["effective_t0", "direction_label", "volatility_label"]).copy()
df = df.sort_values(["effective_t0", "event_id"]).reset_index(drop=True)

print("Rows:", len(df))
print("Date range:", df["effective_t0"].min().date(), "to", df["effective_t0"].max().date())
print("Direction distribution:")
print(df["direction_label"].value_counts())
print("Volatility distribution:")
print(df["volatility_label"].value_counts())
print("Missing enriched numerical features:")
print(df[[c for c in ["pre_event_return", "pre_event_volatility", "pre_event_volume_change",
                     "nifty50_prev_day_return", "india_vix_pct_change"] if c in df]].isna().sum())
""")

markdown("""## 2. Chronological split and purging

Events overlapping the partition boundaries are removed by a five-calendar-day embargo.
Same-date events are kept within one partition to avoid cross-split contamination.
""")

code("""def chronological_purged_split(data, embargo_days=5):
    data = data.sort_values(["effective_t0", "event_id"]).reset_index(drop=True)
    train_idx = int(len(data) * 0.70)
    val_idx = int(len(data) * 0.85)
    train_end = pd.to_datetime(data.iloc[train_idx]["effective_t0"])
    val_end = pd.to_datetime(data.iloc[val_idx]["effective_t0"])
    dates = pd.to_datetime(data["effective_t0"])

    train = data.loc[dates < train_end - pd.Timedelta(days=embargo_days)].copy()
    val = data.loc[
        (dates > train_end + pd.Timedelta(days=embargo_days))
        & (dates < val_end - pd.Timedelta(days=embargo_days))
    ].copy()
    test = data.loc[dates > val_end + pd.Timedelta(days=embargo_days)].copy()
    return train, val, test

train, val, test = chronological_purged_split(df)
print({"train": len(train), "validation": len(val), "test": len(test)})
print("Train end:", train["effective_t0"].max())
print("Validation range:", val["effective_t0"].min(), "to", val["effective_t0"].max())
print("Test start:", test["effective_t0"].min())
""")

markdown("""## 3. Shared event features and preprocessing

Numerical features are median-imputed and standardized. Categorical features are
most-frequent-imputed and one-hot encoded. The transformer is fitted only on training rows.
""")

code("""CATEGORICAL = ["ticker", "sector", "event_type", "is_primary_filing"]
NUMERICAL = [
    "pre_event_price",
    "pre_event_return",
    "pre_event_volatility",
    "pre_event_volume_change",
    "nifty50_prev_day_return",
    "india_vix_pct_change",
]

def make_preprocessor():
    return ColumnTransformer([
        ("numerical", Pipeline([
            ("impute", SimpleImputer(strategy="median")),
            ("scale", StandardScaler()),
        ]), NUMERICAL),
        ("categorical", Pipeline([
            ("impute", SimpleImputer(strategy="most_frequent")),
            ("encode", OneHotEncoder(handle_unknown="ignore")),
        ]), CATEGORICAL),
    ])

def evaluate_predictions(y_true, y_pred, positive=None):
    result = {
        "accuracy": accuracy_score(y_true, y_pred),
        "balanced_accuracy": balanced_accuracy_score(y_true, y_pred),
        "mcc": matthews_corrcoef(y_true, y_pred),
        "precision_macro": precision_score(y_true, y_pred, average="macro", zero_division=0),
        "recall_macro": recall_score(y_true, y_pred, average="macro", zero_division=0),
        "macro_f1": f1_score(y_true, y_pred, average="macro", zero_division=0),
    }
    if positive is not None:
        result.update({
            "positive_precision": precision_score(y_true, y_pred, pos_label=positive, zero_division=0),
            "positive_recall": recall_score(y_true, y_pred, pos_label=positive, zero_division=0),
            "positive_f1": f1_score(y_true, y_pred, pos_label=positive, zero_division=0),
        })
    return result
""")

markdown("""## 4. Traditional machine-learning models

The models in this section are:

- Majority-class baseline
- Random Forest
- XGBoost
- CatBoost
- SVM
- Logistic Regression

Macro-F1 selects the model using the validation set. The test set is evaluated once.
""")

code("""try:
    from xgboost import XGBClassifier
    HAS_XGBOOST = True
except Exception:
    HAS_XGBOOST = False

try:
    from catboost import CatBoostClassifier
    HAS_CATBOOST = True
except Exception:
    HAS_CATBOOST = False

print("XGBoost available:", HAS_XGBOOST)
print("CatBoost available:", HAS_CATBOOST)
""")

code("""def run_classification_task(task_name, target, task_train, task_val, task_test):
    X_train = task_train[CATEGORICAL + NUMERICAL]
    X_val = task_val[CATEGORICAL + NUMERICAL]
    X_test = task_test[CATEGORICAL + NUMERICAL]

    y_train = task_train[target].astype(str).str.strip().str.title()
    y_val = task_val[target].astype(str).str.strip().str.title()
    y_test = task_test[target].astype(str).str.strip().str.title()
    classes = sorted(y_train.unique())
    class_map = {name: i for i, name in enumerate(classes)}
    y_train_encoded = y_train.map(class_map)
    y_val_encoded = y_val.map(class_map)
    y_test_encoded = y_test.map(class_map)
    binary = classes == ["No", "Yes"] if isinstance(classes, list) else False
    binary = sorted(classes) == ["No", "Yes"]

    models = {
        "Majority Baseline": DummyClassifier(strategy="most_frequent"),
        "Random Forest": RandomForestClassifier(
            n_estimators=300, min_samples_leaf=3, class_weight="balanced",
            random_state=SEED, n_jobs=-1
        ),
        "SVM": SVC(kernel="rbf", class_weight="balanced", probability=True, random_state=SEED),
        "Logistic Regression": LogisticRegression(
            max_iter=3000, class_weight="balanced", random_state=SEED
        ),
    }
    if HAS_XGBOOST:
        models["XGBoost"] = XGBClassifier(
            n_estimators=300, max_depth=6, learning_rate=0.05,
            subsample=0.8, colsample_bytree=0.8,
            objective="binary:logistic" if binary else "multi:softprob",
            eval_metric="logloss" if binary else "mlogloss",
            random_state=SEED, n_jobs=-1
        )
    if HAS_CATBOOST:
        models["CatBoost"] = CatBoostClassifier(
            iterations=300, depth=6, learning_rate=0.05,
            loss_function="Logloss" if binary else "MultiClass",
            random_seed=SEED, verbose=False
        )

    rows = []
    fitted = {}
    for name, estimator in models.items():
        pipeline = Pipeline([
            ("preprocessor", make_preprocessor()),
            ("model", estimator),
        ])
        pipeline.fit(X_train, y_train_encoded)
        val_pred = pipeline.predict(X_val)
        val_scores = evaluate_predictions(y_val_encoded, val_pred)
        rows.append({"Model": name, **{f"Validation {k}": v for k, v in val_scores.items()}})
        fitted[name] = pipeline

    comparison = pd.DataFrame(rows).sort_values("Validation macro_f1", ascending=False)
    best_name = comparison.iloc[0]["Model"]
    best = fitted[best_name]
    best.fit(
        pd.concat([X_train, X_val]),
        pd.concat([y_train_encoded, y_val_encoded]),
    )
    test_pred = best.predict(X_test)
    test_scores = evaluate_predictions(
        y_test_encoded,
        test_pred,
        positive=1 if binary else None,
    )

    average_precision = None
    if binary and hasattr(best, "predict_proba"):
        yes_index = list(best.classes_).index(1)
        test_prob = best.predict_proba(X_test)[:, yes_index]
        average_precision = average_precision_score(y_test_encoded, test_prob)
        test_scores["average_precision_yes"] = average_precision

    cm = confusion_matrix(y_test_encoded, test_pred, labels=list(range(len(classes))))
    pd.DataFrame(cm, index=classes, columns=classes).to_csv(
        OUTPUT_DIR / f"{task_name.lower()}_traditional_confusion_matrix.csv"
    )
    summary = {
        "task": task_name,
        "selected_model": best_name,
        "primary_metric": "macro_f1",
        "n_train": len(task_train),
        "n_validation": len(task_val),
        "n_test": len(task_test),
        "classes": classes,
        **{f"test_{k}": v for k, v in test_scores.items()},
    }
    comparison.to_csv(OUTPUT_DIR / f"{task_name.lower()}_traditional_validation.csv", index=False)
    with open(OUTPUT_DIR / f"{task_name.lower()}_traditional_summary.json", "w") as handle:
        json.dump(summary, handle, indent=2)
    return comparison, summary

direction_comparison, direction_summary = run_classification_task(
    "Direction", "direction_label", train, val, test
)
available = df["volatility_label_status"].fillna("Unknown").eq("Available")
available_ids = set(df.loc[available, "event_id"])
volatility_train = train[train["event_id"].isin(available_ids)]
volatility_val = val[val["event_id"].isin(available_ids)]
volatility_test = test[test["event_id"].isin(available_ids)]
volatility_comparison, volatility_summary = run_classification_task(
    "Volatility", "volatility_label",
    volatility_train, volatility_val, volatility_test
)

display(direction_comparison)
display(volatility_comparison)
print(json.dumps({"direction": direction_summary, "volatility": volatility_summary}, indent=2))
""")

markdown("""## 5. Sequence deep-learning models

These models use three pre-event adjusted-price sessions (`T-3`, `T-2`, `T-1`)
and static event features:

- Returns
- Relative adjusted close
- Volume ratio
- Price momentum

The sequence architectures are:

- LSTM
- GRU
- 1D-CNN
- TCN
- CNN-LSTM
- Transformer Encoder
""")

code("""from torch.utils.data import DataLoader, TensorDataset

class LSTMClassifier(nn.Module):
    def __init__(self, sequence_size, static_size, output_size):
        super().__init__()
        self.lstm = nn.LSTM(sequence_size, 64, batch_first=True)
        self.static = nn.Sequential(nn.Linear(static_size, 32), nn.ReLU(), nn.Dropout(0.20))
        self.output = nn.Sequential(nn.Linear(96, 64), nn.ReLU(), nn.Dropout(0.20), nn.Linear(64, output_size))
    def forward(self, sequence, static):
        _, (hidden, _) = self.lstm(sequence)
        return self.output(torch.cat([hidden[-1], self.static(static)], dim=1))

class GRUClassifier(nn.Module):
    def __init__(self, sequence_size, static_size, output_size):
        super().__init__()
        self.gru = nn.GRU(sequence_size, 64, batch_first=True)
        self.static = nn.Sequential(nn.Linear(static_size, 32), nn.ReLU(), nn.Dropout(0.20))
        self.output = nn.Sequential(nn.Linear(96, 64), nn.ReLU(), nn.Dropout(0.20), nn.Linear(64, output_size))
    def forward(self, sequence, static):
        _, hidden = self.gru(sequence)
        return self.output(torch.cat([hidden[-1], self.static(static)], dim=1))

class Conv1DClassifier(nn.Module):
    def __init__(self, sequence_size, static_size, output_size):
        super().__init__()
        self.conv = nn.Sequential(nn.Conv1d(sequence_size, 32, 2), nn.ReLU(),
                                   nn.Conv1d(32, 64, 2), nn.ReLU(),
                                   nn.AdaptiveAvgPool1d(1))
        self.static = nn.Sequential(nn.Linear(static_size, 32), nn.ReLU(), nn.Dropout(0.20))
        self.output = nn.Sequential(nn.Linear(96, 64), nn.ReLU(), nn.Dropout(0.20), nn.Linear(64, output_size))
    def forward(self, sequence, static):
        features = self.conv(sequence.transpose(1, 2)).squeeze(-1)
        return self.output(torch.cat([features, self.static(static)], dim=1))

class TCNClassifier(nn.Module):
    def __init__(self, sequence_size, static_size, output_size):
        super().__init__()
        self.convs = nn.Sequential(
            nn.Conv1d(sequence_size, 32, 2, padding=1), nn.ReLU(),
            nn.Conv1d(32, 32, 2, dilation=2, padding=2), nn.ReLU(),
            nn.Conv1d(32, 64, 2, dilation=4, padding=4), nn.ReLU(),
            nn.AdaptiveAvgPool1d(1),
        )
        self.static = nn.Sequential(nn.Linear(static_size, 32), nn.ReLU(), nn.Dropout(0.20))
        self.output = nn.Sequential(nn.Linear(96, 64), nn.ReLU(), nn.Dropout(0.20), nn.Linear(64, output_size))
    def forward(self, sequence, static):
        features = self.convs(sequence.transpose(1, 2)).squeeze(-1)
        return self.output(torch.cat([features, self.static(static)], dim=1))

class CNNLSTMClassifier(nn.Module):
    def __init__(self, sequence_size, static_size, output_size):
        super().__init__()
        self.conv = nn.Sequential(nn.Conv1d(sequence_size, 32, 2), nn.ReLU())
        self.lstm = nn.LSTM(32, 64, batch_first=True)
        self.static = nn.Sequential(nn.Linear(static_size, 32), nn.ReLU(), nn.Dropout(0.20))
        self.output = nn.Sequential(nn.Linear(96, 64), nn.ReLU(), nn.Dropout(0.20), nn.Linear(64, output_size))
    def forward(self, sequence, static):
        convolved = self.conv(sequence.transpose(1, 2)).transpose(1, 2)
        _, (hidden, _) = self.lstm(convolved)
        return self.output(torch.cat([hidden[-1], self.static(static)], dim=1))

class TransformerClassifier(nn.Module):
    def __init__(self, sequence_size, static_size, output_size):
        super().__init__()
        self.input = nn.Linear(sequence_size, 64)
        layer = nn.TransformerEncoderLayer(
            d_model=64, nhead=4, dim_feedforward=128,
            dropout=0.20, batch_first=True
        )
        self.encoder = nn.TransformerEncoder(layer, num_layers=2)
        self.static = nn.Sequential(nn.Linear(static_size, 32), nn.ReLU(), nn.Dropout(0.20))
        self.output = nn.Sequential(nn.Linear(96, 64), nn.ReLU(), nn.Dropout(0.20), nn.Linear(64, output_size))
    def forward(self, sequence, static):
        encoded = self.encoder(self.input(sequence)).mean(dim=1)
        return self.output(torch.cat([encoded, self.static(static)], dim=1))
""")

code("""def build_sequence(event_id):
    matches = list(WINDOW_DIR.glob(f"{event_id}_*.csv"))
    if not matches:
        return np.zeros((3, 4), dtype=np.float32)
    window = pd.read_csv(matches[0])
    window = window[window["relative_session"].isin([-3, -2, -1])]
    window = window.sort_values("relative_session")
    if len(window) != 3:
        return np.zeros((3, 4), dtype=np.float32)
    close = pd.to_numeric(window["Adj Close"], errors="coerce").ffill().bfill().to_numpy(dtype=np.float32)
    volume = pd.to_numeric(window["Volume"], errors="coerce").ffill().bfill().to_numpy(dtype=np.float32)
    returns = np.zeros(3, dtype=np.float32)
    returns[1:] = np.diff(close) / np.clip(np.abs(close[:-1]), 1e-8, None)
    relative_close = close / max(float(close.mean()), 1e-8)
    volume_ratio = volume / max(float(volume.mean()), 1e-8)
    momentum = np.concatenate([[0.0], np.diff(close)])
    return np.column_stack([returns, relative_close, volume_ratio, momentum]).astype(np.float32)

def prepare_sequence_tensors(task_train, task_val, task_test, target):
    preprocessor = make_preprocessor()
    preprocessor.fit(task_train[CATEGORICAL + NUMERICAL])
    static_train = preprocessor.transform(task_train[CATEGORICAL + NUMERICAL])
    static_val = preprocessor.transform(task_val[CATEGORICAL + NUMERICAL])
    static_test = preprocessor.transform(task_test[CATEGORICAL + NUMERICAL])
    static_train = static_train.toarray() if hasattr(static_train, "toarray") else np.asarray(static_train)
    static_val = static_val.toarray() if hasattr(static_val, "toarray") else np.asarray(static_val)
    static_test = static_test.toarray() if hasattr(static_test, "toarray") else np.asarray(static_test)

    raw_train_sequence = np.asarray([build_sequence(x) for x in task_train["event_id"]], dtype=np.float32)
    sequence_mean = raw_train_sequence.mean(axis=(0, 1), keepdims=True)
    sequence_std = raw_train_sequence.std(axis=(0, 1), keepdims=True)
    sequence_std = np.where(sequence_std < 1e-8, 1.0, sequence_std)

    def sequence_tensor(split):
        sequence = np.asarray([build_sequence(x) for x in split["event_id"]], dtype=np.float32)
        sequence = (sequence - sequence_mean) / sequence_std
        return torch.tensor(sequence, dtype=torch.float32)

    y_train_raw = task_train[target].astype(str).str.strip().str.title()
    y_val_raw = task_val[target].astype(str).str.strip().str.title()
    y_test_raw = task_test[target].astype(str).str.strip().str.title()
    classes = sorted(y_train_raw.unique())
    mapping = {name: i for i, name in enumerate(classes)}

    return {
        "sequence_train": sequence_tensor(task_train),
        "sequence_val": sequence_tensor(task_val),
        "sequence_test": sequence_tensor(task_test),
        "static_train": torch.tensor(static_train, dtype=torch.float32),
        "static_val": torch.tensor(static_val, dtype=torch.float32),
        "static_test": torch.tensor(static_test, dtype=torch.float32),
        "y_train": torch.tensor(y_train_raw.map(mapping).to_numpy(), dtype=torch.long),
        "y_val": torch.tensor(y_val_raw.map(mapping).to_numpy(), dtype=torch.long),
        "y_test": torch.tensor(y_test_raw.map(mapping).to_numpy(), dtype=torch.long),
    }, classes

def train_sequence_model(model, tensors, classes, epochs=50, patience=8):
    sequence_train = tensors["sequence_train"]
    static_train = tensors["static_train"]
    y_train = tensors["y_train"]
    sequence_val = tensors["sequence_val"]
    static_val = tensors["static_val"]
    y_val = tensors["y_val"]

    counts = torch.bincount(y_train, minlength=len(classes)).float()
    weights = counts.sum() / torch.clamp(counts, min=1)
    weights = weights / weights.sum() * len(classes)
    criterion = nn.CrossEntropyLoss(weight=weights)
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-3)
    loader = DataLoader(
        TensorDataset(sequence_train, static_train, y_train),
        batch_size=64, shuffle=True, drop_last=True,
        generator=torch.Generator().manual_seed(SEED),
    )
    best_state = copy.deepcopy(model.state_dict())
    best_f1 = -1.0
    wait = 0
    for _ in range(epochs):
        model.train()
        for sequence, static, labels in loader:
            optimizer.zero_grad(set_to_none=True)
            loss = criterion(model(sequence, static), labels)
            loss.backward()
            optimizer.step()
        model.eval()
        with torch.no_grad():
            probabilities = torch.softmax(model(sequence_val, static_val), dim=1).numpy()
        predictions = probabilities.argmax(axis=1)
        macro_f1 = f1_score(y_val.numpy(), predictions, average="macro", zero_division=0)
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

def select_validation_threshold(probabilities, y_val, yes_index):
    best = {"threshold": 0.5, "macro_f1": -1.0}
    for threshold in np.arange(0.20, 0.81, 0.02):
        predictions = np.where(probabilities[:, yes_index] >= threshold, yes_index, 1 - yes_index)
        macro_f1 = f1_score(y_val, predictions, average="macro", zero_division=0)
        if macro_f1 > best["macro_f1"]:
            best = {"threshold": float(threshold), "macro_f1": float(macro_f1)}
    return best

def run_sequence_task(task_name, target, task_train, task_val, task_test):
    tensors, classes = prepare_sequence_tensors(task_train, task_val, task_test, target)
    static_size = tensors["static_train"].shape[1]

    factories = {
        "LSTM": lambda: LSTMClassifier(4, static_size, len(classes)),
        "GRU": lambda: GRUClassifier(4, static_size, len(classes)),
        "1D-CNN": lambda: Conv1DClassifier(4, static_size, len(classes)),
        "TCN": lambda: TCNClassifier(4, static_size, len(classes)),
        "CNN-LSTM": lambda: CNNLSTMClassifier(4, static_size, len(classes)),
        "Transformer Encoder": lambda: TransformerClassifier(4, static_size, len(classes)),
    }
    rows = []
    fitted = {}
    for name, factory in factories.items():
        model = factory()
        model, validation_f1 = train_sequence_model(model, tensors, classes)
        with torch.no_grad():
            val_prob = torch.softmax(
                model(tensors["sequence_val"], tensors["static_val"]), dim=1
            ).numpy()
        val_pred = val_prob.argmax(axis=1)
        scores = evaluate_predictions(tensors["y_val"].numpy(), val_pred)
        rows.append({"Model": name, **{f"Validation {k}": v for k, v in scores.items()},
                     "Validation F1 Macro Internal": validation_f1})
        fitted[name] = model

    comparison = pd.DataFrame(rows).sort_values("Validation macro_f1", ascending=False)
    best_name = comparison.iloc[0]["Model"]
    best = fitted[best_name]

    with torch.no_grad():
        test_prob = torch.softmax(
            best(tensors["sequence_test"], tensors["static_test"]), dim=1
        ).numpy()
    test_predictions = test_prob.argmax(axis=1)
    threshold_info = None
    if task_name == "Volatility":
        yes_index = classes.index("Yes")
        with torch.no_grad():
            val_prob = torch.softmax(
                best(tensors["sequence_val"], tensors["static_val"]), dim=1
            ).numpy()
        threshold_info = select_validation_threshold(val_prob, tensors["y_val"].numpy(), yes_index)
        test_predictions = np.where(
            test_prob[:, yes_index] >= threshold_info["threshold"],
            yes_index,
            1 - yes_index,
        )

    test_scores = evaluate_predictions(
        tensors["y_test"].numpy(),
        test_predictions,
        positive=classes.index("Yes") if task_name == "Volatility" else None,
    )
    if task_name == "Volatility":
        yes_index = classes.index("Yes")
        test_scores["average_precision_yes"] = average_precision_score(
            (tensors["y_test"].numpy() == yes_index).astype(int),
            test_prob[:, yes_index],
        )

    cm = confusion_matrix(
        tensors["y_test"].numpy(),
        test_predictions,
        labels=list(range(len(classes))),
    )
    pd.DataFrame(cm, index=classes, columns=classes).to_csv(
        OUTPUT_DIR / f"{task_name.lower()}_sequence_confusion_matrix.csv"
    )
    comparison.to_csv(OUTPUT_DIR / f"{task_name.lower()}_sequence_validation.csv", index=False)
    summary = {
        "task": task_name,
        "selected_model": best_name,
        "primary_metric": "macro_f1",
        "n_train": len(task_train),
        "n_validation": len(task_val),
        "n_test": len(task_test),
        "classes": classes,
        "threshold": threshold_info,
        **{f"test_{k}": v for k, v in test_scores.items()},
    }
    with open(OUTPUT_DIR / f"{task_name.lower()}_sequence_summary.json", "w") as handle:
        json.dump(summary, handle, indent=2)
    return comparison, summary

direction_sequence_comparison, direction_sequence_summary = run_sequence_task(
    "Direction", "direction_label", train, val, test
)
volatility_sequence_comparison, volatility_sequence_summary = run_sequence_task(
    "Volatility", "volatility_label",
    volatility_train, volatility_val, volatility_test
)
display(direction_sequence_comparison)
display(volatility_sequence_comparison)
""")

markdown("""## 6. Statistical time-series models

These models forecast a time series and are reported separately from event classifiers:

- ARIMA
- GARCH
- EGARCH
- VAR

They are not used to generate Up/Down/Neutral or Yes/No event labels.
""")

code("""try:
    from statsmodels.tsa.arima.model import ARIMA
    from statsmodels.tsa.api import VAR
    HAS_STATSMODELS = True
except Exception:
    HAS_STATSMODELS = False

try:
    from arch import arch_model
    HAS_ARCH = True
except Exception:
    HAS_ARCH = False

print("Statsmodels available:", HAS_STATSMODELS)
print("ARCH available:", HAS_ARCH)

def chronological_series_split(series):
    train_idx = int(len(series) * 0.70)
    val_idx = int(len(series) * 0.85)
    return series.iloc[:train_idx], series.iloc[train_idx:val_idx], series.iloc[val_idx:]

statistical_results = []

stock_history = pd.read_csv(CACHE_DIR / "TITAN_history.csv", parse_dates=["Date"])
stock_series = stock_history.sort_values("Date")["Adj Close"].dropna()
stock_series = stock_series.reset_index(drop=True)
if HAS_STATSMODELS:
    arima_train, arima_val, arima_test = chronological_series_split(stock_series)
    arima = ARIMA(arima_train, order=(5, 1, 0)).fit()
    arima_forecast = np.asarray(arima.forecast(steps=len(arima_test)))
    statistical_results.append({
        "Model": "ARIMA(5,1,0)",
        "Metric": "Stock price MAE",
        "Value": mean_absolute_error(arima_test, arima_forecast),
        "RMSE": float(np.sqrt(mean_squared_error(arima_test, arima_forecast))),
    })

if HAS_ARCH:
    stock_history = stock_history.sort_values("Date").copy()
    returns = stock_history["Adj Close"].pct_change().dropna() * 100
    returns = returns.reset_index(drop=True)
    garch_train, garch_val, garch_test = chronological_series_split(returns)
    estimation = pd.concat([garch_train, garch_val])

    for model_name, volatility_type in [("GARCH", "GARCH"), ("EGARCH", "EGARCH")]:
        model = arch_model(
            estimation,
            mean="Constant",
            vol=volatility_type,
            p=1,
            q=1,
            dist="normal",
        )
        fitted = model.fit(disp="off")
        forecast = fitted.forecast(
            horizon=1,
            start=len(estimation) - len(garch_test),
        )
        forecast_variance = forecast.variance["h.1"].to_numpy(dtype=float)
        realized_variance = garch_test.to_numpy() ** 2
        statistical_results.append({
            "Model": model_name,
            "Metric": "Realized variance MAE",
            "Value": mean_absolute_error(realized_variance, forecast_variance),
            "RMSE": float(np.sqrt(mean_squared_error(realized_variance, forecast_variance))),
        })

if HAS_STATSMODELS:
    market_history = pd.read_csv(CACHE_DIR / "NSEI_history.csv", parse_dates=["Date"])
    stock = stock_history[["Date", "Adj Close"]].rename(columns={"Adj Close": "Stock"})
    market = market_history[["Date", "Adj Close"]].rename(columns={"Adj Close": "Market"})
    combined = stock.merge(market, on="Date", how="inner")
    combined["Stock"] = pd.to_numeric(combined["Stock"], errors="coerce").pct_change()
    combined["Market"] = pd.to_numeric(combined["Market"], errors="coerce").pct_change()
    combined = combined.dropna()[["Stock", "Market"]].reset_index(drop=True)
    var_train, var_val, var_test = chronological_series_split(combined)
    var_model = VAR(var_train)
    var_fitted = var_model.fit(maxlags=2, ic="aic")
    forecasts = var_fitted.forecast(
        y=var_train.iloc[-var_fitted.k_ar:].to_numpy(),
        steps=len(var_test),
    )
    forecasts = pd.DataFrame(forecasts, columns=["Stock", "Market"])
    statistical_results.append({
        "Model": "VAR",
        "Metric": "Joint return MAE",
        "Value": (
            mean_absolute_error(var_test["Stock"], forecasts["Stock"])
            + mean_absolute_error(var_test["Market"], forecasts["Market"])
        ) / 2,
        "RMSE": float(np.sqrt(mean_squared_error(
            var_test[["Stock", "Market"]],
            forecasts,
        ))),
    })

statistical_comparison = pd.DataFrame(statistical_results)
statistical_comparison.to_csv(OUTPUT_DIR / "statistical_models_results.csv", index=False)
display(statistical_comparison)
""")

markdown("""## 7. Unified model comparison

The following table combines event-classification models and separately marks
statistical time-series models.
""")

code("""classification_summary = [
    {"Family": "Traditional", "Task": "Direction", **direction_summary},
    {"Family": "Traditional", "Task": "Volatility", **volatility_summary},
    {"Family": "Sequence Deep Learning", "Task": "Direction", **direction_sequence_summary},
    {"Family": "Sequence Deep Learning", "Task": "Volatility", **volatility_sequence_summary},
]

classification_table = pd.DataFrame(classification_summary)
classification_table.to_csv(OUTPUT_DIR / "unified_classification_summary.csv", index=False)
display(classification_table)

print("Detailed statistical results:")
display(statistical_comparison)

with open(OUTPUT_DIR / "unified_pipeline_summary.json", "w") as handle:
    json.dump({
        "classification": classification_summary,
        "statistical": statistical_comparison.to_dict(orient="records"),
        "split": {
            "train": len(train),
            "validation": len(val),
            "test": len(test),
            "embargo_days": 5,
        },
        "primary_metric": "macro_f1",
        "seed": SEED,
    }, handle, indent=2)
""")

markdown("""## 8. Interpretation

- Macro-F1 is the primary event-classification measure because it avoids giving
  every class equal weight.
- Accuracy is not sufficient for the imbalanced volatility task.
- Yes precision and recall are required for volatility-spike detection.
- Statistical ARIMA/GARCH/EGARCH/VAR outputs use forecasting metrics and must not
  be directly compared with event-classification accuracy or macro-F1.
- Historical weak model performance should be reported honestly as limited predictive
  evidence, not as investment advice.
""")

notebook.cells = cells

output_path = Path("NiftyEvent50_Unified_Model_Pipeline.ipynb")
nbf.write(notebook, output_path)
print(output_path)
