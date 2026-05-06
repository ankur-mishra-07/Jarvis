"""Productivity tools — timers, reminders, notes, calendar."""

import subprocess
import datetime
import os
from .registry import tool
import config


def _applescript(script):
    result = subprocess.run(["osascript", "-e", script],
                            capture_output=True, text=True, timeout=5)
    return result.stdout.strip()


OWNER = config.get("owner_name") or "Boss"


@tool("set_timer", "Set a countdown timer",
      {"minutes": "Minutes", "seconds": "Seconds (optional)"})
def set_timer(minutes=0, seconds=0, **kw):
    m, s = int(minutes or 0), int(seconds or 0)
    total = m * 60 + s
    if total <= 0:
        return "Timer needs a duration."
    subprocess.Popen(["bash", "-c",
        f'sleep {total} && say "Timer is up, {OWNER}!" && '
        f'osascript -e \'display notification "Timer is up!" with title "JARVIS" sound name "Glass"\''])
    parts = []
    if m: parts.append(f"{m} min")
    if s: parts.append(f"{s} sec")
    return f"Timer set for {' '.join(parts)}."


@tool("set_reminder", "Set a reminder",
      {"text": "What to remind about", "minutes": "Minutes from now"})
def set_reminder(text, minutes=5, **kw):
    m = int(minutes or 5)
    subprocess.Popen(["bash", "-c",
        f'sleep {m * 60} && say "Reminder: {text}" && '
        f'osascript -e \'display notification "{text}" with title "JARVIS Reminder" sound name "Glass"\''])
    return f"Reminder set: {text} in {m} minutes."


@tool("take_note", "Save a note",
      {"text": "The note content"})
def take_note(text, **kw):
    _applescript(f'''tell application "Notes"
        activate
        make new note at folder "Notes" with properties {{body:"{text}"}}
    end tell''')
    return f"Note saved: {text[:80]}"


@tool("calendar_today", "Get today's calendar events", {})
def calendar_today(**kw):
    events = _applescript('''
        set today to current date
        set time of today to 0
        set tomorrow to today + (1 * days)
        tell application "Calendar"
            set allEvents to {}
            repeat with aCal in calendars
                set calEvents to (every event of aCal whose start date >= today and start date < tomorrow)
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


@tool("set_alarm", "Set an alarm for a specific time",
      {"time_str": "Time like '7:30 am' or '19:00'"})
def set_alarm(time_str, **kw):
    import re
    m = re.search(r'(\d{1,2})[:\s]?(\d{2})?\s*(am|pm)?', time_str.lower())
    if not m:
        return "Couldn't parse time. Try '7:30 am'."
    hour = int(m.group(1))
    minute = int(m.group(2)) if m.group(2) else 0
    period = m.group(3)
    if period and 'p' in period and hour != 12:
        hour += 12
    elif period and 'a' in period and hour == 12:
        hour = 0

    now = datetime.datetime.now()
    alarm = now.replace(hour=hour, minute=minute, second=0)
    if alarm <= now:
        alarm += datetime.timedelta(days=1)
    diff = int((alarm - now).total_seconds())
    time_display = alarm.strftime("%I:%M %p")

    subprocess.Popen(["bash", "-c",
        f'sleep {diff} && say "Alarm! Wake up {OWNER}!" && '
        f'osascript -e \'display notification "Alarm!" with title "JARVIS" sound name "Sosumi"\''])
    return f"Alarm set for {time_display}."


@tool("memory_recall", "Search past conversations for a topic",
      {"query": "What to search memory for"})
def memory_recall(query, **kw):
    from memory import recall
    results = recall(query, k=3)
    if not results:
        return "No relevant memories found."
    lines = []
    for r in results:
        lines.append(f"- User: {r['user'][:80]}")
        lines.append(f"  Jarvis: {r['assistant'][:80]}")
    return "\n".join(lines)
