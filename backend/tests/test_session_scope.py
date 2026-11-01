"""The request session commits before the response is sent (D41). FastAPI's default scope for
a dependency with ``yield`` runs the exit code, here ``session.commit()``, after the response has
gone out; a client's immediate next request could then read uncommitted state. Reproduced on the
development backend: a GET 36 ms after a successful Assemble answered ``state: open`` with the
``assembled`` event already listed. The dependency is therefore declared with function scope.
No database, no network."""

from __future__ import annotations

from typing import get_args

from fastapi.params import Depends

from oak_binder.api import deps


def test_the_request_session_is_committed_before_the_response_is_sent() -> None:
    (_, marker) = get_args(deps.DbSession)
    assert isinstance(marker, Depends)
    assert marker.dependency is deps.get_session
    assert marker.scope == "function"
