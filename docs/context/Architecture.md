# NiftyEvent-50 Architecture Diagram

This architecture covers the full six-step dataset pipeline, from defining the event taxonomy through publishing the validated dataset. Steps 1 and 2 are marked as existing inputs; the remaining modules complete Steps 3–6.

```mermaid
flowchart TD
    subgraph INPUTS["Inputs and reference data"]
        TAX["Event taxonomy\n5 approved event types"]
        RAW["raw_events.csv\nCompleted Step 2 output"]
        SECTOR["Ticker-to-sector mapping\n11 approved sectors"]
        YF["yfinance\nHistorical OHLCV data"]
    end

    subgraph PIPELINE["Python data pipeline"]
        CHECK["Validate, normalize, and deduplicate events"]
        ID["Assign stable internal event_id"]
        FETCH["Fetch OHLCV history\nRetries and caching"]
        ALIGN["Align trading sessions\n3 prior + 5 subsequent sessions"]
        WIN["Save per-ticker or per-event\nOHLCV windows"]
        BASE["Compute pre-event and post-event\naverage closing prices"]
        SHOCK["Compute shock_pct\nand Up / Down / Neutral label"]
        VOL["Compute daily returns and rolling\n30-trading-day volatility label"]
        MERGE["Join prices and labels\nto event records"]
        QA["Automated quality checks\ncoverage, duplicates, missingness, schema"]
        SAMPLE["Select reproducible random sample\nof 100 events"]
        REVIEW["Manual review\nevent, price window, labels, sector"]
        GATE{"Release criteria met?"}
        FIX["Resolve defects and rerun\naffected pipeline stages"]
    end

    subgraph INTERMEDIATE["Intermediate files and audit trail"]
        CACHE[("Cached ticker price history")]
        WINDOWS["ohlcv_windows/"]
        FAIL["Run logs and failed-event report"]
        CANDIDATE["Candidate labeled dataset"]
    end

    subgraph OUTPUTS["Final artifacts and release"]
        CSV["NiftyEvent50_final.csv"]
        DICT["data_dictionary.xlsx"]
        SPOT["spot_check_100.xlsx"]
        STATS["dataset_statistics.ipynb"]
        CODE["scraper.py, ohlcv_fetch.py,\nlabel_compute.py, requirements.txt"]
        README["README.md\nSetup, methodology, limitations"]
        ZIP["StudentName_Objective1.zip"]
        PUBLIC["GitHub source repository\nZenodo or Hugging Face dataset\nDOI when issued"]
    end

    TAX --> CHECK
    RAW --> CHECK
    CHECK --> ID
    ID --> FETCH
    YF --> FETCH
    FETCH <--> CACHE
    FETCH --> ALIGN
    FETCH --> FAIL
    ALIGN --> WIN
    WIN --> WINDOWS
    ALIGN --> BASE
    CACHE --> VOL
    BASE --> SHOCK
    BASE --> VOL
    SHOCK --> MERGE
    VOL --> MERGE
    MERGE --> CANDIDATE
    CANDIDATE --> QA
    SECTOR --> QA
    QA --> SAMPLE
    SAMPLE --> REVIEW
    REVIEW --> GATE
    GATE -- Yes --> CSV
    GATE -- Yes --> DICT
    GATE -- Yes --> SPOT
    GATE -- Yes --> STATS
    GATE -- Yes --> CODE
    GATE -- Yes --> README
    GATE -- No --> FIX
    FIX --> FETCH
    CSV --> ZIP
    DICT --> ZIP
    SPOT --> ZIP
    STATS --> ZIP
    CODE --> ZIP
    README --> ZIP
    ZIP --> PUBLIC
```

## Architecture notes

- **Step 1 — Taxonomy:** The approved five event types and their detection rules are a versioned input to the pipeline.
- **Step 2 — Announcements:** `raw_events.csv` is the existing input. Validate and retain provenance where available; do not silently discard source records.
- **Step 3 — OHLCV:** Retrieve historical market data, align events to trading sessions, and persist reusable price history and event windows. The 30-day volatility calculation requires more history than the three-before/five-after event window.
- **Step 4 — Labels:** Calculate the pre/post average close, price shock, direction, and volatility-spike label using explicitly documented methodology settings.
- **Step 5 — Quality:** Map sectors, report row-level and column-level missingness, calculate coverage statistics, and manually review a reproducible random sample of 100 events.
- **Step 6 — Release:** Export the final CSV, data dictionary, validation workbook, statistics notebook, source scripts, and README. Publish only after the release gate; record a DOI only after it has actually been issued.

## Decisions to freeze before a full run

1. Raw `Close` versus adjusted price series, especially for stock splits and bonus issues.
2. The precise historical baseline used for the 1.5x volatility-spike threshold.
3. How announcements on non-trading days or after market close are aligned.
4. Whether the historical universe means current Nifty 50 tickers or historical constituents for each year.
5. The earnings-surprise source and the exact rule for calculating an EPS surprise.

These decisions affect labels and must be documented in the data dictionary and README.
