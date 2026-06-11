"""
J.A.R.V.I.S. Configuration
Persistent settings stored in config.json.
"""

import os
import json

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

DEFAULTS = {
    "owner_name": "Boss",
    "wake_word": "jarvis",
    "voice_id": "",  # Empty = auto-select from profile
    "voice_profile": "zoro",  # zoro, zoro_light, zoro_heavy, default
    "voice_rate": 162,
    "voice_volume": 1.0,
    "claude_api_key": "",
    "claude_model": "claude-sonnet-4-20250514",
    "listen_timeout": 5,
    "phrase_time_limit": 10,
    # Server config
    "server_host": "0.0.0.0",
    "server_port": 8786,
    "server_api_key": "",  # Must be set to enable server mode
    # Proactive announcements (battery, WiFi, disk, market open/close)
    "proactive_events": True,
}


def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r") as f:
            saved = json.load(f)
        # Merge with defaults for any missing keys
        merged = {**DEFAULTS, **saved}
        return merged
    return dict(DEFAULTS)


def save_config(cfg):
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)


def get(key):
    return load_config().get(key, DEFAULTS.get(key))


def set_key(key, value):
    cfg = load_config()
    cfg[key] = value
    save_config(cfg)
