"""The template check command: shipped files load and report their placeholders; a draft
file is checked by path; a broken file is refused with the loader's reason. No database."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from oak_binder import templates_check
from oak_binder.services.templates import TEMPLATES_DIR


def test_shipped_templates_load_and_report_placeholders(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = templates_check.main([])
    assert code == 0
    out = capsys.readouterr().out
    assert "4 of 4 file(s) load" in out
    for name in ("statutory", "tax_audit", "bank_branch", "internal"):
        assert f"{name}.json: loads (23 sections, 6 required papers)" in out
    assert "financial statement areas D-T (17) carry generic names" in out
    assert "marked draft" in out


def test_a_draft_file_is_checked_by_path_and_a_broken_one_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    good = json.loads((TEMPLATES_DIR / "statutory.json").read_text(encoding="utf-8"))
    good["sections"] = [
        {"code": s["code"], "name": ("Revenue" if s["code"] == "D" else s["name"])}
        for s in good["sections"]
    ]
    good["required"].append(
        {"ref": "D-1", "section": "D", "title": "Revenue lead schedule", "sa_refs": []}
    )
    draft = tmp_path / "statutory.json"
    draft.write_text(json.dumps(good), encoding="utf-8")
    broken = tmp_path / "tax_audit.json"
    bad = json.loads((TEMPLATES_DIR / "tax_audit.json").read_text(encoding="utf-8"))
    bad["sections"] = bad["sections"][:-1]  # Z is missing
    broken.write_text(json.dumps(bad), encoding="utf-8")
    not_json = tmp_path / "internal.json"
    not_json.write_text("{", encoding="utf-8")

    code = templates_check.main([str(draft), str(broken), str(not_json)])
    assert code == 1
    out = capsys.readouterr().out
    assert "statutory.json: loads (23 sections, 7 required papers)" in out
    assert "areas E-T (16) carry generic names" in out  # D is now named
    assert "no required paper in any financial statement area" not in out  # D-1 exists
    assert "tax_audit.json: REFUSED: template tax_audit: standard sections ['Z'] are missing" in out
    assert "internal.json: cannot read as JSON" in out
    assert "1 of 3 file(s) load" in out
