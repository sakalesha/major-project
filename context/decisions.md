# NiftyEvent-50: Methodology & Pipeline Decisions

This document records the frozen methodology decisions, empirical data validations, and mathematical definitions for the **NiftyEvent-50** dataset pipeline (Objective 1). All decisions are grounded in the project requirements ([`NiftyEvent50_PRD.md`](file:///c:/Users/ronad/OneDrive/Desktop/Projects/major-project/context/NiftyEvent50_PRD.md), [`Objective1_CorporateEvent_Dataset.pdf`](file:///c:/Users/ronad/OneDrive/Desktop/Projects/major-project/context/Objective1_CorporateEvent_Dataset.pdf)) and verified against the 50 company announcement files in [`data/`](file:///c:/Users/ronad/OneDrive/Desktop/Projects/major-project/data).

---

## 1. Empirical Data Verification Summary

Prior to freezing decisions, an exhaustive analysis of all 50 CSV files in the `data/` folder was performed:
* **Raw Announcements Found:** 87,778 records spanning from 2003 through 2026.
* **Target Period (2018–2024):** 49,690 announcements fall within the approved 6-year window.
* **Post-Deduplication Qualifying Events:** **3,441 events** across the 5 approved event categories after applying the $\pm 2$-day deduplication rule. This confirms that the research target of **$\ge 3,000$ labeled events** is comfortably achieved.
* **Stock Coverage:** Exactly 50 unique tickers exist in the dataset; all 50 (100%) successfully resolve on Yahoo Finance with the `.NS` suffix.
* **Announcement Timing Distribution:**
  * Market Hours (09:15–15:30 IST weekdays): **32.9%** (28,868 rows)
  * After-Hours / Pre-Market (weekdays): **61.6%** (54,066 rows)
  * Weekends (Saturday / Sunday): **5.5%** (4,844 rows)
  * **Key takeaway:** Over **67.1%** of corporate announcements occur outside active exchange trading hours.

---

## 2. Frozen Decisions & Execution Rules

### Decision 1: Trading Session Alignment ($T_0$ Rule)
* **Rule:** An event's effective trading date $T_0$ is defined as the first trading session in which the market can absorb and trade on the news:
  * Announcements broadcast on Monday–Friday between **09:15 and 15:30 IST** $\rightarrow$ $T_0 = \text{Announcement Date}$ (same day).
  * Announcements broadcast on Monday–Friday **after 15:30 IST** or **before 09:15 IST** $\rightarrow$ $T_0 = \text{Next active NSE trading day}$.
  * Announcements broadcast on **weekends or exchange holidays** $\rightarrow$ $T_0 = \text{Next active NSE trading day}$.
* **Traceability:** The raw broadcast date and timestamp are preserved in internal audit metadata; the calendar announcement date is stored in the final `date` column.

---

### Decision 2: Price Series Convention (Adjusted Close)
* **Decision:** All price calculations use split- and bonus-adjusted closing prices (`Adj Close` from `yfinance`).
* **Rationale:** Between 2018 and 2024, the dataset contains **29 Bonus Issues** and **15 Stock Splits**. Using unadjusted raw `Close` would produce artificial, mechanical price drops of -50% to -80% in `shock_pct`, severely distorting the labels.

---

### Decision 3: Volatility Spike Definition & Formula
* **Daily Return Formula:**
  $$R_t = \frac{P_t - P_{t-1}}{P_{t-1}}$$
* **Event Window Volatility ($\sigma_{\text{window}}$):** Sample standard deviation of daily returns across the **8-session event window** ($T_{-3}$ to $T_{+5}$, 8 trading sessions).
* **Baseline Volatility ($\sigma_{\text{baseline}}$):** Average rolling 30-trading-day standard deviation calculated over the **30 trading sessions strictly preceding the event window** ($T_{-33}$ to $T_{-4}$). This guarantees zero look-ahead data leakage.
* **Volatility Spike Label:**
  $$\text{volatility\_label} = \begin{cases} \text{Yes}, & \text{if } \sigma_{\text{window}} > 1.5 \times \sigma_{\text{baseline}} \\ \text{No}, & \text{otherwise} \end{cases}$$
* **Insufficient History Policy:** If a stock has fewer than 30 trading sessions of historical data prior to $T_{-4}$ (e.g., recent listings), record `volatility_label` as `No` and log a warning in `retrieval_failures.csv`.

---

### Decision 4: Price Windows & Event Date Exclusion
* **Pre-Event Price (`pre_event_price`):** Arithmetic mean of closing prices across the 3 eligible trading sessions immediately prior to the event:
  $$\text{pre\_event\_price} = \frac{P_{T-3} + P_{T-2} + P_{T-1}}{3}$$
* **Post-Event Price (`post_event_price`):** Arithmetic mean of closing prices across the 5 eligible trading sessions immediately following the event:
  $$\text{post\_event\_price} = \frac{P_{T+1} + P_{T+2} + P_{T+3} + P_{T+4} + P_{T+5}}{5}$$
* **Day $T_0$ Treatment:** The event trading session $T_0$ is explicitly excluded from both the pre-event and post-event averages to prevent intra-day spillover.
* **Missing Session Tolerance:** Forward-fill is permitted for at most 1 missing trading session per window. Any event record with $\ge 2$ missing sessions across the 8-day window is excluded with the reason recorded in quality logs.

---

### Decision 5: Price Shock and Direction Labels
* **Price Shock Percentage:**
  $$\text{shock\_pct} = \left(\frac{\text{post\_event\_price} - \text{pre\_event\_price}}{\text{pre\_event\_price}}\right) \times 100$$
* **Direction Label:**
  $$\text{direction\_label} = \begin{cases} \text{Up}, & \text{if } \text{shock\_pct} > +0.5\% \\ \text{Down}, & \text{if } \text{shock\_pct} < -0.5\% \\ \text{Neutral}, & \text{if } -0.5\% \le \text{shock\_pct} \le +0.5\% \end{cases}$$
* **Boundary Case:** Exact boundaries $+0.50\%$ and $-0.50\%$ are classified as `Neutral`.

---

### Decision 6: Handling Multi-Event Board Meeting Announcements
* **Decision:** When a single company filing announces both quarterly financial results and a dividend declaration (e.g., *"Approval of Audited Financial Results and Recommendation of Final Dividend"*), the pipeline will generate **two distinct event records** sharing the same timestamp:
  1. One record with `event_type = 'Earnings Surprise (Beat/Miss)'`
  2. One record with `event_type = 'Dividend Declaration'`
* **Rationale:** Indian corporations routinely combine quarterly results and dividend payouts in a single board meeting outcome under SEBI LODR Regulation 30/33. Assigning single-event precedence would discard nearly 50% of legitimate dividend announcements.

---

### Decision 7: Approved Event Taxonomy & Canonical Strings
The 5 canonical strings for the `event_type` column in `NiftyEvent50_final.csv` are:
1. `Dividend Declaration`
2. `Bonus Issue`
3. `Stock Split`
4. `Earnings Surprise (Beat/Miss)`
5. `Management Change`

*Note on Earnings Surprise:* Official NSE regulatory filings report audited/unaudited financial results rather than analyst consensus numbers. In line with the research design, the price shock and direction label (`Up` = Beat, `Down` = Miss) operationalize the market-evaluated surprise.

---

### Decision 8: Sector Mapping (The 11-Sector Taxonomy)
* **Approved Sectors:** `IT`, `Banking`, `Energy`, `FMCG`, `Auto`, `Pharma`, `Metal`, `Realty`, `Telecom`, `Finance`, `Infra`.
* **Company Sector Distribution:**
  * **IT (4):** TCS, INFY, HCLTECH, TECHM
  * **Banking (5):** HDFCBANK, ICICIBANK, KOTAKBANK, AXISBANK, SBIN
  * **Energy (5):** RELIANCE, ONGC, NTPC, POWERGRID, COALINDIA
  * **FMCG (5):** HINDUNILVR, ITC, NESTLEIND, TATACONSUM, ASIANPAINT
  * **Auto (5):** MARUTI, M&M, BAJAJ-AUTO, EICHERMOT, TMPV
  * **Pharma (5):** SUNPHARMA, CIPLA, DRREDDY, APOLLOHOSP, MAXHEALTH
  * **Metal (3):** TATASTEEL, JSWSTEEL, HINDALCO
  * **Finance (7):** BAJFINANCE, BAJAJFINSV, SHRIRAMFIN, HDFCLIFE, SBILIFE, JIOFIN, BSE
  * **Infra (7):** LT, ADANIENT, ADANIPORTS, ULTRACEMCO, GRASIM, BEL, INDIGO
  * **Telecom (1):** BHARTIARTL
* **Realty Sector Documentation:** None of the 50 provided stocks in `data/` are real estate developers (e.g., DLF or Godrej Properties). The data dictionary and README will formally document that the 50 provided companies represent 10 of the 11 taxonomy sectors with 0 Realty constituents.

---

### Decision 9: Precision & Output Formatting
* **Decimal Precision:**
  * `pre_event_price`: 2 decimal places (e.g., `2105.30`)
  * `post_event_price`: 2 decimal places (e.g., `2198.75`)
  * `shock_pct`: 2 decimal places (e.g., `+4.44` or `-1.25`)
* **Final Schema (Strict 9 Columns):**
  `date`, `ticker`, `sector`, `event_type`, `pre_event_price`, `post_event_price`, `shock_pct`, `volatility_label`, `direction_label`.

---

### Decision 10: Deliverables & Submission Archive
* Submission directory: `StudentName_Objective1/`
* Archive: `StudentName_Objective1.zip`
* Required files:
  1. `raw_events.csv`
  2. `ohlcv_windows/`
  3. `NiftyEvent50_final.csv`
  4. `data_dictionary.xlsx`
  5. `spot_check_100.xlsx`
  6. `dataset_statistics.ipynb`
  7. `scraper.py`
  8. `ohlcv_fetch.py`
  9. `label_compute.py`
  10. `requirements.txt`
  11. `README.md`
