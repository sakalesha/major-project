import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error

from statsmodels.tsa.arima.model import ARIMA
from statsmodels.tsa.api import VAR
from arch import arch_model


ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / "NIFTY_EVENT_50" / "cache"
OUTPUT_DIR = Path(__file__).resolve().parent / "outputs"


def rmse(y_true, y_pred):
    return float(np.sqrt(mean_squared_error(y_true, y_pred)))


def chronological_series_split(series):
    split = int(len(series) * 0.70)
    val_split = int(len(series) * 0.85)
    return series.iloc[:split], series.iloc[split:val_split], series.iloc[val_split:]


def run_arima(stock_history):
    stock_history = stock_history.sort_values("Date").copy()
    stock_history["Adj Close"] = pd.to_numeric(stock_history["Adj Close"], errors="coerce")
    series = stock_history.set_index("Date")["Adj Close"].dropna()
    series = series.reset_index(drop=True)
    train, val, test = chronological_series_split(series)
    model = ARIMA(train, order=(5, 1, 0)).fit()
    forecast = model.forecast(steps=len(test))
    forecast = pd.Series(np.asarray(forecast), index=test.index)
    return {
        "model": "ARIMA",
        "order": [5, 1, 0],
        "test_mae": mean_absolute_error(test, forecast),
        "test_rmse": rmse(test, forecast),
        "test_direction_accuracy": float(
            np.mean(
                np.sign(test.diff().fillna(0).values)
                == np.sign(pd.Series(forecast).diff().fillna(0).values)
            )
        ),
    }


def run_garch(stock_history, model_type):
    stock_history = stock_history.sort_values("Date").copy()
    stock_history["Adj Close"] = pd.to_numeric(stock_history["Adj Close"], errors="coerce")
    returns = stock_history.set_index("Date")["Adj Close"].pct_change().dropna() * 100
    returns = returns.reset_index(drop=True)
    train, val, test = chronological_series_split(returns)
    estimation = pd.concat([train, val])
    if model_type == "GARCH":
        model = arch_model(estimation, mean="Constant", vol="GARCH", p=1, q=1, dist="normal")
    else:
        model = arch_model(estimation, mean="Constant", vol="EGARCH", p=1, q=1, dist="normal")
    fitted = model.fit(disp="off")
    variance_forecast = fitted.forecast(horizon=1, start=len(estimation) - len(test))
    forecast_variance = variance_forecast.variance["h.1"].to_numpy(dtype=float)
    realized_variance = test.to_numpy() ** 2
    return {
        "model": model_type,
        "test_variance_mae": mean_absolute_error(realized_variance, forecast_variance),
        "test_variance_rmse": rmse(realized_variance, forecast_variance),
    }


def run_var(stock_history, market_history):
    stock_history = stock_history.sort_values("Date").copy()
    market_history = market_history.sort_values("Date").copy()
    stock = stock_history[["Date", "Adj Close"]].rename(columns={"Adj Close": "Stock"})
    market = market_history[["Date", "Adj Close"]].rename(columns={"Adj Close": "Market"})
    combined = stock.merge(market, on="Date", how="inner")
    combined["Stock"] = pd.to_numeric(combined["Stock"], errors="coerce").pct_change()
    combined["Market"] = pd.to_numeric(combined["Market"], errors="coerce").pct_change()
    combined = combined.dropna().set_index("Date")
    train, val, test = chronological_series_split(combined)
    model = VAR(train)
    fitted = model.fit(maxlags=2, ic="aic")
    lagged = train.iloc[-fitted.k_ar:].to_numpy()
    forecasts = fitted.forecast(y=lagged, steps=len(test))
    forecast_frame = pd.DataFrame(forecasts, columns=combined.columns, index=test.index)
    return {
        "model": "VAR",
        "lags": int(fitted.k_ar),
        "stock_mae": mean_absolute_error(test["Stock"], forecast_frame["Stock"]),
        "stock_rmse": rmse(test["Stock"], forecast_frame["Stock"]),
        "market_mae": mean_absolute_error(test["Market"], forecast_frame["Market"]),
        "market_rmse": rmse(test["Market"], forecast_frame["Market"]),
    }


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stock_path = CACHE_DIR / "TITAN_history.csv"
    market_path = CACHE_DIR / "NSEI_history.csv"
    stock_history = pd.read_csv(stock_path, parse_dates=["Date"])
    market_history = pd.read_csv(market_path, parse_dates=["Date"])

    results = []
    results.append(run_arima(stock_history))
    results.append(run_garch(stock_history, "GARCH"))
    results.append(run_garch(stock_history, "EGARCH"))
    results.append(run_var(stock_history, market_history))

    pd.DataFrame(results).to_csv(OUTPUT_DIR / "statistical_models_results.csv", index=False)
    with open(OUTPUT_DIR / "statistical_models_summary.json", "w") as handle:
        json.dump({"results": results}, handle, indent=2)
    print(pd.DataFrame(results).to_string(index=False))


if __name__ == "__main__":
    main()
