"""Check index template files (spec 3A, 3B) before they are used.

    python -m oak_binder.templates_check                 the four shipped templates
    python -m oak_binder.templates_check FILE [FILE...]  draft files, by path
    python -m oak_binder.templates_check --tree TREE.json FILE...
                                                         also check the area map against a
                                                         saved copy of the Spine's tree
    python -m oak_binder.templates_check --spine FILE... also check it against the live
                                                         Spine (OAK_SPINE_URL), read-only

For each file: whether it loads under the loader's rules, the placeholders it still carries
(content the specification leaves to the firm), and its area map (Stage E, D32): the syntax
check always; the tree checks (every listed head exists, no overlap after expansion, the
mappable heads in no area) only when a tree is given, since a file check should not reach
the network unasked. Exit 0 when every file loads and no area map is refused, 1 otherwise.
Reads files only; never writes.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from oak_binder.services import area_map
from oak_binder.services.spine_client import SpineTree, parse_tree
from oak_binder.services.templates import (
    ADJUSTMENT_CHAIN_REF,
    TEMPLATES_DIR,
    IndexTemplate,
    RequiredPaper,
    TemplateError,
    parse_template,
    template_names,
)


def check_file(path: Path) -> tuple[IndexTemplate | None, str]:
    """The parsed template and a report line, or None and the reason it was refused."""
    name = path.stem
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return None, f"{path}: cannot read as JSON ({exc})"
    if not isinstance(raw, dict):
        return None, f"{path}: the document must be a JSON object"
    try:
        template = parse_template(name, raw)
    except TemplateError as exc:
        return None, f"{path}: REFUSED: {exc}"
    summary = f"{len(template.sections)} sections, {len(template.required)} required papers"
    return template, f"{path}: loads ({summary})"


def _generated_label(paper: RequiredPaper) -> str:
    if paper.ref == ADJUSTMENT_CHAIN_REF:
        return f"{paper.ref} (adjustment chain)"
    return f"{paper.ref} (lead schedule, area {paper.section})"


def report(template: IndexTemplate) -> list[str]:
    lines = [f"  status: {template.status}"]
    findings = template.placeholders()
    if findings:
        lines.append("  placeholders (content the specification leaves to the firm):")
        lines.extend(f"    - {f}" for f in findings)
    else:
        lines.append("  no placeholders")
    generated = template.generated_required()
    if generated:
        lines.append(
            "  required papers the Binder generates (D32): "
            + ", ".join(_generated_label(r) for r in generated)
        )
    return lines


def area_report(template: IndexTemplate, tree: SpineTree | None) -> tuple[list[str], bool]:
    """The area-map lines and whether the map was refused against the tree."""
    if not template.areas:
        lines = ["  area map: empty (no Schedule III head assigned to any area; D32)"]
        if tree is None:
            lines.append(
                "  a default map is derived from the Spine's tree at generation time (D38); give "
                "--tree FILE or --spine to see it"
            )
            return lines, False
        derived = area_map.derive(tree)
        if not derived.areas:
            lines.append("  derived map (D38): the tree has no heads to derive an area from")
            return lines, False
        lines.append(
            "  derived map (D38): "
            + ", ".join(
                f"{code} <- {a.heads[0]} ({derived.names[code]})"
                for code, a in sorted(derived.areas.items())
            )
        )
        if derived.beyond_letters:
            lines.append(
                f"  head groups beyond the letters D-T ({len(derived.beyond_letters)}): "
                + ", ".join(derived.beyond_letters)
            )
        result = area_map.check_areas(derived.areas, tree)
        lines.extend(_tree_lines(result))
        return lines, not result.ok
    listed = sum(len(a.heads) for a in template.areas.values())
    lines = [
        f"  area map: {len(template.areas)} area(s) listing {listed} head(s): "
        + ", ".join(f"{code} [{len(a.heads)}]" for code, a in sorted(template.areas.items()))
    ]
    if tree is None:
        lines.append("  area map tree checks skipped: no tree given (--tree FILE or --spine)")
        return lines, False
    result = area_map.check(template, tree)
    lines.extend(_tree_lines(result))
    return lines, not result.ok


def _tree_lines(result: area_map.AreaMapCheck) -> list[str]:
    lines = [f"  area map REFUSED: {problem}" for problem in result.problems]
    for code, covered in sorted(result.coverage.items()):
        lines.append(f"  area {code} covers {len(covered)} head(s) after expansion")
    if result.unassigned:
        lines.append(
            f"  mappable heads in no area ({len(result.unassigned)}): "
            + ", ".join(result.unassigned)
        )
    else:
        lines.append("  every mappable head is in an area")
    if result.orphans:
        lines.append(f"  served heads whose parent is not served: {', '.join(result.orphans)}")
    return lines


def load_tree(path: Path) -> SpineTree:
    return parse_tree(json.loads(path.read_text(encoding="utf-8")))


def live_tree() -> SpineTree:
    from oak_binder.config import get_settings
    from oak_binder.services.spine_client import build_spine_client

    client = build_spine_client(get_settings())
    if client is None:
        raise SystemExit("--spine needs OAK_SPINE_URL to be configured")
    return client.tree()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check index template files")
    parser.add_argument("files", nargs="*", type=Path, help="template files; default: shipped")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--tree", type=Path, help="a saved GET /api/tree response to check against")
    source.add_argument(
        "--spine", action="store_true", help="read the tree from the configured Spine"
    )
    args = parser.parse_args(argv)
    paths = args.files or [TEMPLATES_DIR / f"{name}.json" for name in template_names()]
    tree: SpineTree | None = None
    if args.tree is not None:
        tree = load_tree(args.tree)
    elif args.spine:
        tree = live_tree()
    refused = 0
    for path in paths:
        template, line = check_file(path)
        print(line)  # noqa: T201
        if template is None:
            refused += 1
            continue
        for extra in report(template):
            print(extra)  # noqa: T201
        area_lines, area_refused = area_report(template, tree)
        for extra in area_lines:
            print(extra)  # noqa: T201
        if area_refused:
            refused += 1
    print(f"{len(paths) - refused} of {len(paths)} file(s) load")  # noqa: T201
    return 1 if refused else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
