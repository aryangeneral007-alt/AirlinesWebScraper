# -*- coding: utf-8 -*-
"""
update_site.py — connects the Air India scraper to the website bundle.

After each successful collection run this script:

  1. Scans sih/data/raw/** for new scrape CSVs (incremental).
  2. Normalizes them into the exact schema data.js expects and merges
     them into Desktop/final_scraper.csv (existing history preserved,
     exact duplicates removed).
  3. Runs build_final.py to regenerate site data.js.
  4. Deploys the fresh data.js to the live site folder and the zip.

Usage:
    python update_site.py                # incremental rebuild + deploy
    python update_site.py --rebuild      # re-ingest ALL raw files (full union)
    python update_site.py --since 2026-09-10   # force-ingest >= this scrape day
    python update_site.py --no-deploy    # rebuild data.js but skip folder/zip

Exit codes:
    0  ok (even when there was nothing new — the bundle is still rebuilt)
    1  error
Intended to be chained by run_collection.py after a successful scrape, or run
manually / from Windows Task Scheduler via UPDATE.bat.
"""
import argparse
import csv
import datetime
import io
import os
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime as Dt
from datetime import timedelta
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PROJECT = Path(__file__).resolve().parent        # repo/pipeline
ROOT = PROJECT.parent                            # repo root (website files live here)
RAW_GLOB = PROJECT / "data" / "raw"
DEFAULT_INPUT = PROJECT / "final_scraper.csv"    # pipeline\final_scraper.csv
DEFAULT_SITE = ROOT                              # website files at repo root
DEFAULT_ZIP = Path(str(ROOT / "airfare-index-dashboard.zip"))
DEV_SITE = PROJECT / "dev"
BUILD_FINAL = PROJECT / "build_final.py"

LOGS = PROJECT / "logs"
LOGS.mkdir(parents=True, exist_ok=True)

FINAL_COLS = ["origin", "destination", "airline", "flight_number", "travel_date",
              "departure_time", "fare_class", "total_fare", "base_fare", "taxes",
              "convenience_fee", "booking_window", "scrape_timestamp"]
REQUIRED = {"origin", "destination", "total_fare", "booking_window", "scrape_timestamp"}

CONVENIENCE_FEE = 399.0   # constant Air India convenience fee (matches final_scraper.csv)


def log(msg):
    print(msg, flush=True)


def parse_ts(s):
    s = (s or "").strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M",
                "%m/%d/%Y %H:%M:%S", "%m/%d/%Y %H:%M", "%m/%d/%Y"):
        try:
            return Dt.strptime(s, fmt)
        except ValueError:
            pass
    for fmt in ("%Y-%m-%d",):
        try:
            return Dt.strptime(s, fmt)
        except ValueError:
            pass
    return None


def parse_date(s):
    s = (s or "").strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%m/%d/%Y", "%m/%d/%Y %H:%M"):
        try:
            return Dt.strptime(s.split(" ")[0], fmt.split(" ")[0])
        except ValueError:
            continue
    dt = parse_ts(s)
    return dt.date() if dt else None


def num(v):
    try:
        return float(str(v).strip().replace(",", ""))
    except Exception:
        return 0.0


def fmt_num(v):
    v = round(num(v), 2)
    return str(int(v)) if float(v).is_integer() else ("%.2f" % v)


def fmt_mdy(dt):
    return "%d/%d/%d" % (dt.month, dt.day, dt.year)


def canonical(row):
    """Normalize a dict of raw fields into a final-schema dict (internal)."""
    try:
        flight = (row.get("flight_number") or "").strip()
        o = (row.get("origin") or "").strip().upper()
        d = (row.get("destination") or "").strip().upper()
        if not o or not d or not flight:
            return None
        ts = parse_ts(row.get("scrape_timestamp"))
        tdate = parse_date(row.get("travel_date"))
        dtime = parse_ts(row.get("departure_time")) if (row.get("departure_time") or "").strip() else None
        if not ts or not tdate:
            return None
        fare = num(row.get("total_fare"))
        base = num(row.get("base_fare")) if (row.get("base_fare") or "").strip() else 0.0
        taxes = num(row.get("taxes")) if (row.get("taxes") or "").strip() else 0.0
        conv = num(row.get("convenience_fee")) if (row.get("convenience_fee") or "").strip() else CONVENIENCE_FEE
        win_raw = str(row.get("booking_window") or "").strip()
        win = str(int(float(win_raw))) if win_raw else None
        if fare <= 0 or win is None:
            return None
        fc = (row.get("fare_class") or "Economy").strip() or "Economy"
        # canonical timestamp/date with second precision on scrape, minute on departure
        out = {
            "origin": o, "destination": d, "airline": (row.get("airline") or "Air India").strip(),
            "flight_number": flight, "travel_date": tdate, "departure_time": dtime,
            "fare_class": fc, "total_fare": fare, "base_fare": base, "taxes": taxes,
            "convenience_fee": conv, "booking_window": win, "scrape_timestamp": ts,
        }
        return out
    except Exception:
        return None


def row_key(c):
    dtime_c = c["departure_time"].strftime("%Y-%m-%dT%H:%M") if c["departure_time"] else ""
    return (c["origin"], c["destination"], c["flight_number"],
            c["travel_date"].strftime("%Y-%m-%d"), dtime_c,
            round(c["total_fare"], 2), round(c["base_fare"], 2), round(c["taxes"], 2),
            round(c["convenience_fee"], 2), c["booking_window"],
            c["scrape_timestamp"].strftime("%Y-%m-%dT%H:%M:%S"), c["fare_class"].upper())


def read_final_csv(path):
    rows = []
    last_day = None
    if Path(path).is_file():
        with io.open(path, encoding="utf-8-sig") as fh:
            for r in csv.DictReader(fh):
                c = canonical(r)
                if not c:
                    continue
                rows.append(c)
                if last_day is None or c["scrape_timestamp"].date() > last_day:
                    last_day = c["scrape_timestamp"].date()
    return rows, last_day


def scan_raw_files(raw_root):
    files = []
    for p in sorted(raw_root.rglob("*.csv")):
        files.append(p)
    return files


def read_raw_file(path):
    with io.open(path, encoding="utf-8-sig") as lfh:
        try:
            rows = list(csv.DictReader(lfh))
        except Exception:
            return []
    if not rows:
        return []
    cols = set(rows[0].keys())
    if not REQUIRED.issubset(cols):
        return []
    out = []
    seen = set()
    for r in rows:
        c = canonical(r)
        if not c:
            continue
        k = row_key(c)
        if k in seen:
            continue
        seen.add(k)
        out.append(c)
    return out


def write_final_csv(path, rows):
    tmp = Path(str(path) + ".tmp")
    with io.open(tmp, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FINAL_COLS)
        w.writeheader()
        ordered = sorted(rows, key=lambda c: (c["scrape_timestamp"], c["origin"], c["destination"], c["flight_number"]))
        for c in ordered:
            w.writerow({
                "origin": c["origin"], "destination": c["destination"], "airline": c["airline"],
                "flight_number": c["flight_number"], "travel_date": fmt_mdy(c["travel_date"]),
                "departure_time": c["departure_time"].strftime("%m/%d/%Y %H:%M") if c["departure_time"] else "",
                "fare_class": c["fare_class"], "total_fare": fmt_num(c["total_fare"]),
                "base_fare": fmt_num(c["base_fare"]), "taxes": fmt_num(c["taxes"]),
                "convenience_fee": fmt_num(c["convenience_fee"]), "booking_window": c["booking_window"],
                "scrape_timestamp": c["scrape_timestamp"].strftime("%m/%d/%Y %H:%M"),
            })
    shutil.move(str(tmp), str(path))


def main():
    ap = argparse.ArgumentParser(description="Rebuild website data from scraper output")
    ap.add_argument("--input", default=str(DEFAULT_INPUT))
    ap.add_argument("--raw", default=str(RAW_GLOB))
    ap.add_argument("--out", default=str(DEFAULT_SITE / "data.js"))
    ap.add_argument("--dev-out", default=str(DEV_SITE / "data.js"))
    ap.add_argument("--rebuild", action="store_true", help="re-ingest ALL raw files")
    ap.add_argument("--since", default=None, help="force-ingest raws from this scrape day (YYYY-MM-DD)")
    ap.add_argument("--no-deploy", action="store_true", help="skip folder/zip deploy")
    args = ap.parse_args()

    stamp = Dt.now().strftime("%Y%m%d_%H%M%S")
    log_path = LOGS / ("update_%s.log" % stamp)
    global log
    fh = io.open(log_path, "a", encoding="utf-8")
    def log(msg):
        line = "[%s] %s" % (Dt.now().strftime("%Y-%m-%d %H:%M:%S"), msg)
        print(line, flush=True)
        fh.write(line + "\n")
        fh.flush()

    log("=== update_site start ===")

    final_path = Path(args.input)
    existing_rows, last_day = read_final_csv(final_path)
    existing_keys = set(row_key(c) for c in existing_rows)
    log("existing final_scraper.csv: %d rows, last scrape day %s" % (len(existing_rows), last_day or "-"))

    raw_root = Path(args.raw)
    new_rows = []
    skipped = 0
    if raw_root.is_dir():
        for p in scan_raw_files(raw_root):
            day = None
            with io.open(p, encoding="utf-8-sig") as lfh:
                try:
                    head = list(csv.DictReader(lfh))
                except Exception:
                    head = []
            if not head:
                skipped += 1
                continue
            cols = set(head[0].keys())
            if not REQUIRED.issubset(cols):
                skipped += 1
                continue
            day = None
            for r in head[:5]:
                ts = parse_ts(r.get("scrape_timestamp"))
                if ts:
                    day = ts.date()
                    break
            if day is None:
                day = parse_date((head[0].get("scrape_timestamp") or ""))
            if day is None:
                skipped += 1
                continue
            if not args.rebuild and args.since is None and last_day is not None and day <= last_day:
                skipped += 1
                continue
            if args.since and day < Dt.strptime(args.since, "%Y-%m-%d").date():
                skipped += 1
                continue
            before = len(new_rows)
            for c in read_raw_file(p):
                k = row_key(c)
                if k in existing_keys:
                    continue
                existing_keys.add(k)
                new_rows.append(c)
            if len(new_rows) > before:
                log("  ingested %s (%s, +%d new)" % (p.name, day, len(new_rows) - before))
        log("raw scan: %d new rows added, %d files skipped" % (len(new_rows), skipped))
    else:
        log("WARN: raw folder not found: %s" % raw_root)

    # preserve existing rows exactly; append only genuinely new ones
    total_rows = existing_rows + sorted(new_rows, key=lambda c: (c["scrape_timestamp"], c["origin"], c["destination"], c["flight_number"]))
    changed = new_rows != [] or not Path(final_path).is_file()

    if Path(final_path).is_file() and changed:
        shutil.copy2(str(final_path), str(final_path) + ".prev")
        log("previous final_scraper.csv backed up to .prev")

    if changed:
        write_final_csv(final_path, total_rows)
        log("final_scraper.csv written: %d rows (was %d)" % (len(total_rows), len(existing_rows)))
    else:
        log("no data change — final_scraper.csv untouched (%d rows)" % len(existing_rows))

    # rebuild data.js
    build = Path(BUILD_FINAL)
    if not build.is_file():
        log("ERROR: build_final.py not found at %s" % build)
        fh.close()
        return 1
    log("running build_final.py --input %s --out %s" % (final_path, args.out))
    try:
        r = subprocess.run([sys.executable, str(build), "--input", str(final_path), "--out", str(args.out)],
                           cwd=str(PROJECT), text=True)
    except Exception as e:
        log("ERROR running build_final.py: %s" % e)
        fh.close()
        return 1
    for line in (r.stdout or "").splitlines():
        log("  | " + line)
    if r.returncode != 0:
        log("ERROR: build_final.py exit code %d" % r.returncode)
        fh.close()
        return r.returncode

    if str(args.out) != str(args.dev_out):
        try:
            Path(args.dev_out).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(args.out), str(args.dev_out))
            log("dev copy refreshed: %s" % args.dev_out)
        except Exception as e:
            log("WARN: dev copy failed: %s" % e)

    if not args.no_deploy:
        site = DEFAULT_SITE
        zip_path = DEFAULT_ZIP
        try:
            site.mkdir(parents=True, exist_ok=True)
            target_js = str(site / "data.js")
            if os.path.abspath(str(args.out)).lower() != os.path.abspath(target_js).lower():
                shutil.copy2(str(args.out), target_js)
                log("deployed data.js to %s" % target_js)
            with zipfile.ZipFile(str(zip_path), "w", zipfile.ZIP_DEFLATED) as z:
                for f in sorted(site.rglob("*")):
                    if f.is_file():
                        z.write(str(f), str(f.relative_to(site)))
            log("deployed: %s (+ zip %s)" % (site, zip_path.name))
        except Exception as e:
            log("ERROR deploying: %s" % e)
            fh.close()
            return 1

    log("=== update_site done ===")
    fh.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())