"""
J.A.R.V.I.S. API Authentication — simple API key verification.
Single-user assistant, so JWT/OAuth is overkill. API key is enough.
"""

from fastapi import HTTPException, Security, Query, WebSocket
from fastapi.security import APIKeyHeader
import config

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def _get_server_key() -> str:
    """Get the configured server API key."""
    return config.get("server_api_key") or ""


async def verify_api_key(api_key: str = Security(_api_key_header)):
    """FastAPI dependency — verify X-API-Key header."""
    server_key = _get_server_key()
    if not server_key:
        raise HTTPException(
            status_code=503,
            detail="Server API key not configured. Set 'server_api_key' in config.json."
        )
    if api_key != server_key:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return api_key


async def verify_ws_api_key(websocket: WebSocket) -> bool:
    """Verify API key for WebSocket connections (passed as query param)."""
    server_key = _get_server_key()
    if not server_key:
        return False
    # Check query param ?api_key=xxx
    api_key = websocket.query_params.get("api_key", "")
    return api_key == server_key


def mask_key(key: str) -> str:
    """Mask an API key for safe display: 'sk-ant-abc...xyz' → 'sk-a***xyz'."""
    if not key or len(key) < 8:
        return "***" if key else ""
    return key[:4] + "***" + key[-3:]
