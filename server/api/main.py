import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Make `core` and `api` importable when running `uvicorn api.main:app` from server/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

load_dotenv()

from api.routes import chat, stt, tts, ws  # noqa: E402
from api.schemas import HealthResponse  # noqa: E402

app = FastAPI(title="Jarvis Server", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok")


app.include_router(chat.router)
app.include_router(stt.router)
app.include_router(tts.router)
app.include_router(ws.router)


@app.on_event("startup")
async def _warn_if_no_key() -> None:
    if not os.environ.get("JARVIS_API_KEY"):
        print("[warn] JARVIS_API_KEY is not set; protected routes will reject requests.")
