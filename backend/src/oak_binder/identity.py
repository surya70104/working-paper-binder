"""Who is acting (architecture D8).

One replaceable function. Today it returns the development identity from settings; real
authentication replaces this function and nothing else. Sign-off endpoints depend on it,
so without an identity they refuse rather than record an empty preparer or reviewer.
"""

from __future__ import annotations

from fastapi import HTTPException, Request, status


def current_user(request: Request) -> str:
    user: str | None = request.app.state.settings.dev_user
    if not user:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "No identity is configured: set OAK_DEV_USER for development, "
            "or real authentication for production (architecture D8).",
        )
    return user
