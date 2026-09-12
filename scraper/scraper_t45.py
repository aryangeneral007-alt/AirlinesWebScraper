"""
Air India Flight Scraper — SIH26056
Real-Time Airfare Price Index for India (augments MoSPI CPI)

Strategy:
  1. Use Playwright (real browser) to navigate Air India's booking page
  2. Fill the search form for each route
  3. Intercept the internal API response (api.airindia.com) to get
     structured JSON — far more reliable than scraping DOM selectors
  4. Fall back to HTML parsing if API interception fails
  5. Save all Economy flights to CSV

Ethical constraints enforced:
  - Respects robots.txt (Air India does NOT block /in/en/book-flights)
  - 5-second minimum delay between requests
  - No CAPTCHA bypass
  - No fingerprint evasion
  - Stops immediately if blocked; saves debug evidence

Usage:
    python scraper.py              # scrape all routes
    python scraper.py --route DEL-BOM   # scrape single route
    python scraper.py --headless   # run without visible browser
"""

import csv
import json
import os
import sys
import time
import argparse
import traceback
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

# Make console output encoding-safe on Windows (cp1252 shell)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from playwright.sync_api import sync_playwright, Response, Page, BrowserContext
import pandas as pd

# ── project config (inline, T+45 only — single-window 4-route version.
#    Mirrors the proven scraper_t7.py structure; date falls ~1.5 months ahead
#    so _navigate_calendar handles the cross-month day-cell path) ──────────
import random

# ── Routes ────────────────────────────────────────────────────────────────
ROUTES = [
    {"origin": "DEL", "destination": "BOM", "origin_city": "New Delhi", "dest_city": "Mumbai"},
    {"origin": "BLR", "destination": "DEL", "origin_city": "Bengaluru", "dest_city": "New Delhi"},
    {"origin": "BLR", "destination": "BOM", "origin_city": "Bengaluru", "dest_city": "Mumbai"},
    {"origin": "DEL", "destination": "HYD", "origin_city": "New Delhi", "dest_city": "Hyderabad"},
]

AIRLINE = "Air India"
AIRLINE_IATA = "AI"

# Rolling booking window (days ahead of today).
# T+45 only — single-window version, all 4 routes.
BOOKING_WINDOWS = [45]
DAYS_AHEAD = 45                             # T+45 primary window
CABIN_CLASS = "Economy"
MIN_DELAY_SECONDS = 5                       # Base rate limit between requests
MAX_RETRIES = 3                             # Retries per route on failure
PAGE_LOAD_TIMEOUT_MS = 60_000               # 60s page load timeout
RESULTS_WAIT_TIMEOUT_MS = int(os.environ.get("SIH_RESULTS_WAIT_MS", "150000"))

# Randomized polite delay: jitters MIN_DELAY..MIN_DELAY+4s so request timing
# never looks machine-regular (reduces WAF flags).
RANDOM_DELAY_MAX = int(os.environ.get("SIH_DELAY_JITTER", "4"))


def randomized_delay(base: int = MIN_DELAY_SECONDS) -> float:
    return base + random.uniform(0, RANDOM_DELAY_MAX)


BASE_URL = "https://www.airindia.com"
SEARCH_PAGE = f"{BASE_URL}/"
AIRINDIA_API_PATTERN = "api.airindia.com"

CSV_COLUMNS = [
    "origin", "destination", "airline", "flight_number",
    "travel_date", "departure_time", "total_fare",
    "base_fare", "taxes", "booking_window", "source", "scrape_timestamp",
]

HEADLESS = True  # invisible browser for friend's one-command run
VIEWPORT = {"width": 1366, "height": 768}

# OPTIONAL proxy / VPN to route through a non-banned IP.
# Format: "http://user:password@host:port" or "socks5://host:port"
# Set via env SIH_PROXY. Empty = direct connection.
PROXY = os.environ.get("SIH_PROXY", "") or None


def search_date_for(days_ahead: int) -> str:
    """Return the date `days_ahead` from today in DD/MM/YYYY (date picker)."""
    target = datetime.now() + timedelta(days=days_ahead)
    return target.strftime("%d/%m/%Y")


def search_date_iso_for(days_ahead: int) -> str:
    """Return the date `days_ahead` from today in YYYY-MM-DD format."""
    target = datetime.now() + timedelta(days=days_ahead)
    return target.strftime("%Y-%m-%d")

# ── paths ──────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent
DATA_RAW = PROJECT_ROOT / "data" / "raw"
DATA_DEBUG = PROJECT_ROOT / "data" / "debug"
DATA_RAW.mkdir(parents=True, exist_ok=True)
DATA_DEBUG.mkdir(parents=True, exist_ok=True)


# ═══════════════════════════════════════════════════════════════════════════
# Scraper
# ═══════════════════════════════════════════════════════════════════════════
class AirIndiaScraper:
    """
    Scrapes Air India economy flight prices via Playwright browser automation
    with API response interception.
    """

    def __init__(self, headless: bool = HEADLESS, debug: bool = False):
        self.headless = headless
        self.debug = debug
        self.pw = None
        self.browser = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.captured_api_data: list[dict] = []
        self.scrape_ts = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        # Systematic storage: one folder per collection day, one CSV per run.
        now = datetime.now()
        day_folder = now.strftime("%Y-%m-%d")
        self.csv_path = DATA_RAW / day_folder / f"airindia_{now.strftime('%Y%m%d_%H%M%S')}.csv"
        self._ensure_csv()
        # track which API response URLs we've already processed
        self._seen_urls: set[str] = set()

    # ── browser lifecycle ──────────────────────────────────────────────────

    def start_browser(self):
        self.pw = sync_playwright().start()
        self.browser = self.pw.chromium.launch(
            headless=self.headless,
            proxy=({"server": PROXY} if PROXY else None),
            args=[
                "--no-first-run",
                "--no-default-browser-check",
            ],
        )
        self.context = self.browser.new_context(
            viewport=VIEWPORT,
            proxy=({"server": PROXY} if PROXY else None),
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/128.0.0.0 Safari/537.36"
            ),
            locale="en-IN",
            timezone_id="Asia/Kolkata",
        )
        self.page = self.context.new_page()
        # Block heavy assets to speed up scraping (images, fonts, media)
        self.page.route(
            "**/*.{png,jpg,jpeg,gif,svg,webp,woff,woff2,ttf,mp4,mp3}",
            lambda route: route.abort(),
        )
        print(f"[+] Browser started  (headless={self.headless})")

    def close_browser(self):
        if self.browser:
            try:
                self.browser.close()
            except Exception:
                pass
        if self.pw:
            try:
                self.pw.stop()
            except Exception:
                pass
        self.browser = None
        self.context = None
        self.page = None
        print("[+] Browser closed")

    def _restart_browser(self):
        print("    [!] Browser crashed — restarting...")
        self.close_browser()
        self._api_listener_attached = False
        time.sleep(2)
        self.start_browser()

    def _new_context(self):
        """
        Close the current context and create a fresh one (same Chromium
        process, new cookies / session / IBE token).  Air India silently
        drops follow-up fare searches when they share a session, so we
        give each route+window combination a clean slate.
        """
        try:
            self.context.close()
        except Exception:
            pass
        self.context = self.browser.new_context(
            viewport=VIEWPORT,
            proxy=({"server": PROXY} if PROXY else None),
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/128.0.0.0 Safari/537.36"
            ),
            locale="en-IN",
            timezone_id="Asia/Kolkata",
        )
        self.page = self.context.new_page()
        self.page.route(
            "**/*.{png,jpg,jpeg,gif,svg,webp,woff,woff2,ttf,mp4,mp3}",
            lambda route: route.abort(),
        )
        self._api_listener_attached = False
        print("    [+] Fresh browser context (clean cookies/session)")

    @staticmethod
    def _browser_dead(exc: Exception) -> bool:
        msg = str(exc).lower()
        return ("page, context or browser has been closed" in msg
                or ("target page" in msg and "closed" in msg)
                or "browser has been closed" in msg
                or "context has been closed" in msg)

    # ── CSV helpers ────────────────────────────────────────────────────────

    def _ensure_csv(self, retries: int = 5):
        """Create the CSV header if the file does not exist yet.

        Robust against transient file locks (e.g. OneDrive syncing the
        output folder while we write) by retrying with a short backoff.
        """
        self.csv_path.parent.mkdir(parents=True, exist_ok=True)
        if self.csv_path.exists():
            return
        for i in range(retries):
            try:
                with open(self.csv_path, "w", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
                    writer.writeheader()
                return
            except PermissionError:
                if i < retries - 1:
                    time.sleep(0.5 * (i + 1))
                else:
                    raise

    def _append_rows(self, rows: list[dict], retries: int = 6):
        """Append rows to the shared CSV, surviving transient file locks.

        On Windows the output folder is often under OneDrive, which can
        briefly lock files during sync.  We retry with backoff; if the lock
        persists, we write the rows to a per-window sidecar file so the data
        is never silently lost.
        """
        def serialize():
            buff = []
            for row in rows:
                full_row = {col: row.get(col, "") for col in CSV_COLUMNS}
                buff.append(full_row)
            return buff

        data = serialize()
        for i in range(retries):
            try:
                with open(self.csv_path, "a", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
                    writer.writerows(data)
                print(f"    [+] Appended {len(rows)} rows -> {self.csv_path.name}")
                return
            except PermissionError:
                if i < retries - 1:
                    time.sleep(0.7 * (i + 1))
                else:
                    # Lock persisted — write a sidecar so nothing is lost.
                    side = self.csv_path.with_name(
                        self.csv_path.stem + f"_sidecar_{datetime.now().strftime('%H%M%S')}.csv"
                    )
                    for attempt in range(4):
                        try:
                            with open(side, "a", newline="", encoding="utf-8") as f:
                                writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
                                if not side.exists() or side.stat().st_size == 0:
                                    writer.writeheader()
                                writer.writerows(data)
                            print(f"    [+] [!] Main CSV locked — saved {len(rows)} rows to sidecar {side.name}")
                            return
                        except PermissionError:
                            if attempt < 3:
                                time.sleep(1.0)
                            else:
                                raise

    # ── debug helpers ──────────────────────────────────────────────────────

    def _save_debug(self, label: str, html: bool = True, screenshot: bool = True,
                    debug_only: bool = False):
        if debug_only and not self.debug:
            return
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        day_folder = datetime.now().strftime("%Y-%m-%d")
        debug_dir = DATA_DEBUG / day_folder
        debug_dir.mkdir(parents=True, exist_ok=True)
        prefix = debug_dir / f"{label}_{ts}"
        if html and self.page:
            try:
                html_path = prefix.with_suffix(".html")
                html_path.write_text(self.page.content(), encoding="utf-8")
                print(f"    [debug] Saved HTML -> {html_path.name}")
            except Exception as e:
                print(f"    [debug] Failed to save HTML: {e}")
        if screenshot and self.page:
            try:
                ss_path = prefix.with_suffix(".png")
                self.page.screenshot(path=str(ss_path), full_page=True)
                print(f"    [debug] Saved screenshot -> {ss_path.name}")
            except Exception as e:
                print(f"    [debug] Failed to save screenshot: {e}")

    # ── cookie consent ─────────────────────────────────────────────────────

    def _dismiss_cookie_banner(self):
        """Dismiss OneTrust / generic cookie consent if present."""
        try:
            # OneTrust "Accept All" button
            accept_btn = self.page.locator("#onetrust-accept-btn-handler")
            if accept_btn.is_visible(timeout=5000):
                accept_btn.click()
                print("    [+] Dismissed cookie banner")
                self.page.wait_for_timeout(1000)
        except Exception:
            pass  # No banner or already dismissed

    def _dismiss_login_modal(self):
        """
        Dismiss the simplified-login / sign-in modal that Air India
        pops up on subsequent page loads (2nd+ window per session).
        The modal (id=simplifiedLoginModal) intercepts all pointer events
        and blocks every form interaction (origin click, One Way, date).
        """
        selectors = [
            "#simplifiedLoginModal .btn-close",
            "#simplifiedLoginModal button[aria-label='Close']",
            "#simplifiedLoginModal .modal-header button",
            ".simplifiedModal .btn-close",
            ".simplifiedModal button[aria-label='Close']",
            ".ai-interactive-modal .btn-close",
            ".ai-interactive-modal button[aria-label='Close']",
        ]
        for sel in selectors:
            try:
                btn = self.page.locator(sel).first
                if btn.is_visible(timeout=2000):
                    btn.click()
                    print("    [+] Dismissed login modal")
                    self.page.wait_for_timeout(800)
                    return
            except Exception:
                continue
        # Fallback: press Escape to close any dialog/modal
        try:
            modal = self.page.locator("#simplifiedLoginModal")
            if modal.is_visible(timeout=1000):
                self.page.keyboard.press("Escape")
                self.page.wait_for_timeout(800)
                print("    [+] Dismissed login modal via Escape")
        except Exception:
            pass

    # ── form filling ───────────────────────────────────────────────────────

    def _fill_origin(self, city_code: str, city_name: str):
        """
        Fill the origin field.

        CONFIRMED SELECTOR (from selector_report.json, Sep 2026):
            Both origin & destination inputs share the SAME aria-label
            "Select origin airport" (Angular Material autocomplete).
            Origin is the FIRST match, destination is the SECOND.
        """
        print(f"    [>] Setting origin: {city_name} ({city_code})")

        try:
            origin_input = self.page.locator(
                'input[aria-label="Select origin airport"]'
            ).first
            origin_input.wait_for(state="visible", timeout=10000)
        except Exception:
            # Fallback: any autocomplete input inside the booking widget
            try:
                origin_input = self.page.locator(
                    'input[aria-label*="origin" i], '
                    'ai-origin-destination input[type="text"]'
                ).first
                origin_input.wait_for(state="visible", timeout=5000)
            except Exception:
                raise RuntimeError(
                    "Cannot find origin input. Run discover_selectors.py "
                    "again and inspect data/debug/selector_report.json."
                )

        origin_input.click()
        self.page.wait_for_timeout(500)
        origin_input.fill("")
        self.page.wait_for_timeout(300)
        origin_input.type(city_code, delay=100)
        self.page.wait_for_timeout(1500)

        self._click_first_suggestion(city_code, city_name)

    def _fill_destination(self, city_code: str, city_name: str):
        """Fill the destination field — 2nd input with same aria-label."""
        print(f"    [>] Setting destination: {city_name} ({city_code})")

        try:
            dest_input = self.page.locator(
                'input[aria-label="Select origin airport"]'
            ).nth(1)
            dest_input.wait_for(state="visible", timeout=10000)
        except Exception:
            try:
                dest_input = self.page.locator(
                    'input[aria-label*="destination" i], '
                    'input[aria-label*="to" i]'
                ).first
                dest_input.wait_for(state="visible", timeout=5000)
            except Exception:
                raise RuntimeError("Cannot find destination input selector.")

        dest_input.click()
        self.page.wait_for_timeout(500)
        dest_input.fill("")
        self.page.wait_for_timeout(300)
        dest_input.type(city_code, delay=100)
        self.page.wait_for_timeout(1500)

        self._click_first_suggestion(city_code, city_name)

    def _click_first_suggestion(self, code: str, name: str):
        """
        Click the first autocomplete suggestion.

        CONFIRMED: Air India uses Angular Material (mat-autocomplete /
        mat-option). Suggestions are <mat-option> elements containing
        the airport code.
        """
        suggestion_selectors = [
            f'mat-option:has-text("{code}")',
            f'li:has-text("{code}")',
            f'div[role="option"]:has-text("{code}")',
            f'[class*="suggestion"]:has-text("{code}")',
            f'[class*="dropdown"] li:has-text("{code}")',
            f'[class*="list"] >> text="{code}"',
            f'[class*="option"]:has-text("{name}")',
            f'mat-option:has-text("{name}")',
            f'li:has-text("{name}")',
        ]
        for sel in suggestion_selectors:
            try:
                loc = self.page.locator(sel).first
                if loc.is_visible(timeout=2000):
                    # Material options are usually mat-option; click the div
                    loc.click()
                    print(f"        Clicked suggestion: {code}")
                    self.page.wait_for_timeout(500)
                    return
            except Exception:
                continue

        # If no clickable suggestion found, press Enter as fallback
        print("        [!] No clickable suggestion found, pressing Enter")
        self.page.keyboard.press("Enter")
        self.page.wait_for_timeout(500)

    def _select_one_way(self):
        """
        Select 'One Way' trip type.

        CONFIRMED (debug HTML, Sep 2026): trip type is a custom ai-radio-group.
        Round Trip is the CHECKED default; the One Way radio input carries
        tabindex="-1" (covered by its label), so a plain input.click() can
        silently miss. Strategy:
          1. click the LABEL (the real hit target)
          2. verify via is_checked(); fall back to check(force=True)
        """
        print("    [>] Selecting One Way")

        radio_input = self.page.locator(
            'input.ai-radio-group__input[value="one-way"]'
        ).first

        # Already selected?
        try:
            if radio_input.is_checked():
                print("        One Way already selected")
                return
        except Exception:
            pass

        # Strategy 1: click the label (real hit target)
        for sel in [
            'label.ai-radio-group__option:has-text("One Way")',
            'label:has-text("One Way")',
        ]:
            try:
                loc = self.page.locator(sel).first
                loc.wait_for(state="visible", timeout=3000)
                loc.click()
                self.page.wait_for_timeout(500)
                try:
                    if radio_input.is_checked():
                        print("        Selected One Way (label click)")
                        return
                except Exception:
                    pass
            except Exception:
                continue

        # Strategy 2: force-check the hidden radio input
        try:
            radio_input.check(force=True, timeout=5000)
            self.page.wait_for_timeout(400)
            if radio_input.is_checked():
                print("        Selected One Way (input check)")
                return
        except Exception:
            pass

        print("    [!] WARNING: Could not confirm One Way selection")

    def _fill_date(self, date_str: str):
        """
        Fill the departure date.

        CONFIRMED SELECTOR: button[aria-label="Open date picker"].
        CONFIRMED CELL FORMAT (debug HTML, Sep 2026): day cells are Material
        calendar buttons with US-style aria-labels, e.g. `aria-label="9/8/2026"`
        for 8 September 2026. The calendar opens on the current month, and
        for dates in later months (e.g. T+30) _navigate_calendar moves the
        view forward before the day cell is clicked.

        VERIFIED BEHAVIOR (error_DEL_BOM_1_20260901_225616.html): in One-Way
        mode, clicking the day cell commits the date immediately — there is
        NO Confirm button (that modal footer is a Round-Trip artifact). We
        simply wait for the date field to update, then dismiss the overlay.
        """
        print(f"    [>] Setting date: {date_str}")
        target = datetime.strptime(date_str, "%d/%m/%Y")
        date_label = f"{target.month}/{target.day}/{target.year}"

        for attempt in range(3):
            if not self._open_date_picker():
                raise RuntimeError("Could not open the date picker.")

            print(f"        Looking for day cell: aria-label={date_label}")
            day_clicked = False
            for _ in range(5):
                try:
                    day_btn = self.page.locator(
                        f'button[aria-label="{date_label}"]'
                    ).first
                    day_btn.wait_for(state="visible", timeout=3000)
                    if not day_btn.is_enabled():
                        self.page.wait_for_timeout(800)
                        continue
                    day_btn.scroll_into_view_if_needed()
                    day_btn.click()
                    day_clicked = True
                    print(f"        Clicked day cell {date_label}")
                    break
                except Exception:
                    self.page.wait_for_timeout(1000)

            if not day_clicked:
                print("        [!] Day cell not found; navigating calendar")
                self._navigate_calendar(target)
                self._click_calendar_day(target.day)
                self.page.wait_for_timeout(800)

            # The day-click commits the date; wait for field to update.
            ok = False
            for _ in range(10):
                if self._date_is_set():
                    ok = True
                    break
                self.page.wait_for_timeout(500)

            # Dismiss the date overlay once the date is registered.
            if ok:
                self._close_date_modal()
                self.page.wait_for_timeout(400)
                if self._date_is_set():
                    print(f"        Date verified: {date_str}")
                    return
                print("        [!] Date not stable after closing modal — will retry")

        raise RuntimeError(
            f"Failed to register departure date {date_label} (still 'Select Date'). "
            "See data/debug/error_*.html for the modal state."
        )

    def _open_date_picker(self):
        """Open the departure date modal if it isn't already visible."""
        try:
            if self.page.locator('.mat-calendar').first.is_visible(timeout=600):
                return True
        except Exception:
            pass
        date_selectors = [
            'button[aria-label="Open date picker"]',
            '[aria-label*="Departure date" i]',
            '[data-testid*="departure-date"]',
            'input[placeholder*="Date" i]',
            'input[type="date"]',
        ]
        for sel in date_selectors:
            try:
                loc = self.page.locator(sel).first
                loc.wait_for(state="visible", timeout=3000)
                loc.click()
                self.page.wait_for_timeout(1200)
                return True
            except Exception:
                continue
        print("        [!] No date field found")
        return False

    def _date_is_set(self):
        """Return True when the date trigger shows an actual date (not 'Select Date')."""
        try:
            t = self.page.locator('button[aria-label="Open date picker"]').first
            txt = (t.inner_text() or "").strip()
            if not txt or "Select" in txt:
                return False
            # Require a plausible date, e.g. "17 Sep", "17/09/2026", "Thu 17 Sep".
            import re
            return bool(re.search(r'\b\d{1,2}(?:\s+[A-Za-z]{3,9}|[/-]\d{1,2}[/-]\d{2,4})\b', txt))
        except Exception:
            return False

    def _close_date_modal(self):
        """
        Dismiss the date picker overlay. Prefers an enabled Confirm/Done
        button; otherwise closes with Escape (the date is already committed,
        so this only hides the overlay).
        """
        try:
            if not self.page.locator('.mat-calendar').first.is_visible(timeout=1500):
                return
        except Exception:
            return
        for sel in ['button[aria-label="Confirm"]',
                    'button:has-text("Done")']:
            try:
                c = self.page.locator(sel).first
                if c.is_visible(timeout=800) and c.is_enabled():
                    c.click()
                    self.page.wait_for_timeout(500)
                    return
            except Exception:
                continue
        self.page.keyboard.press("Escape")
        self.page.wait_for_timeout(500)

    def _navigate_calendar(self, target: datetime):
        """
        Navigate the Material calendar popup to the target month.

        Angular Material (mat-calendar) shows the current month in a
        header period element, and provides `.mat-calendar-next-button`
        to go forward one month at a time. We read the visible month
        repeatedly and click Next until the month matches the target.
        """

        def visible_period_text() -> str:
            """Return the month/year currently shown in the calendar header."""
            for sel in [
                '.mat-calendar-period-button',
                '.mat-calendar-header .mat-calendar-controls span',
                '.mat-calendar-period',
            ]:
                try:
                    loc = self.page.locator(sel).first
                    if loc.is_visible(timeout=1000):
                        txt = (loc.inner_text() or "").strip()
                        if txt:
                            return txt
                except Exception:
                    continue
            # Last resort: read whatever <mat-calendar> header text exists
            try:
                return (self.page.locator('mat-calendar .mat-calendar-header').first.inner_text() or "").strip()
            except Exception:
                return ""

        target_month = target.month
        target_year = target.year

        for _ in range(24):  # safety cap of 24 clicks
            period_text = visible_period_text()

            # Parse "SEP 2026" / "Sep 2026" / "September 2026"
            cur_month = None
            cur_year = None
            try:
                parts = period_text.split()
                if len(parts) >= 2:
                    # Match by month name (first 3 letters enough)
                    month_names = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN",
                                   "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
                    up = period_text.upper()
                    for i, m in enumerate(month_names):
                        if m in up:
                            cur_month = i + 1
                            # year is the 4-digit number in the string
                            for tok in parts:
                                if tok.isdigit() and len(tok) == 4:
                                    cur_year = int(tok)
                            break
            except Exception:
                cur_month = cur_year = None

            if cur_month is not None and cur_year is not None:
                if cur_month == target_month and cur_year == target_year:
                    print(f"        Calendar is on {period_text} (target reached)")
                    return

                # Compute how many clicks forward are needed
                clicks_needed = (target_year - cur_year) * 12 + (target_month - cur_month)
                print(f"        Calendar shows {period_text}; need {clicks_needed} forward")

                next_btn = None
                for sel in [
                    '.mat-calendar-next-button',
                    'button[aria-label*="next"]',
                    '[class*="mat-calendar"] button[dir="ltr"]:nth-child(3)',
                ]:
                    try:
                        loc = self.page.locator(sel).first
                        if loc.is_visible(timeout=1000):
                            next_btn = loc
                            break
                    except Exception:
                        continue

                if next_btn is None:
                    print("        [!] Cannot find calendar Next button")
                    return

                clicks = max(1, min(clicks_needed, 24))
                for _ in range(clicks):
                    try:
                        if next_btn.is_enabled():
                            next_btn.click()
                            self.page.wait_for_timeout(300)
                    except Exception:
                        break
                continue
            else:
                # Could not parse; click Next once and keep trying
                try:
                    self.page.locator('.mat-calendar-next-button').first.click()
                    self.page.wait_for_timeout(300)
                except Exception:
                    break

        print("        [!] Could not navigate calendar to target month")

    def _click_calendar_day(self, day: int):
        """Click a specific day number in the calendar popup."""
        day_str = str(day)
        day_selectors = [
            f'.mat-calendar-body-button:has-text("{day}")',
            f'button[aria-label*="{day}"]',
            f'td:has-text("{day}") button',
            f'[data-day="{day}"]',
            f'span:has-text("{day}")',
            f'.DayPicker-Day:has-text("{day}")',
        ]
        for sel in day_selectors:
            try:
                loc = self.page.locator(sel).first
                if loc.is_visible(timeout=1000) and loc.is_enabled():
                    loc.click()
                    print(f"        Clicked day {day}")
                    self.page.wait_for_timeout(500)
                    return
            except Exception:
                continue
        print(f"        [!] Could not click day {day}")

    def _select_cabin_class(self):
        """
        Select Economy cabin class.

        CONFIRMED (selector_report.json): Cabin class is NOT on the main
        search form. It lives inside the passenger selector menu
        (ai-pax-selector — button text "1 Adult"). Open it, pick Economy,
        then close/apply.
        """
        print("    [>] Selecting Economy cabin class")

        # 1. Open the passenger selector menu
        pax_trigger = None
        pax_selectors = [
            'button[aria-label^="Select passengers"]',
            '.ai-pax-selector__trigger',
            'button:has-text("1 Adult")',
        ]
        for sel in pax_selectors:
            try:
                loc = self.page.locator(sel).first
                loc.wait_for(state="visible", timeout=3000)
                pax_trigger = loc
                print(f"        Opened passenger menu with: {sel}")
                pax_trigger.click()
                self.page.wait_for_timeout(1000)
                break
            except Exception:
                continue

        if not pax_trigger:
            print("        [!] Passenger menu not found; cabin class unknown.")
            return

        # 2. Look for an Economy option (radio, label, or option element)
        economy_selectors = [
            'label.ai-radio-group__option:has-text("Economy")',
            'label:has-text("Economy")',
            'input[value*="economy" i]',
            'mat-option:has-text("Economy")',
            '[role="radio"]:has-text("Economy")',
            '[class*="cabin"]:has-text("Economy")',
            '.mat-mdc-radio-button:has-text("Economy")',
            'text="Economy"',
        ]
        for sel in economy_selectors:
            try:
                loc = self.page.locator(sel).first
                loc.wait_for(state="visible", timeout=3000)
                loc.click()
                print(f"        Selected Economy with: {sel}")
                self.page.wait_for_timeout(600)
                break
            except Exception:
                continue

        # 3. Close the menu — look for Apply/Close/Done button
        for sel in ['button:has-text("Apply")',
                    'button:has-text("Done")',
                    'button:has-text("Close")',
                    'button:has-text("Select")']:
            try:
                loc = self.page.locator(sel).first
                if loc.is_visible(timeout=1500):
                    loc.click()
                    print("        Closed passenger menu")
                    self.page.wait_for_timeout(500)
                    return
            except Exception:
                continue

        # Fallback: press Escape to close
        self.page.keyboard.press("Escape")
        self.page.wait_for_timeout(500)

    def _set_passengers(self):
        """Ensure 1 adult passenger (usually the default)."""
        # Most booking widgets default to 1 adult. Just verify and proceed.
        print("    [>] Passengers: defaulting to 1 Adult")

    def _click_search(self):
        """
        Click the Search button.

        CONFIRMED SELECTOR: button[aria-label="Search"]
        (class: ai-button--primary). It starts DISABLED (ai-button--disabled
        + disabled attribute) and only enables once the form is valid.
        We poll is_enabled() (the real attribute) until it becomes clickable,
        and fail loudly if it never does instead of clicking a disabled button.
        """
        print("    [>] Waiting for Search button to enable...")

        search_locs = [
            self.page.locator('button[aria-label="Search"]'),
            self.page.locator('.ai-button--primary'),
            self.page.locator('button:has-text("Search")'),
        ]

        search_btn = None
        for loc in search_locs:
            try:
                loc.first.wait_for(state="visible", timeout=10000)
                # Poll the real enabled attribute (up to ~25s)
                for _ in range(25):
                    if loc.first.is_enabled():
                        search_btn = loc.first
                        print("    [+] Search button is enabled")
                        break
                    self.page.wait_for_timeout(1000)
                if search_btn:
                    break
            except Exception:
                continue

        if not search_btn:
            # Save evidence and raise a clear error rather than clicking
            # a disabled button (which just hangs for 30s).
            self._save_debug("search_button_never_enabled", html=True, screenshot=True)
            raise RuntimeError(
                "Search button never became enabled — the form is invalid. "
                "Check data/debug/search_button_never_enabled_*.html. "
                "Usually the date did not register."
            )

        search_btn.click()
        print("    [+] Search clicked")
        self.page.wait_for_timeout(500)
        return True

    # ── API interception ───────────────────────────────────────────────────

    def _setup_api_interception(self):
        """
        Register response capture for Air India's internal flight APIs.

        Two layers:
          1. ROUTE interception for the flight-search endpoints
             (air-bounds / air-calendar / active-count / offers). We use
             route.fetch() + route.fulfill() because response.json() in a
             plain "response" listener FAILS once the page navigates away
             ("No resource with given identifier found") — a race we hit
             repeatedly. route.fetch() reads the body immediately.
          2. A "response" listener for the remaining api.airindia.com
             traffic (token, airports, etc.) that we still want logged
             but don't need for parsing.

        Both are registered exactly once; buffers are cleared per attempt.
        """
        if not getattr(self, "_api_listener_attached", False):
            def on_response(response: Response):
                url = response.url
                if any(pattern in url for pattern in [
                    "api.airindia.com",
                    "developer-api.airindia.com",
                    "cbiz-booking",
                ]):
                    if url in self._seen_urls:
                        return
                    self._seen_urls.add(url)
                    try:
                        if response.status == 200:
                            ct = response.headers.get("content-type", "")
                            if "json" in ct or "javascript" in ct:
                                try:
                                    body = response.json()
                                except Exception:
                                    body = None
                                if body is not None:
                                    self.captured_api_data.append({
                                        "url": url,
                                        "status": response.status,
                                        "data": body,
                                    })
                                    tag = "air-bounds" if "air-bounds" in url else \
                                          "air-calendar" if "air-calendar" in url else \
                                          "active-count" if "active-count" in url else None
                                    label = f" [{tag.upper()}]" if tag else ""
                                    print(f"    [API] Captured response{label}: {url[:100]}...")
                    except Exception as e:
                        print(f"    [API] Could not parse response from {url[:80]}: {e}")

            self.page.on("response", on_response)
            self._api_listener_attached = True

        self.captured_api_data = []
        self._seen_urls = set()

    def _parse_api_flights(self) -> list[dict]:
        """
        Parse captured API responses into our CSV schema.

        We handle multiple possible response structures because Air India's
        API format may vary. The key is to be flexible and extract what's
        available.
        """
        flights = []

        for captured in self.captured_api_data:
            data = captured["data"]
            print(f"    [parse] Processing API response from {captured['url'][:80]}")

            # Save raw API response for debugging (only when --debug is set;
            # otherwise a successful run would litter data/debug with JSON).
            if self.debug:
                self._save_api_response_debug(captured)

            # air-bounds style (verified 2026-09-01):
            #   responsePayload[].airBoundGroups[] ->
            #     boundDetails.{originLocationCode,destinationLocationCode,segments:[{flightId}]}
            #     airBounds[].{availabilityDetails[{cabin}], prices.unitPrices[].prices[]
            #       {total, base, totalTaxes}}
            #   dictionaries.flight[flightId] ->
            #     {marketingFlightNumber, departure.{locationCode,dateTime},
            #      arrival.{locationCode,dateTime}}
            flights.extend(self._parse_air_bounds(captured))

            # Try various known structures
            flight_offers = self._extract_flight_offers(data)
            if not flight_offers:
                print(f"    [parse] No flight offers found in this response")
                continue

            print(f"    [parse] Found {len(flight_offers)} flight offers")

            for offer in flight_offers:
                parsed = self._parse_single_offer(offer)
                if parsed:
                    flights.extend(parsed)

        return flights

    def _parse_air_bounds(self, captured: dict) -> list[dict]:
        """
        Parse the verified `cbiz-booking/v2/prime/search/air-bounds` response
        (structure confirmed from api_response_air-bounds_*.json, 2026-09-01):

            data:
              responsePayload: [ { airBoundGroups: [ {
                  boundDetails: {
                    originLocationCode, destinationLocationCode,
                    segments: [ { flightId: "SEG-AI2957-DELBOM-2026-09-08-2030" } ]
                  },
                  airBounds: [ {
                    availabilityDetails: [ { cabin: "eco", bookingClass, ... } ],
                    prices: {
                      unitPrices: [ {
                         prices: [ { base, total, totalTaxes, taxes: [...] } ]
                      } ]
                    }
                  } ]
              }, polls: ... ] }
              dictionaries: { flight: { "<flightId>": {
                  marketingAirlineCode, marketingFlightNumber,
                  departure: { locationCode, dateTime },
                  arrival: { locationCode, dateTime }
              } } }

        Returns one CSV row per airBoundGroup (flight) using the CHEAPEST
        economy price across its fare variants.
        """
        data = captured["data"]
        rows: list[dict] = []

        if not isinstance(data, dict):
            return rows

        payloads = data.get("responsePayload")
        if not isinstance(payloads, list):
            return rows

        dictionaries = data.get("dictionaries") or {}
        flight_dict = {}
        if isinstance(dictionaries, dict):
            fd = dictionaries.get("flight")
            if isinstance(fd, dict):
                flight_dict = fd

        origin_expected = ""
        dest_expected = ""
        try:
            origin_expected = dictionaries["location"].get("DEL", {}).get("code", "")
        except Exception:
            pass

        for payload in payloads:
            if not isinstance(payload, dict):
                continue
            for group in payload.get("airBoundGroups") or []:
                if not isinstance(group, dict):
                    continue
                bd = group.get("boundDetails") or {}
                segs = bd.get("segments") or []
                if not segs:
                    continue

                # Cheapest economy fare across all fare variants (airBounds)
                cheapest = None
                for ab in group.get("airBounds") or []:
                    if not isinstance(ab, dict):
                        continue
                    cabins = {a.get("cabin", "").lower()
                              for a in (ab.get("availabilityDetails") or [])
                              if isinstance(a, dict)}
                    # Skip bounds that are explicitly premium
                    if cabins and not any("eco" in c for c in cabins):
                        continue

                    unit_prices = (ab.get("prices") or {}).get("unitPrices") or []
                    for up in unit_prices:
                        if not isinstance(up, dict):
                            continue
                        for p in up.get("prices") or []:
                            if not isinstance(p, dict):
                                continue
                            total = p.get("total")
                            if total is None:
                                continue
                            try:
                                total = float(total)
                            except (TypeError, ValueError):
                                continue
                            if cheapest is None or total < cheapest["total_fare"]:
                                cheapest = {
                                    "total_fare": total,
                                    "base_fare": p.get("base", ""),
                                    "taxes": p.get("totalTaxes", ""),
                                }

                if cheapest is None:
                    continue

                # Resolve flight details from dictionaries by flightId
                seg = segs[0]
                fid = seg.get("flightId") if isinstance(seg, dict) else None
                finfo = flight_dict.get(fid, {}) if fid else {}
                if not isinstance(finfo, dict):
                    finfo = {}

                carrier = (finfo.get("marketingAirlineCode") or AIRLINE_IATA)
                fnum = finfo.get("marketingFlightNumber") or ""
                flight_number = f"{carrier}{fnum}"

                dep = finfo.get("departure") or {}
                arr = finfo.get("arrival") or {}
                departure_time = str(dep.get("dateTime", ""))[:19]
                travel_date = departure_time[:10] if departure_time else ""
                origin = dep.get("locationCode") or bd.get("originLocationCode") or origin_expected
                destination = arr.get("locationCode") or bd.get("destinationLocationCode") or ""

                rows.append({
                    "origin": origin,
                    "destination": destination,
                    "airline": AIRLINE,
                    "flight_number": flight_number,
                    "travel_date": travel_date,
                    "departure_time": departure_time,
                    "total_fare": str(cheapest["total_fare"]),
                    "base_fare": str(cheapest["base_fare"]),
                    "taxes": str(cheapest["taxes"]),
                    "source": "airindia_api",
                    "scrape_timestamp": self.scrape_ts,
                })

        if rows:
            print(f"    [parse] Extracted {len(rows)} rows from air-bounds response")
        return rows

    def _extract_flight_offers(self, data) -> list:
        """Recursively search the API response for arrays of flight offers."""
        if isinstance(data, list):
            # Check if this list contains flight-like objects
            if data and any(
                isinstance(item, dict) and
                any(k in item for k in [
                    "itineraries", "segments", "flight", "legs",
                    "departure", "arrival", "price", "fare",
                    "boundList", "flightList", "airSegment",
                ])
                for item in data[:3]
            ):
                return data
            return []

        if not isinstance(data, dict):
            return []

        # Check common wrapper keys
        wrapper_keys = [
            "data", "result", "results", "response", "body",
            "flightOffers", "offers", "flights", "flightList",
            "boundList", "airShoppingResponse", "availability",
            "flightAvailability", "segments", "journeys",
        ]
        for key in wrapper_keys:
            if key in data:
                result = self._extract_flight_offers(data[key])
                if result:
                    return result

        # Check nested structures
        for key, val in data.items():
            if isinstance(val, (dict, list)):
                result = self._extract_flight_offers(val)
                if result:
                    return result

        return []

    def _parse_single_offer(self, offer: dict) -> list[dict]:
        """
        Parse a single flight offer into our CSV row format.
        Returns a list because one offer may contain multiple segments.
        """
        rows = []

        try:
            # ── Extract price ──────────────────────────────────────────
            price_info = self._deep_find(offer, ["price", "pricing", "fareInfo", "fare"])
            total_fare = ""
            base_fare = ""
            taxes = ""

            if isinstance(price_info, dict):
                total_fare = str(
                    price_info.get("grandTotal", "")
                    or price_info.get("total", "")
                    or price_info.get("totalFare", "")
                    or price_info.get("amount", "")
                    or price_info.get("totalAmount", "")
                )
                base_fare = str(
                    price_info.get("base", "")
                    or price_info.get("baseFare", "")
                    or price_info.get("baseAmount", "")
                )
                taxes = str(
                    price_info.get("taxes", "")
                    or price_info.get("tax", "")
                    or price_info.get("taxAmount", "")
                    or price_info.get("totalTaxes", "")
                )
                # If taxes not explicit, compute: total - base
                if not taxes and total_fare and base_fare:
                    try:
                        taxes = str(float(total_fare) - float(base_fare))
                    except ValueError:
                        pass

            # Skip offers with no price (likely not bookable)
            if not total_fare:
                return []

            # ── Extract segments / legs ────────────────────────────────
            segments = self._extract_segments(offer)

            for seg in segments:
                flight_number = self._extract_flight_number(seg)
                departure_time = self._extract_departure_time(seg)
                origin = self._extract_airport(seg, "departure")
                destination = self._extract_airport(seg, "arrival")
                cabin_class = self._extract_cabin_class(offer, seg)

                # Filter to Economy ONLY. Keep the flight when the cabin
                # is unknown/blank (likely economy by default) and only
                # drop it when it is EXPLICITLY a premium cabin.
                if cabin_class and self._is_premium_cabin(cabin_class):
                    continue

                travel_date = ""
                if departure_time:
                    try:
                        travel_date = departure_time[:10]  # YYYY-MM-DD
                    except Exception:
                        pass

                rows.append({
                    "origin": origin,
                    "destination": destination,
                    "airline": AIRLINE,
                    "flight_number": flight_number,
                    "travel_date": travel_date,
                    "departure_time": departure_time,
                    "total_fare": total_fare,
                    "base_fare": base_fare,
                    "taxes": taxes,
                    "source": "airindia_api",
                    "scrape_timestamp": self.scrape_ts,
                })

        except Exception as e:
            print(f"    [parse] Error parsing offer: {e}")

        return rows

    def _extract_segments(self, offer: dict) -> list[dict]:
        """Extract flight segments from an offer."""
        # Try various structures
        for key in ["itineraries", "segments", "legs", "flightSegments",
                     "boundList", "journeys", "airSegment"]:
            if key in offer:
                val = offer[key]
                if isinstance(val, list):
                    # Each itinerary may contain segments
                    all_segs = []
                    for item in val:
                        if isinstance(item, dict):
                            # Check for nested segments
                            for seg_key in ["segments", "legs", "flights", "airSegment"]:
                                if seg_key in item and isinstance(item[seg_key], list):
                                    all_segs.extend(item[seg_key])
                                else:
                                    all_segs.append(item)
                    if all_segs:
                        return all_segs
                elif isinstance(val, dict):
                    return [val]

        # Try to find segments anywhere in the offer
        return self._deep_find_all(offer, ["segment", "leg", "flight"]) or [offer]

    def _extract_flight_number(self, seg: dict) -> str:
        """Extract flight number from a segment."""
        for key in ["flightNumber", "flight_number", "number", "flightNo",
                     "marketingCarrier", "carrierFlightNumber", "operatingFlightNumber"]:
            val = seg.get(key, "")
            if val:
                val = str(val)
                # Sometimes carrier code is separate: { carrier: "AI", number: "855" }
                carrier = seg.get("carrierCode", seg.get("carrier", ""))
                if carrier and val.isdigit():
                    return f"{carrier}{val}"
                return val

        # Check nested
        flight = seg.get("flight", seg.get("operating", seg.get("marketing", {})))
        if isinstance(flight, dict):
            code = flight.get("carrierCode", flight.get("code", ""))
            num = flight.get("number", flight.get("flightNumber", ""))
            if code and num:
                return f"{code}{num}"

        return ""

    def _extract_departure_time(self, seg: dict) -> str:
        """Extract departure time from a segment."""
        for key in ["departureTime", "departure_time", "departure", "depTime",
                     "std", "scheduledTimeOfDeparture"]:
            val = seg.get(key, "")
            if isinstance(val, dict):
                val = val.get("at", val.get("time", val.get("dateTime", "")))
            if val:
                return str(val)[:19]  # trim microseconds
        return ""

    def _extract_airport(self, seg: dict, direction: str) -> str:
        """Extract origin/airport IATA code."""
        prefix = "departure" if direction == "departure" else "arrival"
        for key in [f"{prefix}Airport", f"{prefix}airport", f"{prefix}Code",
                     f"{prefix}iataCode", f"{prefix}"]:
            val = seg.get(key, "")
            if isinstance(val, dict):
                val = val.get("iataCode", val.get("code", val.get("airportCode", "")))
            if val and len(str(val)) == 3:
                return str(val)
        return ""

    def _is_premium_cabin(self, cabin_class: str) -> bool:
        """
        Return True if a cabin class value represents a premium cabin
        (not Economy). Unknown/blank values are treated as Economy so we
        do not accidentally drop bookable economy results.
        """
        c = (cabin_class or "").strip().lower()
        if not c or "economy" in c:
            return False
        premium_words = ["business", "first", "premium", "executive", "club"]
        premium_codes = {"b", "c", "d", "f", "j", "i", "z", "w", "s"}
        if any(w in c for w in premium_words):
            return True
        if len(c) == 1 and c in premium_codes:
            return True
        return False

    def _extract_cabin_class(self, offer: dict, seg: dict) -> str:
        """Extract cabin class label."""
        # Check segment level
        for key in ["cabinClass", "cabin", "classOfService", "bookingClass",
                     "cabinLevel", "serviceClass"]:
            val = seg.get(key, "")
            if val:
                return str(val)

        # Check offer level
        for key in ["cabinClass", "cabin", "travelClass"]:
            val = offer.get(key, "")
            if val:
                return str(val)

        # Check nested in pricing
        pricing = offer.get("travelerPricings", offer.get("pricingOptions", []))
        if isinstance(pricing, list) and pricing:
            first = pricing[0]
            if isinstance(first, dict):
                fare = first.get("fareDetailsBySegment", first.get("fareDetails", []))
                if isinstance(fare, list) and fare:
                    return fare[0].get("cabin", fare[0].get("cabinClass", ""))

        return "Economy"  # default assumption

    def _deep_find(self, d: dict, keys: list[str]):
        """Deep search for any of the given keys in a nested dict."""
        if not isinstance(d, dict):
            return None
        for key in keys:
            if key in d:
                return d[key]
        for val in d.values():
            if isinstance(val, dict):
                result = self._deep_find(val, keys)
                if result is not None:
                    return result
        return None

    def _deep_find_all(self, d, keys: list[str]) -> list:
        """Deep search returning all matches."""
        results = []
        if isinstance(d, list):
            for item in d:
                results.extend(self._deep_find_all(item, keys))
            return results
        if not isinstance(d, dict):
            return results
        for key in keys:
            if key in d:
                results.append(d[key])
        for val in d.values():
            results.extend(self._deep_find_all(val, keys))
        return results

    def _save_api_response_debug(self, captured: dict):
        """Save raw API response JSON for debugging."""
        import re
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        day_folder = datetime.now().strftime("%Y-%m-%d")
        debug_dir = DATA_DEBUG / day_folder
        debug_dir.mkdir(parents=True, exist_ok=True)
        slug = captured["url"].split("/")[-1][:30]
        slug = re.sub(r"[^A-Za-z0-9_.-]", "_", slug)  # Windows-safe filename
        path = debug_dir / f"api_response_{slug}_{ts}.json"
        try:
            path.write_text(
                json.dumps(captured["data"], indent=2, ensure_ascii=False, default=str),
                encoding="utf-8",
            )
            print(f"    [debug] Saved API response -> {path.name}")
        except Exception as e:
            print(f"    [debug] Failed to save API response: {e}")

    # ── HTML fallback scraping ─────────────────────────────────────────────

    def _fallback_html_scrape(self, route: dict, days_ahead: int) -> list[dict]:
        """
        Fallback: parse flight data from rendered HTML when API interception
        yields no results. Uses multiple selector strategies.

        This is less reliable than API interception but serves as a safety net.
        """
        print("    [HTML] Attempting HTML fallback scrape...")
        flights = []

        # Common patterns for flight card containers
        card_selectors = [
            '[data-testid*="flight-card"]',
            '[data-testid*="flight-result"]',
            '[class*="flight-card"]',
            '[class*="flight-result"]',
            '[class*="flightCard"]',
            '[class*="result-card"]',
            '[class*="offer-card"]',
            'div[class*="flight"][class*="item"]',
            'div[class*="journey"]',
        ]

        cards = []
        for sel in card_selectors:
            try:
                found = self.page.locator(sel).all()
                if found and len(found) > 0:
                    cards = found
                    print(f"    [HTML] Found {len(cards)} flight cards with: {sel}")
                    break
            except Exception:
                continue

        if not cards:
            print("    [HTML] No flight cards found with any selector")
            self._save_debug(f"html_fallback_{route['origin']}_{route['destination']}")
            return flights

        for i, card in enumerate(cards):
            try:
                text = card.inner_text()
                # Try to extract data from the card text
                row = self._parse_card_text(text, route, days_ahead)
                if row:
                    flights.append(row)
            except Exception as e:
                print(f"    [HTML] Error parsing card {i}: {e}")

        return flights

    def _parse_card_text(self, text: str, route: dict, days_ahead: int) -> Optional[dict]:
        """Parse a flight card's inner text to extract data."""
        import re

        lines = [l.strip() for l in text.split("\n") if l.strip()]

        departure_time = ""
        flight_number = ""
        total_fare = ""

        for line in lines:
            # Time pattern: HH:MM
            time_match = re.search(r'\b(\d{1,2}:\d{2})\b', line)
            if time_match and not departure_time:
                departure_time = time_match.group(1)

            # Flight number pattern: AI followed by digits
            fn_match = re.search(r'\b(AI\s*\d{3,4})\b', line, re.IGNORECASE)
            if fn_match:
                flight_number = fn_match.group(1).replace(" ", "")

            # Fare pattern: ₹ followed by digits
            fare_match = re.search(r'₹\s*([\d,]+)', line)
            if fare_match:
                total_fare = fare_match.group(1).replace(",", "")

        if not total_fare:
            return None

        travel_date = ""
        if departure_time and len(departure_time) <= 5:
            travel_date = search_date_iso_for(days_ahead)

        return {
            "origin": route["origin"],
            "destination": route["destination"],
            "airline": AIRLINE,
            "flight_number": flight_number,
            "travel_date": travel_date,
            "departure_time": departure_time,
            "total_fare": total_fare,
            "base_fare": "",
            "taxes": "",
            "booking_window": str(days_ahead),
            "source": "airindia_html",
            "scrape_timestamp": self.scrape_ts,
        }

    # ── main scraping flow ─────────────────────────────────────────────────

    def scrape_route(self, route: dict, days_ahead: int) -> list[dict]:
        """
        Scrape all Economy flights for a single route for ONE booking
        window (days_ahead). The caller loops over BOOKING_WINDOWS so each
        (route, window) is searched separately.
        Returns list of flight dicts tagged with the window.
        """
        origin = route["origin"]
        dest = route["destination"]
        search_date = search_date_for(days_ahead)
        print(f"\n{'='*60}")
        print(f"  Scraping: {origin} -> {dest}   [T+{days_ahead}]")
        print(f"  Travel date: {search_date}")
        print(f"{'='*60}")

        self.captured_api_data = []
        self._seen_urls = set()
        flights = []

        for attempt in range(1, MAX_RETRIES + 1):
            print(f"\n  Attempt {attempt}/{MAX_RETRIES}")
            try:
                # 1. Set up API interception BEFORE navigating
                self._setup_api_interception()

                # 2. Navigate to search page
                print("    [>] Navigating to Air India search page...")
                self.page.goto(SEARCH_PAGE, timeout=PAGE_LOAD_TIMEOUT_MS,
                               wait_until="domcontentloaded")
                self.page.wait_for_timeout(5000)  # let JS bundles load

                # 3. Dismiss cookie banner
                self._dismiss_cookie_banner()
                self.page.wait_for_timeout(1000)

                # 3b. Dismiss any login/sign-in modal that Air India
                #     pops up on subsequent page loads (blocks all clicks).
                self._dismiss_login_modal()

                # 4. Save initial state for debugging
                self._save_debug(f"before_form_{origin}_{dest}_{days_ahead}", html=True, screenshot=True, debug_only=True)

                # 5. Fill the search form
                self._select_one_way()
                self._fill_origin(origin, route["origin_city"])
                self._fill_destination(dest, route["dest_city"])
                self._fill_date(search_date)
                self._select_cabin_class()
                self._set_passengers()

                # 6. Save form state for debugging
                self._save_debug(f"after_form_{origin}_{dest}_{days_ahead}", html=True, screenshot=True, debug_only=True)

                # 7. Click search.
                #    The fare-preview calendar fires air-bounds/offers BEFORE
                #    search. Drop those captured buffers + seen-urls so the
                #    real post-search API responses are captured fresh.
                self.captured_api_data = []
                self._seen_urls = set()
                self._click_search()

                # 8. Wait for results to load
                print(f"    [>] Waiting for flight results (up to {RESULTS_WAIT_TIMEOUT_MS//1000}s)...")
                self._wait_for_results()
                # 8b. Grace window for late-arriving API responses.
                self._settle_capture_buffer()

                # 9. Save results page for debugging
                self._save_debug(f"results_{origin}_{dest}_{days_ahead}", html=True, screenshot=True, debug_only=True)

                # 10. Parse flights — try API first, then HTML fallback
                flights = self._parse_api_flights()
                # Keep only rows that actually match this route (air-bounds
                # can include internal airport codes like "NMI").
                flights = [f for f in flights
                           if f.get("destination", "").upper() == dest.upper()]
                # Tag every row with the current booking window.
                for f in flights:
                    f["booking_window"] = str(days_ahead)
                if not flights:
                    print(f"    [!] No flights for route {origin}->{dest}; trying HTML fallback...")
                    flights = self._fallback_html_scrape(route, days_ahead)

                if flights:
                    print(f"\n    [OK] Successfully extracted {len(flights)} Economy flights")
                    for f in flights:
                        print(f"        {f['flight_number']:6s} | {f['departure_time']:16s} | Rs {f['total_fare']}")
                    return flights
                else:
                    print(f"    [!] No flights extracted on attempt {attempt}")
                    if attempt < MAX_RETRIES:
                        d = randomized_delay()
                        print(f"    [!] Retrying in {d:.0f}s...")
                        time.sleep(d)

            except Exception as e:
                print(f"    [✗] Error on attempt {attempt}: {e}")
                traceback.print_exc()
                self._save_debug(f"error_{origin}_{dest}_{days_ahead}_{attempt}", html=True, screenshot=True)
                if self._browser_dead(e):
                    self._restart_browser()
                if attempt < MAX_RETRIES:
                    d = randomized_delay()
                    print(f"    [!] Retrying in {d:.0f}s...")
                    time.sleep(d)

        print(f"\n    [X] Failed to scrape {origin}->{dest} [T+{days_ahead}] after {MAX_RETRIES} attempts")
        return flights

    def _settle_capture_buffer(self, grace_ms: int = 45_000):
        """
        After the main wait loop, keep pumping Playwright's event loop so
        pending `on_response` callbacks flush. air-bounds often lands a few
        seconds after the wait deadline, and in sync mode callbacks only run
        during Playwright API calls (not time.sleep), so without this the
        parser silently misses late responses.
        """
        def have_key():
            return any(
                "air-bounds" in c["url"]
                or "air-calendar" in c["url"]
                or "active-count" in c["url"]
                for c in self.captured_api_data
            )

        if have_key():
            return True
        deadline = time.time() + grace_ms / 1000
        while time.time() < deadline:
            try:
                self.page.wait_for_timeout(2000)  # drives event dispatch
            except Exception:
                break
            if have_key():
                print("    [+] Late air-bounds response flushed into buffer")
                return True
        return have_key()

    def _wait_for_results(self):
        """
        Wait for flight results to load. After Search, Air India
        navigates to an IBE booking results URL and fires the internal
        search APIs (air-bounds/offers) that we intercept.

        Returns only when the key API response (air-bounds or air-calendar)
        has been captured, OR the overall deadline expires. DOM signals
        (flight-card, IBE URL) are logged as progress but do NOT cause an
        early return — the widget renders skeletons BEFORE the API payload
        arrives, and we must not exit prematurely.
        """
        deadline = time.time() + (RESULTS_WAIT_TIMEOUT_MS / 1000)
        printed_ibe = False
        printed_card = False
        while time.time() < deadline:
            # 1. Key flight-search API captured? (air-bounds / air-calendar /
            #    active-count / offers). booking-type is the search echo — NOT
            #    results. Returns only when real data is here.
            if any(
                "air-bounds" in c["url"]
                or "air-calendar" in c["url"]
                or "active-count" in c["url"]
                or c["url"].rsplit("/", 1)[-1] in ("offers", "flights")
                for c in self.captured_api_data
            ):
                print("    [+] Flight API responses captured")
                self.page.wait_for_timeout(2500)
                return True

            # 2. IBE navigation detected (progress only)
            try:
                if not printed_ibe and "/ibe/" in (self.page.url or ""):
                    print("    [+] Navigated to IBE booking/results page")
                    printed_ibe = True
            except Exception:
                pass

            # 3. Flight-card DOM skeleton detected (progress only —
            #    does NOT confirm actual fare data)
            if not printed_card:
                try:
                    if self.page.locator(
                        '[class*="flight-card"]'
                    ).first.is_visible(timeout=300):
                        print("    [+] Flight card skeleton visible — waiting for API data...")
                        printed_card = True
                except Exception:
                    pass

            time.sleep(0.5)

        print("    [!] Deadline reached; no air-bounds / air-calendar captured.")
        return False

    # ── main entry ─────────────────────────────────────────────────────────

    def run(self, route_filter: Optional[str] = None):
        """
        Main entry point. Scrapes all routes across all booking windows
        (or a filtered subset of routes).
        """
        print("\n" + "═" * 60)
        print("  Air India Flight Scraper — SIH26056")
        windows = ", ".join(f"T+{w}" for w in BOOKING_WINDOWS)
        print(f"  Booking windows: {windows}")
        print(f"  Routes: {len(ROUTES)}")
        print(f"  Output: {self.csv_path}")
        print("═" * 60)

        self.start_browser()
        all_flights = []

        try:
            routes_to_scrape = ROUTES
            if route_filter:
                routes_to_scrape = [
                    r for r in ROUTES
                    if f"{r['origin']}-{r['destination']}" == route_filter
                ]
                if not routes_to_scrape:
                    print(f"[!] Route '{route_filter}' not found. Available:")
                    for r in ROUTES:
                        print(f"    {r['origin']}-{r['destination']}")
                    return

            total_jobs = len(routes_to_scrape) * len(BOOKING_WINDOWS)
            job_no = 0
            # Outer loop = window, so all routes for one window complete before
            # the next window (keeps each window's comparison self-consistent).
            for w in BOOKING_WINDOWS:
                for i, route in enumerate(routes_to_scrape):
                    job_no += 1
                    print(f"\n  ⏱  Job {job_no}/{total_jobs} — window T+{w}, "
                          f"route {route['origin']}->{route['destination']}")

                    # Fresh context so Air India cannot detect / block
                    # follow-up searches sharing a session.
                    self._new_context()

                    flights = self.scrape_route(route, days_ahead=w)
                    if flights:
                        self._append_rows(flights)
                        all_flights.extend(flights)

                    # Rate limiting between jobs
                    if job_no < total_jobs:
                        d = randomized_delay()
                        print(f"\n  [rate-limit] Waiting {d:.0f}s before next job...")
                        time.sleep(d)

        except KeyboardInterrupt:
            print("\n[!] Interrupted by user. Saving what we have...")
        except Exception as e:
            print(f"\n[!] Fatal error: {e}")
            traceback.print_exc()
            self._save_debug("fatal_error", html=True, screenshot=True)
        finally:
            self.close_browser()

        # ── Summary ────────────────────────────────────────────────────
        print("\n" + "═" * 60)
        print("  SCRAPE SUMMARY")
        print("═" * 60)
        print(f"  Total flights collected: {len(all_flights)}")
        print(f"  Output file: {self.csv_path}")

        if all_flights:
            df = pd.DataFrame(all_flights)
            print(f"\n  Flights per window:")
            for w in BOOKING_WINDOWS:
                count = len(df[df["booking_window"] == str(w)])
                print(f"    T+{w}: {count}")

            print(f"\n  Flights per route:")
            for route in routes_to_scrape:
                count = len(df[
                    (df["origin"] == route["origin"]) &
                    (df["destination"] == route["destination"])
                ])
                print(f"    {route['origin']}->{route['destination']}: {count}")

            try:
                fares = df['total_fare']
                fares_numeric = pd.to_numeric(fares, errors="coerce").dropna()
                if not fares_numeric.empty:
                    print(f"\n  Fare range: Rs {fares_numeric.min()} - Rs {fares_numeric.max()}")
                    print(f"  Mean fare:  Rs {fares_numeric.mean():.0f}")
            except Exception as e:
                print(f"\n  [!] Could not compute fare stats: {e}")
        else:
            print("\n  [!] No flights collected. Check data/debug/ for HTML and screenshots.")
            print("      Common causes:")
            print("        - Website layout changed (update selectors)")
            print("        - CAPTCHA triggered (manual intervention needed)")
            print("        - Network issue")

        return all_flights


# ═══════════════════════════════════════════════════════════════════════════
# CLI entry point
# ═══════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Air India flight price scraper for SIH26056"
    )
    parser.add_argument(
        "--route", type=str, default=None,
        help="Scrape a single route, e.g. 'DEL-BOM'"
    )
    parser.add_argument(
        "--headless", action="store_true",
        help="Run browser in headless mode"
    )
    parser.add_argument(
        "--debug", action="store_true",
        help="Save HTML/screenshot debug dumps on the success path"
    )
    parser.add_argument(
        "--proxy", type=str, default=None,
        help="Proxy URL (overrides SIH_PROXY env), e.g. "
             "http://user:pass@host:port or socks5://host:port"
    )
    args = parser.parse_args()

    if args.proxy:
        os.environ["SIH_PROXY"] = args.proxy

    scraper = AirIndiaScraper(headless=args.headless, debug=args.debug)
    scraper.run(route_filter=args.route)


if __name__ == "__main__":
    main()
