import argparse
import numpy as np
import pandas as pd


def bootstrap_ci(values, iterations=1000, seed=42):
    values = pd.to_numeric(pd.Series(values), errors="coerce").dropna().to_numpy()
    if len(values) == 0:
        return np.nan, np.nan, np.nan
    rng = np.random.default_rng(seed)
    means = np.array([
        rng.choice(values, size=len(values), replace=True).mean()
        for _ in range(iterations)
    ])
    return float(values.mean()), float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975))


def summarize(df, group_column, output_path, seed):
    rows = []
    for group, subset in df.groupby(group_column, dropna=False):
        for metric in ("shock_pct", "abnormal_return", "car"):
            mean, low, high = bootstrap_ci(subset[metric], seed=seed)
            rows.append({
                "group": str(group),
                "metric": metric,
                "n": int(subset[metric].notna().sum()),
                "mean": mean,
                "ci95_low": low,
                "ci95_high": high,
            })
    pd.DataFrame(rows).to_csv(output_path, index=False)


def main():
    parser = argparse.ArgumentParser()
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    parser.add_argument("--input", default=os.path.join(root, "NIFTY_EVENT_50", "NiftyEvent50_enriched.csv"))
    parser.add_argument("--output-dir", default=os.path.join(root, "outputs", "benchmark"))
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    df = pd.read_csv(args.input)
    import os
    os.makedirs(args.output_dir, exist_ok=True)
    summarize(df, "event_type", os.path.join(args.output_dir, "event_study_event_type.csv"), args.seed)
    summarize(df, "sector", os.path.join(args.output_dir, "event_study_sector.csv"), args.seed)


if __name__ == "__main__":
    main()
