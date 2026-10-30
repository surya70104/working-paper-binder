"""FastAPI application factory.

Run with ``uvicorn oak_binder.main:create_app --factory --port 8001``. Creating the app
builds the engine but opens no connection; the first request that needs the database does.
"""

from __future__ import annotations

from fastapi import FastAPI, Request, Response

from oak_binder import __version__
from oak_binder.api import router
from oak_binder.config import Settings, get_settings
from oak_binder.db import make_engine, make_session_factory
from oak_binder.errors import install_error_handlers
from oak_binder.services.attachments import build_store


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings if settings is not None else get_settings()
    app = FastAPI(title="OAK Audit - Working Paper Binder", version=__version__)
    app.state.settings = resolved
    app.state.engine = make_engine(resolved.database_url)
    app.state.session_factory = make_session_factory(app.state.engine)
    # The attachment store OAK_STORE selects: the local write-once directory today; a vault
    # adapter once the vault is confirmed (D7, D17, D23).
    app.state.attachment_store = build_store(resolved)
    install_error_handlers(app)
    app.include_router(router)

    @app.middleware("http")
    async def _security_headers(request: Request, call_next):  # type: ignore[no-untyped-def]
        # Audit-file content is never to be cached by an intermediary or guessed at by a
        # browser; every response says so (D24).
        response: Response = await call_next(request)
        response.headers.setdefault("Cache-Control", "no-store")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        return response

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "module": "working-paper-binder", "version": __version__}

    return app
