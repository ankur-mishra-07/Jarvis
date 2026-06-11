"""
J.A.R.V.I.S. System Event Monitor — proactive announcements.

Watches system state in a background thread and speaks up unprompted,
Iron-Man style:

  - Battery low (20% / 10% / 5%), fully charged, charger pulled while low
  - WiFi connected / disconnected / network switched
  - Disk space critically low
  - Indian market open (9:15) and close (15:30) — speaks a finance briefing
  - Calendar: "your meeting starts in ten minutes" (macOS Calendar app)
  - Portfolio: a holding you own moves ±3% intraday
  - Downloads: a new file finishes landing in ~/Downloads

Behaviour rules:
  - Initial state is primed silently (no announcement storm at startup)
  - Every event type has a cooldown so nothing repeats annoyingly
  - Quiet hours (23:00–08:00): only critical battery alerts get through
  - Live toggle: "jarvis disable announcements" flips config, takes effect
    on the next poll cycle without restart
"""
from __future__ import annotations

import datetime
import re
import shutil
import subprocess
import threading
import time

import config

POLL_INTERVAL = 30          # seconds between checks
QUIET_START, QUIET_END = 23, 8   # hour range where only critical alerts speak


class SystemEventMonitor(threading.Thread):
    """Background watcher that announces system events via the speech engine."""

    def __init__(self, speech_engine):
        super().__init__(daemon=True, name="jarvis-event-monitor")
        self._speech = speech_engine
        self._running = True

        # Primed state — set on first poll, compared against afterwards
        self._battery_pct = None
        self._charging = None
        self._wifi = None

        # Dedup / cooldown bookkeeping
        self._battery_level_announced = 100   # lowest threshold already announced
        self._full_charge_announced = False
        self._disk_announced_on = None        # date of last disk warning
        self._market_open_announced_on = None
        self._market_close_announced_on = None

        # Calendar / portfolio / downloads state
        self._calendar_announced = set()      # (title, day) pairs already announced
        self._calendar_next_check = 0         # own cadence: every 3 min
        self._calendar_failures = 0           # disable after repeated errors
        self._portfolio_alerted = {}          # ticker → (date, direction)
        self._portfolio_next_check = 0        # own cadence: every 10 min
        self._downloads_seen = None           # primed filename set (None until primed)

    def stop(self):
        self._running = False

    # ─── Main loop ───────────────────────────────────────────────────────

    def run(self):
        self._prime()
        print("  [Event monitor active — battery, WiFi, disk, market hours]", flush=True)
        while self._running:
            time.sleep(POLL_INTERVAL)
            for check in (self._check_battery, self._check_wifi,
                          self._check_disk, self._check_market,
                          self._check_calendar, self._check_portfolio,
                          self._check_downloads):
                try:
                    check()
                except Exception as e:
                    print(f"  [Event monitor: {check.__name__} error: {e}]", flush=True)

    def _prime(self):
        """Read initial state silently so startup doesn't trigger announcements."""
        try:
            self._battery_pct, self._charging = self._read_battery()
            if self._battery_pct is not None:
                # Don't re-announce levels already below threshold at startup
                for lvl in (20, 10, 5):
                    if self._battery_pct <= lvl:
                        self._battery_level_announced = lvl
        except Exception:
            pass
        try:
            self._wifi = self._read_wifi()
        except Exception:
            pass

    # ─── Announce helper ─────────────────────────────────────────────────

    def _announce(self, text, critical=False):
        # Disabled via "jarvis disable announcements" — critical still gets through
        if not config.get("proactive_events") and not critical:
            return
        hour = datetime.datetime.now().hour
        in_quiet = hour >= QUIET_START or hour < QUIET_END
        if in_quiet and not critical:
            return
        print(f"  [Event: {text}]", flush=True)
        # Non-blocking — never stalls the monitor loop; SpeechEngine's lock
        # serialises against any in-progress command response
        self._speech.speak_nonblocking(text)

    # ─── Battery ─────────────────────────────────────────────────────────

    @staticmethod
    def _read_battery():
        """Returns (percent, is_charging) or (None, None) on desktops."""
        out = subprocess.run(["pmset", "-g", "batt"],
                             capture_output=True, text=True, timeout=5).stdout
        m = re.search(r'(\d+)%;\s*(\w[\w\s]*?);', out)
        if not m:
            return None, None
        pct = int(m.group(1))
        state = m.group(2).strip().lower()
        charging = state in ("charging", "charged", "finishing charge") or "AC Power" in out
        return pct, charging

    def _check_battery(self):
        pct, charging = self._read_battery()
        if pct is None:
            return
        prev_pct, prev_charging = self._battery_pct, self._charging
        self._battery_pct, self._charging = pct, charging

        # Low battery thresholds — each announced once on the way down
        if not charging:
            for lvl, phrase, critical in (
                (5,  "Critical battery — five percent. Plug in now, sir.", True),
                (10, "Battery down to ten percent. I'd plug in soon.", True),
                (20, "Battery at twenty percent, sir.", False),
            ):
                if pct <= lvl < self._battery_level_announced:
                    self._battery_level_announced = lvl
                    self._announce(phrase, critical=critical)
                    break

        # Charger reconnected → reset the low-level ladder
        if charging and prev_charging is False:
            self._battery_level_announced = 100
            self._full_charge_announced = False

        # Charger pulled while battery already low
        if prev_charging is True and not charging and pct <= 30:
            self._announce(f"Charger disconnected with {pct} percent remaining.")

        # Fully charged
        if charging and pct >= 100 and not self._full_charge_announced:
            self._full_charge_announced = True
            self._announce("Battery fully charged — you can unplug.")

    # ─── WiFi ────────────────────────────────────────────────────────────

    @staticmethod
    def _read_wifi():
        """Returns the current SSID, or None if not on WiFi."""
        try:
            out = subprocess.run(
                ["networksetup", "-getairportnetwork", "en0"],
                capture_output=True, text=True, timeout=5).stdout
            m = re.search(r'Current Wi-Fi Network:\s*(.+)', out)
            if m:
                return m.group(1).strip()
        except Exception:
            pass
        return None

    def _check_wifi(self):
        ssid = self._read_wifi()
        prev = self._wifi
        self._wifi = ssid
        if ssid == prev:
            return
        if ssid and prev:
            self._announce(f"Switched WiFi network to {ssid}.")
        elif ssid and prev is None:
            self._announce(f"Connected to {ssid}.")
        elif prev and ssid is None:
            self._announce("WiFi connection lost, sir.")

    # ─── Disk ────────────────────────────────────────────────────────────

    def _check_disk(self):
        free_gb = shutil.disk_usage("/").free / 1e9
        today = datetime.date.today()
        if free_gb < 10 and self._disk_announced_on != today:
            self._disk_announced_on = today
            self._announce(
                f"Heads up — only {free_gb:.0f} gigabytes of disk space left.")

    # ─── Indian market hours ─────────────────────────────────────────────

    def _check_market(self):
        now = datetime.datetime.now()
        if now.weekday() >= 5:   # Sat/Sun
            return
        today = now.date()
        t = now.time()

        # Market open: announce once between 9:15 and 9:30
        if (datetime.time(9, 15) <= t <= datetime.time(9, 30)
                and self._market_open_announced_on != today):
            self._market_open_announced_on = today
            self._announce_market("Markets are open. ")

        # Market close: announce once between 15:30 and 15:45
        if (datetime.time(15, 30) <= t <= datetime.time(15, 45)
                and self._market_close_announced_on != today):
            self._market_close_announced_on = today
            self._announce_market("Markets have closed for the day. ")

    def _announce_market(self, prefix):
        def _bg():
            try:
                import finance
                summary = finance.daily_briefing()
                self._announce(prefix + summary)
            except Exception as e:
                print(f"  [Market announce error: {e}]", flush=True)
        # Network fetch off the monitor thread so a slow API can't stall polling
        threading.Thread(target=_bg, daemon=True).start()

    # ─── Calendar (macOS Calendar app) ───────────────────────────────────

    _CALENDAR_SCRIPT = '''
    tell application "Calendar"
        set out to ""
        set rightNow to current date
        set cutoff to rightNow + 3600
        repeat with cal in calendars
            try
                repeat with ev in (events of cal whose start date is greater than or equal to rightNow and start date is less than or equal to cutoff)
                    set mins to round (((start date of ev) - rightNow) / 60)
                    set out to out & (summary of ev) & "|" & mins & linefeed
                end repeat
            end try
        end repeat
        return out
    end tell'''

    def _read_calendar(self):
        """Returns [(title, minutes_until_start), ...] for the next hour."""
        # Calendar must be running for AppleScript queries (-g: no focus, -j: hidden).
        # First query after a cold launch can take 20s+; warm queries are fast.
        subprocess.run(["open", "-gja", "Calendar"], capture_output=True, timeout=5)
        out = subprocess.run(["osascript", "-e", self._CALENDAR_SCRIPT],
                             capture_output=True, text=True, timeout=30)
        if out.returncode != 0:
            raise RuntimeError(out.stderr.strip()[:80])
        events = []
        for line in out.stdout.strip().splitlines():
            if "|" in line:
                title, _, mins = line.rpartition("|")
                try:
                    events.append((title.strip(), int(mins)))
                except ValueError:
                    continue
        return events

    def _check_calendar(self):
        now = time.time()
        if now < self._calendar_next_check or self._calendar_failures >= 3:
            return
        self._calendar_next_check = now + 180   # every 3 minutes
        if getattr(self, "_calendar_inflight", False):
            return   # previous fetch still running — Calendar queries can take 20s+

        def _bg():
            self._calendar_inflight = True
            try:
                try:
                    events = self._read_calendar()
                    self._calendar_failures = 0
                except Exception as e:
                    self._calendar_failures += 1
                    if self._calendar_failures == 3:
                        print(f"  [Calendar checks disabled after repeated errors: {e}]"
                              "\n  [Grant Automation → Calendar in System Settings]",
                              flush=True)
                    return

                today = datetime.date.today()
                for title, mins in events:
                    key = (title, str(today))
                    # 3-min poll against a ≤12-min window guarantees one hit per event
                    if 0 < mins <= 12 and key not in self._calendar_announced:
                        self._calendar_announced.add(key)
                        when = "now" if mins <= 2 else f"in {mins} minutes"
                        self._announce(f"Your meeting '{title}' starts {when}, sir.")
            finally:
                self._calendar_inflight = False

        # Slow AppleScript query runs off-thread so battery/WiFi checks never stall
        threading.Thread(target=_bg, daemon=True).start()

    # ─── Portfolio price alerts ──────────────────────────────────────────

    def _check_portfolio(self):
        now = time.time()
        if now < self._portfolio_next_check:
            return
        self._portfolio_next_check = now + 600   # every 10 minutes

        # Only during NSE market hours, weekdays
        dt = datetime.datetime.now()
        if dt.weekday() >= 5:
            return
        if not (datetime.time(9, 15) <= dt.time() <= datetime.time(15, 30)):
            return

        def _bg():
            try:
                from finance.agent import _load_portfolio, _fetch, _pct
                threshold = config.get("portfolio_alert_pct") or 3
                today = str(datetime.date.today())
                for h in _load_portfolio()["holdings"]:
                    d = _fetch(h["ticker"])
                    chg = _pct(d["price"], d["prev_close"])
                    if abs(chg) < threshold:
                        continue
                    direction = "up" if chg > 0 else "down"
                    if self._portfolio_alerted.get(h["ticker"]) == (today, direction):
                        continue
                    self._portfolio_alerted[h["ticker"]] = (today, direction)
                    self._announce(
                        f"Portfolio alert: {h['name'].title()} is {direction} "
                        f"{abs(chg):.1f} percent today.")
            except Exception as e:
                print(f"  [Portfolio alert error: {e}]", flush=True)
        threading.Thread(target=_bg, daemon=True).start()

    # ─── Downloads watcher ───────────────────────────────────────────────

    _DOWNLOADS_DIR = None   # resolved lazily so tests can override
    _PARTIAL_EXTS = (".crdownload", ".download", ".part", ".tmp")

    def _scan_downloads(self):
        import os
        d = self._DOWNLOADS_DIR or os.path.expanduser("~/Downloads")
        try:
            return {f for f in os.listdir(d)
                    if not f.startswith(".")
                    and not f.lower().endswith(self._PARTIAL_EXTS)}
        except OSError:
            return set()

    def _check_downloads(self):
        import os
        current = self._scan_downloads()
        if self._downloads_seen is None:      # first poll: prime silently
            self._downloads_seen = current
            return
        new_files = current - self._downloads_seen
        self._downloads_seen = current
        d = self._DOWNLOADS_DIR or os.path.expanduser("~/Downloads")
        for f in sorted(new_files):
            try:
                size = os.path.getsize(os.path.join(d, f))
            except OSError:
                continue
            if size < 1_000_000:              # ignore tiny files / metadata
                continue
            mb = size / 1e6
            size_str = f"{mb/1000:.1f} gigabytes" if mb >= 1000 else f"{mb:.0f} megabytes"
            self._announce(f"Download finished: {f}, {size_str}.")
