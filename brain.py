"""
J.A.R.V.I.S. Brain — thin shim over the Orchestrator.
Maintains backward compatibility with commands.py and jarvis.py
while routing everything through the new modular architecture.
"""

import config

# Singleton orchestrator instance
_orchestrator = None


def _get_orchestrator():
    global _orchestrator
    if _orchestrator is None:
        from orchestrator import Orchestrator
        _orchestrator = Orchestrator()
    return _orchestrator


def ask(message, history=None):
    """Main entry point — used by commands.py and jarvis.py."""
    orch = _get_orchestrator()
    reply = orch.process(message)
    new_hist = (history or []) + [
        {"role": "user", "content": message},
        {"role": "assistant", "content": reply},
    ]
    return reply, new_hist


def is_configured():
    """True if at least one brain backend is available."""
    return bool(
        config.get("groq_api_key")
        or config.get("gemini_api_key")
        or _ollama_available()
        or config.get("claude_api_key")
    )


def _ollama_available():
    try:
        import requests
        url = (config.get("ollama_url") or "http://localhost:11434") + "/api/tags"
        r = requests.get(url, timeout=2)
        return r.status_code == 200
    except Exception:
        return False


def active_backend_name():
    """Return name of the active LLM backend."""
    try:
        orch = _get_orchestrator()
        return orch.llm.active_backend()
    except Exception:
        return "none"
