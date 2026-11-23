# Comparative and Statistical Benchmarks

This folder separates event-classification algorithms from statistical time-series
models.

## Classification models

- Random Forest
- XGBoost
- CatBoost
- SVM
- Logistic Regression

These models use the same chronological purged protocol and macro-F1 selection
used by the main benchmark.

## Statistical models

- ARIMA: stock-price forecast baseline
- GARCH: return variance forecast baseline
- EGARCH: asymmetric return variance forecast baseline
- VAR: joint stock-and-market return forecast baseline

Statistical models are not used as direction or volatility classifiers. They provide
separate time-series forecasting evidence.

## Run

```powershell
python -m pip install -r comparative_benchmarks/requirements.txt
python comparative_benchmarks/run_classification_models.py
python comparative_benchmarks/run_statistical_models.py
```
