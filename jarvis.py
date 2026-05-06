#!/usr/bin/env python3
"""
J.A.R.V.I.S. - Just A Rather Very Intelligent System
Voice-controlled personal assistant with floating UI for macOS.

Architecture:
  - Singleton via PID lockfile (prevents duplicate instances)
  - Always-on microphone with NO timeouts (continuous listening)
  - Persistent mic stream (opened once, never closed during listening)
  - macOS `say` + sox pipeline for Zoro voice profile
  - Background speech recognition thread
  - Runs as a background accessory app (no dock icon, no Cmd+Tab)
"""

import sys
import os
import signal
import datetime
import threading
import subprocess
import re
import atexit
import time
import platform
import speech_recognition as sr
import numpy as np

import config
from commands import process_command

IS_LINUX = platform.system() == "Linux"

try:
    from PyQt6.QtCore import QThread, pyqtSignal
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

    class _NoOpSignal:
        def emit(self, *args): pass
        def connect(self, *args): pass

    class QThread(threading.Thread):
        def __init__(self, *args, **kwargs):
            super().__init__(daemon=True)
        def start(self):
            super().start()
        def isRunning(self):
            return self.is_alive()
        def wait(self, timeout_ms=None):
            self.join(timeout=(timeout_ms / 1000) if timeout_ms else None)

    def pyqtSignal(*args, **kwargs):
        return _NoOpSignal()

# ─── Singleton Lock ──────────────────────────────────────────────────────────

LOCK_FILE = "/tmp/jarvis_assistant.pid"


def acquire_lock():
    """Ensure only one instance of Jarvis runs. Kill stale instances."""
    if os.path.exists(LOCK_FILE):
        try:
            with open(LOCK_FILE, "r") as f:
                old_pid = int(f.read().strip())
            # Check if old process is actually running
            os.kill(old_pid, 0)
            # It's alive — kill it so we become the new instance
            print(f"  [Killing previous Jarvis instance (PID {old_pid})...]")
            os.kill(old_pid, signal.SIGTERM)
            time.sleep(1)
            try:
                os.kill(old_pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        except (ProcessLookupError, ValueError, PermissionError):
            pass  # Stale lock, process already dead
        try:
            os.remove(LOCK_FILE)
        except OSError:
            pass

    # Write our PID
    with open(LOCK_FILE, "w") as f:
        f.write(str(os.getpid()))


def release_lock():
    """Remove PID lockfile on exit."""
    try:
        os.remove(LOCK_FILE)
    except OSError:
        pass


# ─── Configuration ───────────────────────────────────────────────────────────

WAKE_WORD = config.get("wake_word")
OWNER_NAME = config.get("owner_name")

# ─── Speech Engine (macOS `say` + sox, or Linux espeak-ng + aplay) ────────────

class SpeechEngine:
    """
    TTS engine with platform detection.
    macOS: `say` + sox audio pipeline with voice profiles.
    Linux/Pi: espeak-ng + aplay fallback.
    """

    VOICE_PROFILES = {
        "jarvis": {
            "description": "JARVIS — refined British butler (Paul Bettany style)",
            "base_voice": "Daniel",
            "rate": 180,
            "pitch": 0,
            "bass": +1,
            "treble": +1,
            "overdrive": 0,
            "gain": 0,
        },
        "jarvis_deep": {
            "description": "JARVIS (deeper) — British, slightly lower register",
            "base_voice": "Daniel",
            "rate": 175,
            "pitch": -80,
            "bass": +2,
            "treble": 0,
            "overdrive": 0,
            "gain": -1,
        },
        "zoro": {
            "description": "Roronoa Zoro — deep, gruff, commanding",
            "base_voice": "Daniel",
            "rate": 162,
            "pitch": -300,
            "bass": +6,
            "treble": -2,
            "overdrive": 3,
            "gain": -3,
        },
        "zoro_light": {
            "description": "Zoro (lighter) — deep but clearer",
            "base_voice": "Daniel",
            "rate": 168,
            "pitch": -250,
            "bass": +4,
            "treble": -1,
            "overdrive": 1.5,
            "gain": -2,
        },
        "zoro_heavy": {
            "description": "Zoro (heavy) — maximum gruff beast mode",
            "base_voice": "Daniel",
            "rate": 155,
            "pitch": -380,
            "bass": +7,
            "treble": -3,
            "overdrive": 4,
            "gain": -4,
        },
        "default": {
            "description": "Default Jarvis voice — clean Daniel",
            "base_voice": "Daniel",
            "rate": 185,
            "pitch": 0,
            "bass": 0,
            "treble": 0,
            "overdrive": 0,
            "gain": 0,
        },
    }

    TMP_BASE = "/tmp/jarvis_tts_base.aiff"
    TMP_OUT = "/tmp/jarvis_tts_out.aiff"

    def __init__(self):
        cfg = config.load_config()
        self._tts_engine = cfg.get("tts_engine", "say") if IS_LINUX else "say"
        self._espeak_voice = cfg.get("espeak_voice", "en-gb")
        self._espeak_speed = cfg.get("espeak_speed", 170)
        profile_name = cfg.get("voice_profile", "zoro")
        self._profile_name = profile_name
        self._profile = self.VOICE_PROFILES.get(profile_name, self.VOICE_PROFILES["zoro"])
        self._voice = self._resolve_voice(cfg.get("voice_id", ""))
        self._rate = cfg.get("voice_rate", self._profile["rate"])
        self._lock = threading.Lock()
        self._process = None
        self._use_sox = self._has_sox() and self._profile["pitch"] != 0 and not IS_LINUX
        self._is_speaking = False

    def is_speaking(self):
        return self._is_speaking

    @staticmethod
    def _has_sox():
        try:
            subprocess.run(["sox", "--version"], capture_output=True)
            return True
        except FileNotFoundError:
            return False

    def _resolve_voice(self, voice_id):
        if not voice_id:
            return self._profile.get("base_voice", "Daniel")
        parts = voice_id.split(".")
        return parts[-1] if parts else "Daniel"

    def _speak_with_sox(self, text):
        """Generate speech -> sox pitch/effect pipeline -> play (macOS only)."""
        p = self._profile
        voice = p.get("base_voice", self._voice)
        rate = self._rate

        subprocess.run(
            ["say", "-v", voice, "-r", str(rate), "-o", self.TMP_BASE, text],
            capture_output=True,
        )

        effects = []
        if p["pitch"] != 0:
            effects += ["pitch", str(p["pitch"])]
        if p["bass"] != 0:
            effects += ["bass", str(p["bass"])]
        if p["treble"] != 0:
            effects += ["treble", str(p["treble"])]
        if p["overdrive"] > 0:
            effects += ["overdrive", str(p["overdrive"])]
        if p["gain"] != 0:
            effects += ["gain", str(p["gain"])]

        if effects:
            subprocess.run(
                ["sox", self.TMP_BASE, self.TMP_OUT] + effects,
                capture_output=True,
            )
            play_file = self.TMP_OUT
        else:
            play_file = self.TMP_BASE

        self._process = subprocess.Popen(["afplay", play_file])
        self._process.wait()

    def _speak_espeak(self, text):
        """Speak using espeak-ng (Linux/Pi)."""
        self._process = subprocess.Popen(
            ["espeak-ng", "-v", self._espeak_voice, "-s", str(self._espeak_speed), text]
        )
        self._process.wait()

    def speak(self, text):
        with self._lock:
            print(f"  JARVIS: {text}")
            self._is_speaking = True
            try:
                if IS_LINUX:
                    self._speak_espeak(text)
                elif self._use_sox:
                    self._speak_with_sox(text)
                else:
                    self._process = subprocess.Popen(
                        ["say", "-v", self._voice, "-r", str(self._rate), text]
                    )
                    self._process.wait()
            except Exception as e:
                print(f"  [TTS error: {e}]")
            finally:
                self._process = None
                time.sleep(0.4)
                self._is_speaking = False

    def speak_nonblocking(self, text):
        def _bg():
            self.speak(text)
        threading.Thread(target=_bg, daemon=True).start()

    def stop_speaking(self):
        if self._process:
            self._process.terminate()

    def set_voice(self, voice_name):
        self._voice = self._resolve_voice(voice_name)
        if self._profile_name == "default":
            self._use_sox = False
        print(f"  [Voice changed to: {self._voice}]")

    def set_rate(self, rate):
        self._rate = rate
        print(f"  [Speech rate changed to: {self._rate}]")

    def set_profile(self, profile_name):
        profile_name = profile_name.lower().strip()
        if profile_name in self.VOICE_PROFILES:
            self._profile_name = profile_name
            self._profile = self.VOICE_PROFILES[profile_name]
            self._voice = self._profile["base_voice"]
            self._rate = self._profile["rate"]
            self._use_sox = self._has_sox() and self._profile["pitch"] != 0
            config.set_key("voice_profile", profile_name)
            config.set_key("voice_rate", self._rate)
            print(f"  [Profile changed to: {profile_name}]")
            return True
        return False

    def get_voice(self):
        return self._voice

    def get_rate(self):
        return self._rate

    def get_profile_name(self):
        return self._profile_name

    def get_profile_names(self):
        return list(self.VOICE_PROFILES.keys())

    def get_profile_description(self, name):
        p = self.VOICE_PROFILES.get(name)
        return p["description"] if p else ""

    @staticmethod
    def list_voices():
        if IS_LINUX:
            result = subprocess.run(["espeak-ng", "--voices=en"], capture_output=True, text=True)
            voices = []
            for line in result.stdout.strip().split("\n")[1:]:
                parts = line.split()
                if len(parts) >= 4:
                    voices.append({
                        "name": parts[3],
                        "lang": parts[1],
                        "desc": parts[3],
                    })
            return voices
        result = subprocess.run(["say", "-v", "?"], capture_output=True, text=True)
        voices = []
        for line in result.stdout.strip().split("\n"):
            if line.strip():
                match = re.match(r'^(\S+(?:\s+\([^)]+\))?)\s+(\S+)\s+#\s*(.*)', line)
                if match:
                    voices.append({
                        "name": match.group(1).strip(),
                        "lang": match.group(2).strip(),
                        "desc": match.group(3).strip(),
                    })
        return voices



# (ClapDetector removed — was causing lag by competing for the mic and firing false positives)

_COMMAND_STARTERS = (
    "open", "close", "launch", "start", "play", "pause", "stop", "search",
    "set", "timer", "alarm", "remind", "what", "who", "when", "where",
    "tell", "show", "read", "click", "take", "send", "call", "find", "check",
    "volume", "mute", "lock", "note", "weather", "time", "date",
    "calculate", "convert", "directions", "navigate", "help",
    "make it", "full screen", "fullscreen", "scroll", "go back", "refresh",
    "reload", "press", "type ", "maximize", "walk me", "run through",
    "go through", "describe", "screenshot", "battery", "dark mode",
    "brightness",
)

def _looks_like_command(text):
    """
    True only if the text clearly starts with a Jarvis-specific action.
    Must be strict to avoid processing YouTube/media audio as commands.
    Removed: 'how' (too common in video dialogue), 'sleep' (ambiguous).
    """
    t = text.lower().strip(" .,!?")
    # Must start with a known command word
    if not any(t.startswith(s) for s in _COMMAND_STARTERS):
        return False
    # Extra guard: reject if text is too conversational (likely media audio)
    # Real commands are short and directive; video dialogue tends to be longer/narrative
    if len(t.split()) > 12:
        return False
    return True

# ─── Always-On Listener Thread ───────────────────────────────────────────────

class ListenerThread(QThread):
    """
    Continuously listens for the wake word with NO timeouts.
    Keeps the microphone open in a persistent stream.
    Auto-recalibrates ambient noise periodically.
    """

    state_changed = pyqtSignal(str)
    status_changed = pyqtSignal(str)
    heard_text = pyqtSignal(str)       # What the user said (recognized text)
    response_ready = pyqtSignal(str)
    exit_requested = pyqtSignal()

    def __init__(self, speech_engine):
        super().__init__()
        self._speech = speech_engine
        self._recognizer = sr.Recognizer()

        # Tuned for wake-word-only mode — Google STT gate handles media filtering
        # so energy threshold just needs to catch actual sound vs dead silence
        self._recognizer.energy_threshold = 400
        self._recognizer.dynamic_energy_threshold = True
        self._recognizer.dynamic_energy_adjustment_damping = 0.15
        self._recognizer.dynamic_energy_ratio = 1.5
        self._recognizer.pause_threshold = 1.0         # More silence needed to end phrase (captures full sentences)
        self._recognizer.phrase_threshold = 0.3        # Min speech length — filters micro-noises
        self._recognizer.non_speaking_duration = 0.6   # Slightly longer silence to end phrase

        self._running = True
        self._manual_activate = False
        self._mic = None
        self._last_recalibrate = 0
        self._last_activity = time.time()

        # Load Whisper model for local speech recognition (much better with accents)
        self._whisper_model = None
        self._load_whisper()

    def _load_whisper(self):
        """Load Whisper model — primary STT engine."""
        try:
            import whisper
            model_size = config.get("whisper_model") or "base.en"
            print(f"  [Loading Whisper '{model_size}' model...]")
            self._whisper_model = whisper.load_model(model_size)
            print(f"  [Whisper ready on {self._whisper_model.device} — primary STT]")
        except ImportError:
            print("  [⚠ Whisper not installed! Run: pip3 install openai-whisper]")
            print("  [Falling back to Google Speech API]")
        except Exception as e:
            print(f"  [Whisper load error: {e} — falling back to Google Speech API]")

    def manual_activate(self):
        self._manual_activate = True

    def stop(self):
        self._running = False

    def _preprocess_audio(self, audio):
        """
        Clean up raw audio before sending to STT:
        1. Bandpass filter (300-3400 Hz) — isolates human speech, cuts HVAC/fan/rumble
        2. Spectral noise reduction via noisereduce
        Returns a new AudioData object with cleaned audio, or original on error.
        """
        try:
            from scipy.signal import butter, sosfilt
            import struct

            sample_rate = audio.sample_rate
            sample_width = audio.sample_width

            # Convert raw audio bytes → numpy float array
            raw = audio.get_raw_data(convert_rate=sample_rate, convert_width=2)
            samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32)

            if len(samples) < 1000:
                return audio  # Too short to filter

            # ── 1. Bandpass filter: keep 300-3400 Hz (human speech band) ──
            nyq = sample_rate / 2
            low = 300 / nyq
            high = min(3400 / nyq, 0.99)
            sos = butter(5, [low, high], btype='band', output='sos')
            samples = sosfilt(sos, samples)

            # ── 2. Spectral noise reduction ──
            try:
                import noisereduce as nr
                samples = nr.reduce_noise(
                    y=samples, sr=sample_rate,
                    prop_decrease=0.7,     # Moderate — don't kill speech
                    stationary=True,       # Better for steady background noise (fans, AC)
                    n_fft=1024,
                )
            except ImportError:
                pass  # noisereduce not installed — bandpass alone still helps

            # ── 3. Normalize volume ──
            peak = np.max(np.abs(samples))
            if peak > 0:
                samples = samples * (28000 / peak)  # Normalize to ~85% of int16 range

            # Convert back to int16 bytes → AudioData
            samples = np.clip(samples, -32768, 32767).astype(np.int16)
            clean_bytes = samples.tobytes()

            return sr.AudioData(clean_bytes, sample_rate, 2)

        except Exception as e:
            print(f"  [Audio preprocess error: {e}] — using raw audio", flush=True)
            return audio

    def _is_mostly_silence(self, audio):
        """Quick check — reject only dead silence. Google STT wake word gate does the real filtering."""
        try:
            raw = audio.get_raw_data(convert_rate=16000, convert_width=2)
            samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
            rms = np.sqrt(np.mean(samples ** 2))
            if rms < 50:
                return True  # Dead silence only
            return False
        except Exception:
            return False

    def _recognize(self, audio):
        """
        Recognize speech from audio data.
        Pipeline: silence filter → noise reduction → bandpass → STT
        Priority: Groq Whisper API (cloud, if key set) → Local Whisper (primary, accurate)
                  → Google Speech (online fallback)
        """
        # 0. Quick silence/noise rejection before wasting STT calls
        if self._is_mostly_silence(audio):
            return None

        # 0b. Clean audio — bandpass + noise reduction
        audio = self._preprocess_audio(audio)

        # 1. Groq Whisper — free cloud, best accent handling, needs API key
        groq_key = config.get("groq_api_key")
        if groq_key:
            result = self._recognize_groq_whisper(audio, groq_key)
            if result:
                return result

        # 2. Local Whisper — PRIMARY recognizer, accurate, works offline
        if self._whisper_model:
            result = self._recognize_whisper(audio)
            if result:
                return result

        # 3. Google Speech API — online fallback if Whisper fails/unavailable
        google_result = self._recognize_google(audio)
        if google_result:
            return google_result

        return None

    def _recognize_groq_whisper(self, audio, api_key):
        """
        Groq Whisper API — free tier, very fast cloud transcription.
        Falls back silently to local Whisper on any error.
        """
        try:
            import tempfile, requests as _req
            wav_data = audio.get_wav_data(convert_rate=16000, convert_width=2)
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                f.write(wav_data)
                tmp_path = f.name
            with open(tmp_path, "rb") as f:
                resp = _req.post(
                    "https://api.groq.com/openai/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    files={"file": ("audio.wav", f, "audio/wav")},
                    data={"model": "whisper-large-v3-turbo", "language": "en"},
                    timeout=6
                )
            os.unlink(tmp_path)
            if resp.status_code == 200:
                text = resp.json().get("text", "").strip().lower()
                print(f"  [Groq STT: '{text}']", flush=True)
                return text or None
        except Exception as e:
            print(f"  [Groq STT fallback: {e}]", flush=True)
        return None

    def _recognize_whisper(self, audio):
        """Recognize using local Whisper model — PRIMARY STT, great with accents."""
        import tempfile

        try:
            # Convert SpeechRecognition audio to WAV bytes (16kHz mono, Whisper's native format)
            wav_data = audio.get_wav_data(convert_rate=16000, convert_width=2)

            # Write to temp file (Whisper needs a file path)
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                f.write(wav_data)
                tmp_path = f.name

            # Transcribe with Whisper — tuned for accuracy + hallucination rejection
            result = self._whisper_model.transcribe(
                tmp_path,
                language="en",
                fp16=False,                          # CPU-safe
                no_speech_threshold=0.4,             # Aggressive noise rejection
                logprob_threshold=-0.7,              # Filter low-confidence segments
                compression_ratio_threshold=1.8,     # Reject repetitive/looping output
                condition_on_previous_text=False,     # Each phrase independent
                temperature=0.0,                     # Greedy decoding — most accurate
            )
            text = result["text"].strip().lower()

            # Clean up temp file
            os.unlink(tmp_path)

            # Filter out Whisper hallucinations (empty/noise transcriptions)
            if not text or len(text) < 2:
                return None

            # ── Repetition detector: Whisper loops the same phrase on noise ──
            # Split into sentences and check if one phrase dominates
            import re as _re
            sentences = [s.strip() for s in _re.split(r'[.!?]+', text) if s.strip()]
            if len(sentences) >= 3:
                from collections import Counter
                counts = Counter(sentences)
                most_common, freq = counts.most_common(1)[0]
                if freq >= 3 or freq / len(sentences) > 0.5:
                    print(f"  [Whisper repetition hallucination filtered: '{most_common}' x{freq}]", flush=True)
                    return None

            # Whisper sometimes hallucinates these when there's just noise
            hallucinations = {
                "you", "thank you", "thanks for watching", "bye",
                "the", ".", "subscribe", "thank you for watching",
                "thanks", "so", "i", "hmm", "uh", "um",
                "pardon", "pardon?", "he does", "he does.",
                "yeah", "mm", "oh", "ah", "mhm", "okay",
                "job as", "jobs.", "you're welcome", "goodbye",
                "all right", "alright", "right", "you know",
                "...", "ha", "huh", "hi", "hey", "no",
                "yes", "yep", "nope", "well", "like", "just",
                "i'm sorry", "sorry", "oh my god", "thank you so much",
            }
            if text.strip(".!?, ") in hallucinations:
                print(f"  [Whisper hallucination filtered: '{text}']", flush=True)
                return None

            # Check for repeating phrases/n-grams within the text
            clean = text.strip(".!?, ")
            words = clean.split()
            if len(words) >= 8:
                # Check for any repeating n-gram (2-6 words) that appears 3+ times
                for n in range(2, 7):
                    ngrams = [" ".join(words[i:i+n]) for i in range(len(words) - n + 1)]
                    if ngrams:
                        from collections import Counter
                        ng_counts = Counter(ngrams)
                        top_ng, top_freq = ng_counts.most_common(1)[0]
                        if top_freq >= 3:
                            print(f"  [Whisper phrase-loop hallucination: '{top_ng}' x{top_freq}]", flush=True)
                            return None

            # Reject excessively long transcriptions — real speech rarely exceeds 40 words in 8s
            if len(words) > 50:
                print(f"  [Whisper suspiciously long ({len(words)} words) — likely hallucination]", flush=True)
                return None

            print(f"  [Whisper STT: '{text}']", flush=True)
            return text

        except Exception as e:
            print(f"  [Whisper error: {e}] — falling back to Google")
            return self._recognize_google(audio)

    def _recognize_google(self, audio):
        """Google Speech API — fast, free, no key needed. Primary STT when Groq key absent."""
        try:
            text = self._recognizer.recognize_google(audio).lower().strip()
            if not text:
                return None
            # Filter garbage transcriptions from ambient noise
            noise_words = {
                "you", "the", "a", "i", "oh", "ah", "um", "uh", "hmm",
                "mm", "mhm", "yeah", "so", "ok", "okay", "bye", "hi",
                "thanks", "thank you", "right", "all right", "alright",
                "huh", "ha", "he", "she", "it", "is", "was", "no",
                "yes", "yep", "nope", "well", "like", "just",
            }
            if text.strip(".,!? ") in noise_words:
                print(f"  [Google STT noise filtered: '{text}']", flush=True)
                return None
            print(f"  [Google STT: '{text}']", flush=True)
            return text
        except sr.UnknownValueError:
            return None
        except sr.RequestError as e:
            print(f"  [Google Speech API error: {e}]", flush=True)
            return None

    def _listen_continuous(self, source, phrase_time_limit=8):
        """
        Wake-word-only listener. Two-stage approach:
        1. Capture audio → quick Google STT check for wake word (fast, free)
        2. If wake word found → return text for full processing
        Ignores all non-wake-word audio (video, music, background chatter).
        """
        # Wait if Jarvis is currently speaking (prevents echo loop)
        while self._speech.is_speaking():
            time.sleep(0.1)

        try:
            audio = self._recognizer.listen(
                source,
                timeout=None,
                phrase_time_limit=phrase_time_limit,
            )
            if self._speech.is_speaking():
                return None

            # Quick silence/noise rejection
            if self._is_mostly_silence(audio):
                return None

            # Stage 1: Fast wake word check using Google STT
            # Google is instant and free — use it just to detect "jarvis"
            try:
                quick_text = self._recognizer.recognize_google(audio).lower().strip()
            except (sr.UnknownValueError, sr.RequestError):
                quick_text = ""

            if not quick_text:
                return None

            # Check if wake word is in the quick transcription
            # STRICT list — only words that are clearly "jarvis", not common words
            WAKE_WORDS_STRICT = (
                "jarvis", "javis", "jervis", "jarviz", "jarvi",
                "hey jarvis", "yo jarvis",
            )
            # LOOSE matches — only count if they appear at the START of the phrase
            # (prevents matching "service" in "customer service" etc.)
            WAKE_WORDS_START = (
                "java", "javas", "java's", "javaise",
                "travis", "service", "harvis",
            )
            has_wake = (
                any(w in quick_text for w in WAKE_WORDS_STRICT) or
                any(quick_text.startswith(w) for w in WAKE_WORDS_START)
            )

            if not has_wake:
                # No wake word — this is video/background audio, ignore completely
                return None

            # Wake word detected! Use Google's transcription directly (skip Whisper = faster)
            # Google already gave us usable text — no need for a second slower transcription
            print(f"  [Wake word detected: '{quick_text}']", flush=True)
            self.heard_text.emit(quick_text)
            return quick_text

        except sr.WaitTimeoutError:
            return None
        except OSError as e:
            print(f"  [Mic error: {e}] — will retry", flush=True)
            time.sleep(0.5)
            return None

    def _listen_for_command(self, source):
        """
        Listen for a command AFTER wake word — speakers are muted, use Google STT for speed.
        """
        try:
            audio = self._recognizer.listen(
                source,
                timeout=5,             # 5s timeout — if nothing, give up
                phrase_time_limit=15,  # Allow long commands
            )
            # Speakers are muted so no noise — use Google STT directly (fastest)
            try:
                text = self._recognizer.recognize_google(audio).lower().strip()
            except sr.UnknownValueError:
                text = None
            except sr.RequestError:
                # Google failed, fall back to Whisper
                text = self._recognize(audio)

            if text:
                print(f"  Command: '{text}'", flush=True)
                self.heard_text.emit(text)
            return text
        except sr.WaitTimeoutError:
            print(f"  [No command heard — timed out]", flush=True)
            return None
        except OSError as e:
            print(f"  [Mic error: {e}]", flush=True)
            return None

    def _maybe_recalibrate(self, source):
        """Re-adjust for ambient noise every 2 minutes with longer sampling."""
        now = time.time()
        if now - self._last_recalibrate > 120:
            self._recognizer.adjust_for_ambient_noise(source, duration=1.0)
            # Enforce floor after recalibration too
            if self._recognizer.energy_threshold < 200:
                self._recognizer.energy_threshold = 400
            self._last_recalibrate = now
            print(f"  [Recalibrated: energy_threshold={self._recognizer.energy_threshold:.0f}]", flush=True)

    def _speak_and_signal(self, text):
        self.state_changed.emit("speaking")
        self.response_ready.emit(text)
        self._speech.speak(text)

    def _handle_command(self, command, source):
        """Process command, handle control signals, return should_continue."""
        self._last_activity = time.time()   # Reset dormant timer on every interaction
        self.state_changed.emit("processing")
        self.status_changed.emit(f'Heard: "{command[:35]}..."' if len(command) > 35 else f'Heard: "{command}"')

        response, should_continue = process_command(command)

        if response:
            profile_match = re.match(r'__PROFILE_CHANGE__(.+?)__(.*)', response)
            voice_match = re.match(r'__VOICE_CHANGE__(.+?)__(.*)', response)
            speed_match = re.match(r'__SPEED_CHANGE__(\d+)__(.*)', response)

            if profile_match:
                self._speech.set_profile(profile_match.group(1))
                self._speak_and_signal(profile_match.group(2))
            elif voice_match:
                self._speech.set_voice(voice_match.group(1))
                self._speak_and_signal(voice_match.group(2))
            elif speed_match:
                self._speech.set_rate(int(speed_match.group(1)))
                self._speak_and_signal(speed_match.group(2))
            else:
                self._speak_and_signal(response)

        return should_continue

    def run(self):
        """
        Main listener loop — always-on, wake-word activated.
        Simple architecture: listen → detect wake word → process command.
        No dormant mode, no clap detection — just fast, responsive voice.
        """

        # Initial calibration
        self.status_changed.emit("Calibrating microphone...")
        print("  [Calibrating microphone for ambient noise...]", flush=True)

        with sr.Microphone() as source:
            self._recognizer.adjust_for_ambient_noise(source, duration=2.0)
            self._last_recalibrate = time.time()

        # Guard against degenerate calibration
        if self._recognizer.energy_threshold < 200:
            print(f"  [⚠ Low energy threshold ({self._recognizer.energy_threshold:.0f}) — "
                  f"forcing floor to 400]", flush=True)
            self._recognizer.energy_threshold = 400

        print(f"  [Mic calibrated. energy_threshold={self._recognizer.energy_threshold:.0f}]", flush=True)
        print(f"  [Always listening. Wake word: '{WAKE_WORD}']\n", flush=True)

        # Greet
        hour = datetime.datetime.now().hour
        if hour < 12:
            greeting = f"Good morning, {OWNER_NAME}."
        elif hour < 17:
            greeting = f"Good afternoon, {OWNER_NAME}."
        elif hour < 21:
            greeting = f"Good evening, {OWNER_NAME}."
        else:
            greeting = f"Good night, {OWNER_NAME}."

        self._speak_and_signal(greeting)
        self._speak_and_signal("Jarvis at your service.")
        self.state_changed.emit("idle")

        FUZZY_WAKE = (
            WAKE_WORD, "javis", "jervis", "jarvi", "jarviz",
            "service", "starvis", "charles", "travis",
            "job as", "jobs", "javos", "jobless", "java",
            "drivers", "driver", "harvest", "harvis",
            "hey jarvis", "hey javis", "yo jarvis",
            "joe this", "joe's", "joe is", "jobs this",
            "jarvis", "carvis", "garvis", "tarvis",
        )

        def _mute_system():
            try:
                if IS_LINUX:
                    subprocess.run(["amixer", "set", "Headphone", "mute"],
                                  capture_output=True, timeout=2)
                else:
                    subprocess.run(["osascript", "-e", "set volume with output muted"],
                                  capture_output=True, timeout=2)
            except Exception:
                pass

        def _unmute_system():
            try:
                if IS_LINUX:
                    subprocess.run(["amixer", "set", "Headphone", "unmute"],
                                  capture_output=True, timeout=2)
                else:
                    subprocess.run(["osascript", "-e", "set volume without output muted"],
                                  capture_output=True, timeout=2)
            except Exception:
                pass

        def _get_volume():
            try:
                if IS_LINUX:
                    r = subprocess.run(["amixer", "get", "Headphone"],
                                      capture_output=True, text=True, timeout=2)
                    match = re.search(r'\[(\d+)%\]', r.stdout)
                    return int(match.group(1)) if match else None
                r = subprocess.run(["osascript", "-e", "output volume of (get volume settings)"],
                                  capture_output=True, text=True, timeout=2)
                return int(r.stdout.strip())
            except Exception:
                return None

        # ─── Persistent microphone loop ──────────────────────────
        while self._running:
            try:
                with sr.Microphone() as source:
                    while self._running:

                        # ── Manual button activate (always works) ────────
                        if self._manual_activate:
                            self._manual_activate = False
                            self._last_activity = time.time()
                            _mute_system()  # Mute speakers so we can hear clearly
                            self._speech.speak_nonblocking("Yes?")
                            self.state_changed.emit("listening")
                            command = self._listen_for_command(source)
                            _unmute_system()
                            if command and not self._handle_command(command, source):
                                self.exit_requested.emit(); return
                            self.state_changed.emit("idle")
                            continue

                        # ── Always-on listening ─────────────────────────
                        self._maybe_recalibrate(source)
                        text = self._listen_continuous(source, phrase_time_limit=3)
                        if not text:
                            continue

                        wake_fuzzy = any(w in text for w in FUZZY_WAKE)

                        if wake_fuzzy:
                            self._last_activity = time.time()
                            # MUTE speakers immediately so we can hear the command
                            _mute_system()
                            print(f"  [Wake word detected — speakers muted]", flush=True)

                            # Extract command after wake word
                            after_wake = text
                            for w in FUZZY_WAKE:
                                if w in after_wake:
                                    after_wake = after_wake.split(w, 1)[1]
                                    break
                            after_wake = re.sub(r'^[^a-zA-Z]+', '', after_wake).strip()

                            if after_wake and len(after_wake) > 2:
                                # Wake word + inline command: "Jarvis open youtube"
                                if not self._handle_command(after_wake, source):
                                    _unmute_system()
                                    self.exit_requested.emit(); return
                                _unmute_system()
                            else:
                                # Just wake word: "Jarvis" → wait for command
                                self._speech.speak_nonblocking("Yes?")
                                self.state_changed.emit("listening")
                                command = self._listen_for_command(source)
                                _unmute_system()
                                if command and not self._handle_command(command, source):
                                    self.exit_requested.emit(); return

                            # Cooldown after unmute — flush mic buffer so video audio
                            # doesn't immediately trigger a false wake word
                            self.state_changed.emit("idle")
                            time.sleep(1.0)
                            # Flush any audio that accumulated during cooldown
                            try:
                                self._recognizer.listen(source, timeout=0.5, phrase_time_limit=0.5)
                            except (sr.WaitTimeoutError, OSError):
                                pass

                        # No wake word — ignore (video audio, background noise, etc.)

            except OSError as e:
                print(f"  [Microphone error: {e}] — reconnecting in 2s...", flush=True)
                self.status_changed.emit("Mic error — reconnecting...")
                time.sleep(2)
            except Exception as e:
                print(f"  [Listener error: {e}] — restarting loop...", flush=True)
                time.sleep(1)


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    acquire_lock()
    atexit.register(release_lock)

    signal.signal(signal.SIGINT, signal.SIG_DFL)
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))

    cfg = config.load_config()
    headless = cfg.get("headless", False)

    speech = SpeechEngine()

    if headless:
        listener = ListenerThread(speech)
        listener.start()
        print("  [Running in headless mode — no GUI]")
        try:
            while listener.isRunning():
                time.sleep(1)
        except (KeyboardInterrupt, SystemExit):
            pass
        listener.stop()
        listener.wait(3000)
        release_lock()
        sys.exit(0)

    from PyQt6.QtWidgets import QApplication
    from ui import JarvisWidget

    app = QApplication(sys.argv)
    app.setApplicationName("JARVIS")

    try:
        from Foundation import NSBundle
        info = NSBundle.mainBundle().infoDictionary()
        info["LSBackgroundOnly"] = "0"
        info["LSUIElement"] = "1"
    except ImportError:
        pass

    widget = JarvisWidget(speech_engine=speech)
    widget.show()

    listener = ListenerThread(speech)
    listener.state_changed.connect(widget.set_state)
    listener.status_changed.connect(widget.set_status)
    listener.heard_text.connect(widget.set_heard)
    listener.response_ready.connect(widget.set_response)
    listener.exit_requested.connect(app.quit)

    widget.activate_signal.connect(listener.manual_activate)

    listener.start()

    exit_code = app.exec()
    listener.stop()
    listener.wait(3000)
    release_lock()
    sys.exit(exit_code)


if __name__ == "__main__":
    print("=" * 50)
    print("  J.A.R.V.I.S. Personal Assistant")
    print("  Say 'Jarvis' to activate or click the reactor.")
    print("  Say 'Goodbye' to exit.")
    print("=" * 50)
    print()
    main()
