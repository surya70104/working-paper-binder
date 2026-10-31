"""Check index template files (spec 3A, 3B) before they are used.

    python -m oak_binder.templates_check                 the four shipped templates
    python -m oak_binder.templates_check FILE [FILE...]  draft files, by path

For each file: whether it loads under the loader's rules, and the placeholders it still
carries (content the specification leaves to the firm). Exit 0 when every file loads, 1 when
any is refused. Reads files only.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from oak_binder.services.templates import (
    TEMPLATES_DIR,
    IndexTemplate,
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


def report(template: IndexTemplate) -> list[str]:
    lines = [f"  status: {template.status}"]
    findings = template.placeholders()
    if findings:
        lines.append("  placeholders (content the specification leaves to the firm):")
        lines.extend(f"    - {f}" for f in findings)
    else:
        lines.append("  no placeholders")
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check index template files")
    parser.add_argument("files", nargs="*", type=Path, help="template files; default: shipped")
    args = parser.parse_args(argv)
    paths = args.files or [TEMPLATES_DIR / f"{name}.json" for name in template_names()]
    refused = 0
    for path in paths:
        template, line = check_file(path)
        print(line)  # noqa: T201
        if template is None:
            refused += 1
            continue
        for extra in report(template):
            print(extra)  # noqa: T201
    print(f"{len(paths) - refused} of {len(paths)} file(s) load")  # noqa: T201
    return 1 if refused else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
