"""
J.A.R.V.I.S. Audio Processing Engine — extracted from jarvis.py.
Reusable STT pipeline for both local mic and API audio input.
"""
from __future__ import annotations

import os
import tempfile
import numpy as np
import config


class STTEngine:
    """
    Speech-to-Text engine. Handles:
    - Audio preprocessing (bandpass filter + noise reduction)
    - Whisper (local), Groq Whisper (cloud), Google STT
    - Hallucination filtering
    """

    def __init__(self, whisper_model_name=None):
        self._whisper_model = None
        self._model_name = whisper_model_name or config.get("whisper_model") or "base.en"
        self._load_whisper()

    def _load_whisper(self):
        """Load local Whisper model."""
        try:
            import whisper
            print(f"  [Loading Whisper model: {self._model_name}]", flush=True)
            self._whisper_model = whisper.load_model(self._model_name)
            print("  [Whisper model loaded]", flush=True)
        except Exception as e:
            print(f"  [Whisper unavailable: {e}]", flush=True)
            self._whisper_model = None

    @property
    def has_whisper(self):
        return self._whisper_model is not None

    # ─── Audio Preprocessing ─────────────────────────────────────────────────

    def preprocess_audio_bytes(self, raw_bytes: bytes, sample_rate: int = 16000) -> bytes:
        """
        Clean raw PCM audio bytes (16-bit signed):
        1. Bandpass filter 300-3400 Hz (human speech band)
        2. Spectral noise reduction
        3. Volume normalization
        Returns cleaned PCM bytes.
        """
        try:
            from scipy.signal import butter, sosfilt

            samples = np.frombuffer(raw_bytes, dtype=np.int16).astype(np.float32)
            if len(samples) < 1000:
                return raw_bytes

            # Bandpass 300-3400 Hz
            nyq = sample_rate / 2
            low = 300 / nyq
            high = min(3400 / nyq, 0.99)
            sos = butter(5, [low, high], btype='band', output='sos')
            samples = sosfilt(sos, samples)

            # Spectral noise reduction
            try:
                import noisereduce as nr
                samples = nr.reduce_noise(
                    y=samples, sr=sample_rate,
                    prop_decrease=0.7,
                    stationary=True,
                    n_fft=1024,
                )
            except ImportError:
                pass

            # Normalize volume
            peak = np.max(np.abs(samples))
            if peak > 0:
                samples = samples * (28000 / peak)

            samples = np.clip(samples, -32768, 32767).astype(np.int16)
            return samples.tobytes()

        except Exception as e:
            print(f"  [Audio preprocess error: {e}]", flush=True)
            return raw_bytes

    def is_silence(self, raw_bytes: bytes, threshold: float = 50.0) -> bool:
        """Check if audio is dead silence (RMS below threshold)."""
        try:
            samples = np.frombuffer(raw_bytes, dtype=np.int16).astype(np.float32)
            rms = np.sqrt(np.mean(samples ** 2))
            return rms < threshold
        except Exception:
            return False

    # ─── Transcription ───────────────────────────────────────────────────────

    def transcribe(self, audio_bytes: bytes, sample_rate: int = 16000) -> str | None:
        """
        Full STT pipeline: preprocess → Groq Whisper (cloud) → Local Whisper → Google.
        Accepts raw PCM 16-bit mono audio bytes.
        Returns transcribed text or None.
        """
        if self.is_silence(audio_bytes):
            return None

        # Preprocess
        clean = self.preprocess_audio_bytes(audio_bytes, sample_rate)

        # Write to temp WAV for transcription
        wav_bytes = self._pcm_to_wav(clean, sample_rate)

        # 1. Groq Whisper (cloud, fast)
        groq_key = config.get("groq_api_key")
        if groq_key:
            result = self._transcribe_groq(wav_bytes, groq_key)
            if result:
                return result

        # 2. Local Whisper
        if self._whisper_model:
            result = self._transcribe_whisper(wav_bytes)
            if result:
                return result

        # 3. Google STT (fallback)
        result = self._transcribe_google(wav_bytes)
        return result

    def transcribe_wav(self, wav_bytes: bytes) -> str | None:
        """Transcribe from WAV format directly (for audio file uploads)."""
        # Extract PCM from WAV for silence check
        try:
            import wave
            import io
            with wave.open(io.BytesIO(wav_bytes), 'rb') as wf:
                pcm = wf.readframes(wf.getnframes())
                sr = wf.getframerate()
            if self.is_silence(pcm):
                return None
        except Exception:
            pass

        # Try backends
        groq_key = config.get("groq_api_key")
        if groq_key:
            result = self._transcribe_groq(wav_bytes, groq_key)
            if result:
                return result

        if self._whisper_model:
            result = self._transcribe_whisper(wav_bytes)
            if result:
                return result

        return self._transcribe_google(wav_bytes)

    # ─── Backend: Groq Whisper ───────────────────────────────────────────────

    def _transcribe_groq(self, wav_bytes: bytes, api_key: str) -> str | None:
        """Groq Whisper API — free cloud transcription."""
        try:
            import requests
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                f.write(wav_bytes)
                tmp_path = f.name

            with open(tmp_path, "rb") as f:
                resp = requests.post(
                    "https://api.groq.com/openai/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    files={"file": ("audio.wav", f, "audio/wav")},
                    data={"model": "whisper-large-v3-turbo", "language": "en"},
                    timeout=6
                )
            os.unlink(tmp_path)

            if resp.status_code == 200:
                text = resp.json().get("text", "").strip().lower()
                if text and not self._is_hallucination(text):
                    print(f"  [Groq STT: '{text}']", flush=True)
                    return text
        except Exception as e:
            print(f"  [Groq STT error: {e}]", flush=True)
        return None

    # ─── Backend: Local Whisper ──────────────────────────────────────────────

    def _transcribe_whisper(self, wav_bytes: bytes) -> str | None:
        """Local Whisper model transcription with hallucination filtering."""
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                f.write(wav_bytes)
                tmp_path = f.name

            result = self._whisper_model.transcribe(
                tmp_path,
                language="en",
                fp16=False,
                no_speech_threshold=0.4,
                logprob_threshold=-0.7,
                compression_ratio_threshold=1.8,
                condition_on_previous_text=False,
                temperature=0.0,
            )
            text = result["text"].strip().lower()
            os.unlink(tmp_path)

            if not text or len(text) < 2:
                return None

            if self._is_hallucination(text):
                print(f"  [Whisper hallucination filtered: '{text}']", flush=True)
                return None

            print(f"  [Whisper STT: '{text}']", flush=True)
            return text

        except Exception as e:
            print(f"  [Whisper error: {e}]", flush=True)
            return None

    # ─── Backend: Google STT ─────────────────────────────────────────────────

    def _transcribe_google(self, wav_bytes: bytes) -> str | None:
        """Google Speech API — free, fast, online fallback."""
        try:
            import speech_recognition as sr
            recognizer = sr.Recognizer()
            audio = sr.AudioData(wav_bytes, 16000, 2)
            text = recognizer.recognize_google(audio).lower().strip()

            if not text:
                return None

            noise_words = {
                "you", "the", "a", "i", "oh", "ah", "um", "uh", "hmm",
                "mm", "mhm", "yeah", "so", "ok", "okay", "bye", "hi",
                "thanks", "thank you", "right", "all right", "alright",
                "huh", "ha", "he", "she", "it", "is", "was", "no",
                "yes", "yep", "nope", "well", "like", "just",
            }
            if text.strip(".,!? ") in noise_words:
                return None

            print(f"  [Google STT: '{text}']", flush=True)
            return text
        except Exception:
            return None

    # ─── Hallucination Detection ─────────────────────────────────────────────

    def _is_hallucination(self, text: str) -> bool:
        """Detect Whisper hallucination patterns."""
        import re
        from collections import Counter

        # Known hallucination phrases
        hallucinations = {
            "you", "thank you", "thanks for watching", "bye",
            "the", ".", "subscribe", "thank you for watching",
            "thanks", "so", "i", "hmm", "uh", "um",
            "pardon", "he does", "yeah", "mm", "oh", "ah",
            "mhm", "okay", "you're welcome", "goodbye",
            "all right", "alright", "right", "you know",
            "...", "ha", "huh", "hi", "hey", "no",
            "yes", "yep", "nope", "well", "like", "just",
            "i'm sorry", "sorry", "oh my god", "thank you so much",
        }
        if text.strip(".!?, ") in hallucinations:
            return True

        # Sentence repetition (3+ repeats)
        sentences = [s.strip() for s in re.split(r'[.!?]+', text) if s.strip()]
        if len(sentences) >= 3:
            counts = Counter(sentences)
            _, freq = counts.most_common(1)[0]
            if freq >= 3 or freq / len(sentences) > 0.5:
                return True

        # N-gram loop detection
        words = text.strip(".!?, ").split()
        if len(words) >= 8:
            for n in range(2, 7):
                ngrams = [" ".join(words[i:i+n]) for i in range(len(words) - n + 1)]
                if ngrams:
                    ng_counts = Counter(ngrams)
                    _, top_freq = ng_counts.most_common(1)[0]
                    if top_freq >= 3:
                        return True

        # Excessively long = hallucination
        if len(words) > 50:
            return True

        return False

    # ─── Utilities ───────────────────────────────────────────────────────────

    @staticmethod
    def _pcm_to_wav(pcm_bytes: bytes, sample_rate: int = 16000) -> bytes:
        """Convert raw PCM 16-bit mono to WAV format."""
        import struct
        import io
        import wave

        buf = io.BytesIO()
        with wave.open(buf, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(sample_rate)
            wf.writeframes(pcm_bytes)
        return buf.getvalue()

    @staticmethod
    def convert_to_pcm16k(audio_bytes: bytes, input_format: str = "wav") -> bytes:
        """
        Convert audio bytes from any format to 16kHz 16-bit mono PCM.
        Uses ffmpeg for format conversion.
        """
        with tempfile.NamedTemporaryFile(suffix=f".{input_format}", delete=False) as fin:
            fin.write(audio_bytes)
            in_path = fin.name

        out_path = in_path + ".wav"
        try:
            import subprocess
            subprocess.run([
                "ffmpeg", "-y", "-i", in_path,
                "-ar", "16000", "-ac", "1", "-sample_fmt", "s16",
                out_path
            ], capture_output=True, timeout=10)

            with open(out_path, "rb") as f:
                return f.read()
        except Exception as e:
            print(f"  [Audio conversion error: {e}]", flush=True)
            return audio_bytes
        finally:
            for p in [in_path, out_path]:
                try:
                    os.unlink(p)
                except OSError:
                    pass
