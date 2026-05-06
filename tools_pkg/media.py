"""Music and media control tools."""

import subprocess
import webbrowser
from .registry import tool


def _applescript(script):
    result = subprocess.run(["osascript", "-e", script],
                            capture_output=True, text=True, timeout=5)
    return result.stdout.strip()


@tool("play_music", "Start playing music in Apple Music", {})
def play_music(**kw):
    _applescript('tell application "Music" to play')
    return "Playing music."


@tool("pause_music", "Pause music playback", {})
def pause_music(**kw):
    _applescript('tell application "Music" to pause')
    return "Music paused."


@tool("next_track", "Skip to next track", {})
def next_track(**kw):
    _applescript('tell application "Music" to next track')
    return "Skipped to next track."


@tool("now_playing", "Get the currently playing song", {})
def now_playing(**kw):
    name = _applescript('tell application "Music" to get name of current track')
    artist = _applescript('tell application "Music" to get artist of current track')
    if name:
        return f"Now playing: {name} by {artist}."
    return "Nothing is currently playing."


@tool("search_youtube", "Search YouTube for a video",
      {"query": "What to search for"})
def search_youtube(query, **kw):
    webbrowser.open(f"https://youtube.com/results?search_query={query.replace(' ', '+')}")
    return f"Searching YouTube for {query}."


@tool("play_spotify", "Search and play on Spotify",
      {"query": "Song or artist to play"})
def play_spotify(query, **kw):
    webbrowser.open(f"https://open.spotify.com/search/{query.replace(' ', '+')}")
    return f"Searching Spotify for {query}."
