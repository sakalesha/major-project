"""
NiftyEvent-50: Step 2 Event Extraction, Classification, and Deduplication Pipeline
Author: Antigravity Team
Description:
    Processes raw NSE corporate announcements from data/*.csv, filters
    to 2018-2024, classifies into 5 approved corporate event categories,
    distinguishes primary declarations from follow-on administrative filings,
    applies +-2 day deduplication, and exports raw_events.csv.
"""

import os
import glob
import re
import argparse
import pandas as pd
from datetime import datetime


FOLLOW_ON_SUB_PATTERNS = [
    "record date",
    "book closure",
    "date of payment of dividend",
    "agm/book closure",
    "copy of newspaper publication",
    "newspaper advertisements",
    "allotment of securities",
    "analysts/institutional investor meet",
    "transcript of analysts",
    "closure of trading window",
    "trading window",
    "audio recording",
    "investor presentation",
    "press release",
    "general updates"
]


def is_follow_on_subject(sub: str):
    sub_l = str(sub).lower().strip()
    return any(p in sub_l for p in FOLLOW_ON_SUB_PATTERNS)


def classify_announcement(subject: str, details: str):
    """
    Classifies an announcement into approved event categories.
    Returns list of tuples: [(event_type, is_primary_filing), ...]
    """
    sub_l = str(subject).lower() if pd.notnull(subject) else ""
    det_l = str(details).lower() if pd.notnull(details) else ""
    full_text = f"{sub_l} {det_l}"

    results = []

    # 1. Bonus Issue
    if "bonus" in sub_l or "bonus" in det_l:
        if not ("esop" in sub_l or "esos" in sub_l or "esps" in sub_l):
            is_primary = ("bonus" in sub_l) or ("outcome of board meeting" in sub_l and "bonus" in det_l)
            if any(p in sub_l for p in ["record date", "allotment of securities", "newspaper"]):
                is_primary = False
            results.append(("Bonus Issue", is_primary))

    # 2. Stock Split
    if any(k in full_text for k in ["stock split", "sub-division", "sub division", "subdivision", "split of equity", "split of shares"]):
        is_primary = ("stock split" in sub_l) or ("outcome of board meeting" in sub_l and "sub-division" in det_l)
        if any(p in sub_l for p in ["record date", "book closure", "newspaper"]):
            is_primary = False
        results.append(("Stock Split", is_primary))

    # 3. Dividend Declaration
    if "dividend" in sub_l or "dividend" in det_l:
        if not ("reminder" in sub_l or "unclaimed" in sub_l or "loss of" in sub_l):
            is_primary = ("dividend" in sub_l or "dividend updates" in sub_l) or \
                         ("outcome of board meeting" in sub_l and any(k in det_l for k in ["dividend", "interim dividend", "final dividend"]))
            if any(p in sub_l for p in ["record date", "book closure", "date of payment", "agm/book closure", "newspaper"]):
                is_primary = False
            results.append(("Dividend Declaration", is_primary))

    # 4. Financial Results (formerly Earnings Surprise)
    # Strictly primary financial result disclosures
    is_fin = False
    is_primary_fin = False
    fin_primary_subjects = [
        "financial result updates", "financial results updates", "financial results",
        "quarterly financial results", "integrated filing- financial", "integrated filing - financial"
    ]
    if any(k == sub_l for k in fin_primary_subjects):
        is_fin = True
        is_primary_fin = True
    elif "outcome of board meeting" in sub_l and any(k in det_l for k in ["financial result", "financial results", "audited", "unaudited", "quarter ended"]):
        is_fin = True
        is_primary_fin = True
    elif any(k in sub_l for k in ["financial result", "quarterly result", "audited financial"]):
        is_fin = True
        # Check if follow-on notice
        is_primary_fin = not is_follow_on_subject(sub_l)
    elif "financial results" in det_l and not is_follow_on_subject(sub_l):
        is_fin = True
        is_primary_fin = True

    if is_fin:
        results.append(("Financial Results", is_primary_fin))

    # 5. Management Change
    mgmt_keywords = ["appointment", "resignation", "cessation", "change in management", "re-appointment", "reappointment"]
    is_mgmt = False
    is_primary_mgmt = False
    if any(k in sub_l for k in mgmt_keywords):
        if not ("auditor" in sub_l or "scrutinizer" in sub_l):
            is_mgmt = True
            is_primary_mgmt = True
    elif any(k in det_l for k in ["appointment of", "resignation of", "cessation of", "re-appointment of"]):
        if any(r in det_l for r in ["director", "managing director", "ceo", "cfo", "kmp", "senior management", "chief executive", "chief financial"]):
            is_mgmt = True
            is_primary_mgmt = not is_follow_on_subject(sub_l)

    if is_mgmt:
        results.append(("Management Change", is_primary_mgmt))

    return results


def extract_raw_events(data_dir: str = "data", start_year: int = 2018, end_year: int = 2024):
    files = sorted(glob.glob(os.path.join(data_dir, "*.csv")))
    if not files:
        raise FileNotFoundError(f"No CSV files found in directory: {data_dir}")

    print(f"[*] Found {len(files)} company files in {data_dir}. Processing announcements...")

    raw_records = []
    total_parsed_rows = 0

    for file_path in files:
        try:
            df = pd.read_csv(file_path, low_memory=False)
            total_parsed_rows += len(df)
            df.columns = [c.strip().upper() for c in df.columns]

            if "BROADCAST DATE/TIME" not in df.columns:
                continue

            parsed_dt = pd.to_datetime(df["BROADCAST DATE/TIME"], format="%d-%b-%Y %H:%M:%S", errors="coerce")
            missing_mask = parsed_dt.isnull() & df["BROADCAST DATE/TIME"].notnull()
            if missing_mask.any():
                parsed_dt[missing_mask] = pd.to_datetime(df.loc[missing_mask, "BROADCAST DATE/TIME"], errors="coerce", dayfirst=True)

            df["PARSED_DT"] = parsed_dt
            mask_years = (df["PARSED_DT"].dt.year >= start_year) & (df["PARSED_DT"].dt.year <= end_year)
            filtered_df = df[mask_years].copy()

            for _, row in filtered_df.iterrows():
                dt = row["PARSED_DT"]
                sub = str(row.get("SUBJECT", "")).strip()
                det = str(row.get("DETAILS", "")).strip()
                sym = str(row.get("SYMBOL", "")).strip()
                cname = str(row.get("COMPANY NAME", "")).strip()
                attach = str(row.get("ATTACHMENT", "")).strip()
                bcast_str = str(row.get("BROADCAST DATE/TIME", "")).strip()

                if not sym or sym.lower() == "nan":
                    sym = os.path.basename(file_path).split("-")[1].split(".")[0].strip().upper()

                classified = classify_announcement(sub, det)
                for et, is_primary in classified:
                    raw_records.append({
                        "ticker": f"{sym}.NS",
                        "raw_symbol": sym,
                        "company_name": cname,
                        "date": dt.strftime("%Y-%m-%d"),
                        "broadcast_datetime": dt.strftime("%Y-%m-%d %H:%M:%S") if pd.notnull(dt) else bcast_str,
                        "timestamp_dt": dt,
                        "event_type": et,
                        "filing_subject": sub,
                        "is_primary_filing": is_primary,
                        "details": det,
                        "attachment_url": attach if attach != "nan" else ""
                    })

        except Exception as e:
            print(f"[-] Error processing {file_path}: {e}")

    df_events = pd.DataFrame(raw_records)
    print(f"[*] Total raw announcements scanned: {total_parsed_rows}")
    print(f"[*] Total qualifying event records ({start_year}-{end_year}, pre-dedup): {len(df_events)}")
    print(f"    - Primary Declarations: {df_events['is_primary_filing'].sum()}")
    print(f"    - Follow-on Filings: {(~df_events['is_primary_filing']).sum()}")
    return df_events


def deduplicate_events(df_events: pd.DataFrame, window_days: int = 2):
    if df_events.empty:
        return df_events

    print(f"[*] Applying +- {window_days}-day deduplication per (ticker, event_type)...")
    
    # Sort: put primary filings FIRST within same ticker/event/day
    df_sorted = df_events.sort_values(
        by=["ticker", "event_type", "timestamp_dt", "is_primary_filing"],
        ascending=[True, True, True, False]
    ).reset_index(drop=True)

    retained_records = []
    dropped_count = 0

    for (ticker, et), group in df_sorted.groupby(["ticker", "event_type"]):
        last_dt = None
        for _, row in group.iterrows():
            cur_dt = row["timestamp_dt"]
            if last_dt is None:
                retained_records.append(row)
                last_dt = cur_dt
            else:
                diff_days = (cur_dt - last_dt).total_seconds() / 86400.0
                if diff_days > window_days:
                    retained_records.append(row)
                    last_dt = cur_dt
                else:
                    dropped_count += 1

    df_deduped = pd.DataFrame(retained_records).reset_index(drop=True)
    print(f"[*] Removed {dropped_count} duplicate announcements within +- {window_days} days.")
    print(f"[*] Total events post-deduplication: {len(df_deduped)}")
    print(f"    - Clean Primary Declarations: {df_deduped['is_primary_filing'].sum()}")
    print(f"    - Follow-on Filings: {(~df_deduped['is_primary_filing']).sum()}")
    return df_deduped


def main():
    parser = argparse.ArgumentParser(description="Extract and deduplicate NSE events for NiftyEvent-50.")
    parser.add_argument("--data-dir", default="data", help="Directory containing the 50 NSE announcement CSVs")
    parser.add_argument("--output", default="raw_events.csv", help="Path to output raw_events.csv")
    parser.add_argument("--start-year", type=int, default=2018, help="Start year of the study window")
    parser.add_argument("--end-year", type=int, default=2024, help="End year of the study window")
    parser.add_argument("--dedup-days", type=int, default=2, help="Deduplication window in days (+-N days)")
    args = parser.parse_args()

    df_events = extract_raw_events(args.data_dir, args.start_year, args.end_year)
    df_deduped = deduplicate_events(df_events, args.dedup_days)

    df_deduped = df_deduped.sort_values(by=["date", "ticker", "event_type"]).reset_index(drop=True)
    df_deduped["event_id"] = [f"EVT_{i+1:05d}" for i in range(len(df_deduped))]

    final_columns = [
        "event_id",
        "ticker",
        "raw_symbol",
        "company_name",
        "date",
        "broadcast_datetime",
        "event_type",
        "filing_subject",
        "is_primary_filing",
        "details",
        "attachment_url"
    ]
    df_output = df_deduped[final_columns].copy()

    df_output.to_csv(args.output, index=False, encoding="utf-8")
    print(f"[OK] Successfully wrote {len(df_output)} records to {args.output}")

    print("\n--- Event Distribution by Category (All Deduplicated) ---")
    print(df_output["event_type"].value_counts())

    print("\n--- Event Distribution by Category (Clean Primary Filings Only) ---")
    print(df_output[df_output["is_primary_filing"]]["event_type"].value_counts())

    print("\n--- Coverage Summary ---")
    print(f"Distinct Tickers Covered: {df_output['ticker'].nunique()} / 50")
    print(f"Date Range: {df_output['date'].min()} to {df_output['date'].max()}")


if __name__ == "__main__":
    main()
