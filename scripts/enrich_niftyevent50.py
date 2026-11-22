import os
import argparse
import pandas as pd
import numpy as np
import yfinance as yf


def download_index(symbol, cache_dir, start, end):
    cache_file = os.path.join(cache_dir, f"{symbol.replace('^', '')}_history.csv")
    if os.path.exists(cache_file):
        try:
            df = pd.read_csv(cache_file, parse_dates=["Date"])
            if len(df) > 100:
                return df.sort_values("Date").reset_index(drop=True)
        except Exception:
            pass

    df = yf.Ticker(symbol).history(start=start, end=end, auto_adjust=False)
    if df.empty:
        return None
    df = df.reset_index()
    df["Date"] = pd.to_datetime(df["Date"]).dt.tz_localize(None).dt.normalize()
    df.to_csv(cache_file, index=False)
    return df.sort_values("Date").reset_index(drop=True)


def align_history(hist):
    hist = hist.copy()
    hist["Date"] = pd.to_datetime(hist["Date"]).dt.tz_localize(None).dt.normalize()
    for column in ("Adj Close", "Close"):
        if column in hist.columns:
            hist[column] = pd.to_numeric(hist[column], errors="coerce")
    if "Volume" in hist.columns:
        hist["Volume"] = pd.to_numeric(hist["Volume"], errors="coerce")
    return hist.sort_values("Date").reset_index(drop=True)


def add_stock_features(row, hist, index_hist, vix_hist):
    result = {}
    if hist is None or hist.empty:
        return result
    hist = align_history(hist)
    price_col = "Adj Close" if "Adj Close" in hist.columns else "Close"
    trading_dates = hist["Date"].tolist()
    t0 = pd.to_datetime(row["effective_t0"]).normalize()
    if t0 not in trading_dates:
        return result

    t0_idx = trading_dates.index(t0)
    hist["daily_return"] = hist[price_col].pct_change()

    if t0_idx >= 2:
        previous = float(hist.iloc[t0_idx - 1]["daily_return"])
        result["pre_event_return"] = previous if np.isfinite(previous) else np.nan
    if t0_idx >= 21:
        volatility = hist.iloc[t0_idx - 21:t0_idx - 1]["daily_return"].std()
        result["pre_event_volatility"] = float(volatility) if pd.notnull(volatility) else np.nan
    if t0_idx >= 21 and "Volume" in hist.columns:
        volume_today = float(hist.iloc[t0_idx - 1]["Volume"])
        median_volume = float(hist.iloc[t0_idx - 21:t0_idx - 1]["Volume"].median())
        if median_volume > 0:
            result["pre_event_volume_change"] = volume_today / median_volume - 1.0

    if index_hist is not None and not index_hist.empty:
        index_hist = align_history(index_hist)
        if "Adj Close" not in index_hist.columns and "Close" in index_hist.columns:
            index_hist["Adj Close"] = index_hist["Close"]
        index_hist["daily_return"] = index_hist["Adj Close"].pct_change()
        market_map = dict(zip(index_hist["Date"], index_hist["daily_return"]))
        result["nifty50_return"] = market_map.get(t0, np.nan)
        if t0_idx >= 2:
            t1 = trading_dates[t0_idx - 1]
            result["nifty50_prev_day_return"] = market_map.get(t1, np.nan)

    if vix_hist is not None and not vix_hist.empty:
        vix_hist = align_history(vix_hist)
        if "Adj Close" not in vix_hist.columns and "Close" in vix_hist.columns:
            vix_hist["Adj Close"] = vix_hist["Close"]
        vix_hist["pct_change"] = vix_hist["Adj Close"].pct_change()
        vix_map = dict(zip(vix_hist["Date"], vix_hist["pct_change"]))
        if t0_idx >= 2:
            t1 = trading_dates[t0_idx - 1]
            result["india_vix_pct_change"] = vix_map.get(t1, np.nan)

    if index_hist is not None and not index_hist.empty:
        index_hist = align_history(index_hist)
        index_price_col = "Adj Close" if "Adj Close" in index_hist.columns else "Close"
        index_hist["market_return"] = index_hist[index_price_col].pct_change()
        combined = pd.DataFrame({
            "Date": hist["Date"],
            "stock_return": hist["daily_return"],
        }).merge(index_hist[["Date", "market_return"]], on="Date", how="inner").dropna()

        estimation = combined[(combined["Date"] < t0 - pd.Timedelta(days=6)) &
                              (combined["Date"] >= t0 - pd.Timedelta(days=180))]
        if len(estimation) >= 30:
            rm = estimation["market_return"]
            rs = estimation["stock_return"]
            beta = np.cov(rs, rm, ddof=1)[0, 1] / np.var(rm, ddof=1)
            alpha = rs.mean() - beta * rm.mean()

            event_window = combined[(combined["Date"] >= trading_dates[max(0, t0_idx - 3)]) &
                                    (combined["Date"] <= trading_dates[min(len(trading_dates) - 1, t0_idx + 5)])].copy()
            event_window["abnormal_return"] = event_window["stock_return"] - (
                alpha + beta * event_window["market_return"]
            )
            if not event_window.empty:
                result["abnormal_return"] = float(event_window.iloc[0]["abnormal_return"])
                result["car"] = float(event_window["abnormal_return"].sum())

    return result


def enrich(input_path, output_path, cache_dir, end_date):
    df = pd.read_csv(input_path)
    df["effective_t0"] = pd.to_datetime(df["effective_t0"], errors="coerce").dt.strftime("%Y-%m-%d")
    os.makedirs(cache_dir, exist_ok=True)

    index_hist = download_index("^NSEI", cache_dir, "2017-01-01", end_date)
    vix_hist = download_index("^INDIAVIX", cache_dir, "2017-01-01", end_date)

    enriched = []
    for _, row in df.iterrows():
        ticker = str(row["ticker"])
        clean = ticker.replace(".NS", "")
        stock_path = os.path.join(cache_dir, f"{clean}_history.csv")
        hist = pd.read_csv(stock_path, parse_dates=["Date"]) if os.path.exists(stock_path) else None
        features = add_stock_features(row, hist, index_hist, vix_hist)
        enriched.append(features)

    feature_df = pd.DataFrame(enriched)
    df = pd.concat([df.reset_index(drop=True), feature_df], axis=1)

    for threshold in (1.25, 1.5, 2.0):
        df[f"volatility_label_{threshold:g}"] = np.select(
            [
                df["sigma_baseline"].notna() & df["sigma_window"].notna() &
                (df["sigma_baseline"] > 0),
            ],
            [
                np.where(df["sigma_window"] > threshold * df["sigma_baseline"], "Yes", "No")
            ],
            default="Unknown",
        )

    df["volatility_label_status"] = np.where(
        df["sigma_baseline"].notna() & df["sigma_window"].notna(),
        "Available",
        "Unknown",
    )

    raw_path = os.path.join(os.path.dirname(input_path), "raw_events.csv")
    if os.path.exists(raw_path):
        raw = pd.read_csv(raw_path)
        raw = raw.rename(columns={
            "attachment_url": "source_url",
            "filing_subject": "raw_subject",
            "details": "event_description",
        })
        raw = raw[[ "event_id", "source_url", "raw_subject", "event_description",
                    "broadcast_datetime", "ticker", "event_type" ]]
        df = df.merge(raw, on=["event_id", "ticker", "event_type"], how="left",
                      suffixes=("", "_raw"))

        cluster_df = raw.sort_values(["ticker", "event_type", "broadcast_datetime"])
        cluster_ids = {}
        for (ticker, event_type), group in cluster_df.groupby(["ticker", "event_type"], sort=False):
            last_time = None
            cluster_number = 0
            for _, row in group.iterrows():
                current = pd.to_datetime(row["broadcast_datetime"], errors="coerce")
                if last_time is None or (current - last_time).total_seconds() / 86400 > 2:
                    cluster_number += 1
                cluster_ids[row["event_id"]] = f"{ticker}-{event_type}-{cluster_number}"
                last_time = current
        df["event_cluster_id"] = df["event_id"].map(cluster_ids)

    df.to_csv(output_path, index=False)
    print(f"Saved {len(df)} enriched events to {output_path}")
    print("Missing baseline/window:", int((df["volatility_label_status"] == "Unknown").sum()))


def main():
    parser = argparse.ArgumentParser()
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    release_dir = os.path.join(root, "NIFTY_EVENT_50")
    parser.add_argument("--input", default=os.path.join(release_dir, "candidate_labeled_events.csv"))
    parser.add_argument("--output", default=os.path.join(release_dir, "NiftyEvent50_enriched.csv"))
    parser.add_argument("--cache-dir", default=os.path.join(release_dir, "cache"))
    parser.add_argument("--end-date", default="2025-02-01")
    args = parser.parse_args()
    enrich(args.input, args.output, args.cache_dir, args.end_date)


if __name__ == "__main__":
    main()
