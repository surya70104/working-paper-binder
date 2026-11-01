"""The area map: which Schedule III heads each financial statement area D–T covers (spec 3A
"lead schedule per area"; Pass 2 Stage E, D32).

The map itself is the firm's to supply, in the template's ``areas`` block; the shipped
templates carry none. This module only expands and checks a map against the Spine's tree:

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
from oak_binder.services.templates import AreaMap, IndexTemplate


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
    """Steps 2–4 against the served tree. Step 1 (syntax) ran when the template loaded."""
    served = tree.by_id()
    problems: list[str] = []
    coverage: dict[str, frozenset[str]] = {}
    for code, area in sorted(template.areas.items()):
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
