# Deep-Learning Benchmark

This folder contains a separate PyTorch benchmark for NiftyEvent-50. It does not
replace or modify the traditional baseline benchmark.

## Models

- Multilayer perceptron (MLP)
- Residual MLP
- LSTM
- GRU
- 1D-CNN
- Temporal Convolutional Network (TCN)
- CNN-LSTM
- Transformer encoder

Both models use the following verified pre-event features:

- Pre-event adjusted price
- Previous-day return
- 20-session rolling volatility
- Pre-event volume change
- Previous Nifty 50 return
- Previous India VIX percentage change
- Ticker, sector, event type, and filing status

## Validation protocol

- Chronological 70/15/15 split
- Five-calendar-day embargo near split boundaries
- Preprocessing fit only on training data
- Macro-F1 used to select the architecture
- Volatility threshold selected only from validation data
- No test-set model or threshold selection

## Run

```powershell
python -m pip install -r requirements.txt
python deep_learning/run_deep_learning_benchmark.py
python deep_learning/run_sequence_models_benchmark.py
```

The benchmark writes metrics and confusion matrices to `deep_learning/outputs/`.
