import secrets
from typing import Annotated

from fastapi import Security
from fastapi.security import APIKeyHeader
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.config import settings

API_KEY_HEADER_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_HEADER_NAME, auto_error=False)


def api_keys_match(provided: str, expected: str) -> bool:
    try:
        return secrets.compare_digest(provided.encode("utf-8"), expected.encode("utf-8"))
    except Exception:
        return False


async def require_api_key(
    api_key: Annotated[str | None, Security(api_key_header)],
) -> None:
    if api_key is None or not api_keys_match(api_key, settings.api_key):
        from fastapi import HTTPException, status

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )


class APIKeyMiddleware:
    """Reject unauthenticated calls before the body is parsed.

    OpenAPI, docs and health probes stay public. Business routes live under /api/.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope.get("path", "").startswith("/api/"):
            await self.app(scope, receive, send)
            return

        provided = _header(scope, "x-api-key")
        if provided is None or not api_keys_match(provided, settings.api_key):
            response = JSONResponse(
                status_code=401,
                content={"detail": "Invalid or missing API key"},
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)


def _header(scope: Scope, name: str) -> str | None:
    for key, value in scope.get("headers", []):
        if key.decode("latin-1") == name:
            return value.decode("latin-1")
    return None
