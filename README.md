# Jarvis — Mobile Extension

Extends the laptop Python Jarvis virtual assistant to **Android + iOS** via a
shared **Kotlin Multiplatform (KMP)** mobile client. The phone handles wake-word
detection and mic capture on-device; a thin **FastAPI** server wraps the
existing laptop Jarvis core and serves intent/LLM/STT/TTS over HTTP + WebSocket.

```
mobile (KMP)  ──HTTP/WS──►  server (FastAPI)  ──calls──►  laptop Jarvis core
```

## Repo layout

| Path        | What it is                                                       |
|-------------|------------------------------------------------------------------|
| `server/`   | FastAPI service that wraps the laptop Jarvis core                |
| `mobile/`   | KMP project with `shared/`, `androidApp/`, `iosApp/`             |
| `docs/`     | Architecture diagram and endpoint contract                       |

## Running the server

```bash
cd server
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # fill in JARVIS_API_KEY etc.
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
```

Smoke test:

```bash
curl -H "X-API-Key: $JARVIS_API_KEY" \
     -H 'Content-Type: application/json' \
     -d '{"text":"what time is it","session_id":"dev"}' \
     http://localhost:8000/chat
```

## Plugging in your laptop Jarvis

`server/core/jarvis_adapter.py` is the only file that knows about your laptop
project's modules. Drop your laptop code into `server/jarvis_core/` (or
`pip install` it) and import its entry function inside `handle_text()`. Until
then a stub responder runs so the mobile app can be developed end-to-end.

## Building the mobile app

### Android

```bash
cd mobile
echo "BASE_URL=http://<your-laptop-ip>:8000" >> local.properties
echo "API_KEY=<same as server>"              >> local.properties
echo "PORCUPINE_ACCESS_KEY=<from picovoice>" >> local.properties
./gradlew :androidApp:assembleDebug
```

### iOS

Open `mobile/iosApp/iosApp.xcodeproj` in Xcode, set `Config.xcconfig` with the
same values, set your signing team, run on a real device (mic access is flaky
in the simulator).

## Voice flow

1. App listens for "Hey Jarvis" locally (Porcupine, no network).
2. On detection it streams mic PCM to `ws://server/ws/session`.
3. Server runs STT, calls `jarvis_adapter.handle_text()`, runs TTS, streams
   reply audio back.
4. App plays audio and resumes wake-word listening.

## Status

This is the initial scaffolding. The laptop Jarvis core is **not yet pushed**;
`jarvis_adapter.py` returns a stub reply until it is wired up.
