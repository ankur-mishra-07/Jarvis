"""
J.A.R.V.I.S. WebSocket Voice Handler — real-time audio streaming.
Manages per-connection state: audio buffering, VAD, transcription, response.
"""

import asyncio
import base64
import json
import time
import threading

from fastapi import WebSocket, WebSocketDisconnect

from server.audio import STTEngine
from server.tts import TTSEngine


class VoiceSession:
    """
    Per-connection voice session. Handles:
    - Audio chunk accumulation
    - Voice Activity Detection (energy-based)
    - STT transcription
    - Command processing
    - TTS response
    """

    def __init__(self, stt_engine: STTEngine, tts_engine: TTSEngine, command_lock: threading.Lock):
        self.stt = stt_engine
        self.tts = tts_engine
        self._command_lock = command_lock
        self._audio_buffer = bytearray()
        self._is_speaking = False
        self._silence_frames = 0
        self._speech_frames = 0
        self._connected_at = time.time()

        # VAD config
        self.SILENCE_THRESHOLD = 500       # RMS below this = silence
        self.SPEECH_START_FRAMES = 3       # Frames of speech to start recording
        self.SILENCE_END_FRAMES = 15       # Frames of silence to stop recording
        self.MIN_AUDIO_BYTES = 6400        # Minimum audio to transcribe (0.2s at 16kHz)
        self.MAX_AUDIO_BYTES = 480000      # Maximum audio buffer (15s at 16kHz)

    async def handle(self, websocket: WebSocket):
        """Main WebSocket handler loop."""
        from commands import process_command

        await websocket.accept()
        await self._send(websocket, "status", text="Connected to J.A.R.V.I.S.")

        try:
            while True:
                data = await websocket.receive()

                if "text" in data:
                    msg = json.loads(data["text"])
                    await self._handle_text_message(websocket, msg, process_command)

                elif "bytes" in data:
                    await self._handle_audio_chunk(websocket, data["bytes"], process_command)

        except WebSocketDisconnect:
            print(f"  [WS client disconnected after {time.time() - self._connected_at:.0f}s]")
        except Exception as e:
            print(f"  [WS error: {e}]")
            try:
                await self._send(websocket, "error", text=str(e))
            except Exception:
                pass

    async def _handle_text_message(self, ws: WebSocket, msg: dict, process_command):
        """Handle text-based WebSocket messages."""
        msg_type = msg.get("type", "")

        if msg_type == "text":
            # Direct text command
            text = msg.get("text", "").strip()
            if text:
                await self._send(ws, "transcript", text=text)
                response, should_continue = await self._process_command(text, process_command)
                await self._send(ws, "response", text=response or "")

                # Generate TTS audio
                if response:
                    audio_bytes = self.tts.synthesize(response)
                    if audio_bytes:
                        await self._send_audio(ws, audio_bytes)

                if not should_continue:
                    await self._send(ws, "status", text="Session ended by command")

        elif msg_type == "end_of_speech":
            # Client signals end of push-to-talk
            await self._finalize_audio(ws, process_command)

        elif msg_type == "ping":
            await self._send(ws, "pong")

        elif msg_type == "audio":
            # Base64-encoded audio chunk
            audio_b64 = msg.get("data", "")
            if audio_b64:
                chunk = base64.b64decode(audio_b64)
                await self._handle_audio_chunk(ws, chunk, process_command)

    async def _handle_audio_chunk(self, ws: WebSocket, chunk: bytes, process_command):
        """Process an incoming audio chunk with simple VAD."""
        import numpy as np

        # Calculate RMS energy
        try:
            samples = np.frombuffer(chunk, dtype=np.int16).astype(np.float32)
            rms = np.sqrt(np.mean(samples ** 2)) if len(samples) > 0 else 0
        except Exception:
            rms = 0

        if rms > self.SILENCE_THRESHOLD:
            # Speech detected
            self._speech_frames += 1
            self._silence_frames = 0

            if self._speech_frames >= self.SPEECH_START_FRAMES:
                self._is_speaking = True

            if self._is_speaking:
                self._audio_buffer.extend(chunk)

                # Prevent runaway buffers
                if len(self._audio_buffer) > self.MAX_AUDIO_BYTES:
                    await self._finalize_audio(ws, process_command)

        else:
            # Silence
            self._silence_frames += 1

            if self._is_speaking:
                self._audio_buffer.extend(chunk)  # Keep trailing silence

                if self._silence_frames >= self.SILENCE_END_FRAMES:
                    # Speech ended — process
                    await self._finalize_audio(ws, process_command)

            self._speech_frames = 0

    async def _finalize_audio(self, ws: WebSocket, process_command):
        """Transcribe buffered audio and process the command."""
        if len(self._audio_buffer) < self.MIN_AUDIO_BYTES:
            self._reset_vad()
            return

        # Copy and reset buffer
        audio_data = bytes(self._audio_buffer)
        self._reset_vad()

        await self._send(ws, "status", text="Processing speech...")

        # Transcribe
        text = self.stt.transcribe(audio_data, sample_rate=16000)
        if not text:
            await self._send(ws, "status", text="Couldn't understand audio")
            return

        await self._send(ws, "transcript", text=text)

        # Process command
        response, should_continue = await self._process_command(text, process_command)
        await self._send(ws, "response", text=response or "I didn't catch that.")

        # TTS response
        if response:
            audio_bytes = self.tts.synthesize(response)
            if audio_bytes:
                await self._send_audio(ws, audio_bytes)

        if not should_continue:
            await self._send(ws, "status", text="Session ended")

    async def _process_command(self, text: str, process_command) -> tuple:
        """Thread-safe command processing."""
        loop = asyncio.get_event_loop()
        with self._command_lock:
            return await loop.run_in_executor(
                None, lambda: process_command(text, source="api")
            )

    def _reset_vad(self):
        """Reset VAD state."""
        self._audio_buffer = bytearray()
        self._is_speaking = False
        self._silence_frames = 0
        self._speech_frames = 0

    @staticmethod
    async def _send(ws: WebSocket, msg_type: str, text: str = "", data: str = ""):
        """Send a typed JSON message."""
        await ws.send_json({
            "type": msg_type,
            "text": text,
            "data": data,
            "timestamp": time.time(),
        })

    @staticmethod
    async def _send_audio(ws: WebSocket, audio_bytes: bytes):
        """Send audio as base64-encoded message."""
        await ws.send_json({
            "type": "audio",
            "data": base64.b64encode(audio_bytes).decode("ascii"),
            "format": "wav",
            "timestamp": time.time(),
        })
