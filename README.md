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

The public release is under [NIFTY_EVENT_50/](NIFTY_EVENT_50/).

Important files:

- [NiftyEvent50_final.csv](NIFTY_EVENT_50/NiftyEvent50_final.csv)
  - The main 10-column dataset
  - 3,199 event observations
- [NiftyEvent50_primary.csv](NIFTY_EVENT_50/NiftyEvent50_primary.csv)
  - 2,637 primary declarations
- [raw_events.csv](NIFTY_EVENT_50/raw_events.csv)
  - Event provenance, filing subject, timestamp, and source URL
- [NiftyEvent50_enriched.csv](NIFTY_EVENT_50/NiftyEvent50_enriched.csv)
  - The final dataset plus verified market features and abnormal returns
- [data/](NIFTY_EVENT_50/data/)
  - 50 source announcement CSV files
- [ohlcv_windows/](NIFTY_EVENT_50/ohlcv_windows/)
  - Nine-session stock-price windows for every event
- [cache/](NIFTY_EVENT_50/cache/)
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

The unified benchmark includes traditional models, deep sequence models and
statistical forecasting baselines. Ridge and other exploratory classifiers remain
supplementary; they are not included in the publication-facing unified table.

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

See [EXPERIMENT_STATUS.md](docs/EXPERIMENT_STATUS.md)
for the complete benchmark status.

## Complete model list and performance results

### Evaluation protocol

- Dataset: 3,199 events in `NiftyEvent50_enriched.csv`
- Split: 70% training, 15% validation, 15% test
- Embargo: five calendar days at partition boundaries
- Purged split sizes: 2,221 train, 468 validation, 474 test
- Volatility split sizes: 2,220 train, 468 validation, 474 test
- Primary model-selection metric: validation macro-F1
- Test set is used once after model selection
- Random seeds: 42
- Traditional, XGBoost and CatBoost preprocessing: median numerical imputation,
  StandardScaler, most-frequent categorical imputation and OneHotEncoder
- Sequence preprocessing: T-3 to T-1 OHLCV-derived sequences plus standardized static features
- Direction test set has 230 Down, 52 Neutral and 192 Up events
- Volatility test set has 363 No and 111 Yes events

### Metric meanings

| Metric | Meaning |
|---|---|
| Accuracy | Percentage of all correct predictions |
| Balanced accuracy | Mean recall across classes |
| Macro precision | Unweighted mean precision across classes |
| Macro recall | Unweighted mean recall across classes |
| Macro-F1 | Primary metric: unweighted mean class F1 |
| MCC | Matthews correlation coefficient across the confusion matrix |
| Yes precision | Of predicted volatility spikes, fraction that are Yes |
| Yes recall | Of real volatility spikes, fraction detected |
| Yes F1 | Balance of Yes precision and recall |
| Average precision | Threshold-independent ranking quality for the Yes class |
| MAE | Mean absolute error for statistical forecasts |
| RMSE | Root mean squared error for statistical forecasts |

The majority baseline is not useful despite high volatility accuracy because it
usually predicts No and has lower balanced accuracy, macro-F1 and minority-class recall.

### Traditional machine-learning validation results

#### Direction

| Model | Accuracy | Balanced accuracy | MCC | Macro precision | Macro recall | Macro-F1 |
|---|---:|---:|---:|---:|---:|---:|
| Random Forest | 49.36% | 39.84% | 0.1404 | 38.96% | 39.84% | 37.73% |
| XGBoost | 52.78% | 39.76% | 0.1555 | 35.34% | 39.76% | 36.77% |
| CatBoost | 51.92% | 39.37% | 0.1332 | 34.35% | 39.37% | 36.05% |
| SVM | 36.32% | 38.71% | 0.0713 | 37.45% | 38.71% | 33.74% |
| Logistic Regression | 35.47% | 37.59% | 0.0774 | 38.25% | 37.59% | 33.17% |
| Majority Baseline | 57.48% | 33.33% | 0.0000 | 19.16% | 33.33% | 24.33% |

#### Volatility

| Model | Accuracy | Balanced accuracy | MCC | Macro precision | Macro recall | Macro-F1 |
|---|---:|---:|---:|---:|---:|---:|
| Random Forest | 69.02% | 57.22% | 0.1466 | 57.44% | 57.22% | 57.32% |
| SVM | 57.26% | 57.48% | 0.1287 | 55.54% | 57.48% | 53.32% |
| CatBoost | 73.93% | 53.93% | 0.1179 | 58.85% | 53.93% | 53.08% |
| XGBoost | 73.50% | 53.64% | 0.1071 | 57.88% | 53.64% | 52.79% |
| Logistic Regression | 54.70% | 57.27% | 0.1249 | 55.36% | 57.27% | 51.84% |
| Majority Baseline | 75.64% | 50.00% | 0.0000 | 37.82% | 50.00% | 43.07% |

### Traditional held-out test results

Random Forest was selected by validation macro-F1 for both tasks.

| Task | Accuracy | Balanced accuracy | MCC | Macro precision | Macro recall | Macro-F1 | Yes precision | Yes recall | Yes F1 | Yes average precision |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Direction | 50.21% | 39.31% | 0.1277 | 41.11% | 39.31% | 38.55% | - | - | - | - |
| Volatility | 71.31% | 55.94% | 0.1311 | 57.24% | 55.94% | 56.26% | 35.29% | 27.03% | 30.61% | 34.56% |

### Deep sequence-model validation results

#### Direction

| Model | Accuracy | Balanced accuracy | MCC | Macro precision | Macro recall | Macro-F1 |
|---|---:|---:|---:|---:|---:|---:|
| Transformer Encoder | 57.91% | 43.89% | 0.2177 | 44.82% | 43.89% | 44.08% |
| CNN-LSTM | 50.64% | 42.46% | 0.1692 | 41.73% | 42.46% | 41.56% |
| TCN | 49.57% | 42.97% | 0.1708 | 42.13% | 42.97% | 41.49% |
| 1D-CNN | 50.00% | 42.09% | 0.1657 | 41.59% | 42.09% | 41.29% |
| GRU | 53.42% | 41.79% | 0.1779 | 40.95% | 41.79% | 40.80% |
| LSTM | 52.56% | 41.60% | 0.1716 | 40.59% | 41.60% | 40.40% |

#### Volatility

| Model | Accuracy | Balanced accuracy | MCC | Macro precision | Macro recall | Macro-F1 |
|---|---:|---:|---:|---:|---:|---:|
| Transformer Encoder | 67.95% | 65.14% | 0.2695 | 62.00% | 65.14% | 62.24% |
| LSTM | 65.38% | 64.04% | 0.2458 | 60.76% | 64.04% | 60.40% |
| TCN | 63.89% | 63.34% | 0.2320 | 60.09% | 63.34% | 59.31% |
| 1D-CNN | 63.46% | 63.06% | 0.2268 | 59.85% | 63.06% | 58.96% |
| GRU | 61.97% | 63.56% | 0.2335 | 60.05% | 63.56% | 58.34% |
| CNN-LSTM | 65.60% | 57.63% | 0.1423 | 56.63% | 57.63% | 56.82% |

### Deep sequence held-out test results

| Task | Selected model | Accuracy | Balanced accuracy | MCC | Macro precision | Macro recall | Macro-F1 | Yes precision | Yes recall | Yes F1 | Yes average precision |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Direction | Transformer Encoder | 50.84% | 42.24% | 0.1646 | 45.20% | 42.24% | 41.70% | - | - | - | - |
| Volatility | Transformer Encoder | 72.57% | 62.39% | 0.2449 | 62.10% | 62.39% | 62.24% | 41.74% | 43.24% | 42.48% | 43.31% |

The volatility threshold selected on validation data was **0.56** for the
sequence-model result.

### Statistical time-series models

Statistical models forecast prices or market volatility; they are **not**
classification models and must not be compared directly with accuracy or macro-F1.

| Model | Task | Test metric | Value |
|---|---|---|---:|
| ARIMA(5,1,0) | TITAN adjusted-close forecast | MAE | 963.6883 |
| ARIMA(5,1,0) | TITAN adjusted-close forecast | RMSE | 979.4253 |
| GARCH(1,1) | Realized variance forecast | MAE | 2.7499 |
| GARCH(1,1) | Realized variance forecast | RMSE | 4.7368 |
| EGARCH(1,1) | Realized variance forecast | MAE | 2.4784 |
| EGARCH(1,1) | Realized variance forecast | RMSE | 4.7194 |
| VAR | TITAN/Nifty 50 return forecast | Joint return MAE | 0.008334 |
| VAR | TITAN/Nifty 50 return forecast | RMSE | 0.011882 |

### Supplementary traditional baselines

The existing baseline script also includes Ridge Classifier, Stratified Baseline,
and other exploratory models. Ridge, SGD, Perceptron, Passive-Aggressive,
AdaBoost, Bagging, Gaussian Naive Bayes and Quadratic Discriminant Analysis may
appear in historical notebooks, but they are not part of the unified final comparison.
The original random-fallback notebooks are archived and must not be used as evidence.

Detailed machine-readable results:

- [Unified classification summary](outputs/unified_notebook/unified_classification_summary.csv)
- [Traditional validation: Direction](outputs/unified_notebook/direction_traditional_validation.csv)
- [Traditional validation: Volatility](outputs/unified_notebook/volatility_traditional_validation.csv)
- [Sequence validation: Direction](outputs/unified_notebook/direction_sequence_validation.csv)
- [Sequence validation: Volatility](outputs/unified_notebook/volatility_sequence_validation.csv)
- [Statistical results](outputs/unified_notebook/statistical_models_results.csv)

## Dataset quality and provenance

The project provides multiple independent verification layers:

| Check | Result |
|---|---|
| Canonical dataset rows | 3,199 |
| Primary declarations | 2,637 |
| Follow-on filings | 562 |
| 10-column final dataset missing values | 0 |
| Price-shock arithmetic match | 3,199 / 3,199 (100%) |
| Direction-label match | 3,198 / 3,199 (99.97%) |
| Available volatility checks | 3,071 / 3,198 (96.03%) |
| Missing volatility baseline/window status | 1 event |
| Stratified source audit | 96 / 100 (96%) |

The 96% source audit is an encouraging source-validation result, but it is only
a 100-event sample and should be reported with the sample-size limitation.
Automated recomputation proves reproducibility; it does not alone prove economic
correctness or the correctness of every source classification.

### Universe and period

- Study period: 2018-01-03 to 2024-12-31 for the announced-event release
- Universe: 49 Nifty 50 constituents plus BSE Ltd
- Active sectors: 10
- Event categories: 5
- Filing relationships: primary declaration or follow-on notice
- This is a recent-constituent dataset, not a historical point-in-time Nifty 50 universe
- No earnings-surprise/analyst-consensus label is included

### Volatility threshold sensitivity

| Threshold | Yes | No | Unknown |
|---:|---:|---:|---:|
| 1.25 | 1,106 | 2,092 | 1 |
| 1.50 | 692 | 2,506 | 1 |
| 2.00 | 259 | 2,939 | 1 |

The 1.5 threshold is used for the publication-facing volatility label, while the
enriched CSV retains sensitivity labels for 1.25 and 2.0.

## Unified notebook

[NiftyEvent50_Unified_Model_Pipeline.ipynb](NiftyEvent50_Unified_Model_Pipeline.ipynb)
is the end-to-end publication-facing execution:

1. Load and audit the enriched dataset.
2. Create the purged chronological train/validation/test split.
3. Fit imputers, encoders and scalers only on training data.
4. Select traditional and sequence models by validation macro-F1.
5. Refit only where permitted and evaluate the untouched test set once.
6. Use validation-only thresholds for volatility Yes/No prediction.
7. Run ARIMA, GARCH, EGARCH and VAR as forecasting baselines.
8. Export unified metrics and confusion matrices.

## Reproducible commands

Run the unified notebook:

```powershell
python -m ipykernel install --user --name niftyevent50 --display-name "NiftyEvent50 Python 3.11"
jupyter nbconvert --to notebook --execute NiftyEvent50_Unified_Model_Pipeline.ipynb --ExecutePreprocessor.timeout=1800 --ExecutePreprocessor.kernel_name=niftyevent50
```

Run individual benchmark groups:

```powershell
python scripts/benchmark_niftyevent50.py
python deep_learning/run_sequence_models_benchmark.py
python comparative_benchmarks/run_classification_models.py
python comparative_benchmarks/run_statistical_models.py
```

Install comparative benchmark dependencies:

```powershell
python -m pip install -r comparative_benchmarks/requirements.txt
```

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
├── comparative_benchmarks/
│   ├── run_classification_models.py
│   ├── run_statistical_models.py
│   └── outputs/
├── deep_learning/
│   ├── run_sequence_models_benchmark.py
│   └── outputs/
├── notebooks/
│   └── dataset_statistics.ipynb
├── outputs/
│   ├── benchmark/                  Metrics, confusion matrices and models
│   ├── unified_notebook/           Executed unified-pipeline outputs
│   ├── reports/                    Quality and retrieval reports
│   └── releases/                   Packaged release archive
├── docs/
│   ├── EXPERIMENT_STATUS.md
│   └── context/
└── archive/
    └── Historical experimental notebooks
```

## Install and run

### Unified notebook

The simplest way to inspect every benchmark is
[NiftyEvent50_Unified_Model_Pipeline.ipynb](NiftyEvent50_Unified_Model_Pipeline.ipynb).
It is organized into a complete pipeline:

1. Dataset loading and quality audit
2. Chronological 70/15/15 split with purging
3. Training-only preprocessing
4. Random Forest, XGBoost, CatBoost, SVM, and Logistic Regression
5. LSTM, GRU, 1D-CNN, TCN, CNN-LSTM, and Transformer Encoder
6. ARIMA, GARCH, EGARCH, and VAR
7. Unified metrics and comparison tables

The executed notebook and generated result files are under
[outputs/unified_notebook/](outputs/unified_notebook/).

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
- Deduplication is based on a ±2-calendar-day ticker/event rule and can merge
  or retain related filings incorrectly. Alternative windows are included for sensitivity.
- The source-audit sample is 100 events and should not be interpreted as full coverage.
- One event lacks enough baseline/window history for a definitive volatility label.
- The dataset package does not yet include a verified DOI.
- Market-adjusted returns require estimation-window assumptions and should not
  be interpreted as causal estimates.
- The reported test periods represent 2023–2024 market conditions and may not
  generalize to later periods.
- Weak model performance does not imply that an event has no economic effect.
- The project is for research and education, not investment advice.

## Experimental notebooks

The original 10-model and combined 20-model notebooks are retained only in
[archive/](archive/)
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
