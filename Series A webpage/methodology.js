/**
 * Methodology & API page (SIH 2026) — Airfare Price Index.
 * Controller: theme, header state, scroll reveal, system-map details,
 * API console toggles.
 */

/* ==========================================================================
   THEME
   ========================================================================== */
const methState = {
  theme: localStorage.getItem('api_theme') || 'dark'
};

function initTheme() {
  applyTheme(methState.theme);
  const btn = document.getElementById('theme-toggle-btn');
  if (btn) {
    btn.addEventListener('click', () => {
      const next = methState.theme === 'light' ? 'dark' : 'light';
      applyTheme(next);
    });
  }
}

function applyTheme(theme) {
  methState.theme = theme;
  document.documentElement.setAttribute('data-theme', theme);
  localStorage.setItem('api_theme', theme);

  const moon = document.getElementById('theme-icon-moon');
  const sun = document.getElementById('theme-icon-sun');
  if (moon && sun) {
    moon.style.display = theme === 'dark' ? 'none' : 'block';
    sun.style.display = theme === 'dark' ? 'block' : 'none';
  }
}

/* ==========================================================================
   HEADER + REVEAL
   ========================================================================== */
function initHeader() {
  const header = document.getElementById('methodology-header');
  window.addEventListener('scroll', () => {
    header?.classList.toggle('scrolled', window.scrollY > 20);
  });
}

function initReveal() {
  const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) entry.target.classList.add('visible');
    });
  }, { threshold: 0.08 });
  document.querySelectorAll('.reveal-section').forEach(sec => observer.observe(sec));
}

/* ==========================================================================
   SYSTEM MAP — stage details
   ========================================================================== */
const ARCH_STAGES = [
  { name: 'Airlines + OTAs', desc: 'Source fares originate on airline websites and, as OTA partnerships complete, on travel aggregators. These are observed data, not estimates.' },
  { name: 'Automated Web Scrapers', desc: 'Polite, scheduled crawls capture fares for defined corridors and booking horizons continuously, with no manual data entry.' },
  { name: 'Raw Fare Store', desc: 'Every quote is persisted with route, airline, flight number, fare class, departure date and an ISO scrape timestamp for traceability.' },
  { name: 'Data Cleaning & Validation', desc: 'Schema checks, missing-value handling, deduplication and outlier detection run before any statistic is drawn from the quotes.' },
  { name: 'Fare Normalization', desc: 'Fare fields, currency, timestamps, route codes, airline identifiers and booking horizons are standardized into one comparable definition.' },
  { name: 'Route + Lead-Time Aggregation', desc: 'Valid quotes are grouped by route × booking horizon and summarized with robust medians — an observed fare profile, not a forecast.' },
  { name: 'DGCA Traffic Weights', desc: 'Route weights follow passenger traffic so the national index represents the market rather than averaging every route equally.' },
  { name: 'Airfare Price Index', desc: 'Weighted aggregation of route-level price relatives produces the national APIx, rebased so the reference scrape window equals 100.' },
  { name: 'Dashboard + API', desc: 'The index, cleaned observations and quality statistics are exposed through the live dashboard and the documented API.' }
];

function initArch() {
  const rail = document.getElementById('methArchRail');
  const nameEl = document.getElementById('methArchName');
  const descEl = document.getElementById('methArchDesc');
  if (!rail || !nameEl || !descEl) return;

  const nodes = Array.from(rail.querySelectorAll('.meth-arch-node'));
  const set = (idx) => {
    nodes.forEach((n, i) => n.classList.toggle('active', i === idx));
    if (idx === -1) {
      nameEl.textContent = 'Select a stage';
      descEl.textContent = 'Each stage of the pipeline turns raw web observations into a cleaner, more decision-ready artifact — ending in the index and its API.';
    } else {
      nameEl.textContent = ARCH_STAGES[idx].name;
      descEl.textContent = ARCH_STAGES[idx].desc;
    }
  };

  nodes.forEach((node, idx) => {
    node.addEventListener('mouseenter', () => set(idx));
    node.addEventListener('focus', () => set(idx));
    node.addEventListener('blur', () => set(-1));
  });
  nodes[0].addEventListener('mouseleave', () => set(-1));
  set(0);
}

/* ==========================================================================
   API CONSOLE — per-endpoint example responses
   ========================================================================== */
const API_EXAMPLES = [
  { route: '/api/v1/index/latest', body: `{
  "api": 98.29,
  "base": 100,
  "reference": "scrape window",
  "as_of": "2026-09-05",
  "corridors": 4
}` },
  { route: '/api/v1/index/history', body: `{
  "series": "APIx",
  "unit": "index",
  "base": 100,
  "windows": ["2026-09-03", "2026-09-04", "2026-09-05"],
  "latest": 98.29
}` },
  { route: '/api/v1/routes', body: `{
  "routes": 4,
  "weights": [
    { "route": "DEL-BOM", "weight_pct": 38.1 },
    { "route": "BLR-DEL", "weight_pct": 26.9 },
    { "route": "BLR-BOM", "weight_pct": 17.8 },
    { "route": "DEL-HYD", "weight_pct": 17.3 }
  ]
}` },
  { route: '/api/v1/routes/{route}', body: `{
  "route": "DEL-BOM",
  "horizons": {
    "T+7": 6979, "T+15": 6979,
    "T+30": 7138, "T+45": 7636
  },
  "T+1": "rollout"
}` },
  { route: '/api/v1/fares', body: `{
  "corridors": 4,
  "valid_quotes": 1967,
  "aggregation": "median per route x horizon",
  "sources": 1
}` },
  { route: '/api/v1/quality', body: `{
  "valid_quotes": 1967,
  "total_quotes": 2010,
  "outlier_rate_pct": 2.1,
  "missing_rate_pct": 0,
  "latest_scrape": "2026-09-05",
  "scraper_health": "operational"
}` }
];

function initApiConsole() {
  const tryBtns = Array.from(document.querySelectorAll('.meth-try'));
  const panel = document.getElementById('methTryPanel');
  const code = document.getElementById('methTryCode');
  if (!panel || !code) return;

  const show = (idx) => {
    const ex = API_EXAMPLES[idx];
    code.textContent = `GET ${ex.route}\n${ex.body}`;
    panel.hidden = false;
  };

  tryBtns.forEach((btn, idx) => {
    btn.addEventListener('click', () => {
      const active = btn.classList.contains('active');
      tryBtns.forEach(b => b.classList.remove('active'));
      if (active) {
        panel.hidden = true;
        return;
      }
      btn.classList.add('active');
      show(idx);
    });
  });

  const docsBtn = document.getElementById('methDocsBtn');
  const docsNote = document.getElementById('methDocsNote');
  if (docsBtn && docsNote) {
    docsBtn.addEventListener('click', () => {
      docsNote.hidden = !docsNote.hidden;
    });
  }
}

/* ==========================================================================
   BOOT
   ========================================================================== */
document.addEventListener('DOMContentLoaded', () => {
  initTheme();
  initHeader();
  initReveal();
  initArch();
  initApiConsole();
});