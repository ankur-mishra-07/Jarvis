"""Bridge between the FastAPI server and the laptop Jarvis core.

This is the only file that should know about your laptop project's module
layout. Drop the laptop Jarvis package into `server/jarvis_core/` (or pip
install it into the same venv) and import its entry function below.

Until that import is wired up, a stub responder runs so the server and the
mobile app can be developed end-to-end.
"""

from __future__ import annotations

import asyncio
from datetime import datetime

try:
    # When the laptop Jarvis is dropped in as `jarvis_core`, expose a function
    # like `respond(text: str) -> str` and uncomment the line below.
    from jarvis_core import respond as _laptop_respond  # type: ignore
except Exception:  # pragma: no cover — expected until laptop code is added
    _laptop_respond = None


def _stub_respond(text: str) -> str:
    t = text.strip().lower()
    if not t:
        return "I didn't catch that."
    if "time" in t:
        return f"It's {datetime.now().strftime('%I:%M %p')}."
    if "date" in t:
        return f"Today is {datetime.now().strftime('%A, %B %d, %Y')}."
    if t in {"hi", "hello", "hey", "hey jarvis"}:
        return "Hello. How can I help?"
    return f"(stub) You said: {text}. Wire up jarvis_core.respond to enable real replies."


async def handle_text(user_text: str, session_id: str) -> str:
    """Dispatch a text command to the Jarvis core and return its reply."""
    if _laptop_respond is None:
        return _stub_respond(user_text)

    # Run synchronous laptop code off the event loop so it doesn't block.
    return await asyncio.to_thread(_laptop_respond, user_text)
