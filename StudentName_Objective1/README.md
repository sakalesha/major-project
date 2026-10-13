# NiftyEvent-50: A Sector-Wise Corporate Event and Price Shock Dataset for 50 Leading NSE Equities (49 Nifty 50 Constituents + BSE Ltd)

## 1. Overview and Study Scope
**NiftyEvent-50** is a standardized corporate event and market price shock benchmark dataset constructed from regulatory disclosures filed on the National Stock Exchange of India (NSE) across 2018–2024 (7 calendar years).

### Empirical Scope
- **Equities Universe:** 50 prominent equities listed on NSE, consisting of **49 Nifty 50 benchmark constituents** and **BSE Ltd** (`BSE.NS`, India's premier stock exchange institution listed on NSE, constituent of Nifty 500). Formally designated as **49 Nifty 50 Constituents + BSE Ltd**.
- **Study Period:** 2018-01-03 to 2024-12-31.
- **Total Deduplicated Observations:** **3,199 event filings**
- **Clean Primary Board Declarations:** **2,637 events (82.4%)** (available standalone in `NiftyEvent50_primary.csv`)
- **Follow-on Administrative Notices:** **562 events (17.6%)** (Record dates, book closures, payment dates)
- **Approved Event Categories:** 5 Categories (`Financial Results`, `Dividend Declaration`, `Management Change`, `Bonus Issue`, `Stock Split`).
- **Research Sector Taxonomy:** 10 active research sectors (`Realty` has 0 constituents in the provided 50 stocks). Granular sub-sectors like retail/durables and aviation/defense/cement are consolidated into parent sectors with complete rationale documented in `data_dictionary.xlsx`.

---

## 2. Key Methodological Standards

### 2.1 Announcement Timing & T0 Session Alignment
- **Pre-Market (<09:15 IST Weekdays):** Trades same day ($T_0 = \text{Announcement Date}$) at market open.
- **Market Hours (09:15–15:30 IST Weekdays):** Trades same day ($T_0 = \text{Announcement Date}$).
- **Post-Market (>=15:30 IST Weekdays):** Advances to the next active NSE trading day ($T_0 = \text{Next Trading Session}$).
- **Weekends & Exchange Holidays:** Advances to the next active NSE trading day ($T_0 = \text{Next Trading Session}$).
- **Timing Distribution:** **70.0% to 70.1%** of corporate announcements occur outside active exchange trading hours (243 weekend, 54 pre-open, and 1,941 to 1,946 post-close depending on exact 15:30 minute boundary assignment).

### 2.2 Price Series Convention (Adjusted Close)
All price calculations use split- and dividend-adjusted closing prices (`Adj Close` from Yahoo Finance). This eliminates mechanical -50% to -80% price collapses from the 31 bonus issues and 16 stock splits in the study window.

### 2.3 Window Dimensions & Event Date Exclusion
- Stored window files in `ohlcv_windows/` contain **9 rows** ($T_{-3}$ to $T_{+5}$, including $T_0$).
- **Pre-event price (`pre_event_price`):** Mean of 3 trading sessions strictly prior to the event ($T_{-3}, T_{-2}, T_{-1}$).
- **Post-event price (`post_event_price`):** Mean of 5 trading sessions strictly subsequent to the event ($T_{+1}, T_{+2}, T_{+3}, T_{+4}, T_{+5}$).
- **Session $T_0$:** Explicitly excluded from both averages to prevent intra-day spillover.

### 2.4 Label Formulas
- **Price Shock Percentage:**
  $$\text{shock\_pct} = \left(\frac{\text{post\_event\_price} - \text{pre\_event\_price}}{\text{pre\_event\_price}}\right) \times 100$$
- **Direction Label:**
  - `Up`: $\text{shock\_pct} > +0.5\%$
  - `Down`: $\text{shock\_pct} < -0.5\%$
  - `Neutral`: $-0.5\% \le \text{shock\_pct} \le +0.5\%$
- **Volatility Spike Label:**
  - `Yes`: $\sigma_{\text{window}} > 1.5 \times \sigma_{\text{baseline}}$, where $\sigma_{\text{window}}$ is return volatility across 8 event sessions, and $\sigma_{\text{baseline}}$ is rolling 30-day volatility over $T_{-33}$ to $T_{-4}$.
  - `No`: Otherwise.

---

## 3. Two-Tier Quality & Validation Framework

1. **Tier 1 (Automated Consistency Check across all 3,199 rows):**
   Programmatic recomputation of shock percentage, direction boundaries, and volatility spikes proves 100.0% arithmetic reproducibility from window files and offline price histories.
2. **Tier 2 (Stratified Substantive Source Audit of 100 events):**
   A stratified random sample (`seed=42`) of 100 events (35 Financial Results, 25 Dividends, 20 Management Changes, 10 Bonus Issues, 10 Stock Splits) audited against official exchange records on `nsearchives.nseindia.com`, broadcast timestamps, and daily price series.
   - **Observed Accuracy:** **96.0%** (96 / 100 verified correct corporate actions, 4 administrative noise events flagged in Financial Results). Exceeds the $\ge 90.0\%$ project threshold.

---

## 4. Execution & Offline Verification

### Offline Dataset Verification (Single Command)
```bash
python verify_dataset.py
```
This script runs 100% offline using `ticker_histories/` and `ohlcv_windows/`, validating price shocks, direction labels, and rolling 30-day volatility baselines without network calls.

### End-to-End Pipeline Execution
```bash
# Step 2: Extract & deduplicate announcements from data/
python scraper.py --data-dir data --output raw_events.csv

# Step 3: Fetch price histories and slice 9-session windows
python ohlcv_fetch.py --raw-events raw_events.csv --cache-dir cache --windows-dir ohlcv_windows

# Step 4: Compute price shock, direction, and volatility labels
python label_compute.py --summary intermediate_windows_summary.csv --output candidate_labeled_events.csv

# Step 5: Quality checks and stratified spot check
python quality_check.py --candidate candidate_labeled_events.csv --spot-check spot_check_100.xlsx

# Step 6: Build release and zip
python build_release.py
```

---

## 5. Repository Structure
```text
StudentName_Objective1/
├── NiftyEvent50_final.csv       # 10-column canonical dataset with is_primary_filing flag (3,199 rows)
├── NiftyEvent50_primary.csv     # Clean primary board declarations subset (2,637 rows)
├── raw_events.csv              # Master event catalog with provenance and PDF URLs (3,199 rows)
├── ohlcv_windows/              # 3,199 individual 9-session OHLCV window CSV files
├── ticker_histories/           # 50 complete daily price histories for offline baseline verification
├── data/                       # 50 raw NSE announcement CSV files from Step 2
├── data_dictionary.xlsx        # 4-sheet schema, sector, and taxonomy documentation
├── spot_check_100.xlsx         # Stratified 100-event source audit workbook (96.0% score)
├── dataset_statistics.ipynb    # Executed Jupyter notebook with rendered figures & tables
├── verify_dataset.py           # Standalone offline verification script
├── scraper.py                  # Step 2 announcement scraping & deduplication script
├── ohlcv_fetch.py              # Step 3 market data fetch & T0 session alignment script
├── label_compute.py            # Step 4 price shock & volatility labeling script
├── quality_check.py            # Step 5 quality assurance and spot-check sampling script
├── build_release.py            # Step 6 release building and packaging script
├── requirements.txt            # Pinned library dependencies (exact == versions)
├── README.md                   # Full methodology, usage, and provenance guide
└── result.md                   # Audited results and deliverables report
```
