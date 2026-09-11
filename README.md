# ✈️ Airlines Web Scraper & Dashboard

An automated flight fare scraping and tracking system built to extract, clean, and visualize airline ticket pricing, routes, and schedules across major carriers.

---

## 📌 Features

- **Automated Web Scraping:** Extracts flight numbers, routes, departure/arrival times, layovers, and real-time fares.
- **Dynamic Content Handling:** Handles JavaScript-rendered flight aggregators and booking engines.
- **Data Export & Processing:** Formats and saves structured flight records (`CSV` / `JSON`) for downstream analysis.
- **Frontend Interface:** Dedicated dashboard (`/Frontend`) to view, filter, and compare flight prices across dates and routes.

---

## 🏗️ Repository Structure

```text
AirlinesWebScraper/
├── Frontend/             # Web interface (Dashboard, UI components, assets)
├── scrapers/             # Scraper modules and extraction pipelines
├── data/                 # Output datasets (CSV / JSON)
├── requirements.txt      # Python dependencies
├── .gitignore
└── README.md
