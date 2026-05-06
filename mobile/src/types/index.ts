// ─── API Types ──────────────────────────────────────────────────────────────

export interface ChatRequest {
  text: string;
}

export interface ChatResponse {
  response: string | null;
  should_continue: boolean;
  source: string;
  audio_url: string | null;
}

export interface CommandResponse {
  transcript: string | null;
  response: string | null;
  should_continue: boolean;
  audio_url: string | null;
}

export interface StatusResponse {
  status: string;
  version: string;
  active_backend: string;
  llm_configured: boolean;
  uptime_seconds: number;
  owner_name: string;
  wake_word: string;
  voice_profile: string;
  local_listener_active: boolean;
}

export interface ConfigResponse {
  owner_name: string;
  wake_word: string;
  voice_profile: string;
  voice_rate: number;
  voice_volume: number;
  whisper_model: string;
  brain_priority: string[];
  ollama_url: string;
  ollama_model: string;
  groq_model: string;
  gemini_model: string;
  claude_model: string;
  server_host: string;
  server_port: number;
}

// ─── WebSocket Messages ─────────────────────────────────────────────────────

export interface WSMessage {
  type: 'transcript' | 'response' | 'audio' | 'status' | 'error' | 'pong';
  text?: string;
  data?: string;  // base64 audio
  format?: string;
  timestamp?: number;
}

// ─── App State ──────────────────────────────────────────────────────────────

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  text: string;
  audioUrl?: string;
  timestamp: number;
}

export interface Settings {
  serverUrl: string;
  apiKey: string;
  pushToTalk: boolean;
  playAudioResponse: boolean;
}

export type ConnectionStatus = 'disconnected' | 'connecting' | 'connected' | 'error';
