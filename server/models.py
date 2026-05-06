"""
Pydantic request/response schemas for the J.A.R.V.I.S. API.
"""

from pydantic import BaseModel, Field
from typing import Optional, List


# ─── Requests ────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    """Text-based chat / command."""
    text: str = Field(..., min_length=1, max_length=1000, description="User message or command")


class ConfigUpdateRequest(BaseModel):
    """Update safe config keys."""
    owner_name: Optional[str] = None
    wake_word: Optional[str] = None
    voice_profile: Optional[str] = None
    voice_rate: Optional[int] = Field(None, ge=80, le=300)
    voice_volume: Optional[float] = Field(None, ge=0.0, le=1.0)
    listen_timeout: Optional[int] = Field(None, ge=1, le=30)
    phrase_time_limit: Optional[int] = Field(None, ge=3, le=30)


# ─── Responses ───────────────────────────────────────────────────────────────

class ChatResponse(BaseModel):
    """Response from chat/command endpoint."""
    response: Optional[str] = None
    should_continue: bool = True
    source: str = "api"
    audio_url: Optional[str] = None  # URL to TTS audio if generated


class CommandResponse(BaseModel):
    """Response from voice command (audio upload) endpoint."""
    transcript: Optional[str] = None
    response: Optional[str] = None
    should_continue: bool = True
    audio_url: Optional[str] = None


class StatusResponse(BaseModel):
    """System status."""
    status: str = "running"
    version: str = "1.0.0"
    active_backend: str = "none"
    llm_configured: bool = False
    uptime_seconds: float = 0.0
    owner_name: str = "Boss"
    wake_word: str = "jarvis"
    voice_profile: str = "jarvis"
    local_listener_active: bool = False


class ConfigResponse(BaseModel):
    """Sanitized config (no API keys)."""
    owner_name: str
    wake_word: str
    voice_profile: str
    voice_rate: int
    voice_volume: float
    whisper_model: str
    brain_priority: List[str]
    ollama_url: str
    ollama_model: str
    groq_model: str
    gemini_model: str
    claude_model: str
    listen_timeout: int
    phrase_time_limit: int
    server_host: str
    server_port: int
    # API keys shown as masked
    groq_api_key: str = ""
    gemini_api_key: str = ""
    claude_api_key: str = ""


class ConversationEntry(BaseModel):
    """A single conversation turn."""
    role: str  # "user" or "assistant"
    text: str
    timestamp: Optional[str] = None


class HistoryResponse(BaseModel):
    """Conversation history."""
    turns: List[ConversationEntry] = []
    total: int = 0


# ─── WebSocket Messages ─────────────────────────────────────────────────────

class WSMessage(BaseModel):
    """Generic WebSocket message."""
    type: str  # "audio", "text", "transcript", "response", "error", "status"
    data: Optional[str] = None
    text: Optional[str] = None
