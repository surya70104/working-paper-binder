"""Domain errors raised by services and turned into HTTP responses by the app."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class BinderError(Exception):
    status_code = 400


class NotFound(BinderError):
    status_code = 404


class Conflict(BinderError):
    """The action does not fit the current state (wrong status, assembled binder, reused
    reference)."""

    status_code = 409


class Invalid(BinderError):
    """The content does not satisfy a rule of the specification."""

    status_code = 422


class TooLarge(BinderError):
    status_code = 413


class UnsupportedType(BinderError):
    status_code = 415


class StoreUnavailable(BinderError):
    """The attachment store cannot be reached or refused the call; nothing was half-done."""

    status_code = 503


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(BinderError)
    async def _binder_error(request: Request, exc: BinderError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"detail": str(exc)})
