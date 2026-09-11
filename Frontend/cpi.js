/**
 * CPI Augmentation — Understanding CPI Explainer Page (SIH 2026)
 * Controller: theme, reveal, basket bars, driver network, event-time chart.
 */

/* ==========================================================================
   THEME
   ========================================================================== */
const cpiState = {
  theme: localStorage.getItem('api_theme') || 'dark'
};

function initTheme() {
  applyTheme(cpiState.theme);
  const toggleBtn = document.getElementById('theme-toggle-btn');
  if (toggleBtn) {
    toggleBtn.addEventListener('click', () => {
      const nextTheme = cpiState.theme === 'light' ? 'dark' : 'light';
      applyTheme(nextTheme);
    });
  }
}

function applyTheme(theme) {
  cpiState.theme = theme;
  document.documentElement.setAttribute('data-theme', theme);
  localStorage.setItem('api_theme', theme);

  const moonIcon = document.getElementById('theme-icon-moon');
  const sunIcon = document.getElementById('theme-icon-sun');
  if (moonIcon && sunIcon) {
    moonIcon.style.display = theme === 'dark' ? 'none' : 'block';
    sunIcon.style.display = theme === 'dark' ? 'block' : 'none';
  }

  if (cpiState.eventsChart) {
    cpiState.eventsChart.destroy();
    cpiState.eventsChart = null;
    renderEventsChart();
  }
}

/* ==========================================================================
   HEADER + REVEAL
   ========================================================================== */
function initHeader() {
  const header = document.getElementById('cpi-header');
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
   INSIDE THE CPI BASKET — proportional bars + hover detail
   ========================================================================== */
const CPI_BASKET = [
  { name: 'Food & beverages', weight: 45.9, desc: 'Cereals, vegetables, dairy, meat and prepared meals — the largest group in the national basket.', air: false },
  { name: 'Housing', weight: 10.1, desc: 'Rent and housing services.', air: false },
  { name: 'Transport & communication', weight: 8.6, desc: 'Vehicle running, public transport and communication. Rail and air fares sit within this group.', air: true },
  { name: 'Fuel & light', weight: 6.8, desc: 'LPG, electricity and cooking fuel.', air: false },
  { name: 'Clothing & footwear', weight: 6.5, desc: 'Readymade garments, fabrics and footwear.', air: false },
  { name: 'Health', weight: 5.9, desc: 'Medical services, medicines and diagnostics.', air: false },
  { name: 'Education', weight: 3.5, desc: 'School and higher-education fees, books and stationery.', air: false },
  { name: 'Miscellaneous', weight: 12.7, desc: 'Pan and tobacco, personal care, household goods, recreation and other services.', air: false }
];
const BASKET_SHARE = 'of basket';

function renderBasket() {
  const host = document.getElementById('cpi-basket-bars');
  const detail = document.getElementById('cpi-basket-detail');
  if (!host || !detail) return;

  host.innerHTML = CPI_BASKET.map((g, i) => `
    <div class="basket-row ${g.air ? 'is-air' : ''}" data-idx="${i}" role="button" tabindex="0">
      <span class="basket-name">${g.name}</span>
      <div class="basket-track"><div class="basket-fill" style="width: ${g.weight}%;"></div></div>
      <span class="basket-meta"><span class="basket-val">${g.weight}%</span><span class="basket-share">${BASKET_SHARE}</span></span>
    </div>`).join('');

  const rows = host.querySelectorAll('.basket-row');
  const showDetail = (idx) => {
    const g = CPI_BASKET[idx];
    detail.innerHTML = `
      <span class="cpi-basket-detail-head">${g.name}<span class="detail-num">${g.weight}%</span></span>
      <span class="cpi-basket-detail-desc">${g.desc}</span>
      ${g.air ? '<span class="cpi-basket-detail-tag">Airfare component · Transport</span>' : ''}`;
  };

  rows.forEach(row => {
    const idx = Number(row.dataset.idx);
    const activate = () => {
      rows.forEach(r => r.style.opacity = r === row ? '1' : '0.55');
      showDetail(idx);
    };
    row.addEventListener('mouseenter', activate);
    row.addEventListener('focus', activate);
    row.addEventListener('mouseleave', () => rows.forEach(r => r.style.opacity = '1'));
    row.addEventListener('blur', () => rows.forEach(r => r.style.opacity = '1'));
  });

  rows.forEach(r => r.style.opacity = '1');
  const airRow = host.querySelector('.basket-row.is-air');
  const airIdx = CPI_BASKET.findIndex(g => g.air);
  if (airRow) {
    rows.forEach(r => r.style.opacity = r === airRow ? '1' : '0.55');
    showDetail(airIdx);
  }
}

/* ==========================================================================
   WHAT MOVES AIRFARES — driver network
   ========================================================================== */
const DRIVERS = [
  { id: 'fuel', name: 'Crude Oil / ATF', x: 180, y: 132, labelAbove: true, desc: 'Jet fuel is a major airline operating cost; ATF price moves transmit into fare setting.' },
  { id: 'demand', name: 'Demand', x: 820, y: 132, labelAbove: true, desc: 'Seat demand creates booking pressure and drives fare-class availability.' },
  { id: 'season', name: 'Seasonality', x: 500, y: 58, labelAbove: false, desc: 'Festivals, summer and holiday peaks shift demand within the year.' },
  { id: 'capacity', name: 'Capacity', x: 180, y: 324, labelAbove: false, desc: 'Routes, fleet and aircraft availability shape supply on each corridor.' },
  { id: 'events', name: 'Disruptions', x: 820, y: 324, labelAbove: false, desc: 'Weather, geopolitics, cancellations and airspace restrictions can constrain supply.' }
];
const DRIVER_CENTER = { x: 500, y: 206, r: 46 };

const SVG_NS = 'http://www.w3.org/2000/svg';

function svgEl(tag, attrs, parent) {
  const n = document.createElementNS(SVG_NS, tag);
  for (const k in attrs) n.setAttribute(k, attrs[k]);
  parent.appendChild(n);
  return n;
}

function renderDrivers() {
  const host = document.getElementById('cpi-drivers-svg');
  const detailName = document.getElementById('cpi-drivers-name');
  const detailDesc = document.getElementById('cpi-drivers-desc');
  if (!host) return;

  while (host.firstChild) host.removeChild(host.firstChild);

  const defs = svgEl('defs', {}, host);
  const marker = svgEl('marker', {
    id: 'drvArrow', viewBox: '0 0 8 8', refX: '7', refY: '4',
    markerWidth: '6.5', markerHeight: '6.5', orient: 'auto', markerUnits: 'userSpaceOnUse'
  }, defs);
  svgEl('path', { d: 'M0 0 L8 4 L0 8 Z', class: 'drv-arrowhead' }, marker);

  // driver → centre edges
  const edges = DRIVERS.map(d => {
    const dx = DRIVER_CENTER.x - d.x;
    const dy = DRIVER_CENTER.y - d.y;
    const len = Math.hypot(dx, dy);
    const ux = dx / len, uy = dy / len;
    const s = 40, e = DRIVER_CENTER.r + 12;
    return svgEl('line', {
      x1: d.x + ux * s, y1: d.y + uy * s,
      x2: DRIVER_CENTER.x - ux * e, y2: DRIVER_CENTER.y - uy * e,
      class: 'drv-edge', 'marker-end': 'url(#drvArrow)'
    }, host);
  });

  // central node
  svgEl('circle', { cx: DRIVER_CENTER.x, cy: DRIVER_CENTER.y, r: DRIVER_CENTER.r, class: 'drv-center-circle' }, host);
  svgEl('text', { x: DRIVER_CENTER.x, y: DRIVER_CENTER.y - 4, 'text-anchor': 'middle', class: 'drv-center-label' }, host)
    .textContent = 'Passenger Fare';
  svgEl('text', { x: DRIVER_CENTER.x, y: DRIVER_CENTER.y + 12, 'text-anchor': 'middle', class: 'drv-center-sub' }, host)
    .textContent = 'quoted fare';

  // satellite drivers
  const nodes = DRIVERS.map(d => {
    const g = svgEl('g', { class: 'drv-node', 'data-id': d.id }, host);
    svgEl('title', {}, g).textContent = d.name;
    svgEl('circle', { cx: d.x, cy: d.y, r: 34, class: 'drv-node-circle' }, g);
    const ly = d.labelAbove ? d.y - 44 : d.y + 46;
    svgEl('text', { x: d.x, y: ly, 'text-anchor': 'middle', class: 'drv-label' }, g).textContent = d.name;
    return g;
  });

  const active = (idx) => {
    nodes.forEach((n, i) => n.classList.toggle('active', i === idx));
    edges.forEach((e, i) => e.classList.toggle('active', i === idx));
  };

  nodes.forEach((g, i) => {
    const d = DRIVERS[i];
    g.addEventListener('mouseenter', () => { active(i); detailName.textContent = d.name; detailDesc.textContent = d.desc; });
    g.addEventListener('mouseleave', () => { active(-1); detailName.textContent = 'Select a driver'; detailDesc.textContent = 'Each driver transmits through airline operating conditions into the quoted fare.'; });
    g.addEventListener('focus', () => { active(i); detailName.textContent = d.name; detailDesc.textContent = d.desc; });
    g.setAttribute('tabindex', '0');
  });
}

/* ==========================================================================
   WHEN THE WORLD MOVES — illustrative event-time chart
   ========================================================================== */
const EVENT_EVENTS = [
  { idx: 1,  head: '2019 · Pulwama', mech: 'Airspace → routes' },
  { idx: 5,  head: '2020 · COVID-19', mech: 'Demand shock' },
  { idx: 13, head: '2022 · Ukraine war', mech: 'Oil → ATF' },
  { idx: 17, head: '2023 · Go First', mech: 'Capacity loss' },
  { idx: 28, head: '2026 · W. Asia', mech: 'Oil → ATF' }
];

// Illustrative normalized reconstruction, 2019 Q1 (100 = pre-event) → 2026 Q2
const EVENT_INDEX = [100, 112, 104, 102, 96, 62, 70, 82, 88, 92, 96, 100, 106, 118, 122, 120, 112, 118, 110, 108, 106, 108, 107, 109, 108, 110, 112, 115, 124, 128];

function buildEventLabels() {
  const labels = [];
  for (let y = 2019; y <= 2026; y++) {
    for (let q = 1; q <= 4; q++) labels.push(`${y} Q${q}`);
  }
  return labels.slice(0, EVENT_INDEX.length);
}

function renderEventsChart() {
  const ctx = document.getElementById('cpiEventsChart')?.getContext('2d');
  if (!ctx) return;

  const isDark = cpiState.theme === 'dark';
  const airColor = isDark ? '#38BDF8' : '#0284C7';
  const cpiColor = isDark ? '#FBBF24' : '#D97706';
  const labels = buildEventLabels();

  // small legend chips injected above the chart
  const wrap = document.getElementById('cpi-events-wrap');
  if (wrap) {
    let legend = wrap.querySelector('.cpi-chart-legend');
    if (!legend) {
      legend = document.createElement('div');
      legend.className = 'cpi-chart-legend';
      wrap.insertBefore(legend, wrap.firstChild);
    }
    legend.innerHTML = `
      <span class="cpi-legend-chip"><i style="background:${airColor};"></i>Illustrative airfare index</span>
      <span class="cpi-legend-chip"><i style="background:${cpiColor};"></i>Pre-event reference (100)</span>
      <span class="cpi-legend-chip cpi-legend-seg">▍ event marker</span>`;
  }

  const eventsPlugin = {
    id: 'eventMarkers',
    afterDraw(chart) {
      const { ctx: c, chartArea: a, scales } = chart;
      const base = scales.x;
      c.save();
      EVENT_EVENTS.forEach(ev => {
        const x = base.getPixelForValue(ev.idx);
        if (x < a.left - 2 || x > a.right + 2) return;

        // annotation gutter above the plot area
        c.strokeStyle = isDark ? 'rgba(148,163,184,0.35)' : 'rgba(100,116,139,0.35)';
        c.lineWidth = 1;
        c.setLineDash([3, 4]);
        c.beginPath();
        c.moveTo(x, a.top);
        c.lineTo(x, a.bottom);
        c.stroke();
        c.setLineDash([]);

        c.fillStyle = isDark ? '#93A3B8' : '#475569';
        c.font = "600 8.5px 'JetBrains Mono', monospace";
        c.textAlign = 'center';
        const headY = a.top - 30;
        const mechY = a.top - 17;
        c.fillText(ev.head, x, headY);
        c.fillStyle = isDark ? '#64748B' : '#94A3B8';
        c.fillText(ev.mech, x, mechY);
        c.fillRect(x - 3, a.top - 38, 6, 2);
      });
      c.restore();
    }
  };

  cpiState.eventsChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [
        {
          label: 'Illustrative airfare index',
          data: EVENT_INDEX,
          borderColor: airColor,
          backgroundColor: airColor,
          fill: false,
          borderWidth: 2.2,
          tension: 0.32,
          pointRadius: 1.5,
          pointHoverRadius: 5,
          pointBackgroundColor: airColor
        },
        {
          label: 'Pre-event reference (100)',
          data: labels.map(() => 100),
          borderColor: isDark ? 'rgba(251,191,36,0.6)' : 'rgba(217,119,6,0.6)',
          borderWidth: 1.4,
          borderDash: [6, 5],
          pointRadius: 0,
          fill: false,
          tension: 0
        }
      ]
    },
    plugins: [eventsPlugin],
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'nearest', intersect: false },
      animation: { duration: 500 },
      layout: { padding: { top: 40, right: 14 } },
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
            label: (ctx) => ` Illustrative index: ${ctx.parsed.y}`
          }
        }
      },
      scales: {
        x: {
          grid: { display: false },
          ticks: {
            font: { size: 10 },
            color: isDark ? '#93A3B8' : '#64748B',
            maxTicksLimit: 12,
            callback: function (val, idx) {
              return idx % 4 === 0 ? String(this.getLabelForValue(val)).slice(0, 4) : '';
            }
          },
          title: {
            display: true,
            text: 'Time',
            font: { size: 10, weight: '700' },
            color: isDark ? '#93A3B8' : '#64748B'
          }
        },
        y: {
          min: 40,
          max: 145,
          position: 'left',
          grid: { color: isDark ? '#141E2F' : '#EAEEF4' },
          ticks: { font: { size: 10 }, color: isDark ? '#93A3B8' : '#64748B', callback: v => v.toFixed(0) },
          title: {
            display: true,
            text: 'Normalized airfare index (100 = pre-event)',
            font: { size: 10, weight: '700' },
            color: isDark ? '#93A3B8' : '#64748B'
          }
        }
      }
    }
  });
}

/* ==========================================================================
   BOOT
   ========================================================================== */
document.addEventListener('DOMContentLoaded', () => {
  initTheme();
  initHeader();
  initReveal();
  renderBasket();
  renderDrivers();
  renderEventsChart();
});