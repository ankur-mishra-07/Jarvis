"""
J.A.R.V.I.S. TTS Engine — generates audio bytes for remote clients.
Unlike the local SpeechEngine (plays to speakers), this returns audio data.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
import platform
import config

IS_LINUX = platform.system() == "Linux"

# Voice profiles — same as jarvis.py SpeechEngine
VOICE_PROFILES = {
    "jarvis": {
        "voice": "Daniel",
        "rate": 180,
        "sox_effects": ["pitch", "0", "reverb", "15", "bass", "+2"],
    },
    "jarvis_deep": {
        "voice": "Daniel",
        "rate": 175,
        "sox_effects": ["pitch", "-80", "reverb", "20", "bass", "+4"],
    },
    "zoro": {
        "voice": "Daniel",
        "rate": 162,
        "sox_effects": [
            "pitch", "-300", "reverb", "20", "bass", "+6",
            "overdrive", "3", "gain", "-3",
        ],
    },
    "default": {
        "voice": "Daniel",
        "rate": 180,
        "sox_effects": [],
    },
}


class TTSEngine:
    """Generate TTS audio bytes (WAV) for remote clients."""

    def __init__(self):
        self._profile_name = config.get("voice_profile") or "jarvis"
        self._profile = VOICE_PROFILES.get(self._profile_name, VOICE_PROFILES["default"])
        self._rate = config.get("voice_rate") or self._profile.get("rate", 180)

    def synthesize(self, text: str) -> bytes | None:
        """
        Convert text to WAV audio bytes.
        Returns WAV bytes or None on failure.
        """
        if not text:
            return None

        try:
            if IS_LINUX:
                return self._synthesize_espeak(text)
            else:
                return self._synthesize_macos(text)
        except Exception as e:
            print(f"  [TTS error: {e}]", flush=True)
            return None

    def _synthesize_macos(self, text: str) -> bytes | None:
        """macOS: say → AIFF → sox effects → WAV bytes."""
        voice = self._profile.get("voice", "Daniel")
        effects = self._profile.get("sox_effects", [])

        with tempfile.TemporaryDirectory() as tmpdir:
            aiff_path = os.path.join(tmpdir, "speech.aiff")
            wav_path = os.path.join(tmpdir, "speech.wav")

            # Generate speech with macOS `say`
            subprocess.run(
                ["say", "-v", voice, "-r", str(self._rate), "-o", aiff_path, text],
                timeout=15, capture_output=True
            )

            if not os.path.exists(aiff_path):
                return None

            if effects and self._has_sox():
                # Apply sox effects: AIFF → WAV with effects
                cmd = ["sox", aiff_path, "-r", "44100", "-c", "1", wav_path] + effects
                subprocess.run(cmd, timeout=10, capture_output=True)
                read_path = wav_path if os.path.exists(wav_path) else aiff_path
            else:
                # Convert AIFF → WAV without effects
                subprocess.run(
                    ["sox", aiff_path, "-r", "44100", "-c", "1", wav_path],
                    timeout=10, capture_output=True
                )
                read_path = wav_path if os.path.exists(wav_path) else aiff_path

            # If no sox, convert with ffmpeg
            if not os.path.exists(wav_path):
                subprocess.run(
                    ["ffmpeg", "-y", "-i", aiff_path, "-ar", "44100", "-ac", "1", wav_path],
                    timeout=10, capture_output=True
                )
                read_path = wav_path

            if os.path.exists(read_path):
                with open(read_path, "rb") as f:
                    return f.read()
        return None

    def _synthesize_espeak(self, text: str) -> bytes | None:
        """Linux: espeak-ng → WAV bytes."""
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            wav_path = f.name

        try:
            subprocess.run(
                ["espeak-ng", "-v", "en+m3", "-s", str(self._rate), "-w", wav_path, text],
                timeout=10, capture_output=True
            )
            if os.path.exists(wav_path) and os.path.getsize(wav_path) > 44:
                with open(wav_path, "rb") as f:
                    return f.read()
        finally:
            try:
                os.unlink(wav_path)
            except OSError:
                pass
        return None

    @staticmethod
    def _has_sox() -> bool:
        try:
            subprocess.run(["sox", "--version"], capture_output=True, timeout=2)
            return True
        except Exception:
            return False

    @property
    def profile_name(self) -> str:
        return self._profile_name

    def set_profile(self, name: str) -> bool:
        if name in VOICE_PROFILES:
            self._profile_name = name
            self._profile = VOICE_PROFILES[name]
            self._rate = self._profile.get("rate", 180)
            return True
        return False
