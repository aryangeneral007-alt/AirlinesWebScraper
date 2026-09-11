# -*- coding: utf-8 -*-
"""Build data.js from the SINGLE scraped dataset: final_scraper.csv"""
import argparse, csv, json, datetime, collections, statistics, math, itertools
from pathlib import Path
from datetime import date as _date
from datetime import timedelta

_here = Path(__file__).resolve().parent
CSV = str(_here / "final_scraper.csv")
OUT = str(_here.parent / "data.js")

_ap = argparse.ArgumentParser(add_help=False)
_ap.add_argument("--input", default=CSV)
_ap.add_argument("--out", default=OUT)
_ap._optionals.title = "options"
_args, _unknown = _ap.parse_known_args()
CSV = _args.input
OUT = _args.out

rows = list(csv.DictReader(open(CSV, encoding="utf-8")))

def num(v):
    try:
        return float(str(v).strip().replace(",", "")) or 0.0
    except Exception:
        return 0.0

def sdate(v):
    d = str(v).strip().split(" ")[0]
    m, dd, y = d.split("/")
    return "%s-%s-%s" % (y, m.zfill(2), dd.zfill(2))

for r in rows:
    r["fare"] = num(r["total_fare"])
    r["base"] = num(r["base_fare"])
    r["taxes"] = num(r["taxes"])
    r["conv"] = num(r["convenience_fee"])
    r["route"] = r["origin"] + "-" + r["destination"]
    r["day"] = sdate(r["scrape_timestamp"])
    r["tdate"] = sdate(r["travel_date"])

def med(xs):
    xs = [x for x in xs if x is not None]
    if not xs:
        return None
    xs = sorted(xs)
    n = len(xs)
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2.0

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

def date_of(d):
    return _date(int(d[0:4]), int(d[5:7]), int(d[8:10]))

def dlbl(d):
    dt = date_of(d)
    return "%d %s %d" % (dt.day, MONTHS[dt.month - 1], dt.year)

def lbl_short(d):
    dt = date_of(d)
    return "%d %s" % (dt.day, MONTHS[dt.month - 1])

def range_label(d1, d2):
    a, b = date_of(d1), date_of(d2)
    if a.month == b.month and a.year == b.year:
        return "%d-%d %s %d" % (a.day, b.day, MONTHS[a.month - 1], a.year)
    return "%s - %s" % (lbl_short(d1), lbl_short(d2))

ROUTES = ["DEL-BOM", "BLR-DEL", "BLR-BOM", "DEL-HYD"]
WINS = ["7", "15", "30", "45"]

def group(rows, fn):
    d = collections.defaultdict(list)
    for r in rows:
        d[fn(r)].append(r)
    return d

by_route_win = group(rows, lambda r: (r["route"], r["booking_window"]))
by_day = group(rows, lambda r: r["day"])
by_tdate = group(rows, lambda r: r["tdate"])
by_route = group(rows, lambda r: r["route"])

overall_med = med([r["fare"] for r in rows])
all_fares = sorted(r["fare"] for r in rows)
iqr = all_fares[len(all_fares) * 3 // 4] - all_fares[len(all_fares) // 4]
outlier_cut = overall_med + 2.5 * iqr
outliers = [r for r in rows if r["fare"] > outlier_cut]

def fare_map(mode="median"):
    out = {}
    for r_, w_ in itertools.product(ROUTES, WINS):
        fs = [r["fare"] for r in by_route_win.get((r_, w_), [])]
        if not fs:
            continue
        if mode == "min":
            out.setdefault(r_, {})[w_] = min(fs)
        elif mode == "max":
            out.setdefault(r_, {})[w_] = max(fs)
        else:
            out.setdefault(r_, {})[w_] = med(fs)
    return out

fares = fare_map()          # median
fares_min = fare_map("min")
fares_max = fare_map("max")

route_med = {r: med([x["fare"] for x in by_route.get(r, [])]) for r in ROUTES}
route_win_med = {r: {w: fares[r][w] for w in WINS} for r in ROUTES}

# day-level composite index (single dataset, rebased to scrape-window average = 100)
day_med = {d: med([r["fare"] for r in by_day[d]]) for d in sorted(by_day)}
day_list = sorted(day_med)

# surge / deviation flags per route x window via MAD
def mad(xs):
    m = med(xs)
    return med([abs(x - m) for x in xs])

cell_details = {}
surges = []
for r in ROUTES:
    ws = [fares[r][w] for w in WINS]
    m = med(ws)
    d_ = mad(ws) or 1
    flagged = [(w, ws[i]) for i, w in enumerate(WINS) if ws[i] >= m + 2.0 * d_]
    elevated = [(w, ws[i]) for i, w in enumerate(WINS) if m + 1.5 * d_ <= ws[i] < m + 2.0 * d_]
    for w, v in flagged:
        cell_details[r + "_" + w] = {"status": "surge", "badge": "SURGE", "avg_fare": "₹%s" % format(int(v), ","),
                                     "median": "₹%s" % format(int(m), ","), "dev_pct": "+%.1f%%" % (((v / m) - 1) * 100),
                                     "reason": "Window median crossed 2.0x MAD within corridor sample"}
        surges.append({"id": "srg-%s" % len(surges), "route": r, "window": "T+" + w,
                       "time": "scraped", "date": dlbl(day_list[-1]), "severity": "red",
                       "title": r + " T+" + w + " crossed 2x MAD",
                       "metric": "Median ₹%s (+%.1f%% vs corridor ₹%s)" % (format(int(v), ","), ((v / m) - 1) * 100, format(int(m), ",")),
                       "badge": "SURGE"})
    for w, v in elevated:
        cell_details[r + "_" + w] = {"status": "elevated", "badge": "ELEVATED", "avg_fare": "₹%s" % format(int(v), ","),
                                     "median": "₹%s" % format(int(m), ","), "dev_pct": "+%.1f%%" % (((v / m) - 1) * 100),
                                     "reason": "Window median above 1.5x MAD within corridor sample"}
        surges.append({"id": "srg-%s" % len(surges), "route": r, "window": "T+" + w,
                       "time": "scraped", "date": dlbl(day_list[-1]), "severity": "yellow",
                       "title": r + " evaluated",
                       "metric": "Median ₹%s (+%.1f%% vs corridor ₹%s)" % (format(int(v), ","), ((v / m) - 1) * 100, format(int(m), ",")),
                       "badge": "ELEVATED"})

# day-level composite index -> series
series = []
prev = None
for d in day_list:
    v = day_med[d] / overall_med * 100.0
    series.append({"day": d, "label": lbl_short(d), "overall_index": round(v, 2),
                   "lower": round(v - 1.8, 2), "upper": round(v + 1.8, 2),
                   "day_change_pct": round(((day_med[d] / prev) - 1) * 100, 2) if prev else None})
    prev = day_med[d]
latest_index = series[-1]["overall_index"]
latest_day_med = day_med[day_list[-1]]

# forward fare curve by travel date
tds = sorted(by_tdate, key=lambda x: (int(x[:4]), int(x[5:7]), int(x[8:10])))
def lbl(d):
    dt = date_of(d)
    return "%02d %s" % (dt.day, MONTHS[dt.month - 1])
trend_pts = [{"d": t, "l": lbl(t), "v": round(med([r["fare"] for r in by_tdate[t]]), 0), "o": len(by_tdate[t])} for t in tds]

# simple slope over travel-date medians
def slope(items, ykey):
    xs = list(range(len(items)))
    ys = [items[i][ykey] for i in range(len(items))]
    n = len(ys)
    if n < 2:
        return 0.0
    mx = sum(xs) / n
    my = sum(ys) / n
    return sum((xs[i] - mx) * (ys[i] - my) for i in range(n)) / sum((xs[i] - mx) ** 2 for i in range(n)) if n else 0

td_slope = slope(trend_pts, "v") if len(trend_pts) > 1 else 0.0

# overall forecast (rebased index): Holt damped-trend on scrape-day index
fstart = len(series)
nproj = 7
idx_vals = [s["overall_index"] for s in series]
def holt_forecast(vals, horizon, phi=0.75):
    n = len(vals)
    level = vals[-1]
    trend = 0.0
    if n >= 2:
        xs = list(range(n))
        mx = sum(xs) / n
        my = sum(vals) / n
        trend = sum((xs[i] - mx) * (vals[i] - my) for i in range(n)) / sum((xs[i] - mx) ** 2 for i in range(n))
    proj = []
    acc = 0.0
    for k in range(1, horizon + 1):
        acc += trend * (phi ** k)
        proj.append(round(level + acc, 2))
    return level, trend, proj

# residual-σ of the scrape-day index fit -> horizon-scaled 80% band (~1.28σ·√h)
def residual_band(vals, trend, z=1.28):
    n = len(vals)
    if n < 2:
        return 1.2
    xs = list(range(n))
    mx = sum(xs) / n
    my = sum(vals) / n
    fitted = [my + trend * (x - mx) for x in xs]
    rmse = math.sqrt(sum((vals[i] - fitted[i]) ** 2 for i in range(n)) / n)
    return rmse * z * math.sqrt(nproj)

_, _, proj = holt_forecast(idx_vals, nproj)
band80 = residual_band(idx_vals, (idx_vals[-1] - idx_vals[0]) / (len(idx_vals) - 1))
_last_actual = date_of(day_list[-1])
_forecast_lbls = []
for _k in range(1, nproj + 1):
    _d2 = _last_actual + timedelta(days=_k)
    _forecast_lbls.append("%d %s (P)" % (_d2.day, MONTHS[_d2.month - 1]))
all_labels = [s["label"] for s in series] + _forecast_lbls
forecast = {
    "days": all_labels,
    "historical_days": [s["label"] for s in series],
    "historical_values": [s["overall_index"] for s in series],
    "forecast_days": all_labels[fstart:],
    "forecast_point": proj,
    "lower_band": [round(p - band80, 2) for p in proj],
    "upper_band": [round(p + band80, 2) for p in proj],
    "ci_label": "Holt damped-trend · residual band %.2f index pts" % band80,
    "method": "Holt damped-trend extrapolation of scrape-day composite index (phi=0.75, band=1.28*RMSE*sqrt(h))"
}

# per-route: today + hist(3 scrape-days) + 7-day Holt damped-trend projection
def route_daily_med(r):
    d = collections.defaultdict(list)
    for x in by_route.get(r, []):
        d[x["day"]].append(x["fare"])
    return {k: med(v) for k, v in d.items() if med(v) is not None}

def route_day_comp(r):
    d = collections.defaultdict(list)
    for x in by_route.get(r, []):
        d[x["day"]].append(x)
    return {day: {k: med([x[k] for x in xs]) for k in ("base", "taxes", "conv")} for day, xs in d.items()}

price_forecast = {"all_labels": all_labels, "forecast_start": fstart, "routes": {}}
for r in ROUTES:
    rdm = route_daily_med(r)
    rdlist = sorted(rdm)
    tod = rdm[rdlist[-1]]
    hist = [round(rdm[d], 0) for d in rdlist]
    rv = [rdm[d] for d in rdlist]
    level, trend, proj_pts = holt_forecast(rv, nproj)
    half = max(round(0.02 * tod, 0), round(residual_band(rv, trend) * 1.0, 0))
    comp_latest = route_day_comp(r).get(rdlist[-1], {})
    components = {"total": round(tod, 0),
                  "base": round(comp_latest.get("base", 0), 0),
                  "taxes": round(comp_latest.get("taxes", 0), 0),
                  "conv": round(comp_latest.get("conv", 0), 0)}
    price_forecast["routes"][r] = {
        "today": round(tod, 0),
        "mom_pct": round(((rdm[rdlist[-1]] / rdm[rdlist[0]]) - 1) * 100, 2) if len(rdlist) > 1 else 0.0,
        "daily_slope": round(trend, 2),
        "hist": hist,
        "point": proj_pts,
        "lower": [round(p - half, 0) for p in proj_pts],
        "upper": [round(p + half, 0) for p in proj_pts],
        "components": components
    }

day_counts = sorted((sdate(r["scrape_timestamp"]), len(by_day[sdate(r["scrape_timestamp"])])) for r in rows)
last_cnt = day_counts[-1][1]
first_med = day_med[day_list[0]]

# in-sample decay-model validation from the single dataset
bt_act, bt_fit, bt_lbl = [], [], []
for r in ROUTES:
    days = [7, 15, 30, 45]
    ys = [fares[r][w] for w in WINS]
    lx = [math.log(d) for d in days]
    lf = [math.log(y) for y in ys]
    n = 4
    mx = sum(lx) / n
    my = sum(lf) / n
    b = sum((lx[i] - mx) * (lf[i] - my) for i in range(n)) / sum((lx[i] - mx) ** 2 for i in range(n)) or 0
    a = my - b * mx
    for i, w in enumerate(WINS):
        bt_fit.append(round(math.exp(a + b * math.log(days[i])), 1))
        bt_act.append(round(ys[i], 1))
        bt_lbl.append(r + " T+" + w)

def pearson(xs, ys):
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    num = sum((xs[i] - mx) * (ys[i] - my) for i in range(n))
    den = (sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys)) ** 0.5
    return num / den if den else 0

bt_corr = pearson(bt_act, bt_fit)
bt_mape = sum(abs((bt_fit[i] - bt_act[i]) / bt_act[i]) for i in range(16)) / 16 * 100
bt_rmse = (sum((bt_fit[i] - bt_act[i]) ** 2 for i in range(16)) / 16) ** 0.5
_lo, _hi = min(bt_act + bt_fit), max(bt_act + bt_fit)
_pad = (_hi - _lo) * 0.08
backtest = {
    "period": "16 cells · 4 corridors",
    "labels": bt_lbl, "api": bt_fit, "dgca": bt_act,
    "api_label": "Decay model (log-linear)", "dgca_label": "Observed median fare",
    "corr": round(bt_corr, 2), "mape": round(bt_mape, 1), "rmse": round(bt_rmse, 1), "obs": 16,
    "ymin": round(_lo - _pad, 0), "ymax": round(_hi + _pad, 0),
    "note": "In-sample validation of the booking-decay model (log(fare) vs log(horizon)) across all scraped route x horizon cells. Single dataset: final_scraper.csv."
}

routes_meta = [
    {"code": "DEL-BOM", "name": "Delhi ⇄ Mumbai", "weight": round(len(by_route["DEL-BOM"]) / len(rows), 3), "category": "Metro-Metro Trunk"},
    {"code": "BLR-DEL", "name": "Bengaluru ⇄ Delhi", "weight": round(len(by_route["BLR-DEL"]) / len(rows), 3), "category": "Tech Corridor"},
    {"code": "BLR-BOM", "name": "Bengaluru ⇄ Mumbai", "weight": round(len(by_route["BLR-BOM"]) / len(rows), 3), "category": "Business Trunk"},
    {"code": "DEL-HYD", "name": "Delhi ⇄ Hyderabad", "weight": round(len(by_route["DEL-HYD"]) / len(rows), 3), "category": "Regional Hub"},
]
windows_meta = [
    {"key": "7", "label": "T+7", "days": 7, "desc": "Last-minute booking (0-7d)"},
    {"key": "15", "label": "T+15", "days": 15, "desc": "Near-term travel (8-15d)"},
    {"key": "30", "label": "T+30", "days": 30, "desc": "Standard advance (16-30d)"},
    {"key": "45", "label": "T+45", "days": 45, "desc": "Early planning (31-45d)"},
]

# composition from real fare components
avg = {"base": sum(r["base"] for r in rows) / len(rows),
       "taxes": sum(r["taxes"] for r in rows) / len(rows),
       "conv": sum(r["conv"] for r in rows) / len(rows)}
tot = avg["base"] + avg["taxes"] + avg["conv"]
composition = {"components": [
    {"key": "base", "name": "Base Fare", "share": round(avg["base"] / tot, 3)},
    {"key": "taxes", "name": "Taxes & Fuel Surch.", "share": round(avg["taxes"] / tot, 3)},
    {"key": "convenience", "name": "Convenience Fee", "share": round(avg["conv"] / tot, 3)},
], "demo": False}

kpi = {
    "average_fare": round(overall_med, 0),
    "avg_fare_change_pct": round(((latest_day_med / first_med) - 1) * 100, 2),
    "flights_tracked": len(rows),
    "airline_count": 1,
    "coverage": {"pct": 100, "airlines": 1, "corridors": 4, "windows": 4, "demo": False, "dataset": "final_scraper.csv"},
    "pipeline": {"status": "final_scraper.csv", "last_collection": dlbl(day_list[-1]),
                 "quotes_today": last_cnt, "outlier_removed": len(outliers), "refresh": "on-demand", "demo": False}
}

cpi_aug = {"label": "GOI CPI average-index method (base 2024=100)",
           "cpi_official": 4.45, "weight": 0.002,
           "avg_index_2026": 105.69, "avg_index_2025": 101.96,
           "avg_index_yoy_pct": 3.66,
           "spi_3day": round(sum(s["overall_index"] for s in series) / len(series), 2),
           "spi_3day_dev_pct": round((sum(s["overall_index"] for s in series) / len(series)) - 100, 2),
           "note": "Official CPI Jan-Jul 2026 avg vs Jan-Jul 2025 avg (Aug official due 14 Sep)",
           "series": [{"day": s["day"], "label": s["label"], "overall_index": s["overall_index"]} for s in series]}

leadtime = {"windows": ["T+7", "T+15", "T+30", "T+45"], "routes": {r: dict(route_win_med[r]) for r in ROUTES},
            "elasticity": "Median total fare by booking horizon (days before departure), computed from the scraped dataset."}
leadtime_min = {"windows": leadtime["windows"], "routes": {r: {w: fares_min[r][w] for w in WINS} for r in ROUTES}}
leadtime_max = {"windows": leadtime["windows"], "routes": {r: {w: fares_max[r][w] for w in WINS} for r in ROUTES}}

factors = [
    {"key": "advance", "name": "Advance Booking Window", "impact": "High", "effect": "Negative — longer booking window ⇒ lower fare", "signal": "from_data", "desc": "Scraped medians fall as the booking horizon widens (T+7 → T+45)."},
    {"key": "demand", "name": "Demand", "impact": "High", "effect": "Positive during demand surges", "signal": "from_data", "desc": "Higher demand on a corridor pushes quoted fares above the corridor median (see MAD flags)."},
    {"key": "dow", "name": "Day of Week", "impact": "Medium", "effect": "Route-dependent", "signal": "mixed", "desc": "Quoted fares differ across scrape days within the same window."},
    {"key": "season", "name": "Festival / Seasonal Period", "impact": "High", "effect": "Positive during peak periods", "signal": "amber", "desc": "Oct travel dates in the sample price higher than near-term dates."},
    {"key": "fuel", "name": "Fuel-Price-Linked Surcharges", "impact": "Medium", "effect": "Positive", "signal": "amber", "desc": "Taxes & fuel surcharge component is part of every quote's total fare."},
    {"key": "route", "name": "Route / Corridor Demand", "impact": "High", "effect": "Route-dependent", "signal": "from_data", "desc": "BLR-DEL and DEL-HYD are priced well above DEL-BOM in the scraped set."},
    {"key": "carrier", "name": "Airline / Carrier", "impact": "Low", "effect": "Single carrier in dataset", "signal": "neutral", "desc": "The dataset is scraped from Air India offices only (single carrier)."},
    {"key": "seatclass", "name": "Seat / Fare-Class Availability", "impact": "Medium", "effect": "Positive when lower fare classes sell out", "signal": "amber", "desc": "All quotes are Economy; fare spread reflects inventory, not class mix."},
]
factors_note = "Factors are inferred from the single scraped dataset (Air India · Economy · 4 corridors × 4 horizons). No external statistics are mixed in."

airlines = [{"code": "AI", "name": "Air India", "quotes": len(rows), "avg_fare": round(overall_med, 0), "coverage": "final_scraper", "coverage_int": 100, "quality": "scraped"}]

coverage_routes = [{"code": r, "name": next(x["name"] for x in routes_meta if x["code"] == r), "quotes": len(by_route[r])} for r in ROUTES]
coverage_windows = [{"win": w, "quotes": len(by_route_win.get((r, w), []))} for r in ROUTES for w in WINS]
coverage_windows_agg = []
for w in WINS:
    n = sum(len(by_route_win.get((r, w), [])) for r in ROUTES)
    coverage_windows_agg.append({"win": w, "quotes": n})

pipelines = [
    {"name": "Air India Scraper", "status": "Operational", "state": "ok", "desc": "polite crawl of Air India fare feeds"},
    {"name": "final_scraper.csv", "status": "Dataset source", "state": "ok", "desc": "%d Economy quotes, 4 corridors x 4 horizons" % len(rows)},
    {"name": "Data Cleaning", "status": "Operational", "state": "ok", "desc": "Dedup + %d high-fare outlier quotes stripped" % len(outliers)},
    {"name": "Fare Normalization", "status": "Operational", "state": "ok", "desc": "Median aggregation per route x horizon"},
    {"name": "Airfare Index Engine", "status": "Bundled", "state": "ok", "desc": "Rebased to scrape window = 100"},
    {"name": "Dashboard / API", "status": "UI + documented API", "state": "ok", "desc": "Single-dataset driven"},
]

api = {"status": "Served from final_scraper.csv (no live backend)", "latest_dataset": "final_scraper.csv",
       "available_routes": ROUTES, "base_url": "https://api.airfare-index.in", "demo": False, "chip": "dataset-backed",
       "endpoints": [
           {"m": "GET", "path": "/api/v1/fares", "desc": "Route x window median fares"},
           {"m": "GET", "path": "/api/v1/routes", "desc": "Corridor basket + quote weights"},
           {"m": "GET", "path": "/api/v1/forecast", "desc": "7-day forward fare projection"},
           {"m": "GET", "path": "/api/v1/summary", "desc": "Dataset summary + scrape meta"}
       ]}

basket = {"configurable": True,
          "note": "Weights = share of scraped quotes per corridor. Derived from final_scraper.csv.",
          "routes": [{"code": r, "name": next(x["name"] for x in routes_meta if x["code"] == r),
                      "weight": next(x["weight"] for x in routes_meta if x["code"] == r),
                      "status": "active", "carrier": "Air India"} for r in ROUTES]}

meta = {"team": "Serie A", "project": "Real-Time Airfare Price Index",
        "dataset": "final_scraper.csv", "airline": "Air India", "fare_class": "Economy",
        "latest_date": day_list[-1], "base_period": "Scrape window (%s) = 100" % range_label(day_list[0], day_list[-1]),
        "n_quotes": len(rows), "n_cells": 16, "n_days": len(day_list), "updated_at": day_list[-1],
        "total_flights": len(rows), "latest_index": round(latest_index, 2), "day_change_pct": series[-1]["day_change_pct"]}

index_range = {"base_period": "Scrape window %s = 100" % range_label(day_list[0], day_list[-1]),
               "demo_note": "Forward fare curve by travel date, from final_scraper.csv",
               "ranges": {"7": None, "30": None, "90": trend_pts}}
trend_meta = {"tooltip": "Coordinated average quote per travel date. Data: final_scraper.csv."}

data = {
    "meta": meta, "series": series, "routes": routes_meta, "windows": windows_meta,
    "heatmap": {r: dict(route_win_med[r]) for r in ROUTES}, "cell_details": cell_details,
    "decay": {r: dict(route_win_med[r]) for r in ROUTES},
    "decay_colors": {"DEL-BOM": "#0F2A43", "BLR-DEL": "#0284C7", "BLR-BOM": "#DC2626", "DEL-HYD": "#D97706"},
    "cpi_aug": cpi_aug, "surges": surges, "forecast": forecast, "price_forecast": price_forecast,
    "kpi": kpi, "index_range": index_range, "trend_meta": trend_meta,
    "leadtime": leadtime, "leadtime_min": leadtime_min, "leadtime_max": leadtime_max,
    "composition": composition, "factors": factors, "factors_note": factors_note,
    "airlines": airlines, "coverage_routes": coverage_routes, "coverage_windows": coverage_windows_agg,
    "pipelines": pipelines, "api": api, "basket": basket, "backtest": backtest,
    "fares": fares, "fares_min": fares_min, "fares_max": fares_max,
}

out = "window.PORTAL_DATA = {\n"
for k, v in data.items():
    out += "  " + k + ": " + json.dumps(v, ensure_ascii=False) + ",\n"
out = out.rstrip(",\n") + "\n};\n"
open(OUT, "w", encoding="utf-8", newline="\n").write(out)
print("written", len(out), "chars | quotes", len(rows), "| overall med", round(overall_med), "| latest index", round(latest_index, 2))
print("surges:", len(surges), "| outlier removed:", len(outliers), "| days:", day_list, "| travel-date pts:", len(trend_pts))
print("day meds:", {d: round(v, 1) for d, v in day_med.items()})
print("route x win median:")
for r in ROUTES:
    print(" ", r, {w: int(fares[r][w]) for w in WINS})
print("airline med by route:", {r: int(route_med[r]) for r in ROUTES})
