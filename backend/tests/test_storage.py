"""The storage contract (D23): what every attachment store must do, run against the local
store and the in-memory vault stand-in, plus the store-independent verified read and the
OAK_STORE factory. No database."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from oak_binder.config import Settings
from oak_binder.errors import Conflict, Invalid, NotFound
from oak_binder.hashing import sha256_of_bytes
from oak_binder.services.attachments import (
    AttachmentStore,
    InMemoryVaultStore,
    LocalAttachmentStore,
    build_store,
    verified_read,
)
from oak_binder.services.google_drive import GoogleDriveStore
from tests.fake_drive import FakeDrive

PDF = b"%PDF-1.4 minimal\n"
CSV = b"a,b\n1,2\n"


def stores(
    tmp_path: Path,
) -> list[tuple[str, AttachmentStore, Callable[[AttachmentStore, str, bytes], None]]]:
    """Each store with a way to alter a stored document behind the Binder's back."""

    def tamper_local(store: AttachmentStore, doc_id: str, data: bytes) -> None:
        assert isinstance(store, LocalAttachmentStore)
        store.path_for(doc_id).write_bytes(data)

    def tamper_vault(store: AttachmentStore, doc_id: str, data: bytes) -> None:
        assert isinstance(store, InMemoryVaultStore)
        store.tamper(doc_id, data)

    drive = FakeDrive()

    def tamper_drive(store: AttachmentStore, doc_id: str, data: bytes) -> None:
        assert isinstance(store, GoogleDriveStore)
        drive.tamper(doc_id, data)

    return [
        ("local", LocalAttachmentStore(tmp_path / "store"), tamper_local),
        ("vault", InMemoryVaultStore(), tamper_vault),
        ("drive", drive.store(), tamper_drive),
    ]


def attachment_like(doc_id: str, data: bytes) -> Any:
    """Enough of a WpAttachment row for verified_read."""
    return SimpleNamespace(vault_doc_id=doc_id, sha256=sha256_of_bytes(data))


@pytest.mark.parametrize("index", [0, 1, 2], ids=["local", "vault", "drive"])
def test_round_trip_exists_and_delete(tmp_path: Path, index: int) -> None:
    _, store, _ = stores(tmp_path)[index]
    assert isinstance(store, AttachmentStore)  # the runtime-checkable protocol
    doc_id = store.put(PDF, filename="a.pdf", media_type="application/pdf")
    assert doc_id and store.exists(doc_id)
    assert store.read(doc_id) == PDF
    assert verified_read(store, attachment_like(doc_id, PDF)) == PDF
    assert store.delete(doc_id) is True
    assert store.exists(doc_id) is False
    assert store.delete(doc_id) is False
    with pytest.raises(NotFound):
        store.read(doc_id)


@pytest.mark.parametrize("index", [0, 1, 2], ids=["local", "vault", "drive"])
def test_altered_bytes_are_refused_by_verified_read_whatever_the_store(
    tmp_path: Path, index: int
) -> None:
    _, store, tamper = stores(tmp_path)[index]
    doc_id = store.put(CSV, filename="a.csv", media_type="text/csv")
    row = attachment_like(doc_id, CSV)
    tamper(store, doc_id, CSV.replace(b"1,2", b"9,9"))
    assert store.read(doc_id) != CSV  # the store itself hands back whatever it holds
    with pytest.raises(Conflict, match="no longer matches its hash"):
        verified_read(store, row)


def test_local_store_is_content_addressed_and_write_once(tmp_path: Path) -> None:
    store = LocalAttachmentStore(tmp_path / "store")
    first = store.put(PDF, filename="a.pdf", media_type="application/pdf")
    second = store.put(PDF, filename="b.pdf", media_type="application/pdf")
    assert first == second == sha256_of_bytes(PDF)
    assert sum(1 for p in (tmp_path / "store").rglob("*") if p.is_file()) == 1
    assert store.path_for(first) == tmp_path / "store" / first[:2] / first
    with pytest.raises(Invalid, match="not a local store key"):
        store.path_for("../etc/passwd")


def test_vault_stand_in_hands_out_opaque_ids() -> None:
    store = InMemoryVaultStore()
    first = store.put(PDF, filename="a.pdf", media_type="application/pdf")
    second = store.put(PDF, filename="a.pdf", media_type="application/pdf")
    assert first != second and first.startswith("vault-")
    assert first != sha256_of_bytes(PDF)
    assert store.documents[first][1:] == ("a.pdf", "application/pdf")


def _settings(**values: Any) -> Settings:
    from tests.conftest import IsolatedSettings

    base: dict[str, Any] = {
        "env": "test",
        "database_url": "postgresql+psycopg://oak_binder_app:x@localhost:5432/oak_binder",
    }
    base.update(values)
    return IsolatedSettings(**base)


def test_build_store_defaults_to_local(tmp_path: Path) -> None:
    store = build_store(_settings(attachments_dir=tmp_path / "attachments"))
    assert isinstance(store, LocalAttachmentStore)
    assert store.root == (tmp_path / "attachments").resolve()


def test_build_store_vault_needs_the_credential_files_before_it_opens(tmp_path: Path) -> None:
    # Vault mode is the Drive adapter (D27). Without the files it fails at start-up with a
    # plain message, never half-configured, and never with a file's contents.
    from oak_binder.errors import StoreUnavailable

    settings = _settings(
        store="vault",
        vault_url="https://www.googleapis.com/drive/v3",
        vault_credential=str(tmp_path / "token.json"),
        vault_container="1XiA9-vRVldypsN61ZPRj-T3bq1pYGY12",
        vault_client_file=str(tmp_path / "client.json"),
    )
    with pytest.raises(StoreUnavailable, match="OAuth client file not found"):
        build_store(settings)
