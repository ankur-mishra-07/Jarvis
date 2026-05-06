"""
J.A.R.V.I.S. Tool Use Layer
Gives the LLM brain structured tool-calling ability.

The brain receives a list of available tools with descriptions.
It returns a JSON tool_call when it wants to take action.
This module executes the call and returns the result.

Tools cover: system commands, file access, web search, app control, automation.
"""

import os
import re
import json
import subprocess
import datetime
import webbrowser

import config

# ─── Tool Registry ──────────────────────────────────────────────────────────
# Each tool: {name, description, parameters: {name: description}, handler_fn}

TOOLS = {}


def tool(name, description, params=None):
    """Decorator to register a tool."""
    def decorator(fn):
        TOOLS[name] = {
            "name": name,
            "description": description,
            "parameters": params or {},
            "handler": fn,
        }
        return fn
    return decorator


# ─── System Commands ────────────────────────────────────────────────────────

@tool("open_app", "Open a macOS application by name",
      {"app_name": "Name of the app (e.g. 'Chrome', 'Spotify', 'Terminal')"})
def tool_open_app(app_name, **kw):
    from commands import APP_MAP, WEBSITE_MAP
    name = app_name.lower().strip()
    if name in WEBSITE_MAP:
        webbrowser.open(WEBSITE_MAP[name])
        return f"Opened {name} in browser."
    resolved = APP_MAP.get(name, app_name.title())
    result = subprocess.run(["open", "-a", resolved], capture_output=True, text=True, timeout=5)
    if result.returncode == 0:
        return f"Opened {resolved}."
    return f"Could not find app: {resolved}"


@tool("close_app", "Close/quit a running macOS application",
      {"app_name": "Name of the app to close"})
def tool_close_app(app_name, **kw):
    from commands import APP_MAP
    resolved = APP_MAP.get(app_name.lower().strip(), app_name.title())
    subprocess.run(["osascript", "-e", f'tell application "{resolved}" to quit'],
                   capture_output=True, text=True)
    return f"Closed {resolved}."


@tool("web_search", "Search the internet for information using DuckDuckGo",
      {"query": "The search query"})
def tool_web_search(query, **kw):
    from commands import internet_search
    result = internet_search(query)
    return result or "No relevant results found."


@tool("set_timer", "Set a countdown timer",
      {"minutes": "Number of minutes (can be 0)", "seconds": "Number of seconds (can be 0)"})
def tool_set_timer(minutes=0, seconds=0, **kw):
    m = int(minutes or 0)
    s = int(seconds or 0)
    total = m * 60 + s
    if total <= 0:
        return "Timer needs a duration."
    owner = config.get("owner_name") or "Boss"
    subprocess.Popen(
        ["bash", "-c",
         f'sleep {total} && say "Timer is up, {owner}!" && '
         f'osascript -e \'display notification "Timer is up!" with title "JARVIS Timer" sound name "Glass"\'']
    )
    if m and s:
        return f"Timer set for {m} min {s} sec."
    elif m:
        return f"Timer set for {m} minutes."
    return f"Timer set for {s} seconds."


@tool("get_time", "Get the current time", {})
def tool_get_time(**kw):
    return datetime.datetime.now().strftime("It's %I:%M %p on %A, %B %d, %Y.")


@tool("get_weather", "Get current weather for a location",
      {"city": "City name (optional — leave empty for local weather)"})
def tool_get_weather(city="", **kw):
    import requests
    url = f"https://wttr.in/{city}?format=3" if city else "https://wttr.in/?format=3"
    try:
        r = requests.get(url, timeout=5)
        return r.text.strip() if r.status_code == 200 else "Couldn't fetch weather."
    except Exception:
        return "Weather service unavailable."


@tool("set_volume", "Set the system volume (0-100)",
      {"level": "Volume level 0-100"})
def tool_set_volume(level, **kw):
    level = max(0, min(100, int(level)))
    subprocess.run(["osascript", "-e", f"set volume output volume {level}"],
                   capture_output=True)
    return f"Volume set to {level}%."


@tool("take_screenshot", "Capture the screen and save to Desktop", {})
def tool_take_screenshot(**kw):
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.expanduser(f"~/Desktop/screenshot_{ts}.png")
    subprocess.run(["screencapture", path], capture_output=True)
    return f"Screenshot saved to Desktop."


@tool("read_screen", "OCR the current screen and return visible text", {})
def tool_read_screen(**kw):
    from commands import read_screen
    return read_screen()


@tool("run_shell", "Run a shell command and return its output (use carefully)",
      {"command": "The shell command to execute"})
def tool_run_shell(command, **kw):
    # Safety: block destructive commands
    blocked = ("rm -rf", "sudo rm", "mkfs", "dd if=", "> /dev/", "format", "diskutil erase")
    if any(b in command.lower() for b in blocked):
        return "Blocked: that command could be destructive."
    try:
        result = subprocess.run(command, shell=True, capture_output=True,
                                text=True, timeout=15)
        output = (result.stdout + result.stderr).strip()
        return output[:500] if output else "(no output)"
    except subprocess.TimeoutExpired:
        return "Command timed out after 15 seconds."
    except Exception as e:
        return f"Error: {e}"


@tool("read_file", "Read the contents of a file",
      {"path": "Absolute or relative file path"})
def tool_read_file(path, **kw):
    path = os.path.expanduser(path)
    try:
        with open(path) as f:
            content = f.read()
        if len(content) > 1000:
            return content[:1000] + f"\n... ({len(content)} chars total, truncated)"
        return content or "(empty file)"
    except Exception as e:
        return f"Cannot read file: {e}"


@tool("write_file", "Write or append text to a file",
      {"path": "File path", "content": "Text to write", "append": "true to append, false to overwrite"})
def tool_write_file(path, content, append="false", **kw):
    path = os.path.expanduser(path)
    mode = "a" if str(append).lower() == "true" else "w"
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, mode) as f:
            f.write(content)
        return f"Written to {path}."
    except Exception as e:
        return f"Write error: {e}"


@tool("take_note", "Save a note to the Notes app or notes file",
      {"text": "The note content"})
def tool_take_note(text, **kw):
    from commands import take_note
    return take_note(f"note that {text}")


@tool("calendar_today", "Get today's calendar events", {})
def tool_calendar_today(**kw):
    from commands import whats_on_calendar
    return whats_on_calendar()


@tool("set_reminder", "Set a reminder that fires after a delay",
      {"text": "What to remind about", "minutes": "Minutes from now"})
def tool_set_reminder(text, minutes=5, **kw):
    m = int(minutes or 5)
    total = m * 60
    owner = config.get("owner_name") or "Boss"
    subprocess.Popen(
        ["bash", "-c",
         f'sleep {total} && say "Reminder: {text}" && '
         f'osascript -e \'display notification "{text}" with title "JARVIS Reminder" sound name "Glass"\'']
    )
    return f"Reminder set: {text} in {m} minutes."


@tool("memory_recall", "Search your memory for past conversations about a topic",
      {"query": "What to search for in memory"})
def tool_memory_recall(query, **kw):
    import memory
    results = memory.recall(query, k=3)
    if not results:
        return "No relevant memories found."
    lines = []
    for r in results:
        lines.append(f"- User said: {r['user'][:80]}")
        lines.append(f"  Jarvis replied: {r['assistant'][:80]}")
    return "\n".join(lines)


@tool("battery_status", "Check MacBook battery level", {})
def tool_battery_status(**kw):
    result = subprocess.run(["pmset", "-g", "batt"], capture_output=True, text=True)
    for line in result.stdout.split("\n"):
        if "%" in line:
            parts = line.split("\t")
            if len(parts) > 1:
                return f"Battery: {parts[1].strip()}"
    return "Couldn't read battery."


@tool("toggle_dark_mode", "Toggle macOS dark/light mode", {})
def tool_toggle_dark_mode(**kw):
    subprocess.run(["osascript", "-e", '''
        tell application "System Events"
            tell appearance preferences
                set dark mode to not dark mode
            end tell
        end tell
    '''], capture_output=True)
    return "Dark mode toggled."


# ─── Tool Description Generator (for system prompt) ────────────────────────

def get_tool_descriptions():
    """
    Generate a text block describing all tools for the system prompt.
    The LLM reads this and outputs structured tool_call JSON.
    """
    lines = ["Available tools (call by returning JSON with tool_call):"]
    for name, t in TOOLS.items():
        params_str = ""
        if t["parameters"]:
            params_str = ", ".join(
                f'{k}: {v}' for k, v in t["parameters"].items()
            )
        lines.append(f'  - {name}({params_str}): {t["description"]}')
    lines.append("")
    lines.append("To use a tool, include this EXACT JSON in your response:")
    lines.append('  {"tool_call": {"name": "tool_name", "arguments": {"param": "value"}}}')
    lines.append("After the tool runs, you'll see the result and can respond to the user.")
    return "\n".join(lines)


# ─── Tool Execution ────────────────────────────────────────────────────────

def parse_tool_call(text):
    """
    Extract a tool_call JSON from the model's response text.
    Returns (tool_name, arguments_dict) or (None, None).
    """
    # Try to find JSON block with tool_call
    patterns = [
        r'\{[^{}]*"tool_call"\s*:\s*\{[^{}]*\}[^{}]*\}',
        r'```json\s*(\{.*?\})\s*```',
    ]
    for pat in patterns:
        m = re.search(pat, text, re.DOTALL)
        if m:
            try:
                blob = m.group(0) if '```' not in pat else m.group(1)
                data = json.loads(blob)
                if "tool_call" in data:
                    tc = data["tool_call"]
                    return tc.get("name"), tc.get("arguments", {})
            except (json.JSONDecodeError, KeyError):
                continue

    # Fallback: look for any JSON object with "name" and "arguments"
    try:
        m = re.search(r'\{[^{}]*"name"\s*:.*?"arguments"\s*:\s*\{.*?\}[^{}]*\}', text, re.DOTALL)
        if m:
            data = json.loads(m.group(0))
            return data.get("name"), data.get("arguments", {})
    except (json.JSONDecodeError, KeyError):
        pass

    return None, None


def execute_tool(name, arguments):
    """
    Execute a registered tool and return its output string.
    Handles flexible argument names (e.g. "param" mapped to first parameter).
    """
    if name not in TOOLS:
        return f"Unknown tool: {name}. Available: {', '.join(TOOLS.keys())}"

    tool_def = TOOLS[name]
    handler = tool_def["handler"]

    # Flexible argument mapping: if model used "param" or "query" generically,
    # map it to the tool's first defined parameter name
    if arguments and tool_def["parameters"]:
        expected_keys = list(tool_def["parameters"].keys())
        generic_keys = {"param", "value", "input", "text", "query", "arg"}
        for gk in generic_keys:
            if gk in arguments and gk not in expected_keys and expected_keys:
                # Map the generic key to the first expected parameter
                arguments[expected_keys[0]] = arguments.pop(gk)

    try:
        result = handler(**arguments)
        return str(result)
    except Exception as e:
        return f"Tool error ({name}): {e}"
