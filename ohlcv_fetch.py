"""
NiftyEvent-50: Step 3 OHLCV Market Data Fetch & Session Alignment Pipeline
Author: Antigravity Team
Description:
    Downloads historical OHLCV data for all 50 tickers via yfinance, caches history locally,
    applies the corrected T0 session alignment rule (pre-09:15 on trading days trades same-day,
    after-15:30 and weekends trade next day), extracts 3 prior and 5 subsequent sessions,
    persists individual window CSVs, and computes pre_event_price and post_event_price.
"""

import os
import argparse
import pandas as pd
import numpy as np
import yfinance as yf


def ensure_dirs(dirs):
    for d in dirs:
        os.makedirs(d, exist_ok=True)


def download_ticker_history(ticker: str, cache_dir: str = "cache", start_date: str = "2017-01-01", end_date: str = "2025-02-01"):
    """
    Downloads and caches daily OHLCV history for a ticker using yfinance.
    Uses Adj Close for price calculations to eliminate corporate action distortions.
    """
    clean_sym = ticker.replace(".NS", "").strip()
    cache_file = os.path.join(cache_dir, f"{clean_sym}_history.csv")
    if os.path.exists(cache_file):
        try:
            df = pd.read_csv(cache_file, parse_dates=["Date"])
            if len(df) > 50:
                return df
        except Exception:
            pass

    yf_symbol = f"{clean_sym}.NS"
    print(f"[*] Downloading market history for {yf_symbol}...")
    try:
        t = yf.Ticker(yf_symbol)
        df = t.history(start=start_date, end=end_date, auto_adjust=False)
        if df.empty:
            df = yf.download(yf_symbol, start=start_date, end=end_date, progress=False, auto_adjust=False)
        
        if df.empty:
            print(f"[-] Warning: No data returned for {yf_symbol}")
            return None

        df = df.reset_index()
        if "Date" in df.columns:
            df["Date"] = pd.to_datetime(df["Date"]).dt.tz_localize(None).dt.normalize()
        
        col_rename = {c: c.title() for c in df.columns}
        if "Adj Close" in df.columns:
            col_rename["Adj Close"] = "Adj Close"
        df = df.rename(columns=col_rename)

        df.to_csv(cache_file, index=False)
        return df
    except Exception as e:
        print(f"[-] Error fetching {yf_symbol}: {e}")
        return None


def determine_effective_t0(broadcast_dt_str: str, trading_dates: list):
    """
    Applies the corrected frozen T0 rule:
    - Broadcast on a trading weekday before or during market close (<= 15:30 IST):
      Both pre-market (e.g. 08:30 IST) and market-hours (09:15-15:30 IST) announcements
      are traded on the SAME DAY (calendar_date).
    - Broadcast after 15:30 IST on a weekday, or on a weekend/holiday:
      Market is closed; first opportunity to react is strictly the NEXT active trading day.
    """
    try:
        dt = pd.to_datetime(broadcast_dt_str)
    except Exception:
        return None

    calendar_date = dt.normalize()
    is_weekend = dt.weekday() >= 5

    # Announcements before or at 15:30 IST on a weekday:
    if not is_weekend and (dt.hour < 15 or (dt.hour == 15 and dt.minute <= 30)):
        if calendar_date in trading_dates:
            return calendar_date
        # If today was an exchange holiday, advance to next trading day
        next_days = [d for d in trading_dates if d >= calendar_date]
        return next_days[0] if next_days else None
    else:
        # After 15:30 IST or on weekend: market has closed; advance to strictly NEXT trading day
        next_days = [d for d in trading_dates if d > calendar_date]
        return next_days[0] if next_days else None


def fetch_all_windows(
    raw_events_path: str = "raw_events.csv",
    cache_dir: str = "cache",
    windows_dir: str = "ohlcv_windows",
    output_summary_path: str = "intermediate_windows_summary.csv",
    reports_dir: str = "reports"
):
    ensure_dirs([cache_dir, windows_dir, reports_dir])

    if not os.path.exists(raw_events_path):
        raise FileNotFoundError(f"Missing {raw_events_path}. Run scraper.py first.")

    df_events = pd.read_csv(raw_events_path)
    print(f"[*] Loaded {len(df_events)} events from {raw_events_path}")

    # Unique tickers (clean symbol for caching)
    unique_tickers = df_events["ticker"].unique()
    print(f"[*] Found {len(unique_tickers)} unique tickers. Loading/updating caches...")

    ticker_histories = {}
    for ticker in sorted(unique_tickers):
        clean_sym = ticker.replace(".NS", "").strip()
        hist = download_ticker_history(clean_sym, cache_dir)
        if hist is not None and not hist.empty:
            ticker_histories[ticker] = hist
        else:
            print(f"[-] Warning: Failed to retrieve history for {ticker}")

    print(f"[OK] Market history available for {len(ticker_histories)}/{len(unique_tickers)} tickers.")

    # Process each event
    print(f"[*] Slicing 3-prior and 5-subsequent trading session windows (9-row windows including T0)...")
    
    event_summaries = []
    failures = []

    for idx, row in df_events.iterrows():
        eid = row["event_id"]
        ticker = row["ticker"]
        bcast = row["broadcast_datetime"]
        ann_date = row["date"]

        if ticker not in ticker_histories:
            failures.append({
                "event_id": eid, "ticker": ticker, "date": ann_date,
                "reason": "Missing price history for ticker"
            })
            continue

        hist = ticker_histories[ticker].copy()
        hist = hist.sort_values(by="Date").reset_index(drop=True)
        trading_dates = hist["Date"].tolist()

        t0 = determine_effective_t0(bcast, trading_dates)
        if t0 is None or t0 not in trading_dates:
            failures.append({
                "event_id": eid, "ticker": ticker, "date": ann_date,
                "reason": f"Unable to align T0 for broadcast time {bcast}"
            })
            continue

        t0_idx = trading_dates.index(t0)

        # Require at least 3 sessions prior and 5 sessions post
        if t0_idx < 3:
            failures.append({
                "event_id": eid, "ticker": ticker, "date": ann_date,
                "reason": f"Insufficient prior trading sessions (index={t0_idx})"
            })
            continue

        if (t0_idx + 5) >= len(trading_dates):
            failures.append({
                "event_id": eid, "ticker": ticker, "date": ann_date,
                "reason": f"Insufficient subsequent trading sessions ({len(trading_dates) - t0_idx - 1} available)"
            })
            continue

        # Extract 9 trading sessions: T-3, T-2, T-1, T0, T+1, T+2, T+3, T+4, T+5
        window_df = hist.iloc[t0_idx - 3 : t0_idx + 6].copy()
        window_df["event_id"] = eid
        window_df["relative_session"] = [-3, -2, -1, 0, 1, 2, 3, 4, 5]

        price_col = "Adj Close" if "Adj Close" in window_df.columns else "Close"

        if window_df[price_col].isnull().sum() > 2:
            failures.append({
                "event_id": eid, "ticker": ticker, "date": ann_date,
                "reason": f"Too many missing prices in window ({window_df[price_col].isnull().sum()} missing)"
            })
            continue

        window_df[price_col] = window_df[price_col].ffill().bfill()

        # Pre-event: average of sessions -3, -2, -1 (3 sessions)
        pre_prices = window_df[window_df["relative_session"].isin([-3, -2, -1])][price_col]
        # Post-event: average of sessions +1, +2, +3, +4, +5 (5 sessions)
        post_prices = window_df[window_df["relative_session"].isin([1, 2, 3, 4, 5])][price_col]

        pre_mean = round(float(pre_prices.mean()), 2)
        post_mean = round(float(post_prices.mean()), 2)

        # Save individual 9-session window file
        window_filename = f"{eid}_{ticker.replace('.NS', '')}.csv"
        window_file_path = os.path.join(windows_dir, window_filename)
        window_df.to_csv(window_file_path, index=False)

        event_summaries.append({
            "event_id": eid,
            "ticker": ticker,
            "raw_symbol": row.get("raw_symbol", ticker.replace(".NS", "")),
            "date": ann_date,
            "broadcast_datetime": bcast,
            "effective_t0": t0.strftime("%Y-%m-%d"),
            "event_type": row["event_type"],
            "filing_subject": row.get("filing_subject", ""),
            "is_primary_filing": row.get("is_primary_filing", True),
            "pre_event_price": pre_mean,
            "post_event_price": post_mean,
            "window_file": window_filename
        })

    df_summary = pd.DataFrame(event_summaries)
    df_summary.to_csv(output_summary_path, index=False)
    print(f"[OK] Successfully extracted windows for {len(df_summary)} / {len(df_events)} events.")
    print(f"[OK] Saved intermediate window summary to {output_summary_path}")

    df_failures = pd.DataFrame(failures)
    fail_report_path = os.path.join(reports_dir, "retrieval_failures.csv")
    df_failures.to_csv(fail_report_path, index=False)
    print(f"[*] Failures/Exclusions logged: {len(df_failures)} (saved to {fail_report_path})")

    return df_summary


def main():
    parser = argparse.ArgumentParser(description="Fetch OHLCV price windows and compute pre/post averages.")
    parser.add_argument("--raw-events", default="raw_events.csv", help="Input raw_events.csv path")
    parser.add_argument("--cache-dir", default="cache", help="Directory to cache ticker price histories")
    parser.add_argument("--windows-dir", default="ohlcv_windows", help="Directory to store individual window CSVs")
    parser.add_argument("--output-summary", default="intermediate_windows_summary.csv", help="Output summary file")
    parser.add_argument("--reports-dir", default="reports", help="Reports directory")
    args = parser.parse_args()

    fetch_all_windows(
        raw_events_path=args.raw_events,
        cache_dir=args.cache_dir,
        windows_dir=args.windows_dir,
        output_summary_path=args.output_summary,
        reports_dir=args.reports_dir
    )


if __name__ == "__main__":
    main()
