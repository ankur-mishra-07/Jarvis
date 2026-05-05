import io
import json
import os

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from core.jarvis_adapter import handle_text
from core.speech import synthesize_speech, transcribe_audio_bytes

router = APIRouter()


@router.websocket("/ws/session")
async def session_ws(ws: WebSocket) -> None:
    expected = os.environ.get("JARVIS_API_KEY")
    provided = ws.headers.get("x-api-key") or ws.query_params.get("api_key")
    if not expected or provided != expected:
        await ws.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await ws.accept()

    session_id: str = "default"
    sample_rate: int = 16000
    pcm_buffer = bytearray()

    try:
        while True:
            msg = await ws.receive()
            if msg.get("type") == "websocket.disconnect":
                break

            if "bytes" in msg and msg["bytes"] is not None:
                pcm_buffer.extend(msg["bytes"])
                continue

            text = msg.get("text")
            if text is None:
                continue

            try:
                event = json.loads(text)
            except json.JSONDecodeError:
                await ws.send_json({"type": "error", "message": "invalid json"})
                continue

            etype = event.get("type")

            if etype == "start":
                session_id = event.get("session_id", session_id)
                sample_rate = int(event.get("sample_rate", sample_rate))
                pcm_buffer.clear()

            elif etype == "end":
                transcript = await transcribe_audio_bytes(
                    io.BytesIO(bytes(pcm_buffer)), sample_rate=sample_rate
                )
                pcm_buffer.clear()
                await ws.send_json({"type": "final", "text": transcript})

                reply = await handle_text(transcript, session_id)
                await ws.send_json({"type": "reply", "text": reply})

                audio_bytes, mime = await synthesize_speech(reply)
                await ws.send_json({"type": "audio_meta", "mime": mime})
                await ws.send_bytes(audio_bytes)
                await ws.send_json({"type": "done"})

            elif etype == "ping":
                await ws.send_json({"type": "pong"})

    except WebSocketDisconnect:
        return
