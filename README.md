# ✈️ AirIndex (APIx) — Real-Time Airfare Price Index for India

> Built for **Smart India Hackathon 2026** — Problem Statement **SIH26056**
> Theme: Smart Automation · Category: Software · Team: **Serie A**

---

## 📌 The Problem

India's Consumer Price Index (CPI) — the number used to measure inflation — is only updated **once a month**. But airfares don't move monthly, they move **by the hour**, driven by demand, booking window, seasonality, and disruptions (fuel prices, geopolitical events, capacity shocks). This creates a real data gap: short-term airfare movements are completely invisible to official inflation tracking until the next monthly CPI release catches up, weeks later.

**AirIndex (APIx)** closes that gap. It's a real-time, high-frequency airfare index built to *augment* the transport sub-component of the CPI — giving MoSPI (Ministry of Statistics and Programme Implementation) and the Ministry of Civil Aviation a continuously updated signal that sits alongside the official monthly number, instead of replacing it.

---

## 🛠️ What It Actually Does

1. **Scrapes** live economy-class fares directly from Air India's website using browser automation
2. **Cleans** the raw fares — removes duplicates and statistical outliers (IQR-based)
3. **Aggregates** fares per route and booking-window using the **median** fare
4. **Builds an index** — a Laspeyres-style, Base-100 composite index (APIx) from those aggregated fares
5. **Forecasts** 7 days ahead using a damped-trend model, and flags fare **surges** automatically
6. **Presents** everything on a live, offline-capable dashboard with route views, booking-window comparisons, and a fare-surge heatmap

---

## ✈️ Why Only Air India?

Before building the scraper, we evaluated several airlines and OTA (Online Travel Aggregator) platforms as potential data sources. Most of them explicitly **disallow automated access through their `robots.txt` files** — scraping past that isn't ethical and isn't something we're willing to do, regardless of how it might help the project.

**Air India was the one platform where ethical, permitted scraping was possible.** So this prototype is built entirely on Air India Economy fares, across 4 domestic trunk routes:

- **DEL–BOM** (Delhi–Mumbai)
- **BLR–DEL** (Bengaluru–Delhi)
- **BLR–BOM** (Bengaluru–Mumbai)
- **DEL–HYD** (Delhi–Hyderabad)

The system is fully **config-driven** — adding more airlines or OTAs (wherever permitted) or more routes later doesn't require rebuilding the pipeline, just updating the config.

### How the scraper works (technical summary)

Rather than reading rendered HTML off the page (fragile, breaks with any UI change), the scraper:
- Drives a real Chromium browser via **Playwright**, filling out Air India's actual search form like a human would
- **Intercepts Air India's internal API response** (`air-bounds`) — the raw structured JSON that powers the flight cards — before the page even finishes rendering
- Falls back to HTML parsing only if API interception fails
- Runs a fresh browser session per route/booking-window (Air India silently drops repeat searches on a shared session) and waits a randomized 5–9 second delay between requests to stay well within polite, non-aggressive scraping limits
- Retries failed searches up to 3 times, with full browser-crash recovery if Chromium itself dies mid-run

---

## ⚠️ Current Dataset — Please Read

The `final_scraper.csv` included in this repo is a **3-day test collection window, scraped from 3rd to 5th September 2026**, covering all 4 routes across all 4 booking horizons (T+7, T+15, T+30, T+45).

**This is a prototype-stage dataset, not a production-scale one.** 3 days of data is enough to prove the entire pipeline works end-to-end — scraping, cleaning, indexing, forecasting, and visualization, all running on real, live-scraped data — but it is **not enough history to draw firm conclusions about long-term trends or volatility**. The architecture is built to keep running and accumulating data; the same system run over months would produce a genuinely robust, trend-validated index.

- Raw scraped rows: **2,010**
- Duplicates removed: **138**
- Final clean observations: **1,872**

---

## 📁 Repository Structure

```text
airlineswebscraper/
├── frontend/              # Dashboard — HTML/CSS/JS, Chart.js visualizations
│   ├── index.html         # Main dashboard
│   ├── cpi.html           # CPI augmentation explainer page
│   ├── methodology.html   # Methodology & API docs page
│   ├── styles.css / cpi.css / methodology.css
│   ├── app.js / cpi.js / methodology.js
│   └── data.js            # Normalized dataset consumed by the dashboard
├── scraper/                # Playwright-based Air India fare scraper
│   └── scraper_t15.py      # (one scraper file per booking window)
├── pipeline/                # Data cleaning + index-building scripts
│   ├── update_site.py      # Merges raw scraped CSVs into final_scraper.csv
│   └── build_final.py      # Cleans, deduplicates, aggregates, builds data.js
├── final_scraper.csv        # 3-day test dataset (3–5 Sept 2026)
├── .gitignore
└── README.md
```

---

## 🚀 How to Run the Dashboard

**Option 1 — Just open it:**
Double-click `frontend/index.html` in any browser.

**Option 2 — Local server:**
```bash
cd frontend
python -m http.server 8000
```
Then open `http://localhost:8000`.

## 🐍 How to Run the Scraper

```bash
pip install playwright pandas
playwright install chromium
cd scraper
python scraper_t15.py --headless
```

## 🔁 How to Rebuild the Index from Scraped Data

```bash
cd pipeline
python build_final.py
```
This reads `final_scraper.csv`, cleans and deduplicates it, aggregates fares by route × booking window using the median, removes outliers via an IQR-based cutoff, and regenerates `frontend/data.js` for the dashboard.

---

## 📐 Methodology (MoSPI-Aligned)

- **Aggregation:** Median fare per (route × booking window), computed after outlier removal
- **Outlier detection:** Any fare exceeding `median + 2.5 × IQR` is flagged and excluded
- **Index formula (Laspeyres-style):**

$$I_t = \sum_{r} \sum_{w} W_{r,w} \cdot \left(\frac{P_{r,w,t}}{P_{r,w,0}}\right) \times 100$$

- **Forecast:** 7-day damped-trend forecast (trend continues, but its influence shrinks with each day forecasted, rather than extrapolating a straight line indefinitely)
- **Surge detection:** Fares statistically far above the recent median for that route/window are flagged as a surge

---

## 🎯 Impact

- **For policy:** A high-frequency alternate-data input that fills the gap between monthly CPI releases, specifically for the transport/airfare sub-component
- **For travelers:** Early surge alerts and forward-looking fare visibility, helping consumers plan more affordable travel

---

## 🏛️ References

- [airindia.com](https://www.airindia.com)
- [dgca.gov.in](https://www.dgca.gov.in) — Directorate General of Civil Aviation
- [mospi.gov.in](https://www.mospi.gov.in) — Ministry of Statistics and Programme Implementation

---

*Built by Team Serie A for Smart India Hackathon 2026.*
