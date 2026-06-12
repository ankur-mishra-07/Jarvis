"""
J.A.R.V.I.S. Command Engine
Natural language command processing with everyday voice commands.
"""

import datetime
import os
import subprocess
import time
import webbrowser
import platform
import re
import json
import math
import random

import threading
import config
import claude_brain
import brain

OWNER_NAME = config.get("owner_name")

# Conversation history for Claude
_claude_history = []

# Thread lock for concurrent access (local voice + API server)
_command_lock = threading.Lock()

# ─── Conversation Context ─────────────────────────────────────────────────────

class ConversationContext:
    """
    Lightweight stateful context — remembers what Jarvis last did so
    follow-up phrases like "cancel it", "make it 10 minutes", "add that
    to notes" resolve correctly without an LLM.
    """
    MAX_HISTORY = 8

    def __init__(self):
        self.history      = []   # [(user_said, jarvis_said), ...]
        self.last_action  = None  # e.g. "timer", "alarm", "note", "app", "search"
        self.last_subject = None  # e.g. "5 minutes", "youtube", "meeting"
        self.last_reply   = None
        self.mode         = None  # "taking_notes" | None
        self.note_buffer  = []   # accumulated lines in note-taking mode

    def record(self, user_said, jarvis_said, action=None, subject=None):
        self.history.append((user_said, jarvis_said))
        if len(self.history) > self.MAX_HISTORY:
            self.history.pop(0)
        if action:
            self.last_action  = action
            self.last_subject = subject
        self.last_reply = jarvis_said

    def resolve_pronouns(self, command):
        """Replace 'it'/'that'/'this' with last known subject where safe."""
        c = command.lower()
        if self.last_subject and re.search(r'\b(it|that|this|the same)\b', c):
            c = re.sub(r'\b(it|that|this|the same)\b', self.last_subject, c, count=1)
        return c

    def recent_user_text(self, n=3):
        return [u for u, _ in self.history[-n:]]

    def clear_mode(self):
        self.mode = None
        self.note_buffer = []


_ctx = ConversationContext()

MEMORY_FILE = os.path.expanduser("~/Jarvis/logs/conversation_memory.json")


def _load_memory():
    """Load last N exchanges from previous session."""
    try:
        if os.path.exists(MEMORY_FILE):
            with open(MEMORY_FILE) as f:
                data = json.load(f)
            _ctx.history = data.get("history", [])[-6:]   # last 6 turns
            print(f"  [Memory: loaded {len(_ctx.history)} turns from previous session]",
                  flush=True)
    except Exception:
        pass


def _save_memory():
    """Persist recent conversation to disk."""
    try:
        os.makedirs(os.path.dirname(MEMORY_FILE), exist_ok=True)
        with open(MEMORY_FILE, "w") as f:
            json.dump({"history": _ctx.history}, f, indent=2)
    except Exception:
        pass


_load_memory()

# ─── Utility ─────────────────────────────────────────────────────────────────

def _run_applescript(script):
    """Run an AppleScript and return stdout."""
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    return result.stdout.strip()


def _notify(title, message):
    """Send a macOS notification."""
    _run_applescript(
        f'display notification "{message}" with title "{title}"'
    )


# ─── Command Handlers ────────────────────────────────────────────────────────

# --- Time & Date ---

def tell_time():
    now = datetime.datetime.now().strftime("%I:%M %p")
    return f"The time is {now}."


def tell_date():
    today = datetime.datetime.now().strftime("%A, %B %d, %Y")
    return f"Today is {today}."


def tell_day():
    day = datetime.datetime.now().strftime("%A")
    return f"Today is {day}."


# --- Alarms, Timers & Reminders ---

def set_timer(command):
    """Set a timer using macOS 'say' after delay via background process."""
    minutes = 0
    seconds = 0
    # Extract minutes
    m = re.search(r'(\d+)\s*minute', command)
    if m:
        minutes = int(m.group(1))
    # Extract seconds
    s = re.search(r'(\d+)\s*second', command)
    if s:
        seconds = int(s.group(1))
    # Extract hours
    h = re.search(r'(\d+)\s*hour', command)
    if h:
        minutes += int(h.group(1)) * 60

    if minutes == 0 and seconds == 0:
        return "Please specify a duration, like 'set a timer for 5 minutes'."

    total_seconds = minutes * 60 + seconds
    # Launch background timer
    subprocess.Popen(
        ["bash", "-c", f'sleep {total_seconds} && say "Timer is up, {OWNER_NAME}!" && osascript -e \'display notification "Timer is up!" with title "JARVIS Timer" sound name "Glass"\''],
    )
    if minutes > 0 and seconds > 0:
        return f"Timer set for {minutes} minutes and {seconds} seconds."
    elif minutes > 0:
        return f"Timer set for {minutes} minutes."
    else:
        return f"Timer set for {seconds} seconds."


def set_alarm(command):
    """Set an alarm for a specific time."""
    # Try to parse time like "7:30 am", "7 am", "19:30"
    time_match = re.search(r'(\d{1,2})[:\s]?(\d{2})?\s*(am|pm|a\.m\.|p\.m\.)?', command)
    if not time_match:
        return "Please specify a time, like 'set alarm for 7:30 am'."

    hour = int(time_match.group(1))
    minute = int(time_match.group(2)) if time_match.group(2) else 0
    period = time_match.group(3)

    if period and 'p' in period.lower() and hour != 12:
        hour += 12
    elif period and 'a' in period.lower() and hour == 12:
        hour = 0

    now = datetime.datetime.now()
    alarm_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if alarm_time <= now:
        alarm_time += datetime.timedelta(days=1)

    diff = (alarm_time - now).total_seconds()
    time_str = alarm_time.strftime("%I:%M %p")

    subprocess.Popen(
        ["bash", "-c", f'sleep {int(diff)} && say "Alarm! Wake up {OWNER_NAME}!" && osascript -e \'display notification "Alarm!" with title "JARVIS Alarm" sound name "Sosumi"\''],
    )
    return f"Alarm set for {time_str}."


def set_reminder(command):
    """Set a reminder with macOS Reminders app."""
    # Extract the reminder text
    text = re.sub(r'(set a |set |create a |add a |make a )?(reminder|remind me)( to| that| about)?', '', command).strip()
    # Extract time if specified
    in_match = re.search(r'in (\d+)\s*(minute|hour|second)', text)
    if in_match:
        amount = int(in_match.group(1))
        unit = in_match.group(2)
        text = text[:in_match.start()].strip()
        multiplier = {"second": 1, "minute": 60, "hour": 3600}[unit]
        total = amount * multiplier[0] if isinstance(multiplier, tuple) else amount * multiplier

        subprocess.Popen(
            ["bash", "-c", f'sleep {total} && say "Reminder: {text}" && osascript -e \'display notification "{text}" with title "JARVIS Reminder" sound name "Glass"\''],
        )
        return f"I'll remind you to {text} in {amount} {unit}{'s' if amount > 1 else ''}."

    if text:
        # Add to macOS Reminders
        _run_applescript(f'''
            tell application "Reminders"
                make new reminder with properties {{name:"{text}"}}
            end tell
        ''')
        return f"Reminder added: {text}"
    return "What would you like me to remind you about?"


# --- Weather ---

def get_weather(command):
    """Get weather using wttr.in (no API key needed)."""
    # Extract city if mentioned
    city = ""
    for prefix in ["weather in ", "weather for ", "weather at ", "forecast for ", "forecast in "]:
        if prefix in command:
            city = command.split(prefix)[1].strip()
            break
    try:
        import requests
        url = f"https://wttr.in/{city}?format=3" if city else "https://wttr.in/?format=3"
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            return resp.text.strip()
        return "I couldn't fetch the weather right now."
    except Exception:
        return "I need an internet connection to check the weather."


def get_forecast(command):
    """Get weather forecast."""
    city = ""
    for prefix in ["forecast for ", "forecast in ", "forecast at "]:
        if prefix in command:
            city = command.split(prefix)[1].strip()
            break
    try:
        import requests
        url = f"https://wttr.in/{city}?format=%l:+%c+%t+%w" if city else "https://wttr.in/?format=%l:+%c+%t+%w"
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            return resp.text.strip()
        return "I couldn't fetch the forecast right now."
    except Exception:
        return "I need an internet connection to check the forecast."


# --- News ---

def get_news():
    """Open top news in browser."""
    webbrowser.open("https://news.google.com")
    return "Opening Google News for you."


# --- Applications ---

APP_MAP = {
    "chrome": "Google Chrome", "google chrome": "Google Chrome",
    "safari": "Safari", "firefox": "Firefox", "brave": "Brave Browser",
    "terminal": "Terminal", "iterm": "iTerm", "finder": "Finder",
    "notes": "Notes", "music": "Music", "spotify": "Spotify",
    "slack": "Slack", "discord": "Discord", "zoom": "zoom.us",
    "teams": "Microsoft Teams", "microsoft teams": "Microsoft Teams",
    "vscode": "Visual Studio Code", "vs code": "Visual Studio Code",
    "code": "Visual Studio Code", "xcode": "Xcode",
    "mail": "Mail", "gmail": "Google Chrome",
    "messages": "Messages", "imessage": "Messages",
    "calendar": "Calendar", "photos": "Photos",
    "settings": "System Settings", "system settings": "System Settings",
    "system preferences": "System Preferences",
    "activity monitor": "Activity Monitor", "calculator": "Calculator",
    "preview": "Preview", "pages": "Pages", "numbers": "Numbers",
    "keynote": "Keynote", "word": "Microsoft Word",
    "excel": "Microsoft Excel", "powerpoint": "Microsoft PowerPoint",
    "notion": "Notion", "obsidian": "Obsidian",
    "whatsapp": "WhatsApp", "telegram": "Telegram",
    "facetime": "FaceTime", "app store": "App Store",
    "maps": "Maps", "books": "Books",
    "podcasts": "Podcasts", "tv": "TV", "news": "News",
    # clock / timer / stopwatch
    "clock": "Clock", "timer": "Clock", "stopwatch": "Clock", "alarm": "Clock",
    "alarms": "Clock", "world clock": "Clock",
    # creative / editing
    "photoshop": "Adobe Photoshop", "illustrator": "Adobe Illustrator",
    "premiere": "Adobe Premiere Pro", "figma": "Figma", "sketch": "Sketch",
    "final cut": "Final Cut Pro", "logic pro": "Logic Pro",
    # dev / productivity
    "github desktop": "GitHub Desktop", "postman": "Postman",
    "docker": "Docker", "chatgpt": "ChatGPT", "claude": "Claude",
    "cursor": "Cursor", "warp": "Warp",
    # social / comms
    "signal": "Signal", "skype": "Skype", "linkedin": "LinkedIn",
    # media
    "vlc": "VLC", "quicktime": "QuickTime Player", "quick time": "QuickTime Player",
    "spotify music": "Spotify", "apple music": "Music",
    # browsers aliases
    "edge": "Microsoft Edge", "arc": "Arc", "opera": "Opera",
    # utilities
    "weather": "Weather", "reminders": "Reminders", "stocks": "Stocks",
    "shortcuts": "Shortcuts", "airdrop": "Finder",
    "bluetooth": "System Settings", "wifi settings": "System Settings",
}

def _clean_app_command(command, action_words):
    """Strip filler words and extract just the app name."""
    # Remove polite/filler prefixes
    c = re.sub(r'^(can you |could you |would you |please |jarvis |hey )+', '', command.lower()).strip()
    # Remove action word and everything before it
    pat = r'.*?\b(' + '|'.join(action_words) + r')\s+(?:the\s+|a\s+|an\s+|app\s+|application\s+)?'
    c = re.sub(pat, '', c, count=1).strip()
    # Remove trailing 'app', 'application', 'please', punctuation
    c = re.sub(r'\s+(app|application|for me|please)\.?$', '', c).strip(" .,!?")
    return c


WEBSITE_MAP = {
    "youtube": "https://youtube.com",
    "gmail": "https://mail.google.com",
    "google": "https://google.com",
    "facebook": "https://facebook.com",
    "instagram": "https://instagram.com",
    "twitter": "https://twitter.com",
    "x": "https://x.com",
    "reddit": "https://reddit.com",
    "github": "https://github.com",
    "linkedin": "https://linkedin.com",
    "netflix": "https://netflix.com",
    "amazon": "https://amazon.com",
    "chatgpt": "https://chat.openai.com",
    "claude": "https://claude.ai",
    "stack overflow": "https://stackoverflow.com",
    "stackoverflow": "https://stackoverflow.com",
    "wikipedia": "https://wikipedia.org",
    "twitch": "https://twitch.tv",
    "discord": "https://discord.com",
    "whatsapp web": "https://web.whatsapp.com",
    "spotify web": "https://open.spotify.com",
    "hotstar": "https://hotstar.com",
    "disney plus": "https://disneyplus.com",
    "prime video": "https://primevideo.com",
    "notion": "https://notion.so",
    "figma": "https://figma.com",
    "maps": "https://maps.google.com",
    "google maps": "https://maps.google.com",
    "drive": "https://drive.google.com",
    "google drive": "https://drive.google.com",
    "calendar": "https://calendar.google.com",
    "google calendar": "https://calendar.google.com",
    "docs": "https://docs.google.com",
    "google docs": "https://docs.google.com",
    "sheets": "https://sheets.google.com",
    "slides": "https://slides.google.com",
    "translate": "https://translate.google.com",
    "news": "https://news.google.com",
}

BROWSER_MAP = {
    "safari": "Safari",
    "chrome": "Google Chrome", "google chrome": "Google Chrome",
    "firefox": "Firefox", "brave": "Brave Browser",
    "edge": "Microsoft Edge", "arc": "Arc", "opera": "Opera",
}


WHISPER_FIXES = {
    "jethub": "github", "jithub": "github", "geethub": "github",
    "git hub": "github", "get hub": "github", "github.": "github",
    "you tube": "youtube", "yutube": "youtube", "u-tube": "youtube",
    "you-tube": "youtube", "youtub": "youtube",
    "g mail": "gmail", "g-mail": "gmail",
    "face book": "facebook", "insta gram": "instagram",
    "linked in": "linkedin", "what's app": "whatsapp",
    "stack over flow": "stackoverflow",
    "javis": "jarvis", "jervis": "jarvis", "starvis": "jarvis",
    "joe this": "jarvis",
}


def _normalize_command(command):
    """Pre-process voice input to fix common Whisper mishears + fused words."""
    c = command.lower()
    # Insert space AROUND verbs when they're glued to other words.
    # 'javasopenjithub' -> 'javas open jithub'
    # 'openjethub'      -> 'open jethub'
    # BUT: do NOT split legitimate words like 'player', 'closer', 'display', 'playing'
    protected_words = {
        "player", "players", "playing", "played", "playback", "playlist", "display",
        "closer", "closest", "closed", "closing", "closet",
        "starting", "started", "starter", "startup",
        "searching", "searched", "searcher",
        "finding", "finder", "findings",
        "paused", "pausing", "stopping", "stopped",
        "showing", "showed", "shower", "shown",
        "setting", "settings", "setup",
        "telling", "opening", "opener", "launched",
        "visited", "visiting", "visitor",
    }
    # Check if any protected word would be broken
    words = c.split()
    protected_spans = set()
    for w in words:
        if w in protected_words:
            protected_spans.add(w)

    for verb in ("open", "launch", "start", "close", "play", "search",
                 "visit", "tell", "show", "set", "find", "pause", "stop"):
        # Skip splitting if it would break a protected word
        skip = False
        for pw in protected_spans:
            if verb in pw and verb != pw:
                skip = True
                break
        if skip:
            continue
        # Letter-letter sandwich (mid-word): insert spaces both sides
        c = re.sub(rf'(?<=[a-z]){verb}(?=[a-z])', f' {verb} ', c)
        # Verb followed by letters (start of word): split
        c = re.sub(rf'\b{verb}(?=[a-z])', f'{verb} ', c)
    # Collapse whitespace
    c = re.sub(r'\s+', ' ', c).strip()
    # Fix common Whisper substitutions (whole-word match)
    for wrong, right in WHISPER_FIXES.items():
        c = re.sub(rf'\b{re.escape(wrong)}\b', right, c)
    return c


def _parse_website_in_browser(command):
    """
    Detect patterns like:
        'open youtube in safari'
        'open gmail on chrome'
        'youtube on firefox'
    Returns (website_name, browser_app_name) or (None, None).
    """
    c = _normalize_command(command)
    # "X in/on Y" pattern
    m = re.search(
        r'(?:open|launch|start|go to|visit|play|pull up)\s+(.+?)\s+(?:in|on|using|with|via)\s+(.+?)(?:\s+browser)?$',
        c,
    )
    if not m:
        m = re.search(r'(.+?)\s+(?:in|on)\s+(' + '|'.join(BROWSER_MAP.keys()) + r')\b', c)
    if m:
        site = m.group(1).strip(" ,.?!")
        # Remove leading "the " word (not stripping chars!)
        site = re.sub(r'^(the|a|an)\s+', '', site).strip()
        browser = m.group(2).strip(" ,.?!")
        browser = BROWSER_MAP.get(browser, None)
        if site and browser:
            return site, browser
    return None, None


def _resolve_website_url(name):
    """Resolve a site name to URL. Adds https:// if bare domain."""
    n = name.lower().strip(" ,.?!")
    if n in WEBSITE_MAP:
        return WEBSITE_MAP[n]
    # If it looks like a bare domain, use it
    if "." in n:
        return n if n.startswith("http") else f"https://{n}"
    # Otherwise Google-search for it
    return f"https://www.google.com/search?q={n.replace(' ', '+')}"


def open_application(command):
    # FIRST: check for "X in/on BROWSER" pattern
    site, browser = _parse_website_in_browser(command)
    if site and browser:
        url = _resolve_website_url(site)
        try:
            subprocess.Popen(["open", "-a", browser, url])
            return f"Opening {site} in {browser}, sir."
        except Exception:
            return f"Sorry, I couldn't open {site} in {browser}."

    # SECOND: standard app-open
    app_name = _clean_app_command(command, ["open", "launch", "start", "run", "fire up", "pull up"])
    if not app_name:
        return "Which app would you like to open?"

    # If it's actually a known website, open it in default browser
    if app_name.lower() in WEBSITE_MAP:
        url = WEBSITE_MAP[app_name.lower()]
        webbrowser.open(url)
        return f"Opening {app_name} in your browser, sir."

    resolved = APP_MAP.get(app_name.lower(), app_name.title())
    try:
        result = subprocess.run(["open", "-a", resolved], capture_output=True, text=True, timeout=5)
        if result.returncode != 0:
            # Fallback: maybe the user meant a website
            if "." in app_name or len(app_name.split()) == 1:
                url = _resolve_website_url(app_name)
                webbrowser.open(url)
                return f"Couldn't find the app — searching for {app_name} instead."
            return f"Sorry, I couldn't find {resolved}. Please check the app name."
        return f"Opening {resolved}, sir."
    except Exception as e:
        return f"Sorry, I couldn't open {resolved}."


def close_application(command):
    app_name = _clean_app_command(command, ["close", "quit", "exit", "kill", "shut"])
    if not app_name:
        return "Which app would you like to close?"
    resolved = APP_MAP.get(app_name.lower(), app_name.title())
    try:
        _run_applescript(f'tell application "{resolved}" to quit')
        return f"Closing {resolved}."
    except Exception:
        return f"Sorry, I couldn't close {resolved}."


# --- Web Search & Browsing ---

def _route_search(command):
    """Smart search router — if command mentions youtube/spotify, route there."""
    lower = command.lower()
    if any(kw in lower for kw in ("youtube", "on yt", "in yt")):
        return search_youtube(command)
    if any(kw in lower for kw in ("spotify", "on spotify")):
        return spotify_play(command)
    return search_web(command)


def search_web(command):
    query = re.sub(r'^(search for|search|google|look up|find)\s+', '', command).strip()
    if query:
        webbrowser.open(f"https://www.google.com/search?q={query.replace(' ', '+')}")
        return f"Searching for {query}."
    return "What would you like me to search for?"


def search_youtube(command):
    query = re.sub(
        r'(search for|search|play|find|look up|look for)\s+', '', command, count=1
    ).strip()
    # Strip youtube references from query
    query = re.sub(r'\b(on|in|from|inside|within|using|via)\s+youtube\b', '', query).strip()
    query = re.sub(r'\byoutube\b', '', query).strip()
    query = query.strip(" .,!?")
    if query:
        webbrowser.open(f"https://www.youtube.com/results?search_query={query.replace(' ', '+')}")
        return f"Searching YouTube for {query}."
    return "What would you like me to find on YouTube?"


def open_website(command):
    """Open a website by name or URL."""
    site = re.sub(r'^(go to|open|visit|navigate to|browse)\s+', '', command).strip()
    site_map = {
        "gmail": "https://mail.google.com",
        "github": "https://github.com",
        "youtube": "https://youtube.com",
        "twitter": "https://twitter.com",
        "x": "https://x.com",
        "reddit": "https://reddit.com",
        "linkedin": "https://linkedin.com",
        "facebook": "https://facebook.com",
        "instagram": "https://instagram.com",
        "amazon": "https://amazon.com",
        "netflix": "https://netflix.com",
        "google drive": "https://drive.google.com",
        "google docs": "https://docs.google.com",
        "google sheets": "https://sheets.google.com",
        "stack overflow": "https://stackoverflow.com",
        "stackoverflow": "https://stackoverflow.com",
        "chatgpt": "https://chat.openai.com",
        "claude": "https://claude.ai",
    }
    url = site_map.get(site.lower())
    if not url:
        if "." in site:
            url = site if site.startswith("http") else f"https://{site}"
        else:
            url = f"https://www.google.com/search?q={site.replace(' ', '+')}"
    webbrowser.open(url)
    return f"Opening {site}."


# --- Email ---

def compose_email(command):
    """Open a new email compose window."""
    # Try to extract recipient
    to_match = re.search(r'(?:to|for)\s+(\S+@\S+)', command)
    if to_match:
        email = to_match.group(1)
        webbrowser.open(f"mailto:{email}")
        return f"Opening email to {email}."
    else:
        webbrowser.open("mailto:")
        return "Opening a new email."


def check_email():
    subprocess.Popen(["open", "-a", "Mail"])
    return "Opening your email."


# --- Music & Media Controls ---

def music_play(command=None):
    _run_applescript('tell application "Music" to play')
    return "Playing music."


def music_pause():
    _run_applescript('tell application "Music" to pause')
    return "Music paused."


def music_next():
    _run_applescript('tell application "Music" to next track')
    return "Skipping to next track."


def music_previous():
    _run_applescript('tell application "Music" to previous track')
    return "Going back to previous track."


def music_what_playing():
    name = _run_applescript('tell application "Music" to get name of current track')
    artist = _run_applescript('tell application "Music" to get artist of current track')
    if name:
        return f"Now playing: {name} by {artist}."
    return "Nothing is currently playing."


def spotify_play(command):
    query = re.sub(r'(play|on spotify|spotify)\s*', '', command).strip()
    if query:
        webbrowser.open(f"https://open.spotify.com/search/{query.replace(' ', '+')}")
        return f"Searching Spotify for {query}."
    _run_applescript('tell application "Spotify" to play')
    return "Playing Spotify."


# --- System Controls ---

def set_volume(command):
    words = command.split()
    for w in words:
        if w.isdigit():
            level = max(0, min(100, int(w)))
            _run_applescript(f"set volume output volume {level}")
            return f"Volume set to {level} percent."
    if "mute" in command:
        _run_applescript("set volume output volume 0")
        return "Volume muted."
    if "max" in command or "full" in command:
        _run_applescript("set volume output volume 100")
        return "Volume set to maximum."
    return "Please specify a volume level between 0 and 100."


def volume_up():
    current = _run_applescript("output volume of (get volume settings)")
    try:
        new_vol = min(100, int(current) + 15)
        _run_applescript(f"set volume output volume {new_vol}")
        return f"Volume up to {new_vol} percent."
    except ValueError:
        _run_applescript("set volume output volume 60")
        return "Volume increased."


def volume_down():
    current = _run_applescript("output volume of (get volume settings)")
    try:
        new_vol = max(0, int(current) - 15)
        _run_applescript(f"set volume output volume {new_vol}")
        return f"Volume down to {new_vol} percent."
    except ValueError:
        _run_applescript("set volume output volume 30")
        return "Volume decreased."


def mute_volume():
    _run_applescript("set volume output volume 0")
    return "Volume muted."


def unmute_volume():
    _run_applescript("set volume output volume 50")
    return "Volume unmuted, set to 50 percent."


def set_brightness(command):
    m = re.search(r'(\d+)', command)
    if m:
        level = max(0, min(100, int(m.group(1))))
        fraction = level / 100.0
        _run_applescript(f'tell application "System Events" to set value of slider 1 of group 1 of window 1 of application process "SystemUIServer" to {fraction}')
        return f"Brightness set to {level} percent."
    return "Please specify a brightness level."


# --- Screen Control / Keyboard Actions ---

def _bring_browser_to_front():
    """Bring the first open browser to the foreground so screenshots capture it."""
    # Try each browser individually with tight timeout — no loops in AppleScript
    for browser in ("Google Chrome", "Safari", "Firefox", "Arc", "Brave Browser"):
        try:
            r = subprocess.run(["osascript", "-e",
                f'tell application "System Events" to (name of processes) contains "{browser}"'],
                capture_output=True, text=True, timeout=2)
            if "true" in r.stdout.lower():
                subprocess.run(["osascript", "-e",
                    f'tell application "{browser}" to activate'],
                    capture_output=True, timeout=2)
                time.sleep(0.3)
                return
        except Exception:
            continue


def _screenshot_for_ocr(img_path):
    """Bring browser to front and take a screenshot for OCR."""
    _bring_browser_to_front()
    subprocess.run(["screencapture", "-x", "-C", img_path],
                   capture_output=True, timeout=5)


def _applescript_keystroke(key, modifiers=""):
    """Send a keystroke via AppleScript."""
    if modifiers:
        cmd = f'tell application "System Events" to keystroke "{key}" using {{{modifiers}}}'
    else:
        cmd = f'tell application "System Events" to keystroke "{key}"'
    subprocess.run(["osascript", "-e", cmd], capture_output=True, timeout=3)


def _applescript_keycode(code, modifiers=""):
    """Send a key code via AppleScript."""
    if modifiers:
        cmd = f'tell application "System Events" to key code {code} using {{{modifiers}}}'
    else:
        cmd = f'tell application "System Events" to key code {code}'
    subprocess.run(["osascript", "-e", cmd], capture_output=True, timeout=3)


def toggle_fullscreen(command=None):
    """Toggle fullscreen — works in browsers (YouTube: 'f' key) and native apps (Cmd+Ctrl+F)."""
    try:
        # Check if frontmost app is a browser — use 'f' for YouTube/video players
        result = subprocess.run(
            ["osascript", "-e", 'tell application "System Events" to get name of first application process whose frontmost is true'],
            capture_output=True, text=True, timeout=5
        )
        front_app = result.stdout.strip().lower()

        browser_apps = {"safari", "google chrome", "firefox", "arc", "brave browser", "microsoft edge"}
        if front_app in browser_apps:
            # In a browser, press 'f' (YouTube/video fullscreen) — most video players use this
            _applescript_keystroke("f")
            return "Toggled fullscreen in the browser."
    except Exception:
        pass

    # Native macOS fullscreen: Cmd+Ctrl+F (works everywhere)
    _applescript_keycode(3, "command down, control down")  # key code 3 = 'f'
    return "Toggled fullscreen."


def scroll_down(command=None):
    """Scroll down the current page/window."""
    amount = 5  # default scrolls
    if command:
        m = re.search(r'(\d+)', command)
        if m:
            amount = min(int(m.group(1)), 20)
    subprocess.run(["osascript", "-e",
        f'tell application "System Events" to repeat {amount} times\n'
        f'key code 125\nend repeat'],  # down arrow
        capture_output=True, timeout=3)
    return "Scrolled down."


def scroll_up(command=None):
    """Scroll up the current page/window."""
    amount = 5
    if command:
        m = re.search(r'(\d+)', command)
        if m:
            amount = min(int(m.group(1)), 20)
    subprocess.run(["osascript", "-e",
        f'tell application "System Events" to repeat {amount} times\n'
        f'key code 126\nend repeat'],  # up arrow
        capture_output=True, timeout=3)
    return "Scrolled up."


def go_back(command=None):
    """Go back in browser/app — Cmd+[ (browser back)."""
    _applescript_keystroke("[", "command down")  # Cmd+[ = browser back
    return "Going back."


def refresh_page(command=None):
    """Refresh/reload current page — Cmd+R."""
    _applescript_keystroke("r", "command down")
    return "Refreshed the page."


def press_enter(command=None):
    """Press Enter/Return."""
    _applescript_keycode(36)  # Return key
    return "Done."


def press_escape(command=None):
    """Press Escape — exit fullscreen, close popups, etc."""
    _applescript_keycode(53)  # Escape key
    return "Done."


def press_space(command=None):
    """Press Space — play/pause in YouTube, scroll in browser."""
    _applescript_keycode(49)  # Space key
    return "Done."


def type_text(command):
    """Type text into the currently focused field."""
    text = re.sub(r'^(type|enter|input|write)\s+', '', command).strip()
    if not text:
        return "What should I type?"
    # Escape special chars for AppleScript
    safe_text = text.replace('\\', '\\\\').replace('"', '\\"')
    _applescript_keystroke(safe_text)
    return f"Typed: {text[:50]}"


def read_screen(command=None):
    """OCR the current screen and return what's visible."""
    img_name = "jarvis_screen_ocr.png"
    txt_name = "jarvis_screen_ocr"
    tmp_dir = "/tmp"
    img_path = os.path.join(tmp_dir, img_name)
    txt_path = os.path.join(tmp_dir, txt_name)
    try:
        _screenshot_for_ocr(img_path)
        if not os.path.exists(img_path):
            return "I couldn't capture the screen."
        # Leptonica has issues with absolute paths on macOS — run from tmp dir
        result = subprocess.run(
            ["tesseract", img_name, txt_name, "-l", "eng"],
            capture_output=True, timeout=15, cwd=tmp_dir
        )
        with open(txt_path + ".txt", "r") as f:
            text = f.read().strip()
        # Cleanup
        for p in (img_path, txt_path + ".txt"):
            try: os.unlink(p)
            except OSError: pass
        if not text:
            return "I see the screen, but no readable text."
        # Truncate for TTS — full text saved in /tmp for later inspection
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        summary = "; ".join(lines[:5])
        if len(lines) > 5:
            summary += f"; and {len(lines) - 5} more lines."
        return f"On screen: {summary[:300]}"
    except FileNotFoundError:
        return "OCR tool tesseract is not installed."
    except subprocess.TimeoutExpired:
        return "Screen reading timed out."
    except Exception as e:
        return f"Couldn't read the screen: {e}"


def click_text_on_screen(command):
    """Find a text label on screen via OCR with bounding boxes, then click it."""
    # Strip command verb — handle it anywhere in string (wake word may precede it)
    target = re.sub(
        r'(click|tap|press|select|hit)\s+(?:on\s+)?(?:the\s+)?', '', command.lower(), count=1
    ).strip(" ?.!")
    # Also strip any remaining wake word fragments
    target = re.sub(r"^(jarvis|javis|java'?s?|jervis|hey|yo)\s+", '', target).strip()
    if not target:
        return "What should I click?"

    # Check for positional keywords: "first link", "second video", etc.
    positional = None
    ordinal_map = {"first": 0, "second": 1, "third": 2, "fourth": 3, "fifth": 4,
                   "1st": 0, "2nd": 1, "3rd": 2, "4th": 3, "5th": 4}
    target_words = target.lower().split()
    for word in list(target_words):
        if word in ordinal_map:
            positional = ordinal_map[word]
            target_words.remove(word)
    # Filter out generic words that shouldn't be matched literally
    generic_words = {"link", "button", "item", "option", "result", "video", "entry", "one",
                     "click", "tap", "press", "select", "hit", "on", "the", "please", "can", "you"}
    match_words = [w for w in target_words if w not in generic_words]

    img_name = "jarvis_click_ocr.png"
    tmp_dir = "/tmp"
    img_path = os.path.join(tmp_dir, img_name)
    try:
        _screenshot_for_ocr(img_path)
        # Tesseract TSV output gives word-level bounding boxes.
        # Leptonica has issues with absolute paths — run from tmp dir.
        result = subprocess.run(
            ["tesseract", img_name, "stdout", "-l", "eng", "tsv"],
            capture_output=True, timeout=15, text=True, cwd=tmp_dir
        )
        os.unlink(img_path)

        # Parse TSV into word records with positions
        all_words = []
        for line in result.stdout.split("\n")[1:]:  # skip header
            parts = line.split("\t")
            if len(parts) < 12:
                continue
            try:
                conf = float(parts[10])
                word = parts[11].strip()
                if not word or conf < 40:
                    continue
                left, top, w, h = int(parts[6]), int(parts[7]), int(parts[8]), int(parts[9])
                all_words.append({
                    "conf": conf, "word": word, "word_lower": word.lower(),
                    "x": left + w // 2, "y": top + h // 2, "top": top
                })
            except (ValueError, IndexError):
                continue

        if not all_words:
            return "I couldn't read anything on screen."

        # If positional with no specific match words (e.g. "first link"),
        # find clickable-looking text in the CONTENT area (skip menu bar / UI chrome)
        if positional is not None and not match_words:
            # Get screen height to filter — skip top ~8% (menu bar + browser tabs)
            # and filter to meaningful content words (4+ chars, high confidence)
            max_top = max(w["top"] for w in all_words) if all_words else 1000
            min_content_y = max(120, int(max_top * 0.08))  # Skip top UI chrome (Retina pixels)

            clickable = [
                w for w in all_words
                if len(w["word"]) >= 4       # Skip tiny words (UI buttons, icons)
                and w["conf"] > 60           # High confidence only
                and w["top"] > min_content_y # Below menu bar / browser chrome
                and w["word"][0].isalpha()   # Starts with a letter (not symbols/numbers)
            ]
            clickable.sort(key=lambda w: (w["top"], w["x"]))  # reading order

            if positional < len(clickable):
                pick = clickable[positional]
                x, y = pick["x"] // 2, pick["y"] // 2  # Retina halving
                subprocess.run(["cliclick", f"c:{x},{y}"], capture_output=True, timeout=3)
                return f"Clicked on '{pick['word']}' (item #{positional + 1})."
            elif clickable:
                pick = clickable[0]
                x, y = pick["x"] // 2, pick["y"] // 2
                subprocess.run(["cliclick", f"c:{x},{y}"], capture_output=True, timeout=3)
                return f"Clicked on '{pick['word']}' (only found {len(clickable)} items)."
            return f"I couldn't find clickable content on screen."

        # Exact word matching — find all OCR words matching any target word
        search_words = match_words or target_words
        candidates = []
        for w in all_words:
            if any(tw == w["word_lower"] for tw in search_words):
                candidates.append(w)

        if not candidates:
            # Fallback: fuzzy — target word contained in OCR word or vice versa, min 3 chars
            for w in all_words:
                if len(w["word_lower"]) >= 3 and any(
                    (tw == w["word_lower"] or (len(tw) >= 4 and tw in w["word_lower"]))
                    for tw in search_words
                ):
                    candidates.append(w)

        if not candidates:
            return f"I couldn't find '{target}' on screen."

        # Score candidates: prefer alphabetic words, longer words, higher confidence
        # and words that have other target words nearby (same line)
        for c in candidates:
            score = c["conf"]
            if c["word"][0].isalpha():
                score += 50  # Prefer text over numbers
            if len(c["word"]) >= 4:
                score += 30  # Prefer longer words
            # Bonus if other target words are on the same line (within ~same Y)
            nearby = sum(1 for w2 in candidates
                        if w2 is not c and abs(w2["top"] - c["top"]) < 30)
            score += nearby * 20
            c["_score"] = score

        # If positional, sort by position and pick Nth
        if positional is not None:
            candidates.sort(key=lambda w: (w["top"], w["x"]))
            if positional < len(candidates):
                pick = candidates[positional]
            else:
                pick = candidates[0]
        else:
            # Pick best-scored match
            candidates.sort(key=lambda w: w["_score"], reverse=True)
            candidates.sort(key=lambda w: w["conf"], reverse=True)
            pick = candidates[0]

        x, y = pick["x"] // 2, pick["y"] // 2  # macOS Retina halving
        subprocess.run(["cliclick", f"c:{x},{y}"], capture_output=True, timeout=3)
        return f"Clicked on '{pick['word']}'."
    except FileNotFoundError as e:
        return "I need 'tesseract' and 'cliclick' installed."
    except Exception as e:
        return f"Couldn't click: {e}"


def walk_through(command=None):
    """
    Describe what's on screen by grouping OCR words into text lines.
    Returns numbered items the user can click by saying 'click the first/second' etc.
    """
    img_name = "jarvis_walk_ocr.png"
    tmp_dir = "/tmp"
    img_path = os.path.join(tmp_dir, img_name)
    try:
        _screenshot_for_ocr(img_path)
        result = subprocess.run(
            ["tesseract", img_name, "stdout", "-l", "eng", "tsv"],
            capture_output=True, timeout=15, text=True, cwd=tmp_dir
        )
        try: os.unlink(img_path)
        except OSError: pass

        # Parse all words with positions
        words = []
        for line in result.stdout.split("\n")[1:]:
            parts = line.split("\t")
            if len(parts) < 12:
                continue
            try:
                conf = float(parts[10])
                word = parts[11].strip()
                if not word or conf < 50:
                    continue
                left, top, w, h = int(parts[6]), int(parts[7]), int(parts[8]), int(parts[9])
                words.append({"word": word, "conf": conf, "left": left, "top": top,
                              "cx": left + w // 2, "cy": top + h // 2, "h": h})
            except (ValueError, IndexError):
                continue

        if not words:
            return "Nothing readable on screen, sir."

        # Group words into text lines (words within similar Y position)
        words.sort(key=lambda w: (w["top"], w["left"]))
        lines = []
        current_line = [words[0]]
        for w in words[1:]:
            # Same line if Y is within ~1.5x character height of previous word
            if abs(w["top"] - current_line[-1]["top"]) < max(current_line[-1]["h"] * 1.5, 20):
                current_line.append(w)
            else:
                lines.append(current_line)
                current_line = [w]
        lines.append(current_line)

        # Skip top UI chrome (top ~8% of screen)
        max_top = max(w["top"] for w in words)
        min_y = max(120, int(max_top * 0.08))

        # Build readable line strings, filter to content area
        content_lines = []
        for line_words in lines:
            if line_words[0]["top"] < min_y:
                continue
            line_words.sort(key=lambda w: w["left"])
            text = " ".join(w["word"] for w in line_words)
            if len(text) >= 8:  # Skip very short lines (icons, buttons)
                content_lines.append({
                    "text": text,
                    "cx": line_words[len(line_words)//2]["cx"],
                    "cy": line_words[0]["cy"]
                })

        if not content_lines:
            return "Nothing clickable I can recognise on screen, sir."

        # Return top items numbered
        top = content_lines[:6]
        parts = []
        for i, item in enumerate(top):
            parts.append(f"{i+1}. {item['text'][:60]}")

        return (f"I can see {len(content_lines)} items on screen. Here are the top ones:\n"
                + "\n".join(parts)
                + "\nSay 'click the first' or 'click the second' to select one.")
    except FileNotFoundError:
        return "OCR tool tesseract is not installed."
    except Exception as e:
        return f"Couldn't walk the screen: {e}"


def take_screenshot():
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.expanduser(f"~/Desktop/screenshot_{timestamp}.png")
    subprocess.run(["screencapture", path])
    return "Screenshot saved to your Desktop."


def toggle_dark_mode():
    _run_applescript('''
        tell application "System Events"
            tell appearance preferences
                set dark mode to not dark mode
            end tell
        end tell
    ''')
    return "Dark mode toggled."


def toggle_dnd():
    """Toggle Do Not Disturb / Focus mode."""
    _run_applescript('''
        tell application "System Events"
            tell process "ControlCenter"
                click menu bar item "Focus" of menu bar 1
            end tell
        end tell
    ''')
    return "Toggling Focus mode."


def lock_screen():
    subprocess.run(["/System/Library/CoreServices/Menu Extras/User.menu/Contents/Resources/CGSession", "-suspend"])
    return "Locking screen."


def sleep_computer():
    _run_applescript('tell application "System Events" to sleep')
    return "Putting the computer to sleep."


def empty_trash():
    _run_applescript('tell application "Finder" to empty the trash')
    return "Trash emptied."


def battery_status():
    result = subprocess.run(["pmset", "-g", "batt"], capture_output=True, text=True)
    for line in result.stdout.split("\n"):
        if "%" in line:
            parts = line.split("\t")
            if len(parts) > 1:
                return f"Battery: {parts[1].strip()}"
    return "Couldn't determine battery status."


def system_info():
    info = platform.uname()
    return f"Running {info.system} on {info.machine}. Node: {info.node}."


def ip_address():
    try:
        import requests
        resp = requests.get("https://api.ipify.org?format=json", timeout=5)
        public_ip = resp.json()["ip"]
    except Exception:
        public_ip = "unknown"
    local_ip = subprocess.run(["ipconfig", "getifaddr", "en0"], capture_output=True, text=True).stdout.strip()
    return f"Local IP: {local_ip or 'not connected'}. Public IP: {public_ip}."


def wifi_status():
    result = subprocess.run(
        ["/System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/Resources/airport", "-I"],
        capture_output=True, text=True
    )
    for line in result.stdout.split("\n"):
        if "SSID" in line and "BSSID" not in line:
            ssid = line.split(":")[1].strip()
            return f"Connected to Wi-Fi network: {ssid}"
    return "Not connected to Wi-Fi."


# --- Math & Conversions ---

def calculate(command):
    """Evaluate a math expression from natural language."""
    expr = re.sub(r'(what is|what\'s|calculate|compute|solve|how much is)\s*', '', command).strip()
    expr = expr.replace("plus", "+").replace("minus", "-").replace("times", "*")
    expr = expr.replace("multiplied by", "*").replace("divided by", "/")
    expr = expr.replace("x", "*").replace("to the power of", "**").replace("power", "**")
    expr = expr.replace("squared", "**2").replace("cubed", "**3")
    expr = expr.replace("percent of", "*0.01*").replace("mod", "%")
    expr = expr.replace("square root of", "math.sqrt(").replace("sqrt", "math.sqrt(")
    # Clean up
    expr = re.sub(r'[^0-9+\-*/().%\s]', '', expr).strip()
    if not expr:
        return "I couldn't parse the math expression. Try something like 'what is 25 times 4'."
    try:
        result = eval(expr, {"__builtins__": {}, "math": math})
        if isinstance(result, float) and result == int(result):
            result = int(result)
        return f"The answer is {result}."
    except Exception:
        return "I couldn't calculate that. Try phrasing it differently."


def unit_conversion(command):
    """Handle unit conversions."""
    # Temperature
    c_to_f = re.search(r'(\d+\.?\d*)\s*(celsius|c)\s*(to|in)\s*(fahrenheit|f)', command)
    f_to_c = re.search(r'(\d+\.?\d*)\s*(fahrenheit|f)\s*(to|in)\s*(celsius|c)', command)
    km_to_mi = re.search(r'(\d+\.?\d*)\s*(km|kilometer|kilometres?)\s*(to|in)\s*(mi|miles?)', command)
    mi_to_km = re.search(r'(\d+\.?\d*)\s*(mi|miles?)\s*(to|in)\s*(km|kilometer|kilometres?)', command)
    kg_to_lb = re.search(r'(\d+\.?\d*)\s*(kg|kilograms?|kilos?)\s*(to|in)\s*(lb|lbs|pounds?)', command)
    lb_to_kg = re.search(r'(\d+\.?\d*)\s*(lb|lbs|pounds?)\s*(to|in)\s*(kg|kilograms?|kilos?)', command)
    cm_to_in = re.search(r'(\d+\.?\d*)\s*(cm|centimeters?|centimetres?)\s*(to|in)\s*(in|inches)', command)
    in_to_cm = re.search(r'(\d+\.?\d*)\s*(in|inches)\s*(to|in)\s*(cm|centimeters?|centimetres?)', command)

    if c_to_f:
        val = float(c_to_f.group(1))
        return f"{val}°C is {val * 9/5 + 32:.1f}°F."
    elif f_to_c:
        val = float(f_to_c.group(1))
        return f"{val}°F is {(val - 32) * 5/9:.1f}°C."
    elif km_to_mi:
        val = float(km_to_mi.group(1))
        return f"{val} km is {val * 0.621371:.2f} miles."
    elif mi_to_km:
        val = float(mi_to_km.group(1))
        return f"{val} miles is {val * 1.60934:.2f} km."
    elif kg_to_lb:
        val = float(kg_to_lb.group(1))
        return f"{val} kg is {val * 2.20462:.2f} pounds."
    elif lb_to_kg:
        val = float(lb_to_kg.group(1))
        return f"{val} pounds is {val * 0.453592:.2f} kg."
    elif cm_to_in:
        val = float(cm_to_in.group(1))
        return f"{val} cm is {val * 0.393701:.2f} inches."
    elif in_to_cm:
        val = float(in_to_cm.group(1))
        return f"{val} inches is {val * 2.54:.2f} cm."
    return "I can convert temperature, distance, weight, and length. Try '100 celsius to fahrenheit'."


# --- Notes & Lists ---

def take_note(command):
    """Add a note to macOS Notes app."""
    note = re.sub(r'^(take a note|note|write down|jot down|note that|remember that)\s*:?\s*', '', command).strip()
    if note:
        _run_applescript(f'''
            tell application "Notes"
                activate
                make new note at folder "Notes" with properties {{body:"{note}"}}
            end tell
        ''')
        return f"Note saved: {note}"
    return "What would you like me to note down?"


def add_to_list(command):
    """Add item to a simple list file."""
    item = re.sub(r'^(add|put)\s+(.+?)\s+(to|on|in)\s+(my\s+)?(shopping|grocery|to-?do|todo)\s+list', r'\2', command).strip()
    list_type = "shopping" if "shopping" in command or "grocery" in command else "todo"
    list_file = os.path.expanduser(f"~/Documents/jarvis_{list_type}_list.txt")

    with open(list_file, "a") as f:
        f.write(f"- {item}\n")
    return f"Added '{item}' to your {list_type} list."


def read_list(command):
    """Read a list file."""
    list_type = "shopping" if "shopping" in command or "grocery" in command else "todo"
    list_file = os.path.expanduser(f"~/Documents/jarvis_{list_type}_list.txt")
    if os.path.exists(list_file):
        with open(list_file, "r") as f:
            items = f.read().strip()
        if items:
            return f"Your {list_type} list:\n{items}"
    return f"Your {list_type} list is empty."


def clear_list(command):
    list_type = "shopping" if "shopping" in command or "grocery" in command else "todo"
    list_file = os.path.expanduser(f"~/Documents/jarvis_{list_type}_list.txt")
    if os.path.exists(list_file):
        os.remove(list_file)
    return f"Your {list_type} list has been cleared."


# --- Calendar ---

def whats_on_calendar():
    """Read today's calendar events."""
    events = _run_applescript('''
        set today to current date
        set time of today to 0
        set tomorrow to today + (1 * days)
        tell application "Calendar"
            set allEvents to {}
            repeat with aCal in calendars
                set calEvents to (every event of aCal whose start date ≥ today and start date < tomorrow)
                repeat with evt in calEvents
                    set end of allEvents to (summary of evt & " at " & time string of (start date of evt))
                end repeat
            end repeat
            if (count of allEvents) is 0 then
                return "No events today."
            else
                set AppleScript's text item delimiters to ", "
                return allEvents as text
            end if
        end tell
    ''')
    return f"Today's events: {events}" if events else "No events on your calendar today."


def create_calendar_event(command):
    """Open Calendar app to create an event."""
    subprocess.Popen(["open", "-a", "Calendar"])
    return "Opening Calendar. You can create your event there."


# --- Navigation ---

def get_directions(command):
    """Open Apple Maps with directions."""
    dest = re.sub(r'^(get |give me |show )?(directions|navigate|take me)\s+(to|for)\s+', '', command).strip()
    if dest:
        webbrowser.open(f"https://maps.apple.com/?daddr={dest.replace(' ', '+')}")
        return f"Getting directions to {dest}."
    return "Where would you like directions to?"


def show_map(command):
    """Open a location in Maps."""
    location = re.sub(r'^(show|find|where is|locate)\s+', '', command).strip()
    location = re.sub(r'\s+on\s+(the\s+)?map', '', location).strip()
    if location:
        webbrowser.open(f"https://maps.apple.com/?q={location.replace(' ', '+')}")
        return f"Showing {location} on the map."
    return "What location would you like to see?"


# --- Communication ---

def make_facetime_call(command):
    contact = re.sub(r'^(facetime|call|video call)\s+', '', command).strip()
    if contact:
        _run_applescript(f'open location "facetime://{contact}"')
        return f"Starting FaceTime with {contact}."
    return "Who would you like to FaceTime?"


def send_message(command):
    """Open Messages to send a text."""
    subprocess.Popen(["open", "-a", "Messages"])
    return "Opening Messages."


# --- Productivity ---

def open_new_finder_window():
    _run_applescript('tell application "Finder" to make new Finder window')
    return "Opening a new Finder window."


def show_desktop():
    subprocess.run(["osascript", "-e", 'tell application "System Events" to key code 103 using {command down, fn down}'])
    return "Showing desktop."


def show_downloads():
    subprocess.Popen(["open", os.path.expanduser("~/Downloads")])
    return "Opening Downloads folder."


def show_documents():
    subprocess.Popen(["open", os.path.expanduser("~/Documents")])
    return "Opening Documents folder."


# --- Fun ---

def tell_joke():
    jokes = [
        "Why do programmers prefer dark mode? Because light attracts bugs.",
        "There are only 10 types of people: those who understand binary and those who don't.",
        "Why was the JavaScript developer sad? Because he didn't Node how to Express himself.",
        "A SQL query walks into a bar, sees two tables, and asks: Can I join you?",
        "Why do Java developers wear glasses? Because they can't C sharp.",
        "What's a programmer's favorite hangout place? Foo Bar.",
        "I told my wife she was drawing her eyebrows too high. She looked surprised.",
        "Parallel lines have so much in common. It's a shame they'll never meet.",
        "I'm reading a book about anti-gravity. It's impossible to put down.",
        "Did you hear about the mathematician who's afraid of negative numbers? He'll stop at nothing to avoid them.",
    ]
    return random.choice(jokes)


def flip_coin():
    return f"It's {'heads' if random.random() > 0.5 else 'tails'}!"


def roll_dice(command):
    sides = 6
    m = re.search(r'd(\d+)', command)
    if m:
        sides = int(m.group(1))
    return f"You rolled a {random.randint(1, sides)}!"


def tell_fact():
    facts = [
        "Honey never spoils. Archaeologists have found 3000-year-old honey that was still edible.",
        "A group of flamingos is called a 'flamboyance'.",
        "Octopuses have three hearts and blue blood.",
        "Bananas are berries, but strawberries aren't.",
        "The shortest war in history lasted 38 to 45 minutes, between Britain and Zanzibar.",
        "A day on Venus is longer than a year on Venus.",
        "The inventor of the Pringles can is buried in one.",
    ]
    return random.choice(facts)


# --- Voice Management ---

def _get_english_voices():
    """Get list of English voices using macOS say command."""
    result = subprocess.run(["say", "-v", "?"], capture_output=True, text=True)
    voices = []
    for line in result.stdout.strip().split("\n"):
        match = re.match(r'^(.+?)\s{2,}(\S+)\s+#', line)
        if match:
            name = match.group(1).strip()
            lang = match.group(2).strip()
            if lang.startswith("en") or "speech.synthesis" in line.lower():
                voices.append({"name": name, "id": name})
    return voices


def list_voices(command=None):
    """List available voice options."""
    voices = _get_english_voices()
    names = [v["name"] for v in voices]
    voice_list = ", ".join(names[:15])
    extra = f" and {len(names) - 15} more" if len(names) > 15 else ""
    return f"Available voices: {voice_list}{extra}. Say 'change voice to' followed by the name. Or try voice profiles like 'switch to zoro profile'."


def list_profiles(command=None):
    """List available voice profiles."""
    from jarvis import SpeechEngine
    profiles = SpeechEngine.VOICE_PROFILES
    parts = []
    for name, p in profiles.items():
        parts.append(f"{name}: {p['description']}")
    return "Voice profiles: " + ". ".join(parts) + ". Say 'switch to zoro profile' to activate."


def change_voice(command):
    """Change the voice. Returns voice_id to be applied by the engine."""
    target = re.sub(r'(change|switch|set)\s+(my\s+|the\s+)?voice\s+(to|as)\s+', '', command).strip()
    if not target:
        return list_voices()

    voices = _get_english_voices()
    for v in voices:
        if target.lower() in v["name"].lower():
            config.set_key("voice_id", v["id"])
            return f"__VOICE_CHANGE__{v['id']}__Voice changed to {v['name']}."

    return f"I couldn't find a voice named '{target}'. Say 'list voices' to see options."


def change_profile(command):
    """Switch to a voice profile (zoro, zoro_light, zoro_heavy, default)."""
    target = re.sub(r'(switch|change|set|activate)\s+(to\s+)?(the\s+)?', '', command)
    target = re.sub(r'\s*(profile|mode|voice profile).*', '', target).strip().lower()
    target = target.replace(" ", "_")

    from jarvis import SpeechEngine
    profiles = SpeechEngine.VOICE_PROFILES

    # Exact match first
    if target in profiles:
        return f"__PROFILE_CHANGE__{target}__{profiles[target]['description']}. Profile activated."

    # Fuzzy match — prefer longer (more specific) matches
    matches = [(name, profiles[name]) for name in profiles if target in name or name in target]
    if matches:
        # Sort by name length descending so "zoro_heavy" beats "zoro"
        matches.sort(key=lambda x: len(x[0]), reverse=True)
        best_name, best_profile = matches[0]
        return f"__PROFILE_CHANGE__{best_name}__{best_profile['description']}. Profile activated."

    available = ", ".join(profiles.keys())
    return f"Available profiles: {available}. Say 'switch to zoro profile'."


def change_speed(command):
    """Change speech rate."""
    m = re.search(r'(\d+)', command)
    if m:
        rate = max(100, min(300, int(m.group(1))))
        config.set_key("voice_rate", rate)
        return f"__SPEED_CHANGE__{rate}__Speech rate set to {rate}."

    if "faster" in command or "fast" in command:
        rate = min(300, config.get("voice_rate") + 25)
        config.set_key("voice_rate", rate)
        return f"__SPEED_CHANGE__{rate}__Speaking faster now."
    elif "slower" in command or "slow" in command:
        rate = max(100, config.get("voice_rate") - 25)
        config.set_key("voice_rate", rate)
        return f"__SPEED_CHANGE__{rate}__Speaking slower now."

    return "Say 'speak faster', 'speak slower', or 'set speed to 200'."


# --- Identity ---

def which_brain():
    """Tell the user which AI backend and model Jarvis is currently using."""
    backend = brain.active_backend_name()   # e.g. "ollama/mistral:7b..."
    return f"Running on {backend}. Modular architecture with tool use, memory, and planning."


def who_are_you():
    return f"I am Jarvis, your personal assistant. Built to serve you, {OWNER_NAME}."


def how_are_you():
    return "All systems operational. Running at full capacity!"


def thank_you():
    responses = [
        f"You're welcome, {OWNER_NAME}!",
        "Happy to help!",
        "Anytime!",
        f"At your service, {OWNER_NAME}.",
    ]
    return random.choice(responses)


def help_commands():
    return (
        "Here's what I can do: "
        "Tell time and date. Set timers, alarms and reminders. "
        "Check the weather or news. "
        "Open or close any app. Search Google or YouTube. Open websites. "
        "Compose emails. Control music playback. "
        "Adjust volume and brightness. Take screenshots. Toggle dark mode. "
        "Do math and unit conversions. Take notes. Manage lists. "
        "Check your calendar. Get directions. "
        "Check battery, Wi-Fi, IP address, and system info. "
        "Lock screen. Toggle focus mode. Empty trash. "
        "Tell jokes and fun facts. Flip a coin or roll dice. "
        "Change my voice: say 'list voices' or 'change voice to Daniel'. "
        "Speak faster or slower: say 'speak faster' or 'set speed to 200'. "
        "Or just ask me anything — I'm connected to Claude AI for general questions!"
    )


def _enter_note_mode():
    """Switch to note-taking mode."""
    _ctx.mode = "taking_notes"
    _ctx.note_buffer = []
    _ctx.last_action = "note"
    return f"Note-taking mode on. Dictate your notes — say 'done' to save."


def _track(result, action, command):
    """Record last action/subject in context and pass result through."""
    if result:
        # Extract subject from command (rough heuristic — after action verb)
        subject = re.sub(
            r'.*(timer|alarm|reminder|note|open|search|play)\s+(for\s+|a\s+)?', '', command
        ).strip(" .,?")[:40] or command[:40]
        _ctx.last_action  = action
        _ctx.last_subject = subject
    return result


# ─── Natural Language Router ─────────────────────────────────────────────────

# Each entry: (list of trigger patterns, handler)
# Patterns are checked in order; first match wins.
# Use lambda for handlers that need the command text.

COMMAND_TABLE = [
    # --- Exit ---
    (["goodbye", "bye", "quit", "exit", "shut down", "shutdown", "go to sleep"], None),

    # --- Time & Date ---
    (["what time", "current time", "tell me the time", "what's the time"], lambda c: tell_time()),
    (["what date", "today's date", "what day is it", "what day is today", "tell me the date", "what's the date", "what is today"], lambda c: tell_date()),
    (["what day"], lambda c: tell_day()),

    # --- Timer / Alarm / Reminder ---
    (["set a timer", "set timer", "start a timer", "timer for"], lambda c: _track(set_timer(c), "timer", c)),
    (["set an alarm", "set alarm", "wake me up", "alarm for"], lambda c: _track(set_alarm(c), "alarm", c)),
    (["remind me", "set a reminder", "set reminder", "reminder to", "create a reminder"], lambda c: _track(set_reminder(c), "reminder", c)),

    # --- Weather ---
    (["weather", "temperature outside", "how hot", "how cold", "is it raining"], lambda c: get_weather(c)),
    (["forecast"], lambda c: get_forecast(c)),

    # --- News ---
    (["news", "headlines", "what's happening in the world"], lambda c: get_news()),

    # --- Finance Mode (Indian stocks) ---
    # Specific triggers FIRST (analysis before quote, portfolio actions before view)
    (["analyse ", "analyze ", "analysis of", "should i buy", "should i sell",
      "technical analysis"], lambda c: _finance("analyze_stock", c)),
    (["add ", "buy "], lambda c: _finance("portfolio_add", c)
        if re.search(r'\b(portfolio|holdings?)\b', c.lower()) else None),
    (["remove ", "delete ", "sell "], lambda c: _finance("portfolio_remove", c)
        if re.search(r'\b(portfolio|holdings?)\b', c.lower()) else None),
    (["portfolio value", "portfolio worth", "my portfolio worth",
      "value of my portfolio", "how is my portfolio", "how's my portfolio",
      "portfolio performance"], lambda c: _finance("portfolio_value", c)),
    (["my portfolio", "show portfolio", "my holdings", "my stocks",
      "my investments"], lambda c: _finance("portfolio_view", c)),
    (["market summary", "how is the market", "how's the market",
      "market today", "nifty", "sensex", "bank nifty"], lambda c: _finance("market_summary", c)),
    (["top gainers", "top losers", "market movers", "biggest gainers",
      "biggest losers"], lambda c: _finance("top_movers", c)),
    (["stock price", "share price", "price of", "stock quote",
      "how is the stock", "what's the stock"], lambda c: _finance("stock_quote", c)),
    (["finance briefing", "financial briefing", "finance mode",
      "money briefing", "market briefing"], lambda c: _finance("daily_briefing", c)),
    (["sip calculator", "sip of", "calculate sip", "mutual fund sip"],
        lambda c: _finance("sip_calculator", c)),

    # --- Proactive announcements toggle ---
    (["disable announcements", "stop announcements", "turn off announcements",
      "disable alerts", "stop alerting", "quiet mode"],
        lambda c: _toggle_announcements(False)),
    (["enable announcements", "start announcements", "turn on announcements",
      "enable alerts"],
        lambda c: _toggle_announcements(True)),

    # --- Music & Media ---
    (["what song", "what's playing", "what is playing", "currently playing", "now playing"], lambda c: music_what_playing()),
    (["next track", "next song", "skip song", "skip track"], lambda c: music_next()),
    (["previous track", "previous song", "go back a song", "last song", "last track"], lambda c: music_previous()),
    (["pause music", "pause the music", "stop music", "stop the music"], lambda c: music_pause()),
    (["play music", "play the music", "resume music", "resume the music", "start music"], lambda c: music_play()),
    (["play on spotify", "spotify play", "play spotify"], lambda c: spotify_play(c)),
    (["play on youtube", "youtube play", "play youtube"], lambda c: search_youtube(c)),
    # "play X on/in youtube" — catches "play funny video on youtube" etc.
    (["play "], lambda c: search_youtube(c) if re.search(r'\b(on|in|from)\s+youtube\b', c.lower()) else None),

    # --- Volume ---
    (["volume up", "louder", "increase volume", "turn it up", "raise volume"], lambda c: volume_up()),
    (["volume down", "quieter", "decrease volume", "turn it down", "lower volume"], lambda c: volume_down()),
    (["mute", "silence", "shut up"], lambda c: mute_volume()),
    (["unmute"], lambda c: unmute_volume()),
    (["set volume", "volume to", "volume at"], lambda c: set_volume(c)),

    # --- Brightness ---
    (["brightness"], lambda c: set_brightness(c)),

    # --- Screen Reading & Click Automation ---
    (["read screen", "read the screen", "what's on screen", "what's on the screen",
      "what do you see", "what can you see", "what is on my screen",
      "describe screen", "describe the screen"], lambda c: read_screen(c)),
    # --- Autonomous screen agent (multi-step: see → decide → click → repeat) ---
    (["find and ", "browse and ", "search and click", "search and play",
      "find me and play", "look for and", "agent mode", "do it yourself",
      "figure out and", "navigate the screen"],
        lambda c: _screen_agent(c)),

    (["walk through", "walk me through", "run through", "run me through",
      "go through", "go over"], lambda c: walk_through(c)),
    (["click ", "tap ", "press the ", "select the ", "hit the "], lambda c: click_text_on_screen(c)),
    # "open the first video", "play the X video", "open the X link on screen" — route to click
    (["open the first", "open first", "play the first", "click the first",
      "open the video", "play the video"], lambda c: click_text_on_screen(c)),

    # --- Screen Control / Navigation ---
    (["full screen", "fullscreen", "make it full screen", "go full screen",
      "enter full screen", "exit full screen", "toggle full screen",
      "maximize", "maximize the window", "make it bigger"], lambda c: toggle_fullscreen(c)),
    (["scroll down", "page down", "go down"], lambda c: scroll_down(c)),
    (["scroll up", "page up", "go up"], lambda c: scroll_up(c)),
    (["go back", "go back a page", "previous page", "press back",
      "press back button", "hit back", "back button", "back page",
      "going back", "take me back", "press the back"], lambda c: go_back(c)),
    (["refresh", "reload", "refresh the page", "reload the page"], lambda c: refresh_page(c)),
    (["press enter", "hit enter", "press return"], lambda c: press_enter(c)),
    (["press escape", "hit escape", "escape", "close this", "dismiss"], lambda c: press_escape(c)),
    (["pause video", "pause the video", "resume video", "play pause",
      "press space", "hit space"], lambda c: press_space(c)),
    (["type ", "enter text", "input "], lambda c: type_text(c)),

    # --- System ---
    (["screenshot", "screen shot", "capture screen", "take a screenshot"], lambda c: take_screenshot()),
    (["dark mode", "toggle dark mode", "switch to dark", "switch to light"], lambda c: toggle_dark_mode()),
    (["do not disturb", "focus mode", "turn on focus", "turn off focus"], lambda c: toggle_dnd()),
    (["lock screen", "lock my computer", "lock the screen", "lock my mac"], lambda c: lock_screen()),
    (["go to sleep", "sleep mode", "put computer to sleep"], lambda c: sleep_computer()),
    (["empty trash", "empty the trash", "clear trash"], lambda c: empty_trash()),
    (["battery", "battery status", "how much battery", "charge level", "battery level"], lambda c: battery_status()),
    (["system info", "system information", "about this mac", "what system"], lambda c: system_info()),
    (["ip address", "my ip", "what's my ip", "what is my ip"], lambda c: ip_address()),
    (["wifi", "wi-fi", "network", "what network", "am i connected"], lambda c: wifi_status()),

    # --- Web & Search ---
    # YouTube search MUST be before generic search — catches "search for X in/on youtube"
    (["search youtube", "search on youtube", "search in youtube",
      "find on youtube", "find in youtube", "look up on youtube",
      "youtube search"], lambda c: search_youtube(c)),
    (["search for", "search ", "google ", "look up "], lambda c: _route_search(c)),
    (["go to ", "navigate to ", "open website", "visit "], lambda c: open_website(c)),

    # --- Email ---
    (["compose email", "write email", "new email", "send email", "write a mail", "send a mail", "compose a mail"], lambda c: compose_email(c)),
    (["check email", "check my email", "open email", "open mail", "read email", "read my email"], lambda c: check_email()),

    # --- Video/Player control (must be BEFORE generic "close" trigger) ---
    (["close the video", "close video", "close the player", "close player",
      "stop the video", "stop video", "exit the video", "exit video",
      "go back to", "go back from"], lambda c: go_back(c)),

    # --- Apps (broader triggers catch "can you open X", "please open the X") ---
    (["close ", "quit ", "kill ", "shut down "], lambda c: close_application(c)),
    (["open ", "launch ", "start ", "run ", "fire up ", "pull up "], lambda c: open_application(c)),

    # --- Calendar ---
    (["what's on my calendar", "what is on my calendar", "my calendar",
      "calendar for today", "today's calendar", "my schedule", "today's schedule",
      "what's my schedule", "what is my schedule", "my events today",
      "any events today", "my events", "any meetings", "calendar events",
      "what do i have today", "what do i have on", "anything on my calendar",
      "check my calendar", "show my calendar"], lambda c: whats_on_calendar()),
    (["create event", "new event", "add event", "schedule a meeting"], lambda c: create_calendar_event(c)),

    # --- Notes & Lists ---
    (["start taking notes", "take notes", "note taking mode", "begin notes",
      "i want to take notes", "let's take notes", "open notes mode"],
     lambda c: _enter_note_mode()),
    (["take a note", "note that", "write down", "jot down", "save a note"], lambda c: _track(take_note(c), "note", c)),
    (["add to", "put on"], lambda c: add_to_list(c) if ("list" in c) else None),
    (["shopping list", "grocery list", "todo list", "to-do list", "read my list", "show my list", "what's on my list"], lambda c: read_list(c)),
    (["clear my list", "clear the list", "empty list", "delete list"], lambda c: clear_list(c)),

    # --- Navigation ---
    (["directions to", "navigate to", "take me to", "how do i get to"], lambda c: get_directions(c)),
    (["show me", "where is", "find on map", "locate"], lambda c: show_map(c) if ("map" in c or "where" in c) else None),

    # --- Communication ---
    (["facetime", "video call"], lambda c: make_facetime_call(c)),
    (["send a message", "send message", "text ", "open messages", "imessage"], lambda c: send_message(c)),

    # --- Files ---
    (["show desktop", "go to desktop"], lambda c: show_desktop()),
    (["downloads", "open downloads", "show downloads"], lambda c: show_downloads()),
    (["documents", "open documents", "show documents"], lambda c: show_documents()),
    (["new finder", "new window", "open finder"], lambda c: open_new_finder_window()),

    # --- Math & Conversions ---
    (["convert ", "celsius", "fahrenheit", "kilometers", "miles", "pounds to", "kg to", "inches to", "cm to"], lambda c: unit_conversion(c)),
    (["calculate", "compute", "how much is", "solve"], lambda c: calculate(c)),
    # "what is X" only if it looks like a math expression (standalone number, not a word like "qwen3")
    (["what is ", "what's "], lambda c: calculate(c) if re.search(r'(?<!\w)\d+(?!\w)', c) else None),

    # --- Fun ---
    (["tell me a joke", "joke", "make me laugh", "say something funny"], lambda c: tell_joke()),
    (["flip a coin", "coin flip", "heads or tails"], lambda c: flip_coin()),
    (["roll a dice", "roll dice", "roll a die", "roll the dice"], lambda c: roll_dice(c)),
    (["tell me a fact", "random fact", "fun fact", "interesting fact"], lambda c: tell_fact()),

    # --- Voice Settings ---
    (["list voices", "available voices", "voice options", "what voices", "show voices"], lambda c: list_voices(c)),
    (["list profiles", "voice profiles", "available profiles", "show profiles"], lambda c: list_profiles(c)),
    (["switch to zoro", "zoro profile", "zoro mode", "zoro voice", "switch to default", "default profile", "default voice"], lambda c: change_profile(c)),
    (["change profile", "switch profile", "activate profile", "set profile"], lambda c: change_profile(c)),
    (["change voice", "switch voice", "set voice"], lambda c: change_voice(c)),
    (["speak faster", "talk faster", "speed up", "speak slower", "talk slower", "slow down", "set speed"], lambda c: change_speed(c)),

    # --- Identity & Conversation ---
    (["who are you", "what is your name", "what's your name", "introduce yourself"], lambda c: who_are_you()),
    (["which model", "what model", "which brain", "what brain", "which ai", "what ai",
      "which agent", "what agent", "which engine", "what are you running on",
      "what are you powered by", "which llm", "what llm", "are you using ollama",
      "are you using groq", "are you using gemini", "are you using claude",
      "which backend", "what backend"], lambda c: which_brain()),
    (["how are you", "how you doing", "how do you feel"], lambda c: how_are_you()),
    (["thank you", "thanks", "thank", "good job", "well done", "nice work"], lambda c: thank_you()),
    (["help", "what can you do", "what are your commands", "what do you do"], lambda c: help_commands()),
]


def process_command(command, source="local"):
    """
    Route a voice command to the appropriate handler.
    Maintains conversational context across turns.
    Returns (response_text, should_continue).

    Args:
        command: The text command to process.
        source: "local" (mic) or "api" (remote client).
    """
    global _claude_history, _ctx

    if not command:
        return None, True

    raw = command  # Keep original for context logging
    command = _normalize_command(command.lower().strip())

    # Strip wake-word variants from the start of the command so that
    # "hey jarvis run through youtube" doesn't mis-route to open_application
    _WAKE_PREFIXES = (
        "hey jarvis ", "jarvis ", "ok jarvis ", "yo jarvis ",
        "hey javis ", "javis ", "hey jervis ", "jervis ",
    )
    for wp in _WAKE_PREFIXES:
        if command.startswith(wp):
            command = command[len(wp):].strip()
            break

    # ── Note-taking mode ─────────────────────────────────────────────────────
    # If we're mid-dictation, accumulate content until a "done" signal.
    if _ctx.mode == "taking_notes":
        done_words = ("done", "that's it", "stop notes", "finish", "save notes",
                      "save it", "save that", "end notes", "stop taking notes")
        if any(d in command for d in done_words):
            note_text = ". ".join(_ctx.note_buffer)
            _ctx.clear_mode()
            if note_text:
                result = take_note(f"note that {note_text}")
                reply = f"Saved. Note reads: {note_text[:80]}{'...' if len(note_text)>80 else ''}."
            else:
                reply = "Nothing to save — note buffer was empty."
            _ctx.record(raw, reply, action="note", subject=note_text[:40])
            return reply, True
        else:
            # Accumulate this line
            line = command.strip(" .,")
            if line:
                _ctx.note_buffer.append(line)
            reply = f"Got it — {len(_ctx.note_buffer)} line{'s' if len(_ctx.note_buffer)>1 else ''} so far. Keep going or say 'done'."
            _ctx.record(raw, reply)
            return reply, True

    # ── Pronoun / reference resolution ──────────────────────────────────────
    command = _ctx.resolve_pronouns(command)

    # ── Multi-step instructions ──────────────────────────────────────────────
    if _looks_like_multistep(command):
        parts = _split_steps(command)
        if len(parts) > 1:
            replies = []
            for step in parts:
                reply, keep = _run_single(step)
                if reply:
                    replies.append(reply)
                if not keep:
                    combined = " Then, ".join(replies)
                    _ctx.record(raw, combined)
                    return combined, False
            combined = " Then, ".join(replies) if replies else None
            if combined:
                _ctx.record(raw, combined)
            return combined, True

    reply, keep = _run_single(command)
    if reply:
        _ctx.record(raw, reply)
        _save_memory()
    return reply, keep


# Action verbs that indicate a real command worth splitting on
_ACTION_VERBS = (
    "open", "launch", "start", "close", "quit", "play", "pause", "stop",
    "search", "google", "find", "set", "remind", "click", "tap", "press",
    "read", "show", "take", "send", "write", "compose", "mute", "unmute",
    "lock", "sleep", "turn", "increase", "decrease", "switch", "go to", "visit",
)


def _looks_like_multistep(cmd):
    """True if command contains a step separator AND multiple action verbs."""
    if not re.search(r'\b(and then|then|after that)\b|;', cmd):
        return False
    # Count total occurrences across all verbs (same verb used twice still counts twice)
    verb_hits = sum(len(re.findall(rf'\b{v}\b', cmd)) for v in _ACTION_VERBS)
    return verb_hits >= 2


def _split_steps(cmd):
    """Split a command like 'open safari and then play jazz' into ordered steps."""
    # Normalize separators to a single delimiter
    s = re.sub(r'\s+(and then|then|after that)\s+', ' ||| ', cmd)
    s = s.replace(';', ' ||| ')
    parts = [p.strip(" ,.") for p in s.split('|||') if p.strip(" ,.")]
    return parts


def _screen_agent(command):
    """Run the autonomous screen agent for a multi-step browser goal."""
    goal = command.lower()
    # Strip the trigger phrasing — the agent wants the bare goal
    for prefix in ("agent mode", "do it yourself", "navigate the screen and",
                   "navigate the screen"):
        goal = goal.replace(prefix, " ")
    goal = re.sub(r'\s+', ' ', goal).strip(" .,")
    if not goal:
        return "What should I do on screen, sir?"
    try:
        from screen_agent import run_goal
        return run_goal(goal)
    except Exception as e:
        print(f"  [Screen agent error: {e}]", flush=True)
        return "The screen agent hit an error, sir."


def _toggle_announcements(enabled):
    config.set_key("proactive_events", enabled)
    if enabled:
        return "Proactive announcements enabled — I'll speak up when something needs attention."
    return "Going quiet, sir. I'll only alert you on critical battery."


def _finance(func_name, command):
    """Lazy dispatcher for finance agent — keeps yfinance import off the startup path."""
    try:
        import finance
        handler = getattr(finance, func_name)
        return handler(command)
    except ImportError:
        return "Finance mode needs the yfinance package. Run: pip3 install yfinance."
    except Exception as e:
        print(f"  [Finance error: {e}]", flush=True)
        return "The finance module hit an error — market data may be unavailable."


def _run_single(command):
    """Run a single (already normalized) command through the command table."""
    global _claude_history

    for triggers, handler in COMMAND_TABLE:
        for trigger in triggers:
            # Exit triggers: keyword must be at the VERY START of the command.
            # "playing goodbye song" or "open youtube" must NOT trigger exit.
            if handler is None:
                if re.match(r'^' + re.escape(trigger) + r'\b', command):
                    return f"Goodbye, {OWNER_NAME}. Have a great day!", False
                continue
            if trigger in command or command.startswith(trigger):
                result = handler(command)
                if result:
                    return result, True
                break

    # Smart offline fallback — greetings, thanks, identity (no LLM needed)
    offline = _smart_offline_reply(command)
    if offline:
        _save_memory()
        return offline, True

    # Context-aware follow-up (cancel it, add that to notes, etc.)
    ctx_reply = _ctx_followup(command)
    if ctx_reply:
        _save_memory()
        return ctx_reply, True

    # Screen-aware answer — if user is asking about visible content
    if _looks_like_screen_query(command):
        screen_reply = _answer_with_screen(command)
        if screen_reply:
            _ctx.record(command, screen_reply)
            _save_memory()
            return screen_reply, True

    # Internet search — factual questions (Wikipedia + DuckDuckGo)
    if _is_web_searchable(command):
        web_reply = internet_search(command)
        if web_reply:
            _ctx.record(command, web_reply)
            _save_memory()
            return web_reply, True

    # Conversational brain — qwen3 with full conversation history
    # Only for genuine conversation/questions, not action requests
    if brain.is_configured() and not _looks_like_action_request(command):
        # Build history in brain format, seeded with persistent memory
        brain_history = [
            {"role": ("user" if i % 2 == 0 else "assistant"), "content": text}
            for pair in _ctx.history
            for i, text in enumerate(pair)
        ]
        reply, _ = brain.ask(command, brain_history)
        if reply:
            _ctx.record(command, reply)
            _save_memory()
            print(f"  [Brain: conversational]", flush=True)
            return reply, True

    # Nothing worked — log for future trigger additions
    _log_missed_command(command)
    return "I'm not sure about that — logged it for later.", True


MISSED_LOG = os.path.expanduser("~/Jarvis/logs/missed_commands.log")


# Phrases that are clearly information questions worth searching the web
_WEB_QUESTION_STARTERS = (
    "what is", "what are", "what was", "what were", "what does",
    "who is", "who was", "who are", "who invented", "who created",
    "when is", "when was", "when did", "when will",
    "where is", "where was", "where are",
    "how does", "how do", "how did", "how much", "how many", "how tall", "how far",
    "why is", "why does", "why did", "why are",
    "which is", "which are",
    "capital of", "population of", "latest ", "newest ", "best ",
    "price of", "cost of", "distance from", "history of", "definition of",
    "tell me about", "explain ", "describe ",
    "news about", "update on", "current status of",
    "is there ", "are there any",           # only if followed by a factual noun
)

# Conversational starters that should NOT trigger web search
_CONVERSATIONAL_STARTERS = (
    "do you ", "can you ", "will you ", "could you ",
    "are you ", "have you ", "did you ",
    "i want", "i need", "i would", "i think",
    "help me", "show me how",
)


def _is_web_searchable(command):
    """
    True only for clear information-seeking questions.
    Keeps conversational phrases out of the web search pipeline.
    """
    c = command.lower().strip()
    if any(c.startswith(s) for s in _CONVERSATIONAL_STARTERS):
        return False
    if any(c.startswith(s) for s in _WEB_QUESTION_STARTERS):
        return True
    # Bare noun phrases like "offline models better than qwen3" — allow if >4 words
    word_count = len(c.split())
    return word_count >= 4 and "?" in command


def _log_missed_command(command):
    """Append unrecognised commands to a log file for later review."""
    try:
        os.makedirs(os.path.dirname(MISSED_LOG), exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(MISSED_LOG, "a") as f:
            f.write(f"[{ts}] {command}\n")
        print(f"  [Missed command logged: {command}]", flush=True)
    except Exception as e:
        print(f"  [Log error: {e}]", flush=True)


_SPAM_DOMAINS = ("forum", "community", "AT&T", "reddit.com/r/", "quora",
                 "yahoo answers", "answers.com", "thefreedictionary", "cbsnews")
_SPAM_BODIES  = ("sign in", "log in", "subscribe", "cookies", "404", "page not found")

# Keywords that suggest Wikipedia will have a clean answer
_WIKI_TRIGGERS = ("who is", "what is", "who was", "what was", "define", "meaning of",
                  "capital of", "population of", "when was", "how old is", "how tall is",
                  "inventor of", "founded", "born in", "history of", "prime minister",
                  "president of", "ceo of", "speed of", "distance from")


def _wikipedia_search(query):
    """Hit Wikipedia's free summary API — no key needed, very clean answers."""
    try:
        import requests
        q = query.lower().strip(" ?.")

        # ── Special patterns ────────────────────────────────────────────────
        # "capital of X" → fetch Wikipedia's article on that country directly
        m = re.search(r'capital\s+of\s+(.+)', q)
        if m:
            country = m.group(1).strip().title()
            # Direct Wikipedia summary for the country — always mentions the capital
            r = requests.get(
                f"https://en.wikipedia.org/api/rest_v1/page/summary/{country.replace(' ','_')}",
                timeout=6, headers={"User-Agent": "Jarvis/1.0"})
            if r.status_code == 200:
                extract = r.json().get("extract", "")
                # Look for the sentence that names the capital
                for sent in re.split(r'(?<=[.!?])\s', extract):
                    if "capital" in sent.lower() and len(sent) >= 20:
                        return sent[:350]
                # Fallback: first sentence of the article
                first = re.split(r'(?<=[.!?])\s', extract)[0]
                if len(first) >= 20:
                    return first[:350]
            # Also try "Capital of {country}" article
            r2 = requests.get(
                f"https://en.wikipedia.org/api/rest_v1/page/summary/Capital_of_{country.replace(' ','_')}",
                timeout=6, headers={"User-Agent": "Jarvis/1.0"})
            if r2.status_code == 200:
                extract = r2.json().get("extract", "")
                first = re.split(r'(?<=[.!?])\s', extract)[0]
                if len(first) >= 20:
                    return first[:350]

        # "pm/prime minister of X" → look up "Prime_minister_of_X"
        m = re.search(r'(prime\s*minister|president|king|queen|ruler|leader|ceo)\s+of\s+(.+)', q)
        if m:
            role    = m.group(1).replace(' ', '_').title()
            country = m.group(2).strip().title()
            term    = f"{role}_of_{country}"
            r = requests.get(
                f"https://en.wikipedia.org/api/rest_v1/page/summary/{term.replace(' ','_')}",
                timeout=6, headers={"User-Agent": "Jarvis/1.0"}
            )
            if r.status_code == 200:
                extract = r.json().get("extract", "")
                if extract and len(extract) > 20:
                    return re.split(r'(?<=[.!?])\s', extract)[0][:400]

        # ── Generic extraction ───────────────────────────────────────────────
        term = q
        term = re.sub(
            r'^(who|what|when|where|how|tell me about|define|meaning of|'
            r'capital of|population of|history of)\s+(is|are|was|were|the|a|an)?\s*',
            '', term
        )
        term = re.sub(r'\b(current|currently|latest|now|today|recent|2024|2025|2026)\b', '', term)
        term = re.sub(r'\s+', ' ', term).strip(" ?.")
        if not term:
            return None

        # Title-case for Wikipedia (e.g. "speed of light" → "Speed_of_light")
        term_wiki = term[0].upper() + term[1:]

        # Try direct lookup first, then Wikipedia search API as fallback
        url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{term_wiki.replace(' ', '_')}"
        r = requests.get(url, timeout=6, headers={"User-Agent": "Jarvis/1.0"})
        if r.status_code == 200:
            data = r.json()
            extract = data.get("extract", "")
            if extract:
                first = re.split(r'(?<=[.!?])\s', extract)[0]
                return first[:400] if len(first) >= 20 else extract[:400]

        # Fallback: Wikipedia opensearch → pick top result → fetch its summary
        search_url = "https://en.wikipedia.org/w/api.php"
        sr = requests.get(search_url, timeout=6, params={
            "action": "opensearch", "search": term, "limit": 1, "format": "json"
        }, headers={"User-Agent": "Jarvis/1.0"})
        if sr.status_code == 200:
            data = sr.json()
            if data[1]:  # data[1] is list of titles
                top_title = data[1][0]
                r2 = requests.get(
                    f"https://en.wikipedia.org/api/rest_v1/page/summary/{top_title.replace(' ', '_')}",
                    timeout=6, headers={"User-Agent": "Jarvis/1.0"}
                )
                if r2.status_code == 200:
                    extract = r2.json().get("extract", "")
                    if extract:
                        first = re.split(r'(?<=[.!?])\s', extract)[0]
                        return first[:400] if len(first) >= 20 else extract[:400]
        return None
    except Exception:
        return None


def internet_search(query):
    """
    Search DuckDuckGo (free, no API key) and return the best snippet.
    Retries once on network errors. Filters junk/forum results.
    """
    try:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS

        print(f"  [Web search: {query}]", flush=True)

        # Wikipedia first — clean and reliable for factual questions
        q_lower = query.lower()
        if any(t in q_lower for t in _WIKI_TRIGGERS):
            wiki = _wikipedia_search(query)
            if wiki:
                print(f"  [Web answer: Wikipedia]", flush=True)
                return wiki

        results = []
        for attempt in range(2):          # retry once on failure
            try:
                with DDGS() as ddgs:
                    results = list(ddgs.text(query, max_results=6))
                if results:
                    break
            except Exception as e:
                if attempt == 1:
                    raise
                print(f"  [Web search retry after: {e}]", flush=True)

        if not results:
            return None

        # Filter out junk: short bodies, spam sites, login pages
        def _score(r):
            body = r.get("body", "")
            title = r.get("title", "")
            if len(body) < 40:
                return 0
            if any(s.lower() in title.lower() for s in _SPAM_DOMAINS):
                return 0
            if any(s.lower() in body.lower() for s in _SPAM_BODIES):
                return 0
            return len(body)

        ranked = sorted(results, key=_score, reverse=True)
        best = ranked[0]
        if _score(best) == 0:
            return None

        body  = best.get("body", "").strip()
        title = best.get("title", "").strip()

        # ── Relevance check — answer must share keywords with the query ──────
        query_keywords = set(re.findall(r'\b[a-z]{4,}\b', query.lower())) - {
            "what", "when", "where", "which", "there", "that", "this",
            "have", "does", "will", "your", "their", "about", "from",
            "with", "been", "were", "they", "some", "also", "into"
        }
        answer_text = (body + " " + title).lower()
        matches = sum(1 for kw in query_keywords if kw in answer_text)
        if query_keywords and matches == 0:
            # Zero keyword overlap — definitely unrelated result, skip
            print(f"  [Web: relevance=0/{len(query_keywords)}, skipping]", flush=True)
            return None
        # ─────────────────────────────────────────────────────────────────────

        # Strip leading date stamps like "Apr 6, 2026 · "
        body = re.sub(r'^[A-Z][a-z]{2}\s+\d+,\s+\d{4}\s*[·•]\s*', '', body).strip()
        body = re.sub(r'\s*\.\.\.$', '', body).strip()

        sentences = re.split(r'(?<=[.!?])\s+', body)
        first = next((s for s in sentences if len(s) >= 30), None)
        answer = (first or body)[:400] or title

        print(f"  [Web answer: {best.get('href','')[:60]}]", flush=True)
        return answer

    except Exception as e:
        print(f"  [Web search error: {e}]", flush=True)
        return None


_ACTION_REQUEST_VERBS = (
    "open", "launch", "start", "close", "quit", "play", "pause", "stop",
    "search", "find", "set", "create", "remind", "timer", "alarm",
    "screenshot", "volume", "brightness", "mute", "lock", "sleep",
    "navigate", "directions", "email", "message", "call", "facetime",
    "download", "install", "run", "execute",
)


def _looks_like_action_request(command):
    """True if the command is asking Jarvis to DO something (not just talk)."""
    c = command.lower()
    return any(c.startswith(v) or f' {v} ' in c for v in _ACTION_REQUEST_VERBS)


_SCREEN_QUERY_PHRASES = (
    "on my screen", "on screen", "on the screen", "you can see", "i can see",
    "visible", "in front of", "what's open", "what is open",
    "list the", "list of", "show me what", "read the page",
    "what does it say", "what does the", "what's on youtube",
    "videos on", "items on", "links on", "buttons on",
    "in the browser", "in chrome", "in safari", "in the app",
)


def _looks_like_screen_query(command):
    c = command.lower()
    return any(p in c for p in _SCREEN_QUERY_PHRASES)


def _get_screen_context():
    """OCR the screen and return clean text (cached for 10s)."""
    global _screen_cache, _screen_cache_time
    now = time.time()
    if hasattr(_get_screen_context, '_cache') and now - _get_screen_context._time < 10:
        return _get_screen_context._cache

    raw = read_screen()
    # Strip the "On screen: " prefix
    text = re.sub(r'^On screen:\s*', '', raw).strip()
    _get_screen_context._cache = text
    _get_screen_context._time  = now
    return text


def _answer_with_screen(command):
    """
    Read the screen and answer the user's question about visible content.
    Uses the brain with screen text as grounded context.
    """
    screen_text = _get_screen_context()
    if not screen_text or "no readable text" in screen_text.lower():
        return "I can see the screen but there's no readable text right now."

    # Ask the brain to answer the question using ONLY what's on screen
    prompt = (
        f"The user asked: \"{command}\"\n\n"
        f"Here is the text currently visible on their screen:\n{screen_text[:600]}\n\n"
        f"Answer their question using only what is visible above. "
        f"Be concise — one or two sentences."
    )
    reply, _ = brain.ask(prompt, [])
    if reply:
        return reply
    # Fallback: just read the relevant part of screen text
    lines = [l.strip() for l in screen_text.split(";") if l.strip()][:6]
    return "On screen I can see: " + ", ".join(lines) + "."


def _ctx_followup(command):
    """
    Handle follow-up phrases that only make sense in context:
    'cancel it', 'stop it', 'make it 10 minutes', 'change that to X', etc.
    """
    global _ctx
    c = command.lower().strip()

    # "cancel it" / "stop it" / "never mind that"
    if _ctx.last_action and re.match(r'^(cancel|stop|never mind|forget|undo)\b', c):
        action = _ctx.last_action
        subject = _ctx.last_subject or "that"
        _ctx.last_action = None
        _ctx.last_subject = None
        return f"Understood — {action} for {subject} cancelled."

    # "yes" / "ok" in note-taking context
    if c in ("yes", "yeah", "ok", "okay", "sure", "go on", "continue") and _ctx.last_action == "note":
        return "Go ahead, I'm listening."

    # "add that to notes" / "save that" / "note that down"
    if _ctx.last_reply and any(p in c for p in ("add that", "save that", "note that", "write that down", "add to notes")):
        note_text = _ctx.last_reply
        take_note(f"note that {note_text}")
        return f"Noted: {note_text[:80]}."

    return None


def _smart_offline_reply(cmd):
    """
    Offline-only responses to common conversational patterns.
    Keeps Jarvis useful when no LLM backend is configured or affordable.
    """
    c = cmd.lower().strip(" ?.!,")

    # Greetings (substring match — works with Whisper noise)
    if c in ("hi", "hello", "hey", "yo", "sup") or c.startswith(("hi ", "hello ", "hey ")):
        return f"Hello, {OWNER_NAME}. How may I assist?"
    if "good morning" in c or c == "morning":
        return f"Good morning, {OWNER_NAME}. Ready when you are."
    if "good evening" in c or c == "evening":
        return f"Good evening, {OWNER_NAME}."
    if "good night" in c or "goodnight" in c or c == "night":
        return f"Good night, {OWNER_NAME}. Sleep well."
    if "good afternoon" in c:
        return f"Good afternoon, {OWNER_NAME}."

    # Identity / self
    if any(x in c for x in ("who are you", "what are you", "your name")):
        return f"I am JARVIS — your personal assistant, {OWNER_NAME}."
    if any(x in c for x in ("how are you", "how's it going", "you doing", "how do you do")):
        return f"Fully operational, {OWNER_NAME}. How can I help?"
    if "what can you do" in c or "your capabilities" in c or c == "help":
        return ("I can tell time, set timers and alarms, open apps, control volume and music, "
                "take screenshots, do math, check battery, search the web, and much more. "
                "Just ask naturally.")

    # Thanks / affirmations / dismissal
    if c in ("thanks", "thank you", "thanks jarvis", "cheers", "ty"):
        return f"My pleasure, {OWNER_NAME}."
    if c in ("okay", "ok", "alright", "got it", "sure"):
        return "Acknowledged."
    if c in ("nothing", "never mind", "nevermind", "forget it", "cancel"):
        return "As you wish."
    if c in ("yes", "yeah", "yep"):
        return f"Yes, {OWNER_NAME}?"
    if c in ("no", "nope", "nah"):
        return "Understood."

    # Pardon / repeat
    if c in ("pardon", "what", "what did you say", "say that again", "repeat"):
        return "I was just listening, sir. Please go ahead."

    # Short acknowledgements that aren't commands
    if len(c) <= 4:
        return None  # Don't respond to fragments

    # Readiness / capability questions — give a useful response
    _ready_phrases = (
        "are you ready", "are you listening", "are you there",
        "you ready", "are you awake", "are you on",
        "are you available", "can you hear me", "do you hear me",
    )
    if any(p in c for p in _ready_phrases):
        # If specifically asking to take notes — enter note-taking mode
        if "note" in c or "notes" in c or "jot" in c or "write" in c:
            _ctx.mode = "taking_notes"
            _ctx.note_buffer = []
            _ctx.last_action = "note"
            return f"Ready to take notes, {OWNER_NAME}. Go ahead — say 'done' when finished."
        return f"Ready, {OWNER_NAME}. Go ahead."

    # Generic "are you" identity fallback
    if c.startswith("are you "):
        return f"I am JARVIS, your assistant."

    # Pronoun-heavy queries that likely need a real brain
    return None
