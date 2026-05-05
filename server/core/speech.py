"""STT and TTS helpers.

Thin wrappers around the same libraries the laptop Jarvis uses
(`speech_recognition`, `pyttsx3`). Both are run in worker threads so they
don't block the FastAPI event loop.
"""

from __future__ import annotations

import asyncio
import io
import os
import tempfile
import wave


async def transcribe_audio_bytes(stream: io.BytesIO, sample_rate: int = 16000) -> str:
    """Transcribe a chunk of audio. Accepts either a WAV file or raw PCM16 mono.

    Falls back to a stub when SpeechRecognition can't reach a backend so the
    rest of the pipeline stays exercisable in dev.
    """

    def _run() -> str:
        try:
            import speech_recognition as sr
        except Exception:
            return ""

        data = stream.getvalue() if hasattr(stream, "getvalue") else stream.read()

        # If it looks like a WAV header, use as-is. Otherwise wrap raw PCM16
        # into a WAV in a temp file (SpeechRecognition needs a file-like WAV).
        is_wav = len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WAVE"

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = tmp.name
            if is_wav:
                tmp.write(data)
            else:
                with wave.open(tmp, "wb") as wav:
                    wav.setnchannels(1)
                    wav.setsampwidth(2)
                    wav.setframerate(sample_rate)
                    wav.writeframes(data)

        try:
            recognizer = sr.Recognizer()
            with sr.AudioFile(tmp_path) as src:
                audio = recognizer.record(src)
            try:
                return recognizer.recognize_google(audio)
            except Exception:
                return ""
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    return await asyncio.to_thread(_run)


async def synthesize_speech(text: str, voice: str | None = None) -> tuple[bytes, str]:
    """Render `text` to audio bytes. Returns (audio_bytes, mime_type).

    Uses pyttsx3 (offline) by default. If pyttsx3 isn't usable, returns a
    short silent WAV so callers don't have to special-case failures.
    """

    def _run() -> tuple[bytes, str]:
        try:
            import pyttsx3
        except Exception:
            return _silent_wav(), "audio/wav"

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            path = tmp.name

        try:
            engine = pyttsx3.init()
            if voice:
                for v in engine.getProperty("voices"):
                    if voice.lower() in (v.id or "").lower() or voice.lower() in (v.name or "").lower():
                        engine.setProperty("voice", v.id)
                        break
            engine.save_to_file(text, path)
            engine.runAndWait()
            with open(path, "rb") as f:
                return f.read(), "audio/wav"
        except Exception:
            return _silent_wav(), "audio/wav"
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass

    return await asyncio.to_thread(_run)


def _silent_wav(duration_s: float = 0.2, sample_rate: int = 16000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(b"\x00\x00" * int(duration_s * sample_rate))
    return buf.getvalue()
