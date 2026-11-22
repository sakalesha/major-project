# NiftyEvent-50

NiftyEvent-50 is a research project for studying how Indian corporate announcements
affect stock prices.

It combines:

- Corporate announcements filed with the National Stock Exchange of India
- Historical stock-price data
- Market and volatility data
- Machine-learning benchmarks
- Event-study measures

The project covers 2018 to 2024 and contains **3,199 deduplicated event observations**
from 50 NSE-listed companies: **49 current Nifty 50 constituents plus BSE Ltd**.

## What this project does

For each corporate event, the project records:

- The company and sector
- The announcement category
- Whether it is a primary filing or follow-on notice
- The stock's pre-event and post-event prices
- The price direction: Up, Down, or Neutral
- Whether volatility increased
- Additional market-adjusted return measures

The five event categories are:

1. Financial Results
2. Dividend Declaration
3. Management Change
4. Bonus Issue
5. Stock Split

This dataset studies **Financial Results disclosures**, not analyst earnings-surprise
predictions. It does not have historical analyst-consensus data.

## Research questions

### RQ1: Do different corporate events produce different price reactions?

The project compares descriptive price shocks, abnormal returns, and cumulative
abnormal returns across event types and sectors.

### RQ2: Do corporate events increase market volatility?

The project compares event-window volatility with a 30-day pre-event baseline.
The default 1.5 threshold is compared with 1.25 and 2.0 thresholds.

### RQ3: Can pre-event information predict the reaction?

The project trains and compares machine-learning models using real information
available before each event.

## Dataset files

The public release is under [NIFTY_EVENT_50/](/C:/Users/ronad/OneDrive/Desktop/NiftyEvent50_Combined_20_Models/NIFTY_EVENT_50/).

Important files:

- [NiftyEvent50_final.csv](/C:/Users/ronad/OneDrive/Desktop/NiftyEvent50_Combined_20_Models/NIFTY_EVENT_50/NiftyEvent50_final.csv)
  - The main 10-column dataset
  - 3,199 event observations
- [NiftyEvent50_primary.csv](/C:/Users/ronad/OneDrive/Desktop/NiftyEvent50_Combined_20_Models/NIFTY_EVENT_50/NiftyEvent50_primary.csv)
  - 2,637 primary declarations
- [raw_events.csv](/C:/Users/ronad/OneDrive/Desktop/NiftyEvent50_Combined_20_Models/NIFTY_EVENT_50/raw_events.csv)
  - Event provenance, filing subject, timestamp, and source URL
- [NiftyEvent50_enriched.csv](/C:/Users/ronad/OneDrive/Desktop/NiftyEvent50_Combined_20_Models/NIFTY_EVENT_50/NiftyEvent50_enriched.csv)
  - The final dataset plus verified market features and abnormal returns
- [data/](/C:/Users/ronad/OneDrive/Desktop/NiftyEvent50_Combined_20_Models/NIFTY_EVENT_50/data/)
  - 50 source announcement CSV files
- [ohlcv_windows/](/C:/Users/ronad/OneDrive/Desktop/NiftyEvent50_Combined_20_Models/NIFTY_EVENT_50/ohlcv_windows/)
  - Nine-session stock-price windows for every event
- [cache/](/C:/Users/ronad/OneDrive/Desktop/NiftyEvent50_Combined_20_Models/NIFTY_EVENT_50/cache/)
  - Local historical stock and market-index data

## How the labels are calculated

### Price direction

The direction is calculated from the average adjusted price:

- T-3 to T-1 is used as the pre-event price.
- T+1 to T+5 is used as the post-event price.
- T0 is the announcement's effective trading session.

```text
shock_pct = ((post_event_price - pre_event_price) / pre_event_price) * 100
```

Labels:

- **Up**: shock is greater than +0.5%
- **Down**: shock is less than -0.5%
- **Neutral**: shock is between -0.5% and +0.5%

### Volatility

A volatility spike is identified when the event-window daily return volatility is more
than 1.5 times the pre-event baseline volatility.

```text
event volatility > 1.5 * baseline volatility
```

The default threshold is 1.5, but the enriched dataset also provides results for 1.25
and 2.0. Events without enough verified historical data are marked **Unknown**, rather
than automatically marked No.

### Market-adjusted return

The project adds a market-adjusted return estimate and cumulative abnormal return (CAR).
These aim to separate a stock's reaction from overall Nifty 50 movement.

## Model benchmark

The benchmark uses a chronological evaluation process:

1. Sort events by effective trading date.
2. Reserve 70% for training.
3. Reserve 15% for validation.
4. Reserve 15% for testing.
5. Add a five-day embargo around partition boundaries.
6. Select models using validation macro-F1.
7. Refine the selected model on training plus validation data.
8. Evaluate it once on the untouched test period.

The benchmark includes Random Forest, Logistic Regression, Ridge Classifier, SVM,
majority-class baseline, and stratified baseline.

### Performance measures

**Macro-F1 is the primary measure.**

- It is important because every event class should count fairly.
- Direction has three classes: Up, Neutral, and Down.
- Volatility has fewer Yes events than No events.
- Macro-F1 penalizes poor prediction of minority or difficult classes.

Additional measures:

- **Balanced accuracy:** average recall across classes
- **Yes precision:** proportion of predicted volatility spikes that are correct
- **Yes recall:** proportion of actual volatility spikes detected
- **Yes F1:** balance of Yes precision and recall
- **Average precision:** quality of probability ranking for volatility spikes
- **Matthews correlation coefficient:** an overall agreement score
- **Accuracy:** included for context, but not used as the only decision measure

The test results currently show that prediction is difficult. This is useful evidence
that the available pre-event features have limited predictive strength.

See [EXPERIMENT_STATUS.md](/C:/Users/ronad/OneDrive/Desktop/NiftyEvent50_Combined_20_Models/docs/EXPERIMENT_STATUS.md)
for the complete benchmark status.

## Current benchmark results

The selected model for both tasks was Random Forest.

- **Direction:** 50.21% accuracy, 38.55% macro-F1
- **Volatility:** 71.31% accuracy, 56.26% macro-F1
- **Volatility Yes recall:** 27.03%

These numbers should be interpreted as weak predictive benchmarks, not as evidence of
high-confidence trading performance.

Detailed files are available in
[outputs/benchmark/](/C:/Users/ronad/OneDrive/Desktop/NiftyEvent50_Combined_20_Models/outputs/benchmark/).

## Project structure

```text
NiftyEvent50/
├── NIFTY_EVENT_50/                 Dataset and release package
│   ├── data/                       50 source announcement CSV files
│   ├── cache/                      Historical market data
│   ├── ohlcv_windows/              3,199 event windows
│   └── *.csv / *.xlsx              Dataset and audit outputs
├── scripts/
│   ├── enrich_niftyevent50.py      Market feature and CAR enrichment
│   ├── benchmark_niftyevent50.py   Model benchmark
│   ├── audit_deduplication.py      Deduplication sensitivity
│   ├── event_study_analysis.py     Event and sector summaries
│   └── pipeline/                   Dataset construction scripts
├── notebooks/
│   └── dataset_statistics.ipynb
├── outputs/
│   ├── benchmark/                  Metrics, confusion matrices and models
│   ├── reports/                    Quality and retrieval reports
│   └── releases/                   Packaged release archive
├── docs/
│   ├── EXPERIMENT_STATUS.md
│   └── context/
└── archive/
    └── Historical experimental notebooks
```

## Install and run

### 1. Install Python

Python 3.9 or later is recommended.

### 2. Create a virtual environment

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Enrich the dataset

```powershell
python scripts/enrich_niftyevent50.py
```

This creates or updates `NIFTY_EVENT_50/NiftyEvent50_enriched.csv`.

### 4. Run the model benchmark

```powershell
python scripts/benchmark_niftyevent50.py
```

Benchmark outputs are written to `outputs/benchmark/`.

### 5. Run deduplication sensitivity analysis

```powershell
python scripts/audit_deduplication.py
```

### 6. Generate event-study summaries

```powershell
python scripts/event_study_analysis.py
```

### 7. Verify the dataset

```powershell
python scripts/pipeline/verify_dataset.py
```

The verification checks price calculations, direction labels, and volatility labels
from the stored source windows and price histories.

## Reconstruct the dataset from source files

```powershell
python scripts/pipeline/scraper.py --data-dir NIFTY_EVENT_50/data --output NIFTY_EVENT_50/raw_events.csv
python scripts/pipeline/ohlcv_fetch.py --raw-events NIFTY_EVENT_50/raw_events.csv --cache-dir NIFTY_EVENT_50/cache --windows-dir NIFTY_EVENT_50/ohlcv_windows --output-summary NIFTY_EVENT_50/intermediate_windows_summary.csv
python scripts/pipeline/label_compute.py --summary NIFTY_EVENT_50/intermediate_windows_summary.csv --cache-dir NIFTY_EVENT_50/cache --windows-dir NIFTY_EVENT_50/ohlcv_windows --output NIFTY_EVENT_50/candidate_labeled_events.csv
python scripts/pipeline/verify_dataset.py
```

## Important limitations

- The stock universe represents 49 current Nifty 50 constituents plus BSE Ltd.
  It is not a historical point-in-time Nifty 50 universe.
- The project does not use analyst-consensus earnings data.
- Financial Results means that financial statements were announced, not that the
  company beat or missed analyst expectations.
- The price-shock measure is descriptive. CAR and abnormal-return fields provide
  stronger market-adjusted analysis.
- Volatility thresholds are operational definitions and should be tested at multiple levels.
- Weak model performance does not imply that an event has no economic effect.
- The project is for research and education, not investment advice.

## Experimental notebooks

The original 10-model and combined 20-model notebooks are retained only in
[archive/](/C:/Users/ronad/OneDrive/Desktop/NiftyEvent50_Combined_20_Models/archive/)
for audit and reproducibility history.

They contain random fallback features in exploratory cells and must not be cited as
validated machine-learning evidence.

## Documentation

- [Experiment status and validation findings](docs/EXPERIMENT_STATUS.md)
- [NIFTY_EVENT_50 release README](NIFTY_EVENT_50/README.md)
- [Project development notes](docs/PROJECT_DEVELOPMENT.md)

## Citation

Please cite the project as **NiftyEvent-50: Indian Corporate-Event Dataset and Market
Reaction Benchmark**. Include the dataset version and the exact source files used when
reporting results.
