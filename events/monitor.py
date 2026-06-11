"""
J.A.R.V.I.S. System Event Monitor — proactive announcements.

Watches system state in a background thread and speaks up unprompted,
Iron-Man style:

  - Battery low (20% / 10% / 5%), fully charged, charger pulled while low
  - WiFi connected / disconnected / network switched
  - Disk space critically low
  - Indian market open (9:15) and close (15:30) — speaks a finance briefing

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

    def stop(self):
        self._running = False

    # ─── Main loop ───────────────────────────────────────────────────────

    def run(self):
        self._prime()
        print("  [Event monitor active — battery, WiFi, disk, market hours]", flush=True)
        while self._running:
            time.sleep(POLL_INTERVAL)
            for check in (self._check_battery, self._check_wifi,
                          self._check_disk, self._check_market):
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
