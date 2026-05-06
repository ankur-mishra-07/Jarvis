"""
J.A.R.V.I.S. API Server — FastAPI application.
REST + WebSocket endpoints for mobile/web clients.

Usage:
    python -m server.app                    # Standalone server
    python jarvis.py --server               # Server-only mode
    python jarvis.py --dual                 # Local voice + server
"""
from __future__ import annotations

import os
import sys
import time
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, UploadFile, File, Form, WebSocket, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from server.auth import verify_api_key, verify_ws_api_key, mask_key
from server.models import (
    ChatRequest, ChatResponse, CommandResponse,
    StatusResponse, ConfigResponse, ConfigUpdateRequest,
    HistoryResponse, ConversationEntry,
)
from server.audio import STTEngine
from server.tts import TTSEngine
from server.ws_handler import VoiceSession

# ─── Shared State ────────────────────────────────────────────────────────────

_start_time = time.time()
_stt_engine: STTEngine | None = None
_tts_engine: TTSEngine | None = None
_command_lock = threading.Lock()
_local_listener_active = False  # True when running in --dual mode


def set_local_listener_active(active: bool):
    global _local_listener_active
    _local_listener_active = active


# ─── Lifespan ────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize engines on startup, clean up on shutdown."""
    global _stt_engine, _tts_engine

    print("  [Server] Initializing STT engine...", flush=True)
    _stt_engine = STTEngine()
    _tts_engine = TTSEngine()
    print("  [Server] Ready.", flush=True)

    yield  # App runs

    print("  [Server] Shutting down.", flush=True)


# ─── App ─────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="J.A.R.V.I.S. API",
    description="Voice assistant REST + WebSocket API",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — allow mobile app from any origin (single-user assistant)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve TTS audio files if needed
_audio_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "tts_cache")
os.makedirs(_audio_dir, exist_ok=True)


# ─── REST Endpoints ──────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return {"name": "J.A.R.V.I.S.", "status": "online", "version": "1.0.0"}


@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, _=Depends(verify_api_key)):
    """
    Text-based chat/command. Accepts a text message, routes through the
    command pipeline, returns response text + optional TTS audio.
    """
    from commands import process_command

    with _command_lock:
        response, should_continue = process_command(req.text, source="api")

    result = ChatResponse(
        response=response,
        should_continue=should_continue,
        source="api",
    )

    # Generate TTS audio if requested
    if response and _tts_engine:
        audio_bytes = _tts_engine.synthesize(response)
        if audio_bytes:
            # Save to cache and return URL
            import hashlib
            fname = hashlib.md5(response.encode()).hexdigest()[:12] + ".wav"
            fpath = os.path.join(_audio_dir, fname)
            with open(fpath, "wb") as f:
                f.write(audio_bytes)
            result.audio_url = f"/audio/{fname}"

    return result


@app.post("/api/command", response_model=CommandResponse)
async def command(
    audio: UploadFile = File(None),
    text: str = Form(None),
    format: str = Form("wav"),
    _=Depends(verify_api_key),
):
    """
    Voice command endpoint. Accepts either:
    - Audio file (multipart upload) — transcribed then processed
    - Text (form field) — processed directly
    """
    from commands import process_command

    transcript = None

    if audio:
        # Read uploaded audio
        audio_bytes = await audio.read()
        if not audio_bytes:
            raise HTTPException(status_code=400, detail="Empty audio file")

        # Convert to WAV if needed
        if format.lower() not in ("wav", "wave"):
            audio_bytes = STTEngine.convert_to_pcm16k(audio_bytes, format)

        # Transcribe
        transcript = _stt_engine.transcribe_wav(audio_bytes)
        if not transcript:
            return CommandResponse(
                transcript=None,
                response="Sorry, I couldn't understand the audio.",
                should_continue=True,
            )
    elif text:
        transcript = text
    else:
        raise HTTPException(status_code=400, detail="Provide either 'audio' file or 'text' field")

    # Process command
    with _command_lock:
        response, should_continue = process_command(transcript, source="api")

    result = CommandResponse(
        transcript=transcript,
        response=response,
        should_continue=should_continue,
    )

    # TTS
    if response and _tts_engine:
        audio_bytes = _tts_engine.synthesize(response)
        if audio_bytes:
            import hashlib
            fname = hashlib.md5(response.encode()).hexdigest()[:12] + ".wav"
            fpath = os.path.join(_audio_dir, fname)
            with open(fpath, "wb") as f:
                f.write(audio_bytes)
            result.audio_url = f"/audio/{fname}"

    return result


@app.get("/api/status", response_model=StatusResponse)
async def status(_=Depends(verify_api_key)):
    """System status: uptime, active LLM, voice profile, etc."""
    import brain

    return StatusResponse(
        status="running",
        version="1.0.0",
        active_backend=brain.active_backend_name(),
        llm_configured=brain.is_configured(),
        uptime_seconds=round(time.time() - _start_time, 1),
        owner_name=config.get("owner_name") or "Boss",
        wake_word=config.get("wake_word") or "jarvis",
        voice_profile=config.get("voice_profile") or "jarvis",
        local_listener_active=_local_listener_active,
    )


@app.get("/api/config", response_model=ConfigResponse)
async def get_config(_=Depends(verify_api_key)):
    """Read current config (API keys masked for security)."""
    cfg = config.load_config()
    return ConfigResponse(
        owner_name=cfg.get("owner_name", "Boss"),
        wake_word=cfg.get("wake_word", "jarvis"),
        voice_profile=cfg.get("voice_profile", "jarvis"),
        voice_rate=cfg.get("voice_rate", 180),
        voice_volume=cfg.get("voice_volume", 1.0),
        whisper_model=cfg.get("whisper_model", "base.en"),
        brain_priority=cfg.get("brain_priority", ["ollama"]),
        ollama_url=cfg.get("ollama_url", "http://localhost:11434"),
        ollama_model=cfg.get("ollama_model", "mistral"),
        groq_model=cfg.get("groq_model", "llama-3.3-70b-versatile"),
        gemini_model=cfg.get("gemini_model", "gemini-1.5-flash"),
        claude_model=cfg.get("claude_model", "claude-sonnet-4-5"),
        listen_timeout=cfg.get("listen_timeout", 5),
        phrase_time_limit=cfg.get("phrase_time_limit", 10),
        server_host=cfg.get("server_host", "0.0.0.0"),
        server_port=cfg.get("server_port", 8786),
        # Masked keys
        groq_api_key=mask_key(cfg.get("groq_api_key", "")),
        gemini_api_key=mask_key(cfg.get("gemini_api_key", "")),
        claude_api_key=mask_key(cfg.get("claude_api_key", "")),
    )


@app.patch("/api/config")
async def update_config(req: ConfigUpdateRequest, _=Depends(verify_api_key)):
    """Update safe config keys (no API keys via this endpoint)."""
    updates = req.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    for key, value in updates.items():
        config.set_key(key, value)

    return {"updated": list(updates.keys()), "status": "ok"}


@app.get("/api/history", response_model=HistoryResponse)
async def get_history(_=Depends(verify_api_key)):
    """Get recent conversation history."""
    try:
        from commands import _ctx
        turns = []
        for user_said, jarvis_said in _ctx.history:
            turns.append(ConversationEntry(role="user", text=user_said))
            turns.append(ConversationEntry(role="assistant", text=jarvis_said))
        return HistoryResponse(turns=turns, total=len(_ctx.history))
    except Exception:
        return HistoryResponse(turns=[], total=0)


@app.get("/api/screenshot")
async def get_screenshot(_=Depends(verify_api_key)):
    """
    Capture the server Mac's current screen — lets mobile users see
    what the Mac is displaying (for click/walk-through commands).
    """
    import subprocess
    import tempfile

    tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
    tmp.close()

    try:
        subprocess.run(
            ["screencapture", "-x", "-t", "jpg", "-m", tmp.name],
            timeout=5, capture_output=True
        )
        if os.path.exists(tmp.name) and os.path.getsize(tmp.name) > 0:
            return FileResponse(
                tmp.name,
                media_type="image/jpeg",
                filename="jarvis_screen.jpg",
            )
        raise HTTPException(status_code=500, detail="Screenshot failed")
    except FileNotFoundError:
        raise HTTPException(status_code=501, detail="screencapture not available (macOS only)")


@app.get("/audio/{filename}")
async def serve_audio(filename: str):
    """Serve cached TTS audio files."""
    fpath = os.path.join(_audio_dir, filename)
    if os.path.exists(fpath):
        return FileResponse(fpath, media_type="audio/wav")
    raise HTTPException(status_code=404, detail="Audio file not found")


# ─── WebSocket ───────────────────────────────────────────────────────────────

@app.websocket("/ws/voice")
async def voice_websocket(websocket: WebSocket):
    """
    Real-time voice streaming endpoint.
    Client sends audio chunks (16-bit PCM, 16kHz) or text messages.
    Server responds with transcripts, responses, and TTS audio.

    Auth: ?api_key=xxx query parameter.
    """
    # Verify API key
    if not await verify_ws_api_key(websocket):
        await websocket.close(code=4001, reason="Invalid API key")
        return

    session = VoiceSession(_stt_engine, _tts_engine, _command_lock)
    await session.handle(websocket)


# ─── Standalone Runner ───────────────────────────────────────────────────────

def start_server(host: str = None, port: int = None):
    """Start the server (blocking)."""
    import uvicorn

    host = host or config.get("server_host") or "0.0.0.0"
    port = port or config.get("server_port") or 8786

    print(f"\n  J.A.R.V.I.S. Server starting on http://{host}:{port}")
    print(f"  API docs: http://{host}:{port}/docs")
    print(f"  WebSocket: ws://{host}:{port}/ws/voice?api_key=YOUR_KEY\n")

    uvicorn.run(app, host=host, port=port, log_level="info")


def start_server_background(host: str = None, port: int = None):
    """Start the server in a background thread (for --dual mode)."""
    t = threading.Thread(
        target=start_server,
        args=(host, port),
        daemon=True,
        name="jarvis-api-server",
    )
    t.start()
    return t


if __name__ == "__main__":
    start_server()
