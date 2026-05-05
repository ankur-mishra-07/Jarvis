from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    session_id: str = Field(min_length=1, max_length=128)


class ChatResponse(BaseModel):
    reply: str
    session_id: str


class TtsRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    voice: str | None = None


class SttResponse(BaseModel):
    transcript: str


class HealthResponse(BaseModel):
    status: str
