import copy
import json
import random
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
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
from torch import nn
from torch.utils.data import DataLoader, TensorDataset


SEED = 42
random.seed(SEED)
np.random.seed(SEED)
torch.manual_seed(SEED)

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "NIFTY_EVENT_50" / "NiftyEvent50_enriched.csv"
WINDOW_DIR = ROOT / "NIFTY_EVENT_50" / "ohlcv_windows"
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


def build_sequence(event_id):
    window_files = list(WINDOW_DIR.glob(f"{event_id}_*.csv"))
    if not window_files:
        return np.zeros((3, 4), dtype=np.float32)
    window = pd.read_csv(window_files[0])
    window = window[window["relative_session"].isin([-3, -2, -1])].sort_values("relative_session")
    if len(window) != 3:
        return np.zeros((3, 4), dtype=np.float32)

    adj_close = pd.to_numeric(window["Adj Close"], errors="coerce").ffill().bfill()
    close = adj_close.to_numpy(dtype=np.float32)
    volume = pd.to_numeric(window["Volume"], errors="coerce").ffill().bfill().to_numpy(dtype=np.float32)
    returns = np.zeros(3, dtype=np.float32)
    if len(close) > 1:
        returns[1:] = np.diff(close) / np.clip(np.abs(close[:-1]), 1e-8, None)
    relative_close = close / max(float(close.mean()), 1e-8)
    volume_ratio = volume / max(float(np.mean(volume)), 1e-8)
    momentum = np.concatenate([[0.0], np.diff(close)])
    return np.column_stack([returns, relative_close, volume_ratio, momentum]).astype(np.float32)


def fit_static_preprocessor(train):
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
    preprocessor.fit(train[CATEGORICAL + NUMERICAL])
    return preprocessor


class LSTMClassifier(nn.Module):
    def __init__(self, sequence_size, static_size, output_size):
        super().__init__()
        self.lstm = nn.LSTM(sequence_size, 64, batch_first=True)
        self.static = nn.Sequential(nn.Linear(static_size, 32), nn.ReLU(), nn.Dropout(0.20))
        self.output = nn.Sequential(nn.Linear(96, 64), nn.ReLU(), nn.Dropout(0.20), nn.Linear(64, output_size))

    def forward(self, sequence, static):
        _, (hidden, _) = self.lstm(sequence)
        combined = torch.cat([hidden[-1], self.static(static)], dim=1)
        return self.output(combined)


class GRUClassifier(nn.Module):
    def __init__(self, sequence_size, static_size, output_size):
        super().__init__()
        self.gru = nn.GRU(sequence_size, 64, batch_first=True)
        self.static = nn.Sequential(nn.Linear(static_size, 32), nn.ReLU(), nn.Dropout(0.20))
        self.output = nn.Sequential(nn.Linear(96, 64), nn.ReLU(), nn.Dropout(0.20), nn.Linear(64, output_size))

    def forward(self, sequence, static):
        _, hidden = self.gru(sequence)
        combined = torch.cat([hidden[-1], self.static(static)], dim=1)
        return self.output(combined)


class Conv1DClassifier(nn.Module):
    def __init__(self, sequence_size, static_size, output_size):
        super().__init__()
        self.conv = nn.Sequential(
            nn.Conv1d(sequence_size, 32, kernel_size=2),
            nn.ReLU(),
            nn.Conv1d(32, 64, kernel_size=2),
            nn.ReLU(),
            nn.AdaptiveAvgPool1d(1),
        )
        self.static = nn.Sequential(nn.Linear(static_size, 32), nn.ReLU(), nn.Dropout(0.20))
        self.output = nn.Sequential(nn.Linear(96, 64), nn.ReLU(), nn.Dropout(0.20), nn.Linear(64, output_size))

    def forward(self, sequence, static):
        features = self.conv(sequence.transpose(1, 2)).squeeze(-1)
        combined = torch.cat([features, self.static(static)], dim=1)
        return self.output(combined)


class TCNClassifier(nn.Module):
    def __init__(self, sequence_size, static_size, output_size):
        super().__init__()
        self.conv1 = nn.Conv1d(sequence_size, 32, kernel_size=2, dilation=1, padding=1)
        self.conv2 = nn.Conv1d(32, 32, kernel_size=2, dilation=2, padding=2)
        self.conv3 = nn.Conv1d(32, 64, kernel_size=2, dilation=4, padding=4)
        self.relu = nn.ReLU()
        self.pool = nn.AdaptiveAvgPool1d(1)
        self.static = nn.Sequential(nn.Linear(static_size, 32), nn.ReLU(), nn.Dropout(0.20))
        self.output = nn.Sequential(nn.Linear(96, 64), nn.ReLU(), nn.Dropout(0.20), nn.Linear(64, output_size))

    def forward(self, sequence, static):
        x = self.relu(self.conv1(sequence.transpose(1, 2)))
        x = self.relu(self.conv2(x))
        x = self.relu(self.conv3(x))
        features = self.pool(x).squeeze(-1)
        combined = torch.cat([features, self.static(static)], dim=1)
        return self.output(combined)


class CNNLSTMClassifier(nn.Module):
    def __init__(self, sequence_size, static_size, output_size):
        super().__init__()
        self.conv = nn.Sequential(
            nn.Conv1d(sequence_size, 32, kernel_size=2),
            nn.ReLU(),
        )
        self.lstm = nn.LSTM(32, 64, batch_first=True)
        self.static = nn.Sequential(nn.Linear(static_size, 32), nn.ReLU(), nn.Dropout(0.20))
        self.output = nn.Sequential(nn.Linear(96, 64), nn.ReLU(), nn.Dropout(0.20), nn.Linear(64, output_size))

    def forward(self, sequence, static):
        convolved = self.conv(sequence.transpose(1, 2)).transpose(1, 2)
        _, (hidden, _) = self.lstm(convolved)
        combined = torch.cat([hidden[-1], self.static(static)], dim=1)
        return self.output(combined)


class TransformerClassifier(nn.Module):
    def __init__(self, sequence_size, static_size, output_size):
        super().__init__()
        self.input = nn.Linear(sequence_size, 64)
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=64,
            nhead=4,
            dim_feedforward=128,
            dropout=0.20,
            batch_first=True,
        )
        self.encoder = nn.TransformerEncoder(encoder_layer, num_layers=2)
        self.static = nn.Sequential(nn.Linear(static_size, 32), nn.ReLU(), nn.Dropout(0.20))
        self.output = nn.Sequential(nn.Linear(96, 64), nn.ReLU(), nn.Dropout(0.20), nn.Linear(64, output_size))

    def forward(self, sequence, static):
        encoded = self.encoder(self.input(sequence)).mean(dim=1)
        combined = torch.cat([encoded, self.static(static)], dim=1)
        return self.output(combined)


def prepare_split(split, preprocessor, labels, sequence_scaler=None):
    static = preprocessor.transform(split[CATEGORICAL + NUMERICAL])
    static = static.toarray() if hasattr(static, "toarray") else np.asarray(static)
    sequences = np.asarray([build_sequence(event_id) for event_id in split["event_id"]], dtype=np.float32)
    if sequence_scaler is not None:
        mean, std = sequence_scaler
        sequences = (sequences - mean) / std
    return sequences, static


def make_tensors(train, val, test, preprocessor, target):
    train_labels = train[target].astype(str).str.strip().str.title()
    val_labels = val[target].astype(str).str.strip().str.title()
    test_labels = test[target].astype(str).str.strip().str.title()
    classes = sorted(train_labels.unique())
    mapping = {label: index for index, label in enumerate(classes)}

    train_sequence_raw = np.asarray([build_sequence(event_id) for event_id in train["event_id"]], dtype=np.float32)
    mean = train_sequence_raw.mean(axis=(0, 1), keepdims=True)
    std = train_sequence_raw.std(axis=(0, 1), keepdims=True)
    std = np.where(std < 1e-8, 1.0, std)
    sequence_scaler = (mean, std)

    train_sequence, train_static = prepare_split(train, preprocessor, classes, sequence_scaler)
    val_sequence, val_static = prepare_split(val, preprocessor, classes, sequence_scaler)
    test_sequence, test_static = prepare_split(test, preprocessor, classes, sequence_scaler)

    y_train = train_labels.map(mapping).to_numpy(dtype=np.int64)
    y_val = val_labels.map(mapping).to_numpy(dtype=np.int64)
    y_test = test_labels.map(mapping).to_numpy(dtype=np.int64)

    return {
        "train": (
            torch.tensor(train_sequence),
            torch.tensor(train_static, dtype=torch.float32),
            torch.tensor(y_train, dtype=torch.long),
        ),
        "val": (
            torch.tensor(val_sequence),
            torch.tensor(val_static, dtype=torch.float32),
            torch.tensor(y_val, dtype=torch.long),
        ),
        "test": (
            torch.tensor(test_sequence),
            torch.tensor(test_static, dtype=torch.float32),
            torch.tensor(y_test, dtype=torch.long),
        ),
    }, classes


def train_model(model, data, val_data, classes, epochs=70, patience=10):
    sequence_train, static_train, y_train = data
    sequence_val, static_val, y_val = val_data
    counts = torch.bincount(y_train, minlength=len(classes)).float()
    weights = counts.sum() / torch.clamp(counts, min=1)
    weights = weights / weights.sum() * len(classes)
    criterion = nn.CrossEntropyLoss(weight=weights)
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-3)
    loader = DataLoader(
        TensorDataset(sequence_train, static_train, y_train),
        batch_size=64,
        shuffle=True,
        drop_last=True,
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


def fit_retrained_model(model, data, classes, epochs=50):
    sequence, static, labels = data
    counts = torch.bincount(labels, minlength=len(classes)).float()
    weights = counts.sum() / torch.clamp(counts, min=1)
    weights = weights / weights.sum() * len(classes)
    criterion = nn.CrossEntropyLoss(weight=weights)
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-3)
    loader = DataLoader(
        TensorDataset(sequence, static, labels),
        batch_size=64,
        shuffle=True,
        drop_last=True,
        generator=torch.Generator().manual_seed(SEED),
    )
    model.train()
    for _ in range(epochs):
        for sequence_batch, static_batch, labels_batch in loader:
            optimizer.zero_grad(set_to_none=True)
            loss = criterion(model(sequence_batch, static_batch), labels_batch)
            loss.backward()
            optimizer.step()
    model.eval()
    return model


def probabilities(model, sequence, static):
    model.eval()
    with torch.no_grad():
        return torch.softmax(model(sequence, static), dim=1).numpy()


def select_volatility_threshold(probabilities, y_val, yes_index):
    best = {"threshold": 0.5, "macro_f1": -1.0}
    for threshold in np.arange(0.20, 0.81, 0.02):
        predictions = np.where(probabilities[:, yes_index] >= threshold, yes_index, 1 - yes_index)
        macro_f1 = f1_score(y_val, predictions, average="macro", zero_division=0)
        if macro_f1 > best["macro_f1"]:
            best = {"threshold": float(threshold), "macro_f1": float(macro_f1)}
    return best


def run_task(task_name, target, train, val, test, output_dir):
    preprocessor = fit_static_preprocessor(train)
    tensors, classes = make_tensors(train, val, test, preprocessor, target)
    sequence_train, static_train, y_train = tensors["train"]
    sequence_val, static_val, y_val = tensors["val"]
    sequence_test, static_test, y_test = tensors["test"]

    factories = {
        "LSTM": lambda: LSTMClassifier(4, static_train.shape[1], len(classes)),
        "GRU": lambda: GRUClassifier(4, static_train.shape[1], len(classes)),
        "1D-CNN": lambda: Conv1DClassifier(4, static_train.shape[1], len(classes)),
        "TCN": lambda: TCNClassifier(4, static_train.shape[1], len(classes)),
        "CNN-LSTM": lambda: CNNLSTMClassifier(4, static_train.shape[1], len(classes)),
        "Transformer": lambda: TransformerClassifier(4, static_train.shape[1], len(classes)),
    }

    rows = []
    best_name = None
    best_model = None
    best_f1 = -1.0

    for model_name, factory in factories.items():
        model = factory()
        model, validation_f1 = train_model(
            model,
            tensors["train"],
            tensors["val"],
            classes,
        )
        val_probabilities = probabilities(model, sequence_val, static_val)
        val_predictions = val_probabilities.argmax(axis=1)
        row = {
            "Model": model_name,
            "Validation Accuracy": accuracy_score(y_val.numpy(), val_predictions),
            "Validation Balanced Accuracy": balanced_accuracy_score(y_val.numpy(), val_predictions),
            "Validation Precision Macro": precision_score(y_val.numpy(), val_predictions, average="macro", zero_division=0),
            "Validation Recall Macro": recall_score(y_val.numpy(), val_predictions, average="macro", zero_division=0),
            "Validation F1 Macro": f1_score(y_val.numpy(), val_predictions, average="macro", zero_division=0),
        }
        rows.append(row)
        if validation_f1 > best_f1:
            best_f1 = validation_f1
            best_name = model_name
            best_model = copy.deepcopy(model)

    comparison = pd.DataFrame(rows).sort_values("Validation F1 Macro", ascending=False)
    comparison.to_csv(output_dir / f"{task_name.lower()}_sequence_models_validation.csv", index=False)

    retrain_sequence = torch.cat([sequence_train, sequence_val])
    retrain_static = torch.cat([static_train, static_val])
    retrain_labels = torch.cat([y_train, y_val])
    retrained_model = fit_retrained_model(
        factories[best_name](),
        (retrain_sequence, retrain_static, retrain_labels),
        classes,
    )

    test_probabilities = probabilities(retrained_model, sequence_test, static_test)
    threshold = None
    if task_name == "Volatility":
        yes_index = classes.index("Yes")
        val_probabilities = probabilities(best_model, sequence_val, static_val)
        threshold = select_volatility_threshold(val_probabilities, y_val.numpy(), yes_index)
        test_predictions = np.where(
            test_probabilities[:, yes_index] >= threshold["threshold"],
            yes_index,
            1 - yes_index,
        )
    else:
        test_predictions = test_probabilities.argmax(axis=1)

    y_test_array = y_test.numpy()
    cm = confusion_matrix(y_test_array, test_predictions, labels=list(range(len(classes))))
    pd.DataFrame(cm, index=classes, columns=classes).to_csv(
        output_dir / f"{task_name.lower()}_sequence_models_test_confusion_matrix.csv"
    )
    pd.DataFrame(
        classification_report(
            y_test_array,
            test_predictions,
            target_names=classes,
            output_dict=True,
            zero_division=0,
        )
    ).transpose().to_csv(output_dir / f"{task_name.lower()}_sequence_models_test_report.csv")

    summary = {
        "selected_model": best_name,
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
        "class_names": classes,
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

    with open(output_dir / f"{task_name.lower()}_sequence_models_test_summary.json", "w") as handle:
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
    available_ids = set(df.loc[available, "event_id"])
    volatility_train = train[train["event_id"].isin(available_ids)]
    volatility_val = val[val["event_id"].isin(available_ids)]
    volatility_test = test[test["event_id"].isin(available_ids)]
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
        "models": ["LSTM", "GRU", "1D-CNN", "TCN", "CNN-LSTM", "Transformer"],
        "sequence_window": ["T-3", "T-2", "T-1"],
        "seed": SEED,
        "device": "cpu",
    }
    with open(OUTPUT_DIR / "sequence_models_summary.json", "w") as handle:
        json.dump(summary, handle, indent=2)
    print(direction_comparison.to_string(index=False))
    print(volatility_comparison.to_string(index=False))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
