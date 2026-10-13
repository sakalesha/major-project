"""
NiftyEvent-50: Step 4 Label Computation Pipeline
Author: Antigravity Team
Description:
    Computes price shock percentages, direction labels (Up / Down / Neutral),
    historical 30-day baseline return volatility (T-33 to T-4), 8-day event window
    volatility (T-3 to T+5), and volatility spike flags (Yes / No).
"""

import os
import argparse
import pandas as pd
import numpy as np


def compute_labels(
    windows_summary_path: str = "intermediate_windows_summary.csv",
    cache_dir: str = "cache",
    windows_dir: str = "ohlcv_windows",
    output_path: str = "candidate_labeled_events.csv"
):
    if not os.path.exists(windows_summary_path):
        raise FileNotFoundError(f"Missing {windows_summary_path}. Run ohlcv_fetch.py first.")

    df_summary = pd.read_csv(windows_summary_path)
    print(f"[*] Loaded {len(df_summary)} events from {windows_summary_path}")

    # Load cached full histories for baseline volatility calculation
    ticker_histories = {}
    for ticker in df_summary["ticker"].unique():
        clean_sym = ticker.replace(".NS", "").strip()
        hist_path = os.path.join(cache_dir, f"{clean_sym}_history.csv")
        if os.path.exists(hist_path):
            hist = pd.read_csv(hist_path, parse_dates=["Date"])
            hist["Date"] = pd.to_datetime(hist["Date"]).dt.tz_localize(None).dt.normalize()
            hist = hist.sort_values(by="Date").reset_index(drop=True)
            ticker_histories[ticker] = hist
        else:
            print(f"[-] Warning: Cache file missing for {ticker} at {hist_path}")

    labeled_records = []
    insufficient_history_count = 0

    for idx, row in df_summary.iterrows():
        eid = row["event_id"]
        ticker = row["ticker"]
        pre_price = float(row["pre_event_price"])
        post_price = float(row["post_event_price"])
        t0_str = row["effective_t0"]
        t0_date = pd.to_datetime(t0_str).normalize()

        # 1. Price Shock %
        if pre_price <= 0:
            shock_pct = 0.0
        else:
            shock_pct = round(((post_price - pre_price) / pre_price) * 100.0, 2)

        # 2. Direction Label (+-0.5% threshold)
        if shock_pct > 0.5:
            direction_label = "Up"
        elif shock_pct < -0.5:
            direction_label = "Down"
        else:
            direction_label = "Neutral"

        # 3. Volatility Calculations
        hist = ticker_histories.get(ticker)
        vol_label = "No"
        sigma_baseline = np.nan
        sigma_window = np.nan

        if hist is not None and not hist.empty:
            trading_dates = hist["Date"].tolist()
            if t0_date in trading_dates:
                t0_idx = trading_dates.index(t0_date)

                # Baseline: 30 sessions strictly prior to the 8-day window (T-33 to T-4)
                if t0_idx >= 34:
                    baseline_slice = hist.iloc[t0_idx - 34 : t0_idx - 3].copy()
                    price_col = "Adj Close" if "Adj Close" in baseline_slice.columns else "Close"
                    baseline_returns = baseline_slice[price_col].pct_change().dropna()
                    if len(baseline_returns) >= 20:
                        sigma_baseline = baseline_returns.std()

                # Event window volatility: 8 trading sessions around T0 (T-3 to T+5)
                if t0_idx >= 3 and (t0_idx + 5) < len(trading_dates):
                    window_slice = hist.iloc[t0_idx - 3 : t0_idx + 6].copy()
                    price_col = "Adj Close" if "Adj Close" in window_slice.columns else "Close"
                    window_returns = window_slice[price_col].pct_change().dropna()
                    if len(window_returns) >= 5:
                        sigma_window = window_returns.std()

                # Volatility spike evaluation
                if pd.notnull(sigma_baseline) and pd.notnull(sigma_window) and sigma_baseline > 0:
                    if sigma_window > (1.5 * sigma_baseline):
                        vol_label = "Yes"
                    else:
                        vol_label = "No"
                else:
                    insufficient_history_count += 1
                    vol_label = "No"

        labeled_records.append({
            "event_id": eid,
            "ticker": ticker,
            "raw_symbol": row.get("raw_symbol", ticker.replace(".NS", "")),
            "date": row["date"],
            "broadcast_datetime": row["broadcast_datetime"],
            "effective_t0": t0_str,
            "event_type": row["event_type"],
            "filing_subject": row.get("filing_subject", ""),
            "is_primary_filing": row.get("is_primary_filing", True),
            "pre_event_price": pre_price,
            "post_event_price": post_price,
            "shock_pct": shock_pct,
            "volatility_label": vol_label,
            "direction_label": direction_label,
            "sigma_baseline": round(float(sigma_baseline), 6) if pd.notnull(sigma_baseline) else None,
            "sigma_window": round(float(sigma_window), 6) if pd.notnull(sigma_window) else None
        })

    df_labeled = pd.DataFrame(labeled_records)
    df_labeled.to_csv(output_path, index=False)
    print(f"[OK] Successfully computed labels for {len(df_labeled)} events.")
    print(f"[OK] Saved candidate dataset to {output_path}")

    if insufficient_history_count > 0:
        print(f"[*] Note: {insufficient_history_count} events had limited historical lookback (<30 sessions prior, defaulted volatility_label='No').")

    print("\n--- Direction Label Distribution ---")
    print(df_labeled["direction_label"].value_counts(normalize=True).mul(100).round(2).astype(str) + "%")
    print(df_labeled["direction_label"].value_counts())

    print("\n--- Volatility Label Distribution ---")
    print(df_labeled["volatility_label"].value_counts(normalize=True).mul(100).round(2).astype(str) + "%")
    print(df_labeled["volatility_label"].value_counts())

    print("\n--- Price Shock Summary Statistics ---")
    print(df_labeled["shock_pct"].describe().round(2))

    return df_labeled


def main():
    parser = argparse.ArgumentParser(description="Compute price shock and volatility labels.")
    parser.add_argument("--summary", default="intermediate_windows_summary.csv", help="Intermediate window summary CSV")
    parser.add_argument("--cache-dir", default="cache", help="Cache directory for full price histories")
    parser.add_argument("--windows-dir", default="ohlcv_windows", help="OHLCV windows directory")
    parser.add_argument("--output", default="candidate_labeled_events.csv", help="Output candidate labeled events CSV")
    args = parser.parse_args()

    compute_labels(
        windows_summary_path=args.summary,
        cache_dir=args.cache_dir,
        windows_dir=args.windows_dir,
        output_path=args.output
    )


if __name__ == "__main__":
    main()
