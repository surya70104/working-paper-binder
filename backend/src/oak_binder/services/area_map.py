"""The area map: which Schedule III heads each financial statement area D–T covers (spec 3A
"lead schedule per area"; Pass 2 Stage E, D32).

The map is the firm's to supply, in the template's ``areas`` block. When a template carries
none (as the shipped files do), a default map is derived from the Spine's tree alone (D38,
``derive``): one area per statement-level head group, named as the Spine names the head, so
that lead schedules can be generated without the firm's map and the firm's map, once entered,
replaces it. This module expands and checks a map against the Spine's tree:

- a listed head covers itself and every descendant, where descent is read **exclusively from
  the ``parent`` field of each head in ``GET /api/tree``**: a head is a child of another when
  its ``parent`` equals that head's ``id``, and for no other reason. Nothing is derived from
  the shape of an id;
- validation runs in four steps: (1) syntax, done by the template loader; (2) every listed id
  is a head of the served tree; (3) no overlap after expansion, so two areas never cover the
  same head; (4) a coverage report of mappable heads in no area, listed and never refused,
  since the firm may leave an area to a hand-made paper.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from oak_binder.services.spine_client import SpineHead, SpineTree
from oak_binder.services.templates import AREA_SECTIONS, AreaMap, IndexTemplate


def children_index(tree: SpineTree) -> dict[str, tuple[str, ...]]:
    """Parent id → the ids of the heads whose ``parent`` field names it, in served order."""
    index: dict[str, list[str]] = {}
    for head in tree.heads:
        if head.parent is not None:
            index.setdefault(head.parent, []).append(head.id)
    return {parent: tuple(ids) for parent, ids in index.items()}


def expand(listed: Iterable[str], tree: SpineTree) -> frozenset[str]:
    """The listed heads and all their descendants, by the tree's parent links alone. Ids the
    tree does not serve are kept as listed (the check reports them) and have no children."""
    children = children_index(tree)
    covered: set[str] = set()
    queue: deque[str] = deque(listed)
    while queue:
        head_id = queue.popleft()
        if head_id in covered:
            continue
        covered.add(head_id)
        queue.extend(children.get(head_id, ()))
    return frozenset(covered)


@dataclass(frozen=True)
class AreaMapCheck:
    """What the tree says about a template's area map."""

    problems: tuple[str, ...]  # steps 2 and 3: refusals, by name
    coverage: Mapping[str, frozenset[str]]  # area code → covered head ids (after expansion)
    unassigned: tuple[str, ...]  # step 4: mappable heads in no area, in served order
    orphans: tuple[str, ...] = field(default_factory=tuple)  # served heads whose parent is unknown

    @property
    def ok(self) -> bool:
        return not self.problems


def check(template: IndexTemplate, tree: SpineTree) -> AreaMapCheck:
    """Steps 2–4 of the template's own map against the served tree."""
    return check_areas(template.areas, tree)


def check_areas(areas: Mapping[str, AreaMap], tree: SpineTree) -> AreaMapCheck:
    """Steps 2–4 against the served tree. Step 1 (syntax) ran when the template loaded."""
    served = tree.by_id()
    problems: list[str] = []
    coverage: dict[str, frozenset[str]] = {}
    for code, area in sorted(areas.items()):
        unknown = [h for h in area.heads if h not in served]
        if unknown:
            problems.append(
                f"area {code}: heads {unknown} are not heads of the Spine's Schedule III tree"
            )
        coverage[code] = expand(area.heads, tree)
    codes = sorted(coverage)
    for i, first in enumerate(codes):
        for second in codes[i + 1 :]:
            shared = sorted(coverage[first] & coverage[second])
            if shared:
                problems.append(
                    f"areas {first} and {second} both cover heads {shared} after expansion; "
                    "a head belongs to one area"
                )
    assigned = frozenset().union(*coverage.values()) if coverage else frozenset()
    unassigned = tuple(h.id for h in tree.heads if h.mappable and h.id not in assigned)
    orphans = tuple(h.id for h in tree.heads if h.parent is not None and h.parent not in served)
    return AreaMapCheck(tuple(problems), coverage, unassigned, orphans)


@dataclass(frozen=True)
class ResolvedAreas:
    """The area map in force for a binder (D38): the template's own when it has one, otherwise
    one derived from the Spine's tree, or none when neither gives any area. ``names`` is the
    area name a generated lead schedule carries: the template's section name, or the head's
    label as the Spine serves it when derived."""

    areas: dict[str, AreaMap]
    names: dict[str, str]
    source: str  # "template" | "derived" | "none"
    beyond_letters: tuple[str, ...] = ()  # derived head groups left over after D–T were used


def from_template(template: IndexTemplate) -> ResolvedAreas:
    """The template's own map, with its section names; ``none`` when it carries no map."""
    names = {}
    for code in template.areas:
        section = template.section(code)
        names[code] = section.name if section else f"Section {code}"
    return ResolvedAreas(dict(template.areas), names, "template" if template.areas else "none")


def derive(tree: SpineTree, codes: tuple[str, ...] = AREA_SECTIONS) -> ResolvedAreas:
    """A default map from the Spine's tree alone (D38), used when the template has none, so
    that spec 3A's "lead schedule per area" works without the firm's map: one area per
    statement-level head group. For every root head (``parent`` None) in served order, each of
    its children in served order is an area; a root with no children is an area itself. The
    groups are assigned to D–T in that order; any beyond the letters are reported, never
    silently dropped. Each area lists exactly its head, so it covers that head and every
    descendant by the tree's parent links; the area's name is the head's label as served. The
    Binder adds nothing: no head, no name, no grouping the tree does not state."""
    children = children_index(tree)
    by_id = tree.by_id()
    groups: list[SpineHead] = []
    for head in tree.heads:
        if head.parent is not None:
            continue
        kids = children.get(head.id, ())
        groups.extend(by_id[k] for k in kids) if kids else groups.append(head)
    areas = {
        code: AreaMap((group.id,), None, None) for code, group in zip(codes, groups, strict=False)
    }
    names = {code: group.label for code, group in zip(codes, groups, strict=False)}
    return ResolvedAreas(
        areas,
        names,
        "derived" if areas else "none",
        tuple(group.id for group in groups[len(codes) :]),
    )


def resolve(template: IndexTemplate, tree: SpineTree) -> ResolvedAreas:
    """The template's map when it has one; otherwise the map derived from the tree (D38)."""
    if template.areas:
        return from_template(template)
    return derive(tree)


def area_of(coverage: Mapping[str, frozenset[str]], head_id: str | None) -> str | None:
    """The area a head belongs to under a checked map, or None."""
    if head_id is None:
        return None
    for code, heads in coverage.items():
        if head_id in heads:
            return code
    return None


def heads_of(area: AreaMap, tree: SpineTree) -> tuple[SpineHead, ...]:
    """The served heads an area covers, in the tree's served order."""
    covered = expand(area.heads, tree)
    return tuple(h for h in tree.heads if h.id in covered)
