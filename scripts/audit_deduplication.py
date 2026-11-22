import os
import argparse
import pandas as pd


def deduplicate(df, window_days):
    df = df.copy()
    df["timestamp_dt"] = pd.to_datetime(df["broadcast_datetime"], errors="coerce")
    df = df.sort_values(
        ["ticker", "event_type", "timestamp_dt", "is_primary_filing"],
        ascending=[True, True, True, False],
    )
    retained = []
    dropped = 0
    for _, group in df.groupby(["ticker", "event_type"], sort=False):
        last_dt = None
        for _, row in group.iterrows():
            current = row["timestamp_dt"]
            if last_dt is None or (current - last_dt).total_seconds() / 86400 > window_days:
                retained.append(row)
                last_dt = current
            else:
                dropped += 1
    return pd.DataFrame(retained).reset_index(drop=True), dropped


def audit(raw_path, output_path):
    raw = pd.read_csv(raw_path)
    rows = []
    for window in (0, 1, 2, 3, 5):
        deduplicated, dropped = deduplicate(raw, window)
        rows.append({
            "window_days": window,
            "raw_records": len(raw),
            "deduplicated_records": len(deduplicated),
            "dropped_records": dropped,
            "primary_records": int(deduplicated["is_primary_filing"].fillna(False).sum()),
            "follow_on_records": int((~deduplicated["is_primary_filing"].fillna(False)).sum()),
        })
    report = pd.DataFrame(rows)
    report.to_csv(output_path, index=False)
    print(report.to_string(index=False))


def main():
    parser = argparse.ArgumentParser()
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    release_dir = os.path.join(root, "NIFTY_EVENT_50")
    parser.add_argument("--input", default=os.path.join(release_dir, "raw_events.csv"))
    parser.add_argument("--output", default=os.path.join(release_dir, "deduplication_sensitivity.csv"))
    args = parser.parse_args()
    audit(args.input, args.output)


if __name__ == "__main__":
    main()
