"""Local stand-ins for the Financial Spine and WorkMind, served over HTTP for browser checks
(acceptance audit, D40). They wrap the same doubles the test suite uses
(``tests.fake_spine.FakeSpine``, ``tests.fake_workmind.FakeWorkMind``): every answer is the
fixture's, nothing is live, and the servers hold no state beyond the process.

    .venv\\Scripts\\python.exe -m tests.local_stubs --spine-port 8010 --workmind-port 8012

Point a development backend at them with OAK_SPINE_URL=http://127.0.0.1:8010 and
OAK_WORKMIND_URL=http://127.0.0.1:8012. The accepted WorkMind run is ``wm-run-example-7f3a``
(the ``workmind.json`` fixture); the locked Spine version is the one ``tests.fake_spine``
names. This module is development tooling only and is never imported by the application.
"""

from __future__ import annotations

import argparse
import threading
from collections.abc import Callable

import httpx
import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route

from tests.fake_spine import FakeSpine
from tests.fake_workmind import FakeWorkMind

Handler = Callable[[httpx.Request], httpx.Response]


def wrap(handle: Handler) -> Starlette:
    """A Starlette app that forwards every request to a MockTransport-style handler."""

    async def relay(request: Request) -> Response:
        body = await request.body()
        forwarded = httpx.Request(
            request.method,
            str(request.url),
            headers=dict(request.headers),
            content=body,
        )
        try:
            answer = handle(forwarded)
        except httpx.TimeoutException:
            return Response("the double was told to time out", status_code=504)
        return Response(
            answer.content,
            status_code=answer.status_code,
            headers={"content-type": answer.headers.get("content-type", "application/json")},
        )

    return Starlette(
        routes=[Route("/{path:path}", relay, methods=["GET", "POST", "PUT", "DELETE"])]
    )


def serve(app: Starlette, port: int) -> threading.Thread:
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    return thread


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Serve the Spine and WorkMind doubles over HTTP")
    parser.add_argument("--spine-port", type=int, default=8010)
    parser.add_argument("--workmind-port", type=int, default=8012)
    args = parser.parse_args(argv)
    spine = FakeSpine()
    workmind = FakeWorkMind()
    threads = [
        serve(wrap(spine.handle), args.spine_port),
        serve(wrap(workmind.handle), args.workmind_port),
    ]
    print(  # noqa: T201
        f"Spine double on http://127.0.0.1:{args.spine_port} · WorkMind double on "
        f"http://127.0.0.1:{args.workmind_port} · Ctrl+C to stop"
    )
    try:
        for thread in threads:
            thread.join()
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
