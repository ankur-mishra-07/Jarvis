#!/usr/bin/env python3
"""
One-step Groq setup for J.A.R.V.I.S.

Groq gives Jarvis a fast cloud fallback brain (Llama 3.3 70B) AND much
better speech recognition for Indian accents (Whisper large-v3). Both
turn on the moment a valid key is saved — no code changes needed.

Get a free key at: https://console.groq.com/keys

Usage:
    python3 setup_groq.py                 # prompts for the key
    python3 setup_groq.py gsk_xxx...      # pass the key directly
"""

import sys
import json
import config


def validate(key):
    """Confirm the key works against the live Groq API. Returns (ok, message)."""
    import requests
    try:
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": [{"role": "user", "content": "reply with: ok"}],
                "max_tokens": 5,
            },
            timeout=15,
        )
    except Exception as e:
        return False, f"Network error: {e}"

    if r.status_code == 200:
        return True, r.json()["choices"][0]["message"]["content"].strip()
    if r.status_code == 401:
        return False, "Key rejected (401) — check you copied the full key."
    return False, f"Groq returned HTTP {r.status_code}: {r.text[:120]}"


def main():
    key = sys.argv[1].strip() if len(sys.argv) > 1 else ""
    if not key:
        try:
            key = input("Paste your Groq API key (starts with gsk_): ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nCancelled.")
            return 1

    if not key.startswith("gsk_"):
        print("⚠  Groq keys start with 'gsk_'. Double-check the value.")

    print("  Validating against Groq...", flush=True)
    ok, msg = validate(key)
    if not ok:
        print(f"  ✗ {msg}")
        return 1

    print(f"  ✓ Key works (Groq replied: '{msg}')")

    # Save to config.json (gitignored — never committed)
    cfg = config.load_config()
    cfg["groq_api_key"] = key
    # Ensure groq sits right after ollama as the fallback brain
    pr = cfg.get("brain_priority") or ["ollama", "groq", "gemini"]
    if "groq" not in pr:
        pr.insert(1, "groq")
    cfg["brain_priority"] = pr
    config.save_config(cfg)

    print("  ✓ Saved to config.json")
    print()
    print("  Now active:")
    print("   • Brain fallback — if Ollama is busy/down, Jarvis uses Groq Llama 3.3 70B")
    print("   • Speech — Jarvis prefers Groq Whisper large-v3 (better with Indian accents)")
    print()
    print("  Restart Jarvis to apply.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
