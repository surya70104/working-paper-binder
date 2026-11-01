"""The area map against the Spine's tree (Stage E step E1, D32): expansion follows the served
``parent`` field and nothing else; the four validation steps; the coverage report. No
database, no network: the tree is the Spine double's record."""

from __future__ import annotations

import pytest

from oak_binder.services import area_map
from oak_binder.services.spine_client import SpineHead, SpineTree, parse_tree
from oak_binder.services.templates import AreaMap, IndexTemplate, TemplateError, parse_template
from tests.fake_spine import tree_record
from tests.test_templates import raw as valid_document

TREE = parse_tree(tree_record())


def template_with(areas: dict[str, dict[str, object]]) -> IndexTemplate:
    raw = valid_document()
    raw["areas"] = areas
    return parse_template("statutory", raw)


def test_a_listed_head_covers_itself_and_its_descendants_by_parent_links() -> None:
    covered = area_map.expand(["BS.A"], TREE)
    assert covered == {"BS.A", "BS.A.1", "BS.A.2", "BS.A.2.1", "X.ODD"}
    # X.ODD shares nothing with its parent's id: it is covered because its parent field says
    # BS.A.2, and for no other reason.
    assert "X.ODD" in area_map.expand(["BS.A.2"], TREE)
    assert area_map.expand(["BS.A.1"], TREE) == {"BS.A.1"}  # a leaf alone


def test_nothing_is_derived_from_the_shape_of_an_id() -> None:
    # Ids that look like children by their dots but are not in the tree are not covered,
    # and a head whose id "starts with" a listed id is not covered unless its parent chain
    # leads there.
    odd = SpineTree(
        "I",
        3,
        (
            SpineHead("BS", None, "Balance sheet", "assets", 0, False),
            SpineHead("BS.A", "BS", "Assets", "assets", 1, False),
            SpineHead(
                "BS.A.1", "PL", "Looks like a child of BS.A but is filed under PL", None, 1, True
            ),
            SpineHead("PL", None, "Profit and loss", "income", 0, False),
        ),
    )
    assert area_map.expand(["BS.A"], odd) == {"BS.A"}
    assert area_map.expand(["PL"], odd) == {"PL", "BS.A.1"}
    assert area_map.expand(["BS.A.9"], odd) == {"BS.A.9"}  # unknown id: kept, no children


def test_children_index_is_built_from_parent_fields_in_served_order() -> None:
    index = area_map.children_index(TREE)
    assert index["BS.A.2"] == ("X.ODD", "BS.A.2.1")
    assert index["BS"] == ("BS.A", "BS.L")
    assert "BS.A.1" not in index  # a leaf has no entry


def test_unknown_heads_are_refused_by_name() -> None:
    template = template_with({"D": {"heads": ["BS.A.1", "BS.A.9"]}})
    result = area_map.check(template, TREE)
    assert not result.ok
    assert result.problems == (
        "area D: heads ['BS.A.9'] are not heads of the Spine's Schedule III tree",
    )


def test_overlap_after_expansion_is_refused_by_name() -> None:
    template = template_with({"D": {"heads": ["BS.A"]}, "E": {"heads": ["BS.A.2"]}})
    result = area_map.check(template, TREE)
    assert result.problems == (
        "areas D and E both cover heads ['BS.A.2', 'BS.A.2.1', 'X.ODD'] after expansion; a "
        "head belongs to one area",
    )
    # Siblings do not overlap.
    assert area_map.check(
        template_with({"D": {"heads": ["BS.A.1"]}, "E": {"heads": ["BS.A.2"]}}), TREE
    ).ok


def test_coverage_report_lists_mappable_heads_in_no_area_and_does_not_refuse() -> None:
    template = template_with({"D": {"heads": ["BS.A.1"]}, "E": {"heads": ["BS.A.2"]}})
    result = area_map.check(template, TREE)
    assert result.ok
    assert result.coverage["D"] == {"BS.A.1"}
    assert result.coverage["E"] == {"BS.A.2", "X.ODD", "BS.A.2.1"}
    assert result.unassigned == ("BS.L.1", "PL.R.1", "PL.E.1")  # mappable heads, served order
    assert result.orphans == ()
    assert area_map.area_of(result.coverage, "X.ODD") == "E"
    assert area_map.area_of(result.coverage, "PL.R.1") is None
    assert area_map.area_of(result.coverage, None) is None


def test_heads_of_an_area_come_in_served_order() -> None:
    heads = area_map.heads_of(AreaMap(("BS.A.2",)), TREE)
    assert [h.id for h in heads] == ["BS.A.2", "X.ODD", "BS.A.2.1"]


def test_an_empty_map_covers_nothing_and_reports_every_mappable_head() -> None:
    result = area_map.check(parse_template("statutory", valid_document()), TREE)
    assert result.ok and result.coverage == {}
    assert result.unassigned == ("BS.A.1", "X.ODD", "BS.A.2.1", "BS.L.1", "PL.R.1", "PL.E.1")


def test_a_served_head_whose_parent_is_not_served_is_reported() -> None:
    tree = SpineTree(
        "I", 3, (SpineHead("PL.R.1", "PL.R", "Revenue from operations", "income", 2, True),)
    )
    result = area_map.check(template_with({"D": {"heads": ["PL.R.1"]}}), tree)
    assert result.ok and result.orphans == ("PL.R.1",)


def test_syntax_refusals_come_from_the_loader_before_any_tree_is_read() -> None:
    with pytest.raises(TemplateError, match="listed under D and E"):
        template_with({"D": {"heads": ["BS.A.1"]}, "E": {"heads": ["BS.A.1"]}})
