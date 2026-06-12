"""
J.A.R.V.I.S. Screen Agent — autonomous browser navigation.

Agentic loop: screenshot → OCR with positions → LLM picks the next
action → execute → repeat, until the goal is done or the step budget
runs out.

  "Jarvis, find and play a lo-fi music video"
    → sees the YouTube page, clicks the search box, types, presses
      enter, clicks a result — all decided live by the LLM from
      what's actually on screen.

Uses the same battle-tested primitives as commands.py:
tesseract TSV (word boxes), cliclick (Retina-halved coords),
AppleScript keystrokes.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import time

MAX_STEPS = 6
SETTLE_SECONDS = 2.0      # wait after click/type for the page to react
MAX_ELEMENTS = 35         # screen lines shown to the LLM


# ─── Screen reading ──────────────────────────────────────────────────────────

def _capture_elements():
    """
    Screenshot the focused browser and OCR it into clickable elements.
    Returns a list of {"n": idx, "text": line_text, "x": px, "y": px}
    with coordinates in Retina pixels (halve before cliclick).
    """
    from commands import _screenshot_for_ocr

    tmp_dir = tempfile.gettempdir()
    img_name = f"jarvis_agent_{os.getpid()}.png"
    img_path = os.path.join(tmp_dir, img_name)

    _screenshot_for_ocr(img_path)
    result = subprocess.run(
        ["tesseract", img_name, "stdout", "-l", "eng", "tsv"],
        capture_output=True, timeout=15, text=True, cwd=tmp_dir
    )
    try:
        os.unlink(img_path)
    except OSError:
        pass

    # Group words into visual lines using tesseract's block/par/line ids
    lines = {}   # (block, par, line) → {"words": [...], "xs": [...], "ys": [...]}
    max_top = 0
    for row in result.stdout.split("\n")[1:]:
        parts = row.split("\t")
        if len(parts) < 12:
            continue
        try:
            conf = float(parts[10])
            word = parts[11].strip()
            if not word or conf < 45:
                continue
            key = (parts[2], parts[3], parts[4])
            left, top, w, h = int(parts[6]), int(parts[7]), int(parts[8]), int(parts[9])
            max_top = max(max_top, top)
            entry = lines.setdefault(key, {"words": [], "xs": [], "ys": []})
            entry["words"].append(word)
            entry["xs"].append(left + w // 2)
            entry["ys"].append(top + h // 2)
        except (ValueError, IndexError):
            continue

    # Skip top chrome (menu bar + browser tabs ≈ top 7% of Retina pixels)
    min_y = max(120, int(max_top * 0.07))

    elements = []
    seen_text = set()
    for entry in lines.values():
        text = " ".join(entry["words"]).strip()
        cy = sum(entry["ys"]) // len(entry["ys"])
        if len(text) < 3 or cy < min_y:
            continue
        if text.lower() in seen_text:      # dedupe repeated UI labels
            continue
        seen_text.add(text.lower())
        elements.append({
            "text": text[:80],
            "x": sum(entry["xs"]) // len(entry["xs"]),
            "y": cy,
        })

    # Reading order, cap for the LLM prompt
    elements.sort(key=lambda e: (e["y"], e["x"]))
    elements = elements[:MAX_ELEMENTS]
    for i, e in enumerate(elements, 1):
        e["n"] = i
    return elements


# ─── Action primitives ───────────────────────────────────────────────────────

def _do_click(element):
    x, y = element["x"] // 2, element["y"] // 2     # Retina halving
    subprocess.run(["cliclick", f"c:{x},{y}"], capture_output=True, timeout=3)


def _do_type(text):
    """Type arbitrary text into the focused field via AppleScript."""
    safe = text.replace("\\", "\\\\").replace('"', '\\"')
    subprocess.run(["osascript", "-e",
                    f'tell application "System Events" to keystroke "{safe}"'],
                   capture_output=True, timeout=10)


def _do_enter():
    subprocess.run(["osascript", "-e",
                    'tell application "System Events" to key code 36'],
                   capture_output=True, timeout=3)


def _do_scroll():
    from commands import scroll_down
    scroll_down()


def _do_back():
    from commands import go_back
    go_back("go back")


# ─── LLM decision ────────────────────────────────────────────────────────────

_PROMPT = """You are a precise web-browsing agent on a Mac.

GOAL: {goal}

SCREEN — numbered texts you can click:
{elements}

ACTIONS ALREADY TAKEN:
{history}

Decide the single next action. Output ONLY one json object, nothing else.

{{"action":"done","say":"short summary"}}
   Use FIRST if the goal is ALREADY complete. A video timestamp like
   "3:23 / 16:48" or a Pause control means a video IS playing now.
{{"action":"click","element":N}}
   N must be the element whose TEXT best matches what the goal needs.
   Never click headers, logos or menus unless the goal requires it.
{{"action":"type","text":"..."}}   types into the focused box (click a search box first)
{{"action":"enter"}}               press Enter (submits a typed search)
{{"action":"scroll"}}              scroll down when nothing on screen matches yet
{{"action":"back"}}                browser back

Search boxes have text like "Search", "Search Google or type a URL", or "Type here" —
click THOSE to search, never a site logo or page title.

Example — GOAL: play a cat video. SCREEN: 2. "Search"  5. "funny cats compilation 4K"
Correct output: {{"action":"click","element":5}}"""


def _decide(goal, elements, history):
    """Ask the LLM for the next action. Returns a dict or None."""
    from llm.model import LLMRouter
    global _llm
    if "_llm" not in globals() or _llm is None:
        _llm = LLMRouter()

    def _tag(e):
        # Inline tags steer small LLMs far better than rules in the instructions
        t = e["text"].lower()
        if re.search(r'\bsearch\b|type here|type a url', t) and len(e["text"]) < 45:
            return f'{e["n"]}. "{e["text"]}" [SEARCH BOX - click here to search]'
        return f'{e["n"]}. "{e["text"]}"'

    element_lines = "\n".join(_tag(e) for e in elements) or "(screen is empty)"
    history_lines = "\n".join(f"- {h}" for h in history) or "(none yet)"

    prompt = _PROMPT.format(goal=goal, elements=element_lines, history=history_lines)
    reply = _llm.chat([{"role": "user", "content": prompt}],
                      max_tokens=80, temperature=0.1)
    if not reply:
        return None

    m = re.search(r'\{[^{}]*\}', reply, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


_llm = None


# ─── Scripted fast-path for searches ─────────────────────────────────────────

def _try_scripted_search(goal, elements):
    """
    For "search for X ..." goals, the click→type→enter dance is always the
    same — do it deterministically instead of burning 3 LLM steps (and
    risking a 7B model clicking the site logo). Returns history entries,
    or None if this isn't a search goal / no search box visible.
    """
    m = re.match(r'(?:search|look)\s+(?:for\s+)?(.{3,})', goal.lower())
    if not m:
        return None
    query = m.group(1)
    # Trim trailing intent ("...and click the first result" stays for the LLM)
    query = re.split(r'\b(?:and|then)\b', query)[0].strip(" .,")
    if not query:
        return None

    box = next((e for e in elements
                if re.search(r'\bsearch\b|type here|type a url', e["text"].lower())
                and len(e["text"]) < 45), None)
    if box is None:
        return None

    _do_click(box)
    time.sleep(0.6)
    _do_type(query)
    time.sleep(0.3)
    _do_enter()
    return [f'clicked "{box["text"][:40]}"', f'typed "{query}"', "pressed enter"]


# ─── Agent loop ──────────────────────────────────────────────────────────────

def run_goal(goal):
    """
    Run the autonomous screen agent for a natural-language goal.
    Returns a spoken summary string.
    """
    goal = goal.strip()
    if not goal:
        return "Tell me what to do on screen, sir."

    print(f"  [Screen agent goal: {goal}]", flush=True)
    history = []
    last_action_sig = None

    for step in range(1, MAX_STEPS + 1):
        try:
            elements = _capture_elements()
        except FileNotFoundError:
            return "I need tesseract and cliclick installed for screen navigation."
        except Exception as e:
            print(f"  [Screen agent capture error: {e}]", flush=True)
            return "I couldn't read the screen, sir."

        # First step of a search goal: scripted click→type→enter fast-path
        if step == 1 and not history:
            scripted = _try_scripted_search(goal, elements)
            if scripted:
                history.extend(scripted)
                print(f"  [Agent scripted search: {scripted[1]}]", flush=True)
                time.sleep(SETTLE_SECONDS)
                continue

        # Deterministic done-check: a "1:23 / 45:06" timestamp on screen after
        # we acted means a video IS playing — don't rely on the LLM to notice
        if history and re.search(r'\b(play|watch|video|music|song)\b', goal):
            if any(re.search(r'\d+:\d+\s*/\s*\d+:\d+', e["text"]) for e in elements):
                return "Playing now, sir."

        action = _decide(goal, elements, history)
        if not action:
            return ("I lost the thread on that one — "
                    f"I managed {len(history)} step{'s' if len(history) != 1 else ''} so far.")

        kind = action.get("action", "")
        print(f"  [Agent step {step}: {action}]", flush=True)

        # Loop protection: same action twice in a row → bail
        sig = json.dumps(action, sort_keys=True)
        if sig == last_action_sig:
            return f"I seem to be going in circles. Done so far: {'; '.join(history) or 'nothing'}."
        last_action_sig = sig

        if kind == "done":
            say = action.get("say") or "Done."
            return say if len(history) == 0 else f"{say}"

        elif kind == "click":
            n = action.get("element")
            target = next((e for e in elements if e["n"] == n), None)
            if target is None:
                history.append(f"tried to click missing element {n}")
                continue
            _do_click(target)
            history.append(f'clicked "{target["text"][:40]}"')

        elif kind == "type":
            text = str(action.get("text", ""))[:120]
            if text:
                _do_type(text)
                history.append(f'typed "{text[:40]}"')

        elif kind == "enter":
            _do_enter()
            history.append("pressed enter")

        elif kind == "scroll":
            _do_scroll()
            history.append("scrolled down")

        elif kind == "back":
            _do_back()
            history.append("went back")

        else:
            history.append(f"unknown action '{kind}' skipped")

        time.sleep(SETTLE_SECONDS)

    return (f"Step budget reached. I did: {'; '.join(history)}. "
            "Say 'continue' with a fresh goal if you want me to keep going.")
