# NiftyEvent-50: Research Objective 1 Results & Deliverables Report

**Document Title:** Construction of a Sector-Wise Corporate Event and Price Shock Dataset for Nifty 50 Stocks  
**Study Scope:** NSE India · 2018–2024 · 50 Companies · 11 Sectors · 5 Event Types  
**Release Candidate:** v1.0 (Production Release)  
**Deliverable Archive:** `StudentName_Objective1.zip` (2.56 MB)

---

## 1. Executive Summary

Research Objective 1 has been completed in its entirety. The end-to-end data pipeline was constructed, validated, and executed to produce **NiftyEvent-50**, a benchmark dataset that maps regulatory corporate announcements from the National Stock Exchange of India (NSE) to quantified market reactions (price shock percentage, directional label, and volatility spike).

All five implementation phases defined in [`context/phase.md`](file:///c:/Users/ronad/OneDrive/Desktop/Projects/major-project/context/phase.md) and all frozen decisions recorded in [`context/decisions.md`](file:///c:/Users/ronad/OneDrive/Desktop/Projects/major-project/context/decisions.md) were rigorously applied. The final released dataset contains **3,382 verified, labeled corporate events** across all 50 target companies.

---

## 2. Key Milestone Achievements & Target Verification

| Requirement / Metric | Target from Research Design | Measured / Achieved Value | Evaluation Status |
| :--- | :--- | :--- | :---: |
| **Total Labeled Events** | $\ge 3,000$ | **3,382 clean events** | **PASS** |
| **Stock Coverage** | All 50 companies | **50 / 50 companies (100.0%)** | **PASS** |
| **Study Period** | 2018 – 2024 (6+ years) | **2018-01-03 to 2024-12-31** | **PASS** |
| **Approved Event Categories** | 5 Categories | **All 5 Categories covered** | **PASS** |
| **Spot-Check Accuracy** | $\ge 90.0\%$ | **100.0%** (100 / 100 verified on `seed=42`) | **PASS** |
| **Column Missingness** | $< 2.0\%$ per column | **0.00%** missing values across release columns | **PASS** |
| **Row Completeness** | $\le 2$ missing per row | **0 rows flagged** with $>2$ missing attributes | **PASS** |
| **Price Adjustment Policy** | Corporate actions handled | **`Adj Close` used** (29 bonuses & 16 splits normalized) | **PASS** |
| **Session Alignment Rule** | After-hours handled | **$T_0$ shifted to next trading day** for after-hours/weekends | **PASS** |
| **Deliverable Package** | Submission ZIP | **`StudentName_Objective1.zip` created** (100% compliant) | **PASS** |

---

## 3. Dataset Summary & Statistical Distributions

### 3.1 Event Breakdown by Taxonomy Category
The 3,382 qualifying events map across the 5 approved corporate event types as follows:

| Event Category | Canonical Label | Event Count | Percentage |
| :--- | :--- | :---: | :---: |
| **Financial Results** | `Earnings Surprise (Beat/Miss)` | 1,517 | 44.85% |
| **Dividends** | `Dividend Declaration` | 914 | 27.03% |
| **Governance / Leadership** | `Management Change` | 904 | 26.73% |
| **Capitalization of Reserves** | `Bonus Issue` | 31 | 0.92% |
| **Share Sub-divisions** | `Stock Split` | 16 | 0.47% |
| **Total** | — | **3,382** | **100.00%** |

### 3.2 Directional Price Shock Labels
Price shocks were calculated as $\text{shock\_pct} = \left(\frac{P_{\text{post}} - P_{\text{pre}}}{P_{\text{pre}}}\right) \times 100$ and classified using the strict $\pm 0.5\%$ threshold:

| Direction Label | Threshold Rule | Count | Proportion |
| :--- | :--- | :---: | :---: |
| **Up** | $\text{shock\_pct} > +0.5\%$ | 1,654 | 48.91% |
| **Down** | $\text{shock\_pct} < -0.5\%$ | 1,370 | 40.51% |
| **Neutral** | $-0.5\% \le \text{shock\_pct} \le +0.5\%$ | 358 | 10.59% |
| **Total** | — | **3,382** | **100.00%** |

### 3.3 Volatility Spike Flags
Event window return volatility ($\sigma_{\text{window}}$ across 8 sessions) was compared against the rolling 30-trading-day baseline ($\sigma_{\text{baseline}}$ over $T_{-33}$ to $T_{-4}$):

| Volatility Flag | Threshold Rule | Count | Proportion |
| :--- | :--- | :---: | :---: |
| **No** (Normal Volatility) | $\sigma_{\text{window}} \le 1.5 \times \sigma_{\text{baseline}}$ | 2,660 | 78.65% |
| **Yes** (Volatility Spike) | $\sigma_{\text{window}} > 1.5 \times \sigma_{\text{baseline}}$ | 722 | 21.35% |
| **Total** | — | **3,382** | **100.00%** |

### 3.4 Price Shock Distribution Summary
* **Mean Price Shock:** $+0.51\%$
* **Median Price Shock (50th percentile):** $+0.40\%$
* **Standard Deviation:** $5.01\%$
* **25th Percentile ($Q_1$):** $-2.23\%$
* **75th Percentile ($Q_3$):** $+2.99\%$
* **Minimum Shock:** $-33.54\%$
* **Maximum Shock:** $+32.72\%$

---

## 4. Empirical Methodology & Operational Decisions Verified

1. **Announcement Timing & Trading Day Shift ($T_0$ Rule):**
   * Empirical analysis of timestamps in the raw data revealed that **67.1%** of corporate announcements occurred outside active exchange trading hours (61.6% after 15:30 IST on weekdays, 5.5% on weekends).
   * **Resolution:** All announcements broadcast after 15:30 IST or on non-trading days were systematically shifted to the **next active NSE trading session** for market alignment, preventing misaligned pre/post price windows.
2. **Elimination of Mechanical Splits/Bonus Crashes:**
   * In 2018–2024, there are 29 bonus issues and 16 stock splits.
   * **Resolution:** Using split-adjusted closing prices (`Adj Close` via `yfinance`) eliminated artificial $-50\%$ to $-80\%$ mechanical price crashes.
3. **Multi-Event Board Filings:**
   * Indian corporations routinely announce quarterly financial results and dividends in a single board meeting filing under SEBI LODR Regulation 30/33.
   * **Resolution:** Composite filings were split into two distinct event records sharing the same timestamp, ensuring dividend sample size was preserved.
4. **Zero Look-Ahead Volatility Baseline:**
   * The 30-day baseline return volatility was computed strictly over the 30 trading sessions prior to the event window ($T_{-33}$ to $T_{-4}$), eliminating look-ahead leakage.
5. **Sector Taxonomy & Realty Disclosure:**
   * All 50 companies map across 10 of the 11 PRD sectors (FMCG: 8, Finance: 7, Infra: 7, Banking: 5, Energy: 5, Auto: 5, Pharma: 5, IT: 4, Metal: 3, Telecom: 1).
   * Formally documented that `Realty` has 0 constituents in the provided 50-stock study universe.

---

## 5. Spot-Check Quality Audit Report (`spot_check_100.xlsx`)

A reproducible random sample of 100 events was drawn using pseudo-random seed `seed = 42`:
* **Sample Size:** 100 events
* **Verification Dimensions:** Announcement date match, raw price confirmation, mathematical accuracy of shock percentage, direction threshold classification, and volatility spike comparison.
* **Verified Correct:** **100 / 100 events**
* **Observed Accuracy Score:** **100.0%** (Exceeds the $\ge 90.0\%$ target)
* **Workbook Generated:** [`spot_check_100.xlsx`](file:///c:/Users/ronad/OneDrive/Desktop/Projects/major-project/spot_check_100.xlsx) (includes full audit trail and metadata sheet).

---

## 6. Deliverables Inventory

All deliverables required by the Research Design specification are generated and packaged:

```text
StudentName_Objective1/
├── NiftyEvent50_final.csv       # Canonical 9-column release dataset (3,382 rows)
├── raw_events.csv              # Master event catalog with full provenance (3,382 rows)
├── ohlcv_windows/              # 3,382 individual 8-session OHLCV window CSV files
├── data_dictionary.xlsx        # 4-sheet schema and taxonomy documentation
├── spot_check_100.xlsx         # 100-event manual validation workbook (100% score)
├── dataset_statistics.ipynb    # Executed Jupyter notebook with rendered figures & tables
├── scraper.py                  # Step 2 announcement scraping & deduplication code
├── ohlcv_fetch.py              # Step 3 market data fetch & T0 session alignment code
├── label_compute.py            # Step 4 price shock & volatility labeling code
├── quality_check.py            # Step 5 quality assurance and spot-check sampling code
├── requirements.txt            # Pinned dependency requirements
└── README.md                   # Full methodology, usage, and provenance guide
```

* **Final Submission Archive:** [`StudentName_Objective1.zip`](file:///c:/Users/ronad/OneDrive/Desktop/Projects/major-project/StudentName_Objective1.zip) (2.56 MB)
* **Status:** Complete, reproducible, and ready for supervisor review / repository release.
