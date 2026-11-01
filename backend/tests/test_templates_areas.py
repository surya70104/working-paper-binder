"""The template's area map (Stage E step E1, D32): optional, syntax-checked by the loader,
empty in every shipped file and said so; the check command reports it and runs the tree
checks only when given a tree. No database, no network."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from oak_binder import templates_check
from oak_binder.services.templates import (
    TEMPLATES_DIR,
    AreaMap,
    TemplateError,
    list_templates,
    parse_template,
)
from tests.fake_spine import tree_record
from tests.test_templates import raw as valid_document


def test_shipped_templates_carry_an_empty_area_map_and_say_so() -> None:
    for template in list_templates():
        assert template.areas == {}
        assert any("no area map (areas)" in f for f in template.placeholders())
        raw = json.loads((TEMPLATES_DIR / f"{template.name}.json").read_text(encoding="utf-8"))
        assert raw["areas"] == {}


def test_the_area_map_is_optional_and_parsed_with_its_wording() -> None:
    raw = valid_document()
    raw.pop("areas", None)
    assert parse_template("statutory", raw).areas == {}
    raw["areas"] = {
        "D": {"heads": [" BS.A.1 ", "BS.A.2"], "objective": " Agree cash to the Spine. "},
        "E": {"heads": ["BS.L.1"], "procedure": None},
    }
    parsed = parse_template("statutory", raw)
    assert parsed.areas["D"] == AreaMap(("BS.A.1", "BS.A.2"), "Agree cash to the Spine.", None)
    assert parsed.areas["E"] == AreaMap(("BS.L.1",), None, None)
    findings = parsed.placeholders()
    assert not any("no area map" in f for f in findings)
    assert any(f.startswith("areas F, G, H") and "no Schedule III heads" in f for f in findings)


@pytest.mark.parametrize(
    ("areas", "message"),
    [
        ([], "'areas' must be an object"),
        ({"C": {"heads": ["BS.A.1"]}}, "'C' is not a financial statement area D-T"),
        ({"D": ["BS.A.1"]}, "area D: must be an object with 'heads'"),
        ({"D": {"heads": "BS.A.1"}}, "'heads' must be a list of non-blank head ids"),
        ({"D": {"heads": ["BS.A.1", "  "]}}, "'heads' must be a list of non-blank head ids"),
        ({"D": {"heads": ["BS.A.1"], "prefix": "BS"}}, "unknown keys \\['prefix'\\]"),
        (
            {"D": {"heads": ["BS.A.1"], "objective": ""}},
            "'objective' must be non-blank text or absent",
        ),
        ({"D": {"heads": ["BS.A.1"]}, "E": {"heads": ["BS.A.1"]}}, "listed under D and E"),
        ({"D": {"heads": ["BS.A.1", "BS.A.1"]}}, "listed under D and D"),
    ],
)
def test_area_map_syntax_is_refused_by_name(areas: object, message: str) -> None:
    raw = valid_document()
    raw["areas"] = areas
    with pytest.raises(TemplateError, match=message):
        parse_template("statutory", raw)


def test_the_check_command_reports_the_empty_map_and_skips_tree_checks_without_a_tree(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert templates_check.main([]) == 0
    out = capsys.readouterr().out
    assert out.count("area map: empty (no Schedule III head assigned to any area; D32)") == 4
    assert "tree checks skipped" not in out  # nothing to check against for an empty map
    assert "no area map (areas)" in out


def test_the_check_command_checks_a_map_against_a_saved_tree(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    tree = tmp_path / "tree.json"
    tree.write_text(json.dumps(tree_record()), encoding="utf-8")
    raw = valid_document()
    raw["areas"] = {"D": {"heads": ["BS.A.1"]}, "E": {"heads": ["BS.A.2"]}}
    draft = tmp_path / "statutory.json"
    draft.write_text(json.dumps(raw), encoding="utf-8")

    assert templates_check.main([str(draft)]) == 0
    out = capsys.readouterr().out
    assert "area map: 2 area(s) listing 2 head(s): D [1], E [1]" in out
    assert "area map tree checks skipped: no tree given (--tree FILE or --spine)" in out

    assert templates_check.main(["--tree", str(tree), str(draft)]) == 0
    out = capsys.readouterr().out
    assert "area D covers 1 head(s) after expansion" in out
    assert "area E covers 3 head(s) after expansion" in out
    assert "mappable heads in no area (3): BS.L.1, PL.R.1, PL.E.1" in out

    raw["areas"] = {"D": {"heads": ["BS.A"]}, "E": {"heads": ["BS.A.2", "BS.A.9"]}}
    draft.write_text(json.dumps(raw), encoding="utf-8")
    assert templates_check.main(["--tree", str(tree), str(draft)]) == 1
    out = capsys.readouterr().out
    assert "area map REFUSED: area E: heads ['BS.A.9'] are not heads" in out
    assert "area map REFUSED: areas D and E both cover heads" in out
    assert "0 of 1 file(s) load" in out


def test_the_check_command_shows_the_map_derived_from_a_saved_tree_for_an_unmapped_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    tree = tmp_path / "tree.json"
    tree.write_text(json.dumps(tree_record()), encoding="utf-8")
    code = templates_check.main(["--tree", str(tree), str(TEMPLATES_DIR / "statutory.json")])
    assert code == 0
    out = capsys.readouterr().out
    assert "area map: empty" in out
    assert (
        "derived map (D38): D <- BS.A (Assets), E <- BS.L (Liabilities), F <- PL.R (Revenue), "
        "G <- PL.E (Expenses)" in out
    )
    assert "area D covers 5 head(s) after expansion" in out
    assert "every mappable head is in an area" in out
    code = templates_check.main([str(TEMPLATES_DIR / "statutory.json")])
    assert code == 0
    assert "derived from the Spine's tree at generation time (D38)" in capsys.readouterr().out
