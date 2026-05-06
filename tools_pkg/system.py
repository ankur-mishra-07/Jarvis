"""System control tools — volume, brightness, screenshots, battery, etc."""

import os
import subprocess
import datetime
import platform
from .registry import tool


def _applescript(script):
    result = subprocess.run(["osascript", "-e", script],
                            capture_output=True, text=True, timeout=5)
    return result.stdout.strip()


@tool("get_time", "Get the current date and time", {})
def get_time(**kw):
    now = datetime.datetime.now()
    return now.strftime("It's %I:%M %p on %A, %B %d, %Y.")


@tool("set_volume", "Set system volume (0-100)",
      {"level": "Volume level 0-100"})
def set_volume(level, **kw):
    level = max(0, min(100, int(level)))
    _applescript(f"set volume output volume {level}")
    return f"Volume set to {level}%."


@tool("get_weather", "Get weather for a location",
      {"city": "City name (optional)"})
def get_weather(city="", **kw):
    import requests
    url = f"https://wttr.in/{city}?format=3" if city else "https://wttr.in/?format=3"
    try:
        r = requests.get(url, timeout=5)
        return r.text.strip() if r.status_code == 200 else "Weather unavailable."
    except Exception:
        return "Weather service unreachable."


@tool("take_screenshot", "Capture the screen and save to Desktop", {})
def take_screenshot(**kw):
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.expanduser(f"~/Desktop/screenshot_{ts}.png")
    subprocess.run(["screencapture", path], capture_output=True)
    return f"Screenshot saved: {path}"


@tool("battery_status", "Check MacBook battery level", {})
def battery_status(**kw):
    result = subprocess.run(["pmset", "-g", "batt"],
                            capture_output=True, text=True)
    for line in result.stdout.split("\n"):
        if "%" in line:
            parts = line.split("\t")
            if len(parts) > 1:
                return f"Battery: {parts[1].strip()}"
    return "Couldn't read battery."


@tool("system_info", "Get system information", {})
def system_info(**kw):
    info = platform.uname()
    return f"{info.system} {info.machine}, Node: {info.node}"


@tool("toggle_dark_mode", "Toggle macOS dark/light mode", {})
def toggle_dark_mode(**kw):
    _applescript('''tell application "System Events"
        tell appearance preferences
            set dark mode to not dark mode
        end tell
    end tell''')
    return "Dark mode toggled."


@tool("lock_screen", "Lock the screen", {})
def lock_screen(**kw):
    subprocess.run(["/System/Library/CoreServices/Menu Extras/User.menu/Contents/Resources/CGSession", "-suspend"])
    return "Screen locked."


@tool("wifi_status", "Check Wi-Fi connection", {})
def wifi_status(**kw):
    result = subprocess.run(
        ["/System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/Resources/airport", "-I"],
        capture_output=True, text=True)
    for line in result.stdout.split("\n"):
        if "SSID" in line and "BSSID" not in line:
            ssid = line.split(":")[1].strip()
            return f"Connected to: {ssid}"
    return "Not connected to Wi-Fi."


@tool("read_screen", "OCR the screen and return visible text", {})
def read_screen(**kw):
    img_name = "jarvis_ocr.png"
    tmp_dir = "/tmp"
    img_path = os.path.join(tmp_dir, img_name)
    txt_name = "jarvis_ocr"
    txt_path = os.path.join(tmp_dir, txt_name)
    try:
        subprocess.run(["screencapture", "-x", "-C", img_path],
                       capture_output=True, timeout=5)
        subprocess.run(["tesseract", img_name, txt_name, "-l", "eng"],
                       capture_output=True, timeout=15, cwd=tmp_dir)
        with open(txt_path + ".txt") as f:
            text = f.read().strip()
        for p in (img_path, txt_path + ".txt"):
            try: os.unlink(p)
            except OSError: pass
        if not text:
            return "Screen visible but no readable text."
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        return "; ".join(lines[:8])[:500]
    except Exception as e:
        return f"Screen read error: {e}"
