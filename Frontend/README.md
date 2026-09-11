# 🇮🇳 Airfare Price Index – Augmenting CPI (SIH 2026)

> **Real-time high-frequency Indian airfare analytics & Consumer Price Index (CPI) augmentation dashboard.**
> Designed for Smart India Hackathon 2026 (MoSPI & Ministry of Civil Aviation Analytics).

---

## 📁 Project Structure

```text
airfare-index-dashboard/
├── index.html           # Main semantic HTML5 dashboard & interactive modals
├── cpi.html             # CPI augmentation explainer page
├── methodology.html     # Methodology & API documentation page
├── styles.css           # Premium institutional design system (Dark & Light theme, 8px grid)
├── app.js               # Application controller (Chart.js charts, filters, animations)
├── cpi.css              # CPI page styles
├── methodology.css      # Methodology page styles
├── cpi.js               # CPI page logic
├── methodology.js       # Methodology page logic
├── data.js              # Normalized dataset (series, 16 sub-indices, decay, surges, forecast)
├── assets/
│   └── narendra_modi.jpg # Official high-res portrait for leadership spotlight
├── pipeline/            # Optional data-rebuild scripts (see README below)
│   ├── update_site.py   # Scans raw scrape CSVs, merges into final_scraper.csv, rebuilds data.js
│   ├── build_final.py   # Regenerates data.js from final_scraper.csv
│   └── final_scraper.csv # Current normalized dataset (2010 quotes, Air India Economy)
└── README.md            # Documentation & development guide
```

---

## 🚀 How to Run

### Option 1: Instant Direct Open (No Installation Needed)
Simply **double-click `index.html`** in your file explorer to open it in any web browser (Chrome, Edge, Firefox, Safari).

### Option 2: VS Code Live Server
1. Open the `airfare-index-dashboard` folder in **VS Code**.
2. Right-click `index.html` and click **"Open with Live Server"**.

### Option 3: Python Local Server
```bash
cd airfare-index-dashboard
python -m http.server 8000
```
Open **`http://localhost:8000`** in your browser.

### Option 4: Node.js / npx serve
```bash
cd airfare-index-dashboard
npx serve .
```

---

## 🧩 Key Components & Features

1. **Cinematic Opening Takeoff Visual**:
   - Supersonic jet animated flight across the screen with tricolor contrail jetstream on initial page open.
   - Replay button in header to re-trigger the flight visual anytime.

2. **Government Leadership Spotlight**:
   - Hon'ble Prime Minister Shri Narendra Modi spotlight banner with leadership vision quote and national initiative badges.

3. **Composite Index & Forecast-First Hero**:
   - Dynamic count-up KPI (`102.40`) with glowing backdrop.
   - **7-day day-wise fare forecast (₹) for all 4 corridors** with solid history → dashed forecast segments and 80% CI tooltips.
   - **Airfare vs GOI CPI comparison chart** (official CPI vs Airfare Index, both normalised to May = 100) with CPI impact readout (`+0.004 pp`).

4. **Interactive Domestic Corridor Map**:
   - SVG network map showing major trunk corridors (DEL-BOM, BLR-DEL, BLR-BOM, DEL-HYD) with animated flight arcs, floating fare chips, and pulsing surge beacon at Bengaluru.
   - Clicking on any arc filters the matrix and charts automatically.

5. **Route × Horizon Matrix with 16 Inline Sparklines**:
   - 4 trunk routes × 4 booking horizons ($T+7, T+15, T+30, T+45$).
   - Embedded SVG micro-sparklines inside each table cell tracking price trajectory.
   - Interactive modal drill-downs on cell click.

6. **Fare-Decay Curve & CPI Augmentation**:
   - Dynamic multi-route advance booking decay curve.
   - CPI inflation shift calculation ($+0.004\text{ pp}$ contribution based on $0.20\%$ basket weight).

7. **7-Day Price Forecast Section (Corridor-wise)**:
   - Per-route forecast cards: today's fare → day-7 projected fare (₹), % move, 80% confidence band and 7-day trajectory sparkline.
   - Price-based forecast (no index abstraction) built from damped mean-reversion + booking-horizon momentum.

8. **Theme Toggle**:
   - Instant 1-click toggle between institutional Light Mode and Bloomberg/Terminal Dark Mode with `localStorage` persistence.

9. **Data Export**:
   - Direct CSV export of all sub-indices and surge statuses.

---

## 🛠️ How to Extend & Connect Your Backend

To feed live scraped data or an API into this frontend:

1. **Connecting a Live REST API / Flask / FastAPI Backend**:
   - In `app.js`, replace `window.PORTAL_DATA` references with a `fetch('/api/latest-index')` call.
2. **Adding New Routes**:
   - Add new route codes and weights in `data.js` under `routes` and `heatmap`.
3. **Connecting Database**:
   - Store historical flight scrapes in PostgreSQL/MongoDB and output the JSON structure matching `data.js`.

---

## 🏛️ Methodological References (MoSPI Aligned)

- **Laspeyres Price Relatives**: $I_t = \sum_{r} \sum_{w} W_{r,w} \cdot \left(\frac{P_{r,w,t}}{P_{r,w,0}}\right) \times 100$
- **MAD Surge Anomaly Filter**: $\text{Surge Trigger} = P_t > \text{Median} + 2.0 \times \text{MAD}$
- **CPI Impact Formulation**: $\Delta \text{CPI} = w_{\text{air}} \times \left(\frac{I_t - 100}{100}\right) \times \text{CPI}_{\text{base}}$
