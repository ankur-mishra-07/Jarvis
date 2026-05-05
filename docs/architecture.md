# Architecture

## Overview

Hybrid mobile + server architecture. Mobile owns the audio pipeline (mic, wake
word, playback). Server owns the brain (STT, intent, LLM, skills, TTS) and
reuses the existing laptop Jarvis core.

```
┌─────────────────────────────┐         ┌──────────────────────────────────┐
│  Mobile App (KMP)           │         │  Jarvis Server (Python, FastAPI) │
│                             │         │                                  │
│  ┌──────────────────────┐   │  HTTP   │  ┌────────────────────────────┐  │
│  │ Android (Compose)    │   │  +  WS  │  │ FastAPI app (api/)         │  │
│  │ iOS (SwiftUI)        │◄──┼─────────┼──►│  /chat /stt /tts /ws       │  │
│  └──────────────────────┘   │         │  └────────────┬───────────────┘  │
│  ┌──────────────────────┐   │         │               │                  │
│  │ shared/ (commonMain) │   │         │   ┌───────────▼───────────┐      │
│  │  - Ktor client       │   │         │   │ jarvis_adapter        │      │
│  │  - DTOs              │   │         │   │ (your laptop Jarvis)  │      │
│  │  - ViewModel         │   │         │   └───────────────────────┘      │
│  └──────────────────────┘   │         │   ┌───────────────────────┐      │
│  ┌──────────────────────┐   │         │   │ STT (Whisper / SR)    │      │
│  │ Wake word, mic, TTS  │   │         │   │ TTS (pyttsx3 / gTTS)  │      │
│  │ playback (per-OS)    │   │         │   └───────────────────────┘      │
│  └──────────────────────┘   │         │                                  │
└─────────────────────────────┘         └──────────────────────────────────┘
```

## Endpoint contract

| Method | Path           | In                              | Out                              |
|--------|----------------|---------------------------------|----------------------------------|
| GET    | `/health`      | —                               | `{status: "ok"}`                 |
| POST   | `/chat`        | `{text, session_id}`            | `{reply, session_id}`            |
| POST   | `/stt`         | `multipart/form-data` (audio)   | `{transcript}`                   |
| POST   | `/tts`         | `{text, voice?}`                | `audio/mpeg` bytes               |
| WS     | `/ws/session`  | binary PCM frames + json events | json events: partial/final/reply |

All routes (except `/health`) require header `X-API-Key: <JARVIS_API_KEY>`.

### WebSocket frames

Client → server:
- `{"type":"start","sample_rate":16000,"session_id":"..."}` — begin utterance
- _binary_ — raw PCM 16-bit mono frames
- `{"type":"end"}` — end of utterance

Server → client:
- `{"type":"partial","text":"..."}` — interim transcript
- `{"type":"final","text":"..."}` — final transcript
- `{"type":"reply","text":"..."}` — assistant reply text
- _binary_ — TTS audio frames (mp3 or pcm)
- `{"type":"done"}` — turn complete

## Mobile state machine

`Idle → WakeDetected → Listening → Streaming → Thinking → Speaking → Idle`

Held in `AssistantViewModel` (commonMain) as `StateFlow<AssistantState>`,
consumed identically by Compose and SwiftUI.

## Threading & lifecycle

- **Android**: wake word + mic run in a foreground service so the assistant
  works with the screen off.
- **iOS**: `audio` background mode + `AVAudioSession.playAndRecord`.
- **Network**: a single Ktor client instance owned by `shared` and shared
  across both targets.
