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
  ],
  "areas": {}
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
| `required[].sa_refs` | SA references the firm expects on the paper. The Binder screen's Create action for a missing paper prefills them, with the reference, section and title, into the new-paper form; the preparer may edit them before the paper is created, and they are saved on the paper | a list of non-blank text; may be empty |
| `areas` (optional) | the firm's map of Schedule III heads to areas D–T, for lead schedules the Financial Spine produces (Stage E, D32). **When absent, a default map is derived from the Spine's tree at generation time (D38)**: each root head's children, in served order, become areas D, E, F, …, named by the Spine's labels; a map entered here replaces that default entirely | an object keyed by area section codes D–T of this file; each value an object with `heads` and optional `objective` and `procedure` |
| `areas.<code>.heads` | the Schedule III head ids the area covers, spelled exactly as the Spine's `GET /api/tree` serves them | a list of non-blank head ids; no id listed twice anywhere in the file; **ids only, never prefixes**: a listed head covers itself and every descendant found through the tree's `parent` field |
| `areas.<code>.objective`, `.procedure` | approved wording inserted into a generated lead schedule's objective and procedure; the preparer may still edit them | non-blank text or absent |

A required reference the Binder generates itself may be listed so that the generated paper
fills the slot: `<area>-L` is the lead schedule of area D–T (title "Lead schedule: <area
name>") and `W-ADJ` is the adjustment chain, both produced from the Financial Spine (D32).
The loader accepts them only in the section where they are generated and refuses `D-L` in E,
or `W-ADJ` outside W, by name, since a paper there could never satisfy the requirement. The
check command lists such entries.

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
5. **The area map** (`areas`). Which Schedule III heads each area D–T covers, so the Binder
   can generate that area's lead schedule from the Financial Spine (Stage E, D32). **The
   shipped files carry an empty map**, and no lead schedule can be generated for a shipped
   template until the firm enters one; the Binder screen's Spine papers card, the status
   endpoint and the check command say so by name. The adjustment chain needs no map. See
   "The area map" below for the rules.
4. **SA references** per required paper. The shipped files carry none; the previously seeded
   numbers are listed for review in `docs\SA_REFERENCES_FOR_CA_REVIEW.md`.

## The area map

**Default when the file has none (D38).** The Binder derives a map from the Spine's `GET
/api/tree` alone: for every root head (no `parent`), each of its children in served order is
an area, assigned to D, E, F, … in that order; a root without children is an area itself;
groups beyond the seventeen letters are reported on the Spine-papers card and by the check
command, never silently dropped. The area's name is the head's label as served, and a
generated lead schedule records `area_map_source: derived` in its provenance. The derivation
is a technical default; entering any `areas` block here replaces it for that template. The
check command shows the derived map when given `--tree` or `--spine`.

An area covers the heads it lists and all their descendants. Descent is read **only** from the
`parent` field each head carries in the Spine's `GET /api/tree` response: a head is a child of
another when its `parent` equals that head's `id`, and for no other reason. The Binder derives
nothing from the dots in an id, so listing `"BS.A"` means the head whose id is `BS.A` and
whatever the tree places under it, not "every id starting with BS.A". Listing a parent assigns
a whole branch; listing a leaf assigns that leaf alone.

The shape, with ids that illustrate the format only (use the ids the Spine's tree actually
serves, read with `GET /api/tree`):

```json
"areas": {
  "D": {"heads": ["<head id of the area's face head>"], "objective": "<approved wording, optional>"},
  "E": {"heads": ["<head id>", "<another head id>"]}
}
```

Validation runs in four steps:

1. **Syntax**, by the loader, whenever the file is read: `areas` is an object keyed by area
   section codes D–T of this file; each value is an object with `heads`, a list of non-blank
   ids, and optional non-blank `objective` and `procedure`; no id is listed twice anywhere; no
   other key is accepted. A file that fails this is refused.
2. **Existence**, against the tree: every listed id is a head the Spine serves; an unknown id
   is refused by name.
3. **No overlap after expansion**: the covered sets of any two areas are disjoint; a
   descendant listed under one area while its ancestor is listed under another is refused by
   name.
4. **Coverage report**: mappable heads in no area are listed, not refused, since the firm may
   leave an area to a hand-made paper.

Steps 2–4 need the tree, so the check command runs them only when given one (below); at
generation time the Binder reads the tree from the Spine and refuses the request by name if
steps 2 or 3 fail. A mapped area whose heads carry no ledger in the version still gets its lead
schedule, which says so in the Spine's own terms.

## Checking a file before it is used

From `backend\`:

```powershell
.venv\Scripts\python.exe -m oak_binder.templates_check
```

checks the four shipped files and prints, for each, whether it loads, which placeholders it
still carries and which required papers the Binder generates itself. To check a draft file before copying it into place:

```powershell
.venv\Scripts\python.exe -m oak_binder.templates_check path\to\statutory.json
```

The command exits 0 when every file loads, 1 when any file is refused. A file that loads but
still reports placeholders is usable and stays marked draft on the Binders screen.

The area map is reported too: `area map: empty …` for the shipped files, or the areas and
the heads they list. The tree checks (steps 2–4 above) run only when a tree is given, since a
file check should not reach the network unasked:

```powershell
.venv\Scripts\python.exe -m oak_binder.templates_check --tree path\to\tree.json path\to\statutory.json
.venv\Scripts\python.exe -m oak_binder.templates_check --spine path\to\statutory.json
```

`--tree` takes a saved `GET /api/tree` response; `--spine` reads the live tree from the
configured `OAK_SPINE_URL`, read-only. The output names each refusal (`area map REFUSED: …`),
how many heads each area covers after expansion, and the mappable heads in no area. A map
refused against the tree exits 1.

## Applying confirmed content

1. Edit the JSON file; keep `name` equal to the file name.
2. Run the check command on it.
3. Change `status` to text that does not begin with `draft` once the chartered accountant
   has confirmed it; the Binders screen then stops warning.
4. Run the backend test suite; `tests\test_templates.py` loads every shipped file.
5. Record the confirmation (who, when) in `docs\architecture.md` under D15.

Existing binders are unaffected by a template change except in their completeness count,
which is computed from the current template each time a binder is read.
