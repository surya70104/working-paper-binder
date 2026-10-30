from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AttachmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    wp_id: uuid.UUID
    wp_version_id: uuid.UUID | None
    filename: str
    media_type: str
    size_bytes: int
    sha256: str
    # The store's id for the bytes (spec 4: vault_doc_id); what a cross-reference names.
    vault_doc_id: str
    identifying_chars: str | None
    attached_by: str
    attached_at: datetime
