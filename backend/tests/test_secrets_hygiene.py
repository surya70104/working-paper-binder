"""The credential files for the Drive vault live in backend/secrets, which git ignores and no
test reads. This test proves the ignore rule and that the source never names a secret value."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent


def test_backend_secrets_directory_is_ignored_by_git() -> None:
    result = subprocess.run(  # noqa: S603
        ["git", "check-ignore", "-q", "backend/secrets/google-oauth-client.json"],  # noqa: S607
        cwd=REPO,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, "backend/secrets must be matched by .gitignore"
    tracked = subprocess.run(  # noqa: S603
        ["git", "ls-files", "backend/secrets"],  # noqa: S607
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert tracked == "", f"files under backend/secrets are tracked: {tracked}"


def test_no_google_credential_pattern_appears_in_source_or_tests() -> None:
    patterns = [re.compile(r"GOCSPX-[A-Za-z0-9_-]{10,}"), re.compile(r"\b1//0[A-Za-z0-9_-]{20,}")]
    offenders = []
    for path in list((BACKEND / "src").rglob("*.py")) + list((BACKEND / "tests").rglob("*.py")):
        if path.name == "test_secrets_hygiene.py":
            continue  # holds the patterns themselves
        text = path.read_text(encoding="utf-8")
        if path.name == "test_google_drive.py":
            # This file holds a made-up example to prove redaction; it is not a credential.
            text = text.replace("GOCSPX-super-secret", "")
        for pattern in patterns:
            if pattern.search(text):
                offenders.append(str(path.relative_to(BACKEND)))
    assert offenders == []
