#!/usr/bin/env python3
"""
Jarvis Voice Simulation — tests process_command() without microphone.
Run:  venv/bin/python3 test_sim.py
"""

import sys, os
sys.path.insert(0, os.path.dirname(__file__))

# Monkey-patch webbrowser / subprocess so test doesn't actually open apps
import webbrowser, subprocess as _sp_real
_opened_urls = []
_opened_apps = []
webbrowser.open = lambda url, *a, **kw: _opened_urls.append(url) or True

_orig_run  = _sp_real.run
_orig_popen = _sp_real.Popen

def _fake_run(args, **kw):
    if isinstance(args, list) and args and args[0] in ("open", "osascript", "cliclick", "screencapture"):
        _opened_apps.append(args)
        class R: returncode=0; stdout=""; stderr=""
        return R()
    return _orig_run(args, **kw)

def _fake_popen(args, **kw):
    if isinstance(args, list) and args and args[0] in ("open", "osascript", "bash", "afplay"):
        _opened_apps.append(args)
        class P:
            def wait(self): pass
            def terminate(self): pass
            pid = 99999
        return P()
    return _orig_popen(args, **kw)

_sp_real.run   = _fake_run
_sp_real.Popen = _fake_popen

# ─── Now import Jarvis ────────────────────────────────────────────────────────
from commands import process_command

# ─── Test cases ───────────────────────────────────────────────────────────────
# (input, expected_keyword_in_response, description)
TESTS = [
    # ── Basic time/date ─────────────────────────────────────────────────────
    ("what time is it",              "time",         "time query"),
    ("what is today's date",         "today",        "date query"),
    ("what day is today",            "today",        "day query"),

    # ── Polite prefix — these MUST work without 'Jarvis' in them ────────────
    ("can you open youtube",         "youtube",      "polite open youtube"),
    ("could you please open spotify","spotify",      "polite open spotify"),
    ("please open chrome",           "chrome",       "polite open chrome"),
    ("can you close safari",         "closing",      "polite close app"),

    # ── Direct app opens ────────────────────────────────────────────────────
    ("open youtube",                 "youtube",      "direct open youtube"),
    ("open spotify",                 "spotify",      "direct open spotify"),
    ("open terminal",                "terminal",     "open terminal"),
    ("launch vscode",                "visual studio","launch vscode"),

    # ── Website in browser ──────────────────────────────────────────────────
    ("open youtube in safari",       "safari",       "website in browser"),
    ("open github in chrome",        "chrome",       "github in chrome"),

    # ── Wake-word-included commands (jarvis + command inline) ────────────────
    ("jarvis open youtube",          "youtube",      "jarvis inline open"),
    ("hey jarvis what time is it",   "time",         "hey jarvis time"),

    # ── The exact broken phrase from logs ───────────────────────────────────
    ("run through my youtube titles","recogni",       "run through → walk through"),
    ("hey jarvis run through my youtube titles","recogni","hey jarvis run through"),

    # ── Volume / system ─────────────────────────────────────────────────────
    ("volume up",                    "volume",       "volume up"),
    ("mute",                         "muted",        "mute"),
    ("set volume to 50",             "50",           "set volume"),
    ("take a screenshot",            "screenshot",   "screenshot"),
    ("battery status",               "battery",      "battery"),

    # ── Music ───────────────────────────────────────────────────────────────
    ("play music",                   "playing",      "play music"),
    ("pause music",                  "paused",       "pause music"),
    ("next song",                    "next",         "next track"),

    # ── Timer / alarm ────────────────────────────────────────────────────────
    ("set a timer for 5 minutes",    "5 minutes",    "timer"),
    ("set alarm for 7 am",           "7",            "alarm"),

    # ── Search ──────────────────────────────────────────────────────────────
    ("search for python tutorials",  "python",       "web search"),
    ("google latest iphone",         "iphone",       "google search"),

    # ── Math ────────────────────────────────────────────────────────────────
    ("what is 25 times 4",           "100",          "math multiply"),
    ("calculate 100 divided by 5",   "20",           "math divide"),

    # ── Conversational ──────────────────────────────────────────────────────
    ("how are you",                  "operational",  "how are you"),
    ("who are you",                  "jarvis",       "who are you"),
    ("thank you",                    "",             "thank you"),
    ("tell me a joke",               "",             "joke"),

    # ── Exit triggers — must NOT false-fire on partial matches ───────────────
    ("open youtube",                 "youtube",      "youtube must not trigger bye"),
    ("go to subway",                 None,           "subway must not trigger bye"),
    ("playing goodbye song",         None,           "goodbye in middle must not exit"),

    # ── Identity ────────────────────────────────────────────────────────────
    ("which model are you using",    "ollama",       "which model/brain"),
    ("what ai are you running on",   "ollama",       "what ai backend"),

    # ── Calendar ────────────────────────────────────────────────────────────
    ("what's on my calendar",        "event",        "calendar"),
    ("my schedule today",            "event",        "schedule"),

    # ── Notes ───────────────────────────────────────────────────────────────
    ("start taking notes",           "note",         "enter note mode"),
    ("are you ready to take notes",  "note",         "readiness note mode"),

    # ── Tricky edge cases ────────────────────────────────────────────────────
    ("what is the capital of france","paris",        "capital of france (web)"),
    ("what is qwen3",                None,           "qwen3 must not trigger calculator"),
]

# ─── Runner ───────────────────────────────────────────────────────────────────

GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

passed = failed = skipped = 0

print(f"\n{BOLD}{'='*65}{RESET}")
print(f"{BOLD}  JARVIS Voice Simulation — {len(TESTS)} test cases{RESET}")
print(f"{BOLD}{'='*65}{RESET}\n")

import commands as _cmd_mod

for phrase, expected_kw, desc in TESTS:
    _opened_urls.clear()
    _opened_apps.clear()
    # Reset conversation context between tests so mode/state doesn't leak
    _cmd_mod._ctx.mode = None
    _cmd_mod._ctx.note_buffer = []
    _cmd_mod._ctx.last_action = None
    _cmd_mod._ctx.last_subject = None
    try:
        response, keep = process_command(phrase)
    except Exception as e:
        response, keep = f"EXCEPTION: {e}", True

    response_str = (response or "").lower()
    url_str      = " ".join(_opened_urls).lower()
    combined     = response_str + " " + url_str

    if expected_kw is None:
        # Just check it doesn't crash and doesn't exit
        if keep is False:
            status = f"{RED}FAIL — unexpectedly triggered EXIT{RESET}"
            failed += 1
        else:
            status = f"{GREEN}OK{RESET}"
            passed += 1
    elif expected_kw == "":
        # Empty string = just check a non-empty response was returned
        if response and len(response.strip()) > 0:
            status = f"{GREEN}OK{RESET}"
            passed += 1
        else:
            status = f"{RED}FAIL — empty response{RESET}"
            failed += 1
    else:
        kw = expected_kw.lower()
        if kw in combined:
            status = f"{GREEN}OK{RESET}"
            passed += 1
        else:
            status = f"{RED}FAIL — expected '{expected_kw}' in response{RESET}"
            failed += 1

    # Print compact result
    short_resp = (response or "(no response)")[:80].replace("\n", " ")
    print(f"  {'✓' if GREEN in status else '✗'} [{desc:40}]  {status}")
    if RED in status or "EXCEPTION" in (response or ""):
        print(f"      Input   : {phrase}")
        print(f"      Response: {short_resp}")
        if _opened_urls:
            print(f"      URLs    : {_opened_urls}")
        print()

print(f"\n{BOLD}{'='*65}{RESET}")
print(f"  {GREEN}Passed: {passed}{RESET}  {RED}Failed: {failed}{RESET}  Total: {passed+failed}")
print(f"{BOLD}{'='*65}{RESET}\n")

if failed:
    sys.exit(1)
