"""Application control tools — open, close, switch apps."""

import subprocess
import webbrowser
from .registry import tool

APP_MAP = {
    "chrome": "Google Chrome", "google chrome": "Google Chrome",
    "safari": "Safari", "firefox": "Firefox", "brave": "Brave Browser",
    "terminal": "Terminal", "iterm": "iTerm", "finder": "Finder",
    "notes": "Notes", "music": "Music", "spotify": "Spotify",
    "slack": "Slack", "discord": "Discord", "zoom": "zoom.us",
    "teams": "Microsoft Teams", "vscode": "Visual Studio Code",
    "vs code": "Visual Studio Code", "code": "Visual Studio Code",
    "xcode": "Xcode", "mail": "Mail", "messages": "Messages",
    "calendar": "Calendar", "photos": "Photos",
    "settings": "System Settings", "calculator": "Calculator",
    "notion": "Notion", "obsidian": "Obsidian",
    "whatsapp": "WhatsApp", "telegram": "Telegram",
    "chatgpt": "ChatGPT", "claude": "Claude",
    "cursor": "Cursor", "warp": "Warp", "docker": "Docker",
    "postman": "Postman", "vlc": "VLC", "arc": "Arc",
}

WEBSITE_MAP = {
    "youtube": "https://youtube.com",
    "gmail": "https://mail.google.com",
    "google": "https://google.com",
    "facebook": "https://facebook.com",
    "instagram": "https://instagram.com",
    "twitter": "https://twitter.com", "x": "https://x.com",
    "reddit": "https://reddit.com",
    "github": "https://github.com",
    "linkedin": "https://linkedin.com",
    "netflix": "https://netflix.com",
    "amazon": "https://amazon.com",
    "chatgpt": "https://chat.openai.com",
    "claude": "https://claude.ai",
    "stackoverflow": "https://stackoverflow.com",
    "wikipedia": "https://wikipedia.org",
    "twitch": "https://twitch.tv",
    "hotstar": "https://hotstar.com",
    "notion": "https://notion.so",
    "figma": "https://figma.com",
    "drive": "https://drive.google.com",
    "docs": "https://docs.google.com",
    "maps": "https://maps.google.com",
    "translate": "https://translate.google.com",
}


@tool("open_app", "Open a macOS application or website",
      {"app_name": "Name of the app or website"})
def open_app(app_name, **kw):
    name = app_name.lower().strip()

    # Check websites first
    if name in WEBSITE_MAP:
        webbrowser.open(WEBSITE_MAP[name])
        return f"Opened {name} in browser."

    # Try as macOS app
    resolved = APP_MAP.get(name, app_name.title())
    result = subprocess.run(["open", "-a", resolved],
                            capture_output=True, text=True, timeout=5)
    if result.returncode == 0:
        return f"Opened {resolved}."

    # Fallback: try as website search
    if len(name.split()) <= 3:
        webbrowser.open(f"https://www.google.com/search?q={name.replace(' ', '+')}")
        return f"Couldn't find app — searching for {name}."

    return f"Could not find: {app_name}"


@tool("close_app", "Close/quit a running application",
      {"app_name": "Name of the app to close"})
def close_app(app_name, **kw):
    resolved = APP_MAP.get(app_name.lower().strip(), app_name.title())
    subprocess.run(["osascript", "-e", f'tell application "{resolved}" to quit'],
                   capture_output=True)
    return f"Closed {resolved}."


@tool("open_url", "Open a specific URL in the default browser",
      {"url": "The URL to open"})
def open_url(url, **kw):
    if not url.startswith("http"):
        url = "https://" + url
    webbrowser.open(url)
    return f"Opened {url}"
