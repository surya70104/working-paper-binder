# Index template authoring guide

For the chartered accountant who fills in the index templates (spec §3A), and for whoever
applies that input. The mechanism is complete; the content beyond what the specification
names is what remains. Nothing in this guide adds an audit requirement; it explains the file
format and what the loader checks.

## Where the templates live

`backend\src\oak_binder\templates\` holds one JSON file per engagement type the
specification names: `statutory.json`, `tax_audit.json`, `bank_branch.json`,
`internal.json`. The loader (`backend\src\oak_binder\services\templates.py`) reads them
once at first use and refuses any file that breaks the rules below, so a wrong file stops the
application rather than producing a wrong index.

## File format

```json
{
  "name": "statutory",
  "label": "Statutory audit",
  "status": "draft: …",
  "sections": [
    {"code": "A", "name": "Acceptance"},
    {"code": "D", "name": "Financial statement area D"}
  ],
  "required": [
    {"ref": "C-1", "section": "C", "title": "Materiality memo", "sa_refs": []}
  ]
}
```

| Key | Meaning | Rules the loader enforces |
|---|---|---|
| `name` | the engagement type | must equal the file name without `.json`; one of the four |
| `label` | shown on the Binders screen | non-blank |
| `status` | free text shown as a warning while it begins with `draft` | non-blank; remove the `draft` prefix only when the content is confirmed |
| `sections[].code` | the section letter | all 23 standard codes present (A–T, W, X, Z), none repeated, no other code |
| `sections[].name` | the section's name | A, B, C, W, X, Z must carry the spec's names: Acceptance, Planning and risk, Materiality, Completion, Report and opinion, EQR; D–T are the firm's to name |
| `required[].ref` | a required paper's reference | non-blank, unique within the file; stable, never reused (spec §3B) |
| `required[].section` | where it is filed | one of the file's section codes; completeness matches reference **and** section |
| `required[].title` | the paper's title | non-blank |
| `required[].sa_refs` | SA references the paper carries when created from the index | a list of non-blank text; may be empty |

A required paper is "missing" on a binder until a paper with that reference exists in that
section. The count of missing required papers blocks assembly (spec §3A, §3F).

## What the specification fixes and what it leaves open

Fixed by the specification: the four engagement types, the 23 section codes, the six section
names above, and one paper by name, the materiality memo (§3C).

Left to the firm, and therefore awaiting a chartered accountant:

1. **Names for areas D–T.** The files carry "Financial statement area D" to "… T" as
   placeholders. Replace each with the firm's area name. An area the firm does not use in an
   engagement type still keeps its code (the spec's standard set is fixed); give it a name and
   require no paper in it.
2. **Required papers per engagement type.** Add an entry to `required` for every paper the
   firm requires before assembly, in its section. The spec's "lead schedule per area" (§3A)
   becomes one entry per used area once the firm names the areas; the lead schedule content
   itself comes from the Financial Spine in Pass 2.
3. **The five derived titles.** Only "Materiality memo" is the spec's wording. Confirm or
   rename: A-1 Acceptance and continuance, B-1 Planning and risk assessment, W-1 Completion,
   X-1 Report and opinion, Z-1 Engagement quality review.
4. **SA references** per required paper. The shipped files carry none; the previously seeded
   numbers are listed for review in `docs\SA_REFERENCES_FOR_CA_REVIEW.md`.

## Checking a file before it is used

From `backend\`:

```powershell
.venv\Scripts\python.exe -m oak_binder.templates_check
```

checks the four shipped files and prints, for each, whether it loads and which placeholders
it still carries. To check a draft file before copying it into place:

```powershell
.venv\Scripts\python.exe -m oak_binder.templates_check path\to\statutory.json
```

The command exits 0 when every file loads, 1 when any file is refused. A file that loads but
still reports placeholders is usable and stays marked draft on the Binders screen.

## Applying confirmed content

1. Edit the JSON file; keep `name` equal to the file name.
2. Run the check command on it.
3. Change `status` to text that does not begin with `draft` once the chartered accountant
   has confirmed it; the Binders screen then stops warning.
4. Run the backend test suite; `tests\test_templates.py` loads every shipped file.
5. Record the confirmation (who, when) in `docs\architecture.md` under D15.

Existing binders are unaffected by a template change except in their completeness count,
which is computed from the current template each time a binder is read.
