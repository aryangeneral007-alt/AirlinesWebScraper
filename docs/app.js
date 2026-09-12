/**
 * Airfare Price Index – Augmenting CPI (SIH 2026)
 * Premium Institutional Dashboard Controller (with Opening Flight Visual)
 */

// Application State
const state = {
  selectedRoute: 'all',
  selectedWindow: 'all',
  activeDecayRoutes: new Set(['DEL-BOM', 'BLR-DEL', 'BLR-BOM', 'DEL-HYD']),
  theme: localStorage.getItem('api_theme') || 'dark',
  airline: 'all',
  fareType: 'median',
  dateFrom: '2026-09-10',
  dateTo: '2026-10-20',
  routeAnalysisRoute: 'DEL-BOM',
  charts: {}
};

const ROUTE_CONFIG = {
  'DEL-BOM': { name: 'Delhi ⇄ Mumbai', color: '#0F2A43', colorDark: '#60A5FA', weight: '35%' },
  'BLR-DEL': { name: 'Bengaluru ⇄ Delhi', color: '#0284C7', colorDark: '#38BDF8', weight: '30%' },
  'BLR-BOM': { name: 'Bengaluru ⇄ Mumbai', color: '#DC2626', colorDark: '#F87171', weight: '20%' },
  'DEL-HYD': { name: 'Delhi ⇄ Hyderabad', color: '#D97706', colorDark: '#FBBF24', weight: '15%' }
};

const WINDOW_CONFIG = {
  '7': { label: 'T+7', desc: '0–7 days' },
  '15': { label: 'T+15', desc: '8–15 days' },
  '30': { label: 'T+30', desc: '16–30 days' },
  '45': { label: 'T+45', desc: '31–45 days' }
};

const CELL_SPARKLINE_TRENDS = {};

/* Demo corridor fares — not used with single-dataset build */

const DEMO_ROUTE_COLORS = {};

function mergeRouteConfig() {
  const basket = window.PORTAL_DATA?.basket?.routes || [];
  basket.forEach(r => {
    if (ROUTE_CONFIG[r.code]) {
      if (!ROUTE_CONFIG[r.code].carrier && r.carrier) ROUTE_CONFIG[r.code].carrier = r.carrier;
      return;
    }
    const c = DEMO_ROUTE_COLORS[r.code] || { color: '#64748B', colorDark: '#94A3B8' };
    ROUTE_CONFIG[r.code] = {
      name: r.name || r.code,
      weight: Math.round((r.weight || 0) * 100) + '%',
      demo: !!r.demo || r.status === 'demo',
      carrier: r.carrier || '',
      color: c.color,
      colorDark: c.colorDark
    };
  });
}

document.addEventListener('DOMContentLoaded', () => {
  initTheme();
  mergeRouteConfig();
  initScrollEffects();
  initProgressRail();
  initPriceHeatmap();
  initSurgeMonitor();
  initMapInteractions();
  initCharts();
  initRouteAnalysis();
  initDecayLegend();
  initEventListeners();
  initHeroKpi();
});

/* ==========================================================================
   HERO KPI — initial count-up on page load
   ========================================================================== */
function initHeroKpi() {
  const idx = window.PORTAL_DATA?.meta?.latest_index || 98.29;
  animateCountUp(document.getElementById('hero-kpi-number'), 95.0, idx, 1100);
  updateHeroDelta();
}

/* ==========================================================================
   THEME MANAGEMENT (Dark / Light)
   ========================================================================== */
function initTheme() {
  applyTheme(state.theme);
  const toggleBtn = document.getElementById('theme-toggle-btn');
  if (toggleBtn) {
    toggleBtn.addEventListener('click', () => {
      const nextTheme = state.theme === 'light' ? 'dark' : 'light';
      applyTheme(nextTheme);
    });
  }
}

function applyTheme(theme) {
  state.theme = theme;
  document.documentElement.setAttribute('data-theme', theme);
  localStorage.setItem('api_theme', theme);

  const moonIcon = document.getElementById('theme-icon-moon');
  const sunIcon = document.getElementById('theme-icon-sun');
  if (moonIcon && sunIcon) {
    moonIcon.style.display = theme === 'dark' ? 'none' : 'block';
    sunIcon.style.display = theme === 'dark' ? 'block' : 'none';
  }

  updateChartsTheme();
}

function updateChartsTheme() {
  const isDark = state.theme === 'dark';
  const gridColor = isDark ? '#141E2F' : '#EAEEF4';
  const textColor = isDark ? '#93A3B8' : '#64748B';

  Chart.defaults.color = textColor;

  if (state.charts.indexForecast) {
    state.charts.indexForecast.destroy();
    state.charts.indexForecast = null;
    renderIndexForecastChart();
  }

  if (state.charts.decay) {
    state.charts.decay.options.scales.y.grid.color = gridColor;
    state.charts.decay.data.datasets.forEach(ds => {
      const config = ROUTE_CONFIG[ds.label];
      if (config) {
        ds.borderColor = isDark ? config.colorDark : config.color;
        ds.backgroundColor = isDark ? config.colorDark : config.color;
        ds.pointBackgroundColor = isDark ? config.colorDark : config.color;
      }
    });
    state.charts.decay.update();
  }

  if (state.charts.trend) {
    state.charts.trend.options.scales.y.grid.color = gridColor;
    const c = state.charts.trend.data.datasets[0];
    if (c) c.borderColor = isDark ? '#60A5FA' : '#0284C7';
    state.charts.trend.update();
  }

  if (state.charts.backtest) {
    state.charts.backtest.options.scales.y.grid.color = gridColor;
    state.charts.backtest.update();
  }

  if (state.charts.routeAnalysis) {
    state.charts.routeAnalysis.destroy();
    state.charts.routeAnalysis = null;
    renderRouteAnalysis();
  }

  initDecayLegend();
}

/* ==========================================================================
   SCROLL EFFECTS & PROGRESS RAIL
   ========================================================================== */
function initScrollEffects() {
  const header = document.getElementById('app-header');
  window.addEventListener('scroll', () => {
    if (window.scrollY > 20) {
      header?.classList.add('scrolled');
    } else {
      header?.classList.remove('scrolled');
    }
  });

  const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.classList.add('visible');
      }
    });
  }, { threshold: 0.1 });

  document.querySelectorAll('.reveal-section').forEach(sec => observer.observe(sec));
}

function initProgressRail() {
  const dots = document.querySelectorAll('.rail-dot');
  const sections = ['sec-hero', 'sec-corridors', 'sec-heatmap'];

  window.addEventListener('scroll', () => {
    const scrollPos = window.scrollY + 200;
    sections.forEach((id, idx) => {
      const el = document.getElementById(id);
      if (el) {
        const top = el.offsetTop;
        const height = el.offsetHeight;
        if (scrollPos >= top && scrollPos < top + height) {
          dots.forEach(d => d.classList.remove('active'));
          dots[idx]?.classList.add('active');
        }
      }
    });
  });
}

function scrollToSection(id) {
  const el = document.getElementById(id);
  if (el) {
    const offset = 104;
    const pos = el.getBoundingClientRect().top + window.pageYOffset - offset;
    window.scrollTo({ top: pos, behavior: 'smooth' });
  }
}

/* ==========================================================================
   ANIMATED COUNT-UP & FUEL GAUGE
   ========================================================================== */
function animateCountUp(element, start, end, duration, digits) {
  if (!element) return;
  digits = digits || 2;
  const startTime = performance.now();
  
  function update(currentTime) {
    const elapsed = currentTime - startTime;
    const progress = Math.min(elapsed / duration, 1);
    const easeOut = 1 - Math.pow(1 - progress, 3);
    const currentVal = start + (end - start) * easeOut;
    element.innerText = currentVal.toFixed(digits);

    if (progress < 1) {
      requestAnimationFrame(update);
    } else {
      element.innerText = end.toFixed(digits);
    }
  }
  requestAnimationFrame(update);
}

/* ==========================================================================
   MATRIX TABLE WITH 16 INLINE SPARKELINES
   ========================================================================== */
function initPriceHeatmap() {
  const tbody = document.getElementById('price-heatmap-body');
  if (!tbody) return;
  tbody.innerHTML = '';

  const fareType = state.fareType || 'median';
  const fareKey = fareType === 'min' ? 'fares_min' : fareType === 'max' ? 'fares_max' : 'decay';
  const routeFares = window.PORTAL_DATA[fareKey] || window.PORTAL_DATA.decay;
  const routes = Object.keys(routeFares);
  const windows = ['7', '15', '30', '45'];
  const isDark = state.theme === 'dark';

  routes.forEach(route => {
    const isRouteVisible = (state.selectedRoute === 'all' || state.selectedRoute === route);
    if (!isRouteVisible) return;
    if (state.airline !== 'all' && ROUTE_CONFIG[route]?.carrier !== state.airline) return;

    const config = ROUTE_CONFIG[route];

    const fares = windows.map(w => routeFares[route]?.[w] ?? null);
    const valid = fares.filter(v => v != null);
    if (!valid.length) return;
    const min = Math.min(...valid);
    const max = Math.max(...valid);
    const mid = valid.reduce((a, b) => a + b, 0) / valid.length;

    const tr = document.createElement('tr');
    tr.dataset.route = route;

    const tdRoute = document.createElement('td');
    tdRoute.innerHTML = `
      <span class="route-cell-title">${route}</span>
      <span class="route-cell-sub">${config?.name}</span>
    `;
    tr.appendChild(tdRoute);

    windows.forEach((win, i) => {
      const td = document.createElement('td');
      const v = fares[i];
      const isWindowSelected = (state.selectedWindow === 'all' || state.selectedWindow === win);
      if (v == null) {
        td.innerHTML = '<span style="font-size:11px;color:var(--text-muted);">—</span>';
        tr.appendChild(td);
        return;
      }

      const t = (max > min) ? (v - min) / (max - min) : 0.5;
      let bg, fg;
      if (t > 0.66) { bg = isDark ? 'rgba(220,38,38,0.30)' : 'rgba(254,226,226,0.95)'; fg = isDark ? '#FCA5A5' : '#B91C1C'; }
      else if (t > 0.33) { bg = isDark ? 'rgba(217,119,6,0.22)' : 'rgba(254,243,199,0.95)'; fg = isDark ? '#FCD34D' : '#B45309'; }
      else { bg = isDark ? 'rgba(22,163,74,0.22)' : 'rgba(220,252,231,0.95)'; fg = isDark ? '#86EFAC' : '#15803D'; }

      const delta = v - mid;
      const deltaPct = (delta / mid) * 100;
      const deltaCls = deltaPct > 3 ? 'up' : deltaPct < -3 ? 'down' : 'mod';
      td.innerHTML = `
        <div class="cell-interactive-card ${!isWindowSelected ? 'opacity-40' : ''}"
             style="background:${bg};"
             onclick="showCellDetails('${route}', '${win}')"
             title="Inspect ${route} (T+${win})">
          <span class="cell-num num-tabular" style="color:${fg};">₹${Number(v).toLocaleString('en-IN')}</span>
          <span class="price-cell-delta ${deltaCls}">${delta >= 0 ? '▲' : '▼'} ${Math.abs(deltaPct).toFixed(1)}%</span>
        </div>
      `;
      tr.appendChild(td);
    });

    tbody.appendChild(tr);
  });
}

function showCellDetails(route, win) {
  const cellKey = `${route}_${win}`;
  const cellData = window.PORTAL_DATA.cell_details?.[cellKey];
  const modal = document.getElementById('modal-cell-detail');
  const title = document.getElementById('cell-detail-title');
  const body = document.getElementById('cell-detail-body');
  
  if (!modal || !title || !body) return;

  const fare = window.PORTAL_DATA.decay[route]?.[win] || 0;
  const corridorFares = Object.values(window.PORTAL_DATA.decay[route] || {});
  const corridorMed = corridorFares.length ? corridorFares.sort((a,b)=>a-b)[Math.floor(corridorFares.length/2)] : 0;

  title.innerText = `${route} · T+${win} Horizon Analysis`;
  
  body.innerHTML = `
    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 14px;">
      <div style="background: var(--surface-subtle); padding: 10px; border-radius: 6px;">
        <div style="font-size: 11px; color: var(--text-muted);">Window Median Fare</div>
        <div style="font-size: 22px; font-weight: 800;" class="num-tabular">₹${Number(fare).toLocaleString('en-IN')}</div>
      </div>
      <div style="background: var(--surface-subtle); padding: 10px; border-radius: 6px;">
        <div style="font-size: 11px; color: var(--text-muted);">Corridor Median</div>
        <div style="font-size: 22px; font-weight: 800;" class="num-tabular">₹${Number(corridorMed).toLocaleString('en-IN')}</div>
      </div>
    </div>

    ${cellData ? `
      <div style="padding: 10px; border-radius: 6px; background: var(--red-light); border: 1px solid var(--red-border); margin-bottom: 12px;">
        <div style="display: flex; align-items: center; justify-content: space-between; font-weight: 700; color: var(--red-text);">
          <span>${cellData.badge} TRIGGERED</span>
          <span>${cellData.dev_pct} vs median</span>
        </div>
        <p style="font-size: 11px; margin-top: 2px;">${cellData.reason}</p>
      </div>
    ` : `
      <div style="padding: 8px; border-radius: 6px; background: var(--green-light); border: 1px solid var(--green-border); color: var(--green-text); font-size: 11px; margin-bottom: 12px;">
        ✓ Price relative is within normal variance distribution.
      </div>
    `}

    <div style="font-size: 11px; color: var(--text-muted);">
      Trunk Corridor Weight: <strong>${ROUTE_CONFIG[route]?.weight}</strong> · Horizon: <strong>${WINDOW_CONFIG[win]?.desc}</strong>
    </div>
  `;

  modal.classList.add('open');
}

function focusCell(route, win) {
  selectRouteFilter(route);
  showCellDetails(route, win);
}

/* ==========================================================================
   CHARTS INITIALIZATION
   ========================================================================= */
function initCharts() {
  Chart.defaults.font.family = "'Inter', sans-serif";
  Chart.defaults.color = state.theme === 'dark' ? '#93A3B8' : '#64748B';

  renderIndexForecastChart();
  renderDecayCurveChart();
}

function niceNiceStep(lo, hi, targetTicks) {
  const raw = (hi - lo) / (targetTicks || 6);
  const mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const norm = raw / mag;
  let step;
  if (norm >= 5) step = 5;
  else if (norm >= 2) step = 2;
  else step = 1;
  step *= mag;
  step = Math.max(step, 100);
  const loAdj = Math.floor(lo / step) * step;
  const hiAdj = Math.ceil(hi / step) * step;
  return { lo: loAdj, hi: hiAdj, step };
}

function crosshairPlugin() {
  return {
    id: 'crosshairPlugin',
    afterDraw(chart) {
      const { ctx, tooltip } = chart;
      if (!tooltip || tooltip.opacity === 0) return;
      const active = chart.getActiveElements();
      if (!active.length) return;
      const x = active[0].element.x;
      const area = chart.chartArea;
      if (!area) return;

      ctx.save();
      ctx.strokeStyle = 'rgba(148,163,184,0.45)';
      ctx.lineWidth = 1;
      ctx.setLineDash([5, 4]);
      ctx.beginPath();
      ctx.moveTo(x, area.top);
      ctx.lineTo(x, area.bottom);
      ctx.stroke();
      ctx.restore();
    }
  };
}

function renderIndexForecastChart() {
  const ctx = document.getElementById('indexForecastChart')?.getContext('2d');
  if (!ctx) return;

  const isDark = state.theme === 'dark';
  const fc = window.PORTAL_DATA.forecast;
  const series = window.PORTAL_DATA.series || [];
  const labels = fc.days;
  const start = fc.historical_days.length;

  const histVals = fc.historical_values;
  const pointVals = fc.forecast_point;
  const full = [...histVals, ...pointVals];

  // CI band across history (series) + 80% forecast band
  const bandLower = [...series.map(s => s.lower), ...fc.lower_band];
  const bandUpper = [...series.map(s => s.upper), ...fc.upper_band];

  // y-range across everything
  const loAll = Math.min(...full, ...bandLower, ...bandUpper);
  const hiAll = Math.max(...full, ...bandUpper);
  const pad = (hiAll - loAll) * 0.12 || 2;
  const yMin = Math.max(0, Math.floor(loAll - pad));
  const yMax = Math.ceil(hiAll + pad);

  const lineColor = isDark ? '#38BDF8' : '#0284C7';
  const bandFill = isDark ? 'rgba(56,189,248,0.14)' : 'rgba(2,132,199,0.10)';
  const bandEdge = isDark ? 'rgba(56,189,248,0.35)' : 'rgba(2,132,199,0.30)';

  const bandUpperDs = { label: '80% CI upper', data: bandUpper, borderColor: bandEdge, borderWidth: 1, borderDash: [3, 3], pointRadius: 0, tension: 0.3, fill: false };
  const bandLowerDs = { label: '80% CI lower', data: bandLower, borderColor: bandEdge, borderWidth: 1, borderDash: [3, 3], backgroundColor: bandFill, pointRadius: 0, tension: 0.3, fill: '-1' };
  const forecastDs = {
    label: 'Airfare CPI Index',
    data: full,
    borderColor: lineColor,
    backgroundColor: lineColor,
    fill: false,
    borderWidth: 2.4,
    pointRadius: (context) => (context.dataIndex < start ? 4 : 3),
    pointHoverRadius: 6,
    pointBackgroundColor: lineColor,
    pointBorderColor: isDark ? '#0D1626' : '#FFFFFF',
    pointBorderWidth: 1.5,
    tension: 0.3,
    borderDash: (context) => (context.dataIndex >= start - 1 ? [7, 5] : []),
    spanGaps: false
  };

  const refDs = {
    label: 'Base',
    data: labels.map(() => 100),
    borderColor: isDark ? 'rgba(148,163,184,0.5)' : 'rgba(100,116,139,0.45)',
    borderWidth: 1,
    borderDash: [4, 4],
    pointRadius: 0,
    fill: false,
    tension: 0
  };

  state.charts.indexForecast = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [bandUpperDs, bandLowerDs, forecastDs, refDs]
    },
    plugins: [crosshairPlugin()],
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      animation: { duration: 400 },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: isDark ? '#1E2E48' : '#0F2A43',
          padding: 10,
          cornerRadius: 8,
          displayColors: false,
          boxPadding: 4,
          titleFont: { weight: '700', size: 12 },
          filter: (item) => item.datasetIndex === 2,
          callbacks: {
            title: (items) => {
              const idx = items[0]?.dataIndex;
              return `${labels[idx]}${(idx ?? 0) >= start ? ' · forecast' : ''}`;
            },
            label: (ctx) => {
              const idx = ctx.dataIndex;
              const val = idx < start ? histVals[idx] : pointVals[idx - start];
              return ` Airfare CPI Index: ${val.toFixed(2)}`;
            },
            afterLabel: (ctx) => {
              const idx = ctx.dataIndex;
              if (idx < start) return '   observed';
              const lo = fc.lower_band[idx - start];
              const hi = fc.upper_band[idx - start];
              return `   forecast · 80% CI: ${lo.toFixed(2)} – ${hi.toFixed(2)}`;
            }
          }
        }
      },
      scales: {
        x: {
          grid: { display: false },
          ticks: { font: { size: 10 }, color: isDark ? '#93A3B8' : '#64748B', maxTicksLimit: 8 },
          title: {
            display: true,
            text: 'Date (3–12 Sep 2026)',
            font: { size: 10, weight: '700' },
            color: isDark ? '#93A3B8' : '#64748B'
          }
        },
        y: {
          min: yMin,
          max: yMax,
          grid: { color: isDark ? '#141E2F' : '#EAEEF4' },
          position: 'left',
          ticks: { font: { size: 10 }, callback: v => v.toFixed(1) },
          title: {
            display: true,
            text: 'Airfare CPI Index (base = 100)',
            font: { size: 10, weight: '700' },
            color: isDark ? '#93A3B8' : '#64748B'
          }
        }
      }
    }
  });
}

function initSurgeMonitor() {
  const wrap = document.getElementById('surge-monitor-rows');
  if (!wrap) return;
  wrap.innerHTML = '';

  const pf = window.PORTAL_DATA?.price_forecast?.routes;
  if (!pf) return;

  const order = ['DEL-BOM', 'BLR-DEL', 'BLR-BOM', 'DEL-HYD'];

  const AR_UP = `<svg class="surge-arrow" viewBox="0 0 12 12" width="11" height="11" fill="none" aria-hidden="true">
    <path d="M6 10V2M2.5 5.5 6 2l3.5 3.5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
  const AR_DOWN = `<svg class="surge-arrow" viewBox="0 0 12 12" width="11" height="11" fill="none" aria-hidden="true">
    <path d="M6 2v8M2.5 6.5 6 10l3.5-3.5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
  const AR_FLAT = `<svg class="surge-arrow" viewBox="0 0 12 12" width="11" height="11" fill="none" aria-hidden="true">
    <path d="M2 6h8" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>`;

  let html = '';
  order.forEach(route => {
    const r = pf[route];
    if (!r || !Array.isArray(r.hist) || r.hist.length < 2) return;

    const prev = r.hist[r.hist.length - 2];
    const today = r.hist[r.hist.length - 1];
    if (prev == null || today == null) return;

    const pct = ((today - prev) / prev) * 100;

    let tone, label, arrow;
    if (pct > 3) { tone = 'red'; label = 'Rise'; arrow = AR_UP; }
    else if (pct < -3) { tone = 'green'; label = 'Drop'; arrow = AR_DOWN; }
    else { tone = 'mod'; label = 'Moderate'; arrow = AR_FLAT; }

    const [from, to] = route.split('-');
    html += `
      <div class="surge-row">
        <div class="surge-route"><span>${from}</span><span class="surge-route-arrow">→</span><span>${to}</span></div>
        <div class="surge-move ${tone}">${arrow}${pct > 0 ? '+' : ''}${pct.toFixed(1)}%</div>
        <div class="surge-fare num-tabular">₹${Number(today).toLocaleString('en-IN')}</div>
        <div class="surge-tag ${tone}">${label}</div>
      </div>`;
  });

  wrap.innerHTML = html || '<div style="font-size:11px;color:var(--text-muted);padding:8px 0;">No change vs previous day</div>';
}

function renderDecayCurveChart() {
  const ctx = document.getElementById('decayCurveChart')?.getContext('2d');
  if (!ctx) return;

  const isDark = state.theme === 'dark';
  const decayData = window.PORTAL_DATA.decay;
  const windows = ['7', '15', '30', '45'];
  const labels = windows.map(w => `T+${w}`);
  const inr = n => '₹' + Number(n).toLocaleString('en-IN');

  // Dynamic y-range across visible routes
  let lo = Infinity, hi = -Infinity;
  Object.keys(decayData).forEach(route => {
    windows.forEach(w => {
      const v = decayData[route][w];
      if (v != null) { if (v < lo) lo = v; if (v > hi) hi = v; }
    });
  });
  const pad = (hi - lo) * 0.1 || 400;
  const yScale = niceNiceStep(lo - pad, hi + pad, 6);

  const datasets = Object.keys(decayData).map(route => {
    const isVisible = state.activeDecayRoutes.has(route);
    const config = ROUTE_CONFIG[route];
    const routeColor = isDark ? config?.colorDark : config?.color || '#0F2A43';

    const vals = windows.map(w => decayData[route][w]);

    return {
      label: route,
      data: vals,
      borderColor: routeColor,
      backgroundColor: routeColor,
      borderWidth: 2.4,
      pointRadius: 4,
      pointHoverRadius: 7,
      pointBackgroundColor: routeColor,
      pointBorderColor: isDark ? '#0D1626' : '#FFFFFF',
      pointBorderWidth: 1.5,
      hoverBorderWidth: 2,
      hidden: !isVisible,
      tension: 0.25
    };
  });

  state.charts.decay = new Chart(ctx, {
    type: 'line',
    data: {
      labels: labels,
      datasets: datasets
    },
    plugins: [crosshairPlugin()],
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      animation: { duration: 400 },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: isDark ? '#1E2E48' : '#0F2A43',
          padding: 10,
          cornerRadius: 8,
          displayColors: true,
          boxPadding: 4,
          titleFont: { weight: '700', size: 12 },
          callbacks: {
            title: (items) => items[0]?.label ?? '',
            label: (ctx) => ` ${ctx.dataset.label}: ${inr(ctx.parsed.y)}`
          }
        }
      },
      scales: {
        x: {
          grid: { display: false },
          ticks: { font: { size: 10 }, color: isDark ? '#93A3B8' : '#64748B' },
          title: {
            display: true,
            text: 'Booking lead-time window',
            font: { size: 10, weight: '700' },
            color: isDark ? '#93A3B8' : '#64748B'
          }
        },
        y: {
          min: yScale.lo,
          max: yScale.hi,
          position: 'left',
          grid: { color: isDark ? '#141E2F' : '#EAEEF4' },
          ticks: { font: { size: 10 }, stepSize: yScale.step, callback: v => inr(v) },
          title: {
            display: true,
            text: 'Median fare (INR)',
            font: { size: 10, weight: '700' },
            color: isDark ? '#93A3B8' : '#64748B'
          }
        }
      }
    }
  });
}

function initDecayLegend() {
  const container = document.getElementById('decay-legend-container');
  if (!container) return;
  container.innerHTML = '';

  const isDark = state.theme === 'dark';
  const decayRoutes = Object.keys(window.PORTAL_DATA.decay || {});

  decayRoutes.forEach(route => {
    const item = document.createElement('span');
    const isSelected = state.activeDecayRoutes.has(route);
    const config = ROUTE_CONFIG[route];
    item.style.cursor = 'pointer';
    item.style.fontWeight = isSelected ? '700' : '400';
    item.style.color = isSelected ? (isDark ? config.colorDark : config.color) : 'var(--text-muted)';
    item.innerText = route;

    item.onclick = () => {
      if (state.activeDecayRoutes.has(route)) {
        if (state.activeDecayRoutes.size > 1) state.activeDecayRoutes.delete(route);
      } else {
        state.activeDecayRoutes.add(route);
      }
      initDecayLegend();
      state.charts.decay?.data.datasets.forEach(ds => {
        ds.hidden = !state.activeDecayRoutes.has(ds.label);
      });
      state.charts.decay?.update();
    };

    container.appendChild(item);
  });
}

/* ==========================================================================
   ROUTE ANALYSIS
   ========================================================================== */
function initRouteAnalysis() {
  const select = document.getElementById('route-analysis-select');
  const pf = window.PORTAL_DATA?.price_forecast?.routes;
  if (!select || !pf) return;

  if (!select.options.length) {
    const metas = window.PORTAL_DATA?.routes || [];
    Object.keys(pf).forEach(code => {
      const opt = document.createElement('option');
      opt.value = code;
      const meta = metas.find(r => r.code === code);
      opt.textContent = meta?.name || code;
      select.appendChild(opt);
    });
  }

  if (!Object.keys(pf).includes(state.routeAnalysisRoute)) {
    state.routeAnalysisRoute = Object.keys(pf)[0] || 'DEL-BOM';
  }
  select.value = state.routeAnalysisRoute;

  select.addEventListener('change', () => {
    state.routeAnalysisRoute = select.value;
    renderRouteAnalysis();
  });

  renderRouteAnalysis();
}

function renderRouteAnalysis() {
  const select = document.getElementById('route-analysis-select');
  const route = (select?.value) || state.routeAnalysisRoute || 'DEL-BOM';
  const pf = window.PORTAL_DATA?.price_forecast;
  const r = pf?.routes?.[route];
  if (!r) return;

  const isDark = state.theme === 'dark';
  const inr = n => '₹' + Number(n).toLocaleString('en-IN');

  const kpiEl = document.getElementById('ra-kpi-fare');
  if (kpiEl) kpiEl.textContent = inr(r.today);

  const heatSrc = window.PORTAL_DATA?.heatmap?.[route] || window.PORTAL_DATA?.decay?.[route];
  const windows = ['7', '15', '30', '45'];
  const labels = (pf.all_labels || []).slice(0, r.hist.length);

  const rowsWrap = document.getElementById('ra-window-rows');
  if (rowsWrap && heatSrc) {
    const base = heatSrc['7'];
    rowsWrap.innerHTML = windows.map(w => {
      const fare = heatSrc[w];
      const pct = base ? ((fare - base) / base) * 100 : 0;
      const deltaCls = w === '7' || Math.abs(pct) < 0.05 ? 'ra-delta-flat' : (pct > 0 ? 'ra-delta-up' : 'ra-delta-down');
      const deltaTxt = w === '7' ? '—' : `${pct > 0 ? '+' : ''}${pct.toFixed(1)}%`;
      return `
        <div class="ra-window-row">
          <span class="ra-win">${WINDOW_CONFIG[w]?.label || 'T+' + w}</span>
          <span class="ra-win-desc">${WINDOW_CONFIG[w]?.desc || ''}</span>
          <span class="ra-win-fare num-tabular">${inr(fare)}</span>
          <span class="ra-delta ${deltaCls}">${deltaTxt}</span>
        </div>`;
    }).join('');
  }

  const compWrap = document.getElementById('ra-comp-rows');
  if (compWrap) {
    const c = r.components;
    const total = Number(c?.total || r.today || 0);
    if (c && total > 0) {
      const share = v => v > 0 ? `${((v / total) * 100).toFixed(1)}%` : '';
      compWrap.innerHTML =
        `<div class="ra-comp-row"><span class="ra-comp-label">Total Fare</span><span class="ra-comp-value num-tabular">${inr(c.total)}</span><span class="ra-comp-share">${share(c.total)}</span></div>` +
        `<div class="ra-comp-row"><span class="ra-comp-label">Base Fare</span><span class="ra-comp-value num-tabular">${inr(c.base)}</span><span class="ra-comp-share">${share(c.base)}</span></div>` +
        `<div class="ra-comp-row"><span class="ra-comp-label">Taxes</span><span class="ra-comp-value num-tabular">${inr(c.taxes)}</span><span class="ra-comp-share">${share(c.taxes)}</span></div>` +
        `<div class="ra-comp-row"><span class="ra-comp-label">Convenience Fee</span><span class="ra-comp-value num-tabular">${inr(c.conv)}</span><span class="ra-comp-share">${share(c.conv)}</span></div>`;
    } else {
      compWrap.innerHTML =
        `<div class="ra-comp-row"><span class="ra-comp-label">Total Fare</span><span class="ra-comp-value num-tabular">${inr(r.today)}</span><span class="ra-comp-share"></span></div>` +
        `<div class="ra-comp-row"><span class="ra-comp-label">Base Fare</span><span class="ra-comp-muted">Not exposed</span><span class="ra-comp-share"></span></div>` +
        `<div class="ra-comp-row"><span class="ra-comp-label">Taxes</span><span class="ra-comp-muted">Not exposed</span><span class="ra-comp-share"></span></div>` +
        `<div class="ra-comp-row"><span class="ra-comp-label">UDF &amp; Fees</span><span class="ra-comp-muted">Not exposed</span><span class="ra-comp-share"></span></div>`;
    }
  }

  const ctx = document.getElementById('routeAnalysisChart')?.getContext('2d');
  if (!ctx) return;

  if (state.charts.routeAnalysis) {
    state.charts.routeAnalysis.destroy();
    state.charts.routeAnalysis = null;
  }

  const lo = Math.min(...r.hist);
  const hi = Math.max(...r.hist);
  const pad = (hi - lo) * 0.18 || 100;
  const yRange = niceNiceStep(lo - pad, hi + pad, 5);

  const lastIdx = r.hist.length - 1;
  const routeColor = isDark ? '#4D9FFF' : '#1D6FE0';
  const fillColor = routeColor.length === 7 ? routeColor + (isDark ? '33' : '14') : routeColor;

  state.charts.routeAnalysis = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [{
        label: route,
        data: r.hist,
        borderColor: routeColor,
        backgroundColor: fillColor,
        fill: true,
        borderWidth: 2.4,
        tension: 0.3,
        pointRadius: (context) => (context.dataIndex === lastIdx ? 5 : 3),
        pointHoverRadius: 6,
        pointBackgroundColor: routeColor,
        pointBorderColor: isDark ? '#0D1626' : '#FFFFFF',
        pointBorderWidth: 1.5
      }]
    },
    plugins: [crosshairPlugin()],
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      animation: { duration: 400 },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: isDark ? '#1E2E48' : '#0F2A43',
          padding: 10,
          cornerRadius: 8,
          displayColors: false,
          boxPadding: 4,
          titleFont: { weight: '700', size: 12 },
          callbacks: {
            title: (items) => items[0]?.label ?? '',
            label: (ctx) => ` Average fare: ${inr(ctx.parsed.y)}`
          }
        }
      },
      scales: {
        x: {
          grid: { display: false },
          ticks: { font: { size: 10 }, color: isDark ? '#93A3B8' : '#64748B' },
          title: {
            display: true,
            text: 'Scrape date (observed)',
            font: { size: 10, weight: '700' },
            color: isDark ? '#93A3B8' : '#64748B'
          }
        },
        y: {
          min: yRange.lo,
          max: yRange.hi,
          position: 'left',
          grid: { color: isDark ? '#141E2F' : '#EAEEF4' },
          ticks: { font: { size: 10 }, stepSize: yRange.step, callback: v => '₹' + Number(v).toLocaleString('en-IN') },
          title: {
            display: true,
            text: 'Median fare (INR)',
            font: { size: 10, weight: '700' },
            color: isDark ? '#93A3B8' : '#64748B'
          }
        }
      }
    }
  });
}

/* ==========================================================================
   KPI STRIP + EXTENDED DASHBOARD SECTIONS (7–12)
   ========================================================================== */
function initKpiStrip() {
  const host = document.getElementById('kpi-strip');
  if (!host) return;
  const k = window.PORTAL_DATA.kpi;
  const p = window.PORTAL_DATA.kpi.pipeline || {};
  const avgChangeClass = (k.avg_fare_change_pct ?? 0) >= 0 ? 'up' : 'down';
  const avgArrow = (k.avg_fare_change_pct ?? 0) >= 0 ? '▲' : '▼';

  host.innerHTML = `
    <div class="kpi-item">
      <span class="kpi-label">Avg. Median Fare</span>
      <span class="kpi-value num-tabular">₹${Number(k.average_fare).toLocaleString('en-IN')}</span>
      <span class="kpi-sub"><span class="kpi-change ${avgChangeClass}">${avgArrow} ${Math.abs(k.avg_fare_change_pct).toFixed(1)}%</span> vs prior period</span>
    </div>
    <div class="kpi-item">
      <span class="kpi-label">Flights Tracked</span>
      <span class="kpi-value num-tabular">${k.flights_tracked?.toLocaleString('en-IN')}</span>
      <span class="kpi-sub">${p.quotes_today?.toLocaleString('en-IN')} quotes · ${k.airline_count} carriers</span>
    </div>
    <div class="kpi-item">
      <span class="kpi-label">Coverage</span>
      <span class="kpi-value num-tabular">${k.coverage.pct}%</span>
      <span class="kpi-sub">${k.coverage.corridors} corridors watched over ${k.coverage.windows} horizons</span>
    </div>
    <div class="kpi-item">
      <span class="kpi-label">Pipeline</span>
      <span class="kpi-value" style="font-size:16px; line-height:1.4;">${k.pipeline.status}</span>
      <span class="kpi-sub">last collection: ${k.pipeline.last_collection}</span>
    </div>
  `;
}

function getTrendSeries() {
  const d90 = window.PORTAL_DATA.index_range.ranges['90'];
  const from = state.dateFrom || '2026-06-08';
  const to = state.dateTo || '2026-09-05';
  return d90.filter(p => p.d >= from && p.d <= to);
}

function initIndexRangeBanner() {
  const host = document.getElementById('index-range-banner');
  if (!host) return;
  const ser = getTrendSeries();
  const last = ser[ser.length - 1];
  const first = ser[0];
  const vals = ser.map(s => s.v);
  const lo = Math.min(...vals);
  const hi = Math.max(...vals);
  const rangeChg = last.v - first.v;
  host.innerHTML = `
    <div class="irb-item">
      <span class="irb-lbl">Base Period</span>
      <span class="irb-val">${window.PORTAL_DATA.index_range.base_period}</span>
    </div>
    <div class="irb-item">
      <span class="irb-lbl">Latest Fare</span>
      <span class="irb-val num-tabular">₹${Number(last.v).toLocaleString('en-IN')}</span>
    </div>
    <div class="irb-item">
      <span class="irb-lbl">Δ Since Start</span>
      <span class="irb-val num-tabular" style="color:${rangeChg >= 0 ? 'var(--red-text)' : 'var(--green-text)'};">${rangeChg >= 0 ? '▲' : '▼'} ₹${Math.abs(Math.round(rangeChg)).toLocaleString('en-IN')}</span>
    </div>
    <div class="irb-item">
      <span class="irb-lbl">Forward Range</span>
      <span class="irb-val num-tabular">₹${Math.round(lo).toLocaleString('en-IN')} – ₹${Math.round(hi).toLocaleString('en-IN')}</span>
    </div>
  `;
}

function renderTrendIndexChart() {
  const ctx = document.getElementById('trendIndexChart')?.getContext('2d');
  if (!ctx) return;
  const isDark = state.theme === 'dark';
  const tooltipEl = document.getElementById('trend-tooltip');
  const ser = getTrendSeries();
  const labels = ser.map(p => p.l);
  const vals = ser.map(p => p.v);

  if (state.charts.trend) state.charts.trend.destroy();

  const lo = Math.min(...vals);
  const hi = Math.max(...vals);
  const pad = (hi - lo) * 0.15 || 500;

  state.charts.trend = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [{
        label: 'Median Fare (₹)',
        data: vals,
        borderColor: isDark ? '#60A5FA' : '#0284C7',
        backgroundColor: (context) => {
          const c = context.chart.ctx;
          const g = c.createLinearGradient(0, 0, 0, 236);
          g.addColorStop(0, isDark ? 'rgba(96,165,250,0.22)' : 'rgba(2,132,199,0.22)');
          g.addColorStop(1, 'rgba(2,132,199,0)');
          return g;
        },
        fill: true,
        borderWidth: 2.2,
        pointRadius: 0,
        pointHitRadius: 10,
        tension: 0.25
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          enabled: false,
          external: (extCtx) => {
            const { chart, tooltip } = extCtx;
            if (!tooltipEl) return;
            if (!tooltip || tooltip.opacity === 0) { tooltipEl.style.display = 'none'; return; }
            const idx = tooltip.dataPoints[0].dataIndex;
            const p = ser[idx];
            if (!p) return;
            const fare = p.v;
            tooltipEl.innerHTML = `
              <div class="tt-title">${p.d}</div>
              <div class="tt-row"><span class="tt-k">Median Fare</span><strong>₹${Number(fare).toLocaleString('en-IN')}</strong></div>
              <div class="tt-row"><span class="tt-k">Quotations</span><span>${p.o ?? '—'}</span></div>
              <div class="tt-row" style="margin-top:4px;"><span class="tt-k" style="font-size:10px;">${window.PORTAL_DATA.index_range.demo_note || ''}</span></div>
            `;
            const card = tooltipEl.parentElement.getBoundingClientRect();
            tooltipEl.style.display = 'block';
            const left = tooltip.caretX + 14;
            tooltipEl.style.left = (left + 200 > card.width ? tooltip.caretX - 206 : left) + 'px';
            tooltipEl.style.top = '2px';
          }
        }
      },
      scales: {
        x: { grid: { display: false }, ticks: { font: { size: 9 }, maxTicksLimit: 12 } },
        y: {
          min: lo - pad,
          max: hi + pad,
          grid: { color: isDark ? '#141E2F' : '#EAEEF4' },
          ticks: { font: { size: 10 }, callback: v => '₹' + (v / 1000).toFixed(1) + 'k' }
        }
      }
    }
  });

  initIndexRangeBanner();
}

function renderCompositionChart() {
  const ctx = document.getElementById('compositionChart')?.getContext('2d');
  if (!ctx) return;
  const isDark = state.theme === 'dark';
  const comp = window.PORTAL_DATA.composition.components;
  const palette = {
    base: isDark ? '#60A5FA' : '#0F2A43',
    taxes: '#0284C7',
    udf: '#D97706',
    convenience: '#16A34A'
  };
  const data = comp.map(c => ({ name: c.name, value: +(c.share * 100).toFixed(1), color: palette[c.key] || '#64748B' }));

  if (state.charts.composition) state.charts.composition.destroy();

  state.charts.composition = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: data.map(d => d.name),
      datasets: [{
        data: data.map(d => d.value),
        backgroundColor: data.map(d => d.color),
        borderColor: 'transparent',
        borderWidth: 2,
        hoverOffset: 4
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: '62%',
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: isDark ? '#1E2E48' : '#0F2A43',
          callbacks: { label: (t) => ` ${t.label}: ${t.parsed}%` }
        }
      }
    }
  });

  const legend = document.getElementById('composition-legend');
  if (legend) {
    legend.innerHTML = data.map(d => `
      <div class="comp-item">
        <span class="comp-swatch" style="background:${d.color};"></span>
        ${d.name} · <strong>${d.value}%</strong>
      </div>
    `).join('');
  }
}

function initLeadtime() {
  const host = document.getElementById('leadtime-grid');
  if (!host) return;
  const fareType = state.fareType || 'median';
  const ltKey = fareType === 'min' ? 'leadtime_min' : fareType === 'max' ? 'leadtime_max' : 'leadtime';
  const lt = window.PORTAL_DATA[ltKey] || window.PORTAL_DATA.leadtime;
  const scale = { min: 0.94, median: 1.0, max: 1.12 }[state.fareType] || 1.0;
  const base = lt.windows;

  const windowFares = base.map(w => {
    const key = w.replace('T+', '');
    let fares = Object.values(lt.routes).map(r => r[key] || null).filter(v => v !== null);
    const med = fares.length ? [...fares].sort((a, b) => a - b)[Math.floor(fares.length / 2)] : null;
    return { key, label: w, med };
  });

  const t7 = windowFares.find(w => w.key === '7')?.med || 9000;

  host.innerHTML = windowFares.map(w => {
    const scaled = (w.med || 0) * scale;
    const delta = scaled - (t7 * scale);
    const cls = delta <= 0 ? 'cheaper' : 'pricier';
    return `
      <div class="lt-window-card">
        <div class="lt-window-label">${w.label}</div>
        <div class="lt-window-fare num-tabular">₹${Math.round(scaled).toLocaleString('en-IN')}</div>
        <div class="lt-window-delta ${cls}">${w.key === '7' ? '±0 (baseline)' : (delta > 0 ? '▲' : '▼') + ' ₹' + Math.abs(Math.round(delta)).toLocaleString('en-IN') + ' vs T+7'}</div>
      </div>
    `;
  }).join('');

  const note = host.parentElement.querySelector('.lt-aggregation-note');
  if (note) note.textContent = `Median across corridor basket · aggregation: ${state.fareType.toUpperCase()}`;
}

function signalFor(f) {
  if (f.signal === 'amber') return { cls: 'sig-amber', txt: 'Amber' };
  if (f.signal === 'mixed') return { cls: 'sig-mixed', txt: 'Mixed' };
  if (f.signal === 'neutral') return { cls: 'sig-neutral', txt: 'Neutral' };
  if (/negative/i.test(f.effect)) return { cls: 'sig-negative', txt: 'Negative' };
  if (/route|dependent|scatter|window/i.test(f.effect)) return { cls: 'sig-mixed', txt: 'Route-dep.' };
  if (/positive/i.test(f.effect)) return { cls: 'sig-positive', txt: 'Positive' };
  return { cls: 'sig-neutral', txt: 'Neutral' };
}

function initFactors() {
  const tbody = document.getElementById('factors-body');
  if (!tbody) return;
  const factors = window.PORTAL_DATA.factors;

  tbody.innerHTML = factors.map(f => {
    const imp = f.impact.toLowerCase();
    const sig = signalFor(f);
    return `
      <tr>
        <td><span class="factor-name">${f.name}</span></td>
        <td><span class="impact-pill ${imp}">${f.impact}</span></td>
        <td style="font-size:11px;">${f.effect}</td>
        <td><span class="signal-pill ${sig.cls}"><span class="sig-dot"></span>${sig.txt}</span></td>
        <td><span class="factor-desc">${f.desc}</span></td>
      </tr>
    `;
  }).join('');

  const note = document.getElementById('factors-note');
  if (note) note.textContent = window.PORTAL_DATA.factors_note;
}

function coverageBarRow(name, intro, pct, label) {
  return `
    <div class="coverage-row">
      <span class="cov-name" title="${name}">${name}</span>
      <span class="cov-bar-track"><span class="cov-bar-fill" style="width:${Math.min(100, Math.max(4, pct))}%;"></span></span>
      <span class="cov-val">${label}</span>
    </div>
  `;
}

function initCoverage() {
  const airlineHost = document.getElementById('airline-share-body');
  if (airlineHost) {
    const airlines = window.PORTAL_DATA.airlines;
    const maxQ = Math.max(...airlines.map(a => a.quotes));
    airlineHost.innerHTML = airlines.map(a =>
      coverageBarRow(`${a.name} (${a.code})`, a.quotes, (a.quotes / maxQ) * 100, `${a.quotes} quotes`)
    ).join('');
  }
}

function renderBacktestChart() {
  const ctx = document.getElementById('backtestChart')?.getContext('2d');
  if (!ctx) return;
  const isDark = state.theme === 'dark';
  const bt = window.PORTAL_DATA.backtest;
  if (!bt) return;

  const metrics = document.getElementById('backtest-metrics');
  if (metrics) {
    metrics.innerHTML = `
      <div class="bt-metric"><span class="bt-lbl">Correlation</span><span class="bt-val num-tabular">${bt.corr.toFixed(2)}</span></div>
      <div class="bt-metric"><span class="bt-lbl">MAPE</span><span class="bt-val num-tabular">${bt.mape.toFixed(1)}%</span></div>
      <div class="bt-metric"><span class="bt-lbl">RMSE</span><span class="bt-val num-tabular">₹${Number(bt.rmse).toLocaleString('en-IN')}</span></div>
      <div class="bt-metric"><span class="bt-lbl">Observations</span><span class="bt-val num-tabular" style="font-size:16px;">${bt.obs}</span></div>
      <div class="bt-note-inline"><strong>${bt.api_label} vs ${bt.dgca_label}</strong><br>${bt.period}</div>
    `;
  }

  const note = document.getElementById('backtest-note');
  if (note) note.textContent = bt.note;

  if (state.charts.backtest) state.charts.backtest.destroy();

  state.charts.backtest = new Chart(ctx, {
    type: 'line',
    data: {
      labels: bt.labels,
      datasets: [
        {
          label: bt.api_label,
          data: bt.api,
          borderColor: isDark ? '#38BDF8' : '#0284C7',
          borderWidth: 2,
          pointRadius: 2.5,
          pointBackgroundColor: isDark ? '#38BDF8' : '#0284C7',
          tension: 0.15
        },
        {
          label: bt.dgca_label,
          data: bt.dgca,
          borderColor: '#16A34A',
          borderWidth: 2,
          borderDash: [5, 4],
          pointRadius: 2.5,
          pointBackgroundColor: '#16A34A',
          tension: 0.15
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: {
          display: true,
          position: 'bottom',
          labels: {
            color: isDark ? '#93A3B8' : '#64748B',
            boxWidth: 12,
            font: { size: 11 }
          }
        },
        tooltip: {
          backgroundColor: isDark ? '#1E2E48' : '#0F2A43',
          callbacks: {
            title: (items) => items[0].label,
            label: (ctx) => ` ${ctx.dataset.label}: ₹${Number(ctx.parsed.y).toLocaleString('en-IN')}`
          }
        }
      },
      scales: {
        x: { grid: { display: false }, ticks: { font: { size: 9 }, maxRotation: 45 } },
        y: {
          min: bt.ymin,
          max: bt.ymax,
          grid: { color: isDark ? '#141E2F' : '#EAEEF4' },
          ticks: { font: { size: 10 }, callback: v => '₹' + (v / 1000).toFixed(1) + 'k' }
        }
      }
    }
  });
}

function initPipelineApi() {
  const stages = document.getElementById('pipeline-stages');
  if (stages) {
    const pipes = window.PORTAL_DATA.pipelines;
    stages.innerHTML = pipes.map(p => {
      const cls = p.state === 'pending' ? 'pipe-state-pending' : (p.state === 'off' ? 'pipe-state-off' : 'pipe-state-ok');
      return `
        <div class="pipeline-stage">
          <span class="pipe-state-dot ${cls}"></span>
          <div>
            <div class="ps-name">${p.name}</div>
            <div class="ps-desc">${p.desc}</div>
          </div>
          <span class="ps-status">${p.status}</span>
        </div>
      `;
    }).join('');
  }

  const api = window.PORTAL_DATA.api;
  const chip = document.getElementById('api-status-chip');
  if (chip) chip.textContent = api.chip || (api.demo ? 'not connected' : 'live');

  const meta = document.getElementById('api-meta');
  if (meta) {
    meta.innerHTML = `
      <span><strong>Base:</strong> ${api.base_url}</span>
      <span><strong>Latest dataset:</strong> ${api.latest_dataset}</span>
      <span><strong>Routes:</strong> ${api.available_routes.join(', ')}</span>
    `;
  }

  const eps = document.getElementById('api-endpoints');
  if (eps) {
    eps.innerHTML = api.endpoints.map(e => `
      <div class="api-endpoint copyable" onclick="copyApiEndpoint('${e.path}')" title="Click to copy">
        <span class="http-method">${e.m}</span>
        <span class="ep-path">${e.path}</span>
        <span class="ep-desc">${e.desc}</span>
      </div>
    `).join('');
  }
}

function copyApiEndpoint(path) {
  const base = window.PORTAL_DATA.api.base_url;
  navigator.clipboard?.writeText(base + path).catch(() => {});
}

function renderRouteDetail(route) {
  const panel = document.getElementById('route-detail-panel');
  if (!panel) return;
  const cfg = ROUTE_CONFIG[route];
  const wins = ['7', '15', '30', '45'];
  const fares = wins.map(w => window.PORTAL_DATA.decay[route]?.[w]);
  const hasFare = fares.some(v => v != null);
  const heat = window.PORTAL_DATA.heatmap[route] || {};
  const t7 = heat['7'] ?? 100.0;

  if (!hasFare) {
    panel.innerHTML = `
      <div class="rdp-head"><div>
        <div class="rdp-title">${route}</div>
        <div class="rdp-carrier">${cfg?.name || ''}</div>
      </div></div>
      <div style="font-size:12px; color:var(--text-muted); margin-top:12px;">
        No derived fare series for this corridor yet — included as a scenario route in the basket config.
      </div>
    `;
    return;
  }

  const minF = Math.min(...fares);
  const maxF = Math.max(...fares);
  const valid = fares.filter(v => v != null);
  const avg = valid.reduce((a, b) => a + b, 0) / valid.length;
  const isDemo = !!cfg?.demo;

  const winRows = wins.map((w, i) => {
    const v = fares[i];
    const pct = maxF > minF ? ((v - minF) / (maxF - minF)) * 100 : 50;
    const fill = v <= avg ? 'var(--green-main)' : 'var(--saffron-main)';
    return `
      <div class="rdp-win-row">
        <span class="rwr-label">T+${w}</span>
        <span class="rwr-track"><span class="rwr-fill" style="width:${Math.max(6, pct)}%; background:${fill};"></span></span>
        <span class="rwr-val num-tabular">₹${Number(v).toLocaleString('en-IN')}</span>
      </div>
    `;
  }).join('');

  panel.innerHTML = `
    <div style="min-width:0;">
      <div class="rdp-head">
        <div>
          <div class="rdp-title">${route} <span class="route-cell-demo" style="${isDemo ? '' : 'display:none;'}">demo</span></div>
          <div class="rdp-carrier">${cfg?.name} · ${cfg?.carrier || '—'}</div>
        </div>
        <div>
          <div class="rdp-stat" style="min-width:110px;">
            <div class="rdp-lbl">Basket Weight</div>
            <div class="rdp-val num-tabular">${cfg?.weight || '0%'}</div>
          </div>
        </div>
      </div>
      <div class="rdp-stat-grid">
        <div class="rdp-stat"><div class="rdp-lbl">T+7 Sub-Index</div><div class="rdp-val num-tabular">${Number(t7).toFixed(1)}</div></div>
        <div class="rdp-stat"><div class="rdp-lbl">Avg Fare (4 horizons)</div><div class="rdp-val num-tabular">₹${Math.round(avg).toLocaleString('en-IN')}</div></div>
        <div class="rdp-stat"><div class="rdp-lbl">${isDemo ? 'Scenario' : 'Status'}</div><div class="rdp-val" style="font-size:13px;">${isDemo ? 'illustrative' : 'active'}</div></div>
      </div>
    </div>
    <div>
      <div class="rdp-win-bars">${winRows}</div>
    </div>
  `;
}

function initBasket() {
  const host = document.getElementById('basket-chips');
  if (!host) return;
  const routes = window.PORTAL_DATA.basket.routes;

  host.innerHTML = routes.map(r => {
    const isActive = r.status === 'active';
    const pct = Math.round((r.weight || 0) * 100);
    return `
      <button class="basket-chip ${isActive ? '' : 'demo-chip'}" data-route="${r.code}" onclick="selectBasketRoute('${r.code}')">
        ${r.code}
        <span class="bw-pct">${isActive ? `w ${pct}%` : 'demo'}</span>
      </button>
    `;
  }).join('');

  renderRouteDetail('DEL-BOM');
  const first = host.querySelector('[data-route="DEL-BOM"]');
  if (first) first.classList.add('selected');
}

function selectBasketRoute(route) {
  document.querySelectorAll('#basket-chips .basket-chip').forEach(c => {
    c.classList.toggle('selected', c.getAttribute('data-route') === route);
  });
  renderRouteDetail(route);
}

/* ==========================================================================
   EXTENDED FILTERS (date range · airline · fare type)
   ========================================================================== */
function initExtendedFilters() {
  const dateFrom = document.getElementById('date-from');
  const dateTo = document.getElementById('date-to');
  const airline = document.getElementById('airline-select');
  const fare = document.getElementById('fare-select');

  dateFrom?.addEventListener('change', () => { state.dateFrom = dateFrom.value; applyExtendedFilters(); });
  dateTo?.addEventListener('change', () => { state.dateTo = dateTo.value; applyExtendedFilters(); });
  airline?.addEventListener('change', () => { state.airline = airline.value; applyExtendedFilters(); });
  fare?.addEventListener('change', () => { state.fareType = fare.value; applyExtendedFilters(); });
}

function applyExtendedFilters() {
  renderTrendIndexChart();
  initPriceHeatmap();
  initLeadtime();
  initIndexRangeBanner();
}

/* ==========================================================================
   EVENT LISTENERS
   ========================================================================== */
function initEventListeners() {
  document.querySelectorAll('.modal-overlay').forEach(modal => {
    modal.addEventListener('click', (e) => {
      if (e.target === modal) modal.classList.remove('open');
    });
  });
}

function selectRouteFilter(route) {
  state.selectedRoute = route;
}

function scrollToHeatmap(route) {
  const el = document.getElementById('sec-heatmap');
  if (!el) return;
  const offset = 70;
  const pos = el.getBoundingClientRect().top + window.pageYOffset - offset;
  window.scrollTo({ top: pos, behavior: 'smooth' });

  setTimeout(() => {
    document.querySelectorAll('#price-heatmap-body tr').forEach(r => {
      r.classList.toggle('heat-row-active', r.dataset.route === route);
    });
    const targetRow = document.querySelector(`#price-heatmap-body tr[data-route="${route}"]`);
    if (targetRow) {
      targetRow.scrollIntoView({ behavior: 'smooth', block: 'center' });
      targetRow.classList.add('heat-row-flash');
      setTimeout(() => targetRow.classList.remove('heat-row-flash'), 1600);
    }
  }, 500);
}

function initMapInteractions() {
  const tooltip = document.getElementById('map-tooltip');
  const svg = document.querySelector('.map-svg-container svg');
  if (!tooltip || !svg) return;

  const routesMeta = window.PORTAL_DATA?.routes || [];
  const nameOf = (code) => (routesMeta.find(r => r.code === code) || {}).name || code;

  const move = (e) => {
    const rect = svg.getBoundingClientRect();
    tooltip.style.left = (e.clientX - rect.left + 16) + 'px';
    tooltip.style.top = (e.clientY - rect.top - 12) + 'px';
  };
  const show = (e, code) => {
    const heat = window.PORTAL_DATA?.heatmap?.[code] || {};
    const med7 = heat['7'];
    const med45 = heat['45'];
    tooltip.innerHTML = `
      <div class="mt-route">${nameOf(code)}</div>
      <div class="mt-fare">${med7 ? '₹' + Number(med7).toLocaleString('en-IN') : '—'} <span>· T+7 median</span></div>
      ${med45 ? `<div class="mt-fare" style="font-size:11px;font-weight:600;">₹${Number(med45).toLocaleString('en-IN')} <span>· T+45</span></div>` : ''}
      <div class="mt-hint">Click to spotlight in heatmap</div>`;
    tooltip.style.display = 'block';
    move(e);
  };
  const hide = () => { tooltip.style.display = 'none'; };
  const end = () => { hide(); };

  svg.querySelectorAll('[data-route]').forEach(el => {
    el.addEventListener('mouseenter', (e) => show(e, el.getAttribute('data-route')));
    el.addEventListener('mousemove', move);
    el.addEventListener('mouseleave', end);
  });
  svg.addEventListener('mouseleave', end);
}

function openModal(id) {
  document.getElementById(id)?.classList.add('open');
}

function closeModal(id) {
  document.getElementById(id)?.classList.remove('open');
}

/* ==========================================================================
   CSV EXPORT
   ========================================================================== */
function exportToCSV() {
  const routes = Object.keys(window.PORTAL_DATA.heatmap);
  let csv = 'Route,Window,MedianFare_INR,Status\n';

  routes.forEach(route => {
    ['7', '15', '30', '45'].forEach(win => {
      const fare = window.PORTAL_DATA.decay[route]?.[win];
      if (fare == null) return;
      const status = ROUTE_CONFIG[route]?.demo ? 'demo' : 'active';
      csv += `${route},T+${win},${fare},${status}\n`;
    });
  });

  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `Airfare_Fares_final_scraper_${new Date().toISOString().slice(0,10)}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

/* ==========================================================================
   HERO DELTA + SURGE RADAR
   ========================================================================== */
function updateHeroDelta() {
  const meta = window.PORTAL_DATA?.meta;
  if (!meta) return;
  const pill = document.getElementById('hero-delta-pill');
  if (pill) {
    const chg = meta.day_change_pct || 0;
    const isUp = chg >= 0;
    const svgUp = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="18 15 12 9 6 15"/></svg>';
    const svgDown = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="6 9 12 15 18 9"/></svg>';
    pill.innerHTML = `${isUp ? svgUp : svgDown}<span>${isUp ? '+' : ''}${chg.toFixed(2)}%</span>`;
    pill.style.color = isUp ? 'var(--red-text)' : 'var(--green-text)';
    pill.style.background = isUp ? 'var(--red-light)' : 'var(--green-light)';
  }

  const covEl = document.getElementById('hero-meta-coverage');
  const obsEl = document.getElementById('hero-meta-observations');
  if (covEl) {
    const routes = (window.PORTAL_DATA?.routes || []).length;
    covEl.textContent = routes ? `${routes} Routes` : '4 Routes';
  }
  if (obsEl) {
    const n = meta.n_quotes || meta.total_flights || 2010;
    obsEl.textContent = `${n.toLocaleString('en-IN')} Quotes`;
  }
}

function renderSurgeRadar() {
  const list = document.querySelector('.radar-terminal-list');
  if (!list) return;
  const surges = window.PORTAL_DATA?.surges || [];
  if (!surges.length) { list.innerHTML = '<div style="font-size:11px;color:var(--text-muted);">No surge events detected.</div>'; return; }
  const top2 = surges.slice(0, 2);
  const headerCount = document.querySelector('.surge-radar-card .section-head-row span:last-child');
  if (headerCount) headerCount.textContent = surges.length + ' ACTIVE';
  list.innerHTML = top2.map(s => {
    const w = s.window.replace('T+', '');
    const cls = s.severity === 'red' ? 'red' : 'yellow';
    return `
      <div class="radar-item ${cls}" onclick="focusCell('${s.route}', '${w}')">
        <div class="radar-item-header">
          <span>${s.route} ${s.window}</span>
          ${s.severity === 'red' ? '<span class="radar-live-blinker"></span>' : '<span style="font-size:10px;color:var(--text-muted);">elevated</span>'}
        </div>
        <div class="radar-metric-line num-tabular">${s.metric}</div>
      </div>
    `;
  }).join('');
}
