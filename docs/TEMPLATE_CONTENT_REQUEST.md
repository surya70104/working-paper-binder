# Index template content request

**Working Paper Binder (SA 230) · request for template content · 1 November 2026**

## Cover note

This request comes from the Working Paper Binder project at `D:\WORKING PAPER BINDER`. It is not written on behalf of the firm or any engagement partner, and it asks for no decision beyond what the project's own specification leaves open.

The Binder ships four index templates, one per engagement type the specification names: statutory audit, tax audit, bank branch audit, internal audit. Each file today holds exactly what the specification fixes and nothing more, and each is marked draft. The software that reads, checks and uses the templates is complete and tested. What is missing is content only the firm can approve: the names of the financial statement areas, the working papers required in them, the Schedule III heads each area covers, the standards each paper cites, and confirmation of five paper titles the project derived from the specification's section names.

No value on this form has been prefilled. Where a cell is blank, the project has nothing to suggest and will enter only what is returned here. Every rule quoted in Part B was checked against the project's loader, area-map checker and check command on 1 November 2026, so content that follows the rules will load first time.

Reference documents in the project: `docs/TEMPLATE_AUTHORING.md`, `docs/SA_REFERENCES_FOR_CA_REVIEW.md`, `docs/DECISIONS_PENDING.md` items 1–4.

## Part A. What is being asked

| # | Item | Mandatory or optional | Who supplies |
|---|---|---|---|
| A1 | Names for financial statement areas D–T (17 per template; today "Financial statement area D" … "T") | **Mandatory** to leave draft status | Chartered accountant |
| A2 | Required working papers in areas D–T (today none; the specification asks for "a lead schedule per area") | **Mandatory** to answer for every area; "none" for an area is an acceptable answer | Chartered accountant |
| A3 | Area map: the Schedule III head ids each area covers, so the Binder can generate that area's lead schedule from the Financial Spine | **Mandatory** for any area whose lead schedule is to be generated; optional for areas handled by hand-made papers | Chartered accountant, choosing from the Spine's tree |
| A4 | SA or other references on required papers (today none on any) | Optional per paper; a decision of "none" should be stated | Chartered accountant |
| A5 | Confirmation or renaming of five derived paper titles (see B1 for what is fixed and what is not) | **Mandatory**: confirm or rename | Chartered accountant |
| A6 | Approved objective and procedure wording for generated lead schedules | Optional | Chartered accountant |
| A7 | The Financial Spine's `GET /api/tree` response, or a running Spine the Binder may read | **Mandatory** before A3 can be validated; needed once (Part D; separate request in `docs/SPINE_TREE_REQUEST.md`) | Spine operator |

A1–A6 are answered once per engagement type, in Part C. A7 is answered once, in Part D.

## Part B. Formats and rules the Binder enforces

The rules below are implemented in the template loader (`services/templates.py`), the area-map checker (`services/area_map.py`) and the check command `python -m oak_binder.templates_check`. A rule marked **refused** stops the file from loading or fails the check; a rule marked **reported** lists a gap and lets the file load as draft. Where a rule is enforced elsewhere than the template, that is said.

**B1. Fixed section names versus paper titles needing confirmation.** Two different things carry names, and only one is open.

| Kind | What it is | Status |
|---|---|---|
| Section names for A, B, C, W, X, Z | The six section headings the specification itself names: Acceptance · Planning and risk · Materiality · Completion · Report and opinion · EQR | **Fixed by the specification.** The loader refuses any other name for these six codes. Nothing to supply. |
| Section names for D–T | The 17 financial statement area headings | **Open.** The specification names none; today they are placeholders. Supply in Table C*.1 (A1). |
| Working paper titles | The title of each required paper filed in a section | **Open except one.** "Materiality memo" (C-1) is the specification's own wording. The other five (A-1, B-1, W-1, X-1, Z-1) were derived by the project from the section names and have never been confirmed. Confirm or rename in Table C*.3 (A5). |

A section is a heading in the index; a paper is a document filed under it. Confirming a paper title changes nothing about its section.

**B2. File structure and sections.** Each template has exactly the 23 codes A–T, W, X, Z. **Refused** if any code is missing, repeated or not one of the 23, if a section name is blank, or if the file, a section, a required paper or an area carries a key the loader does not know. Nothing to supply.

**B3. Area names (A1).** Free text, non-blank, one per area D–T. An area the firm does not use in an engagement type keeps its code (the standard set is fixed); give it a name and require no paper in it. **Refused** if blank. **Reported** while any name still begins with "Financial statement area".

**B4. Working paper references, sections and titles (A2).**
- Reference: non-blank text, unique within the template. The existing files use `<section letter>-<number>`, for example `C-1`; the firm may keep or change the pattern. **Refused** if blank or repeated within the file.
- Section: one of the 23 codes. **Refused** otherwise. Completeness counts a required paper present only when a paper exists at that reference **in that section**.
- Title: non-blank text. **Refused** if blank.
- Stability: the specification says references are stable and never reused. That rule is enforced on each binder when a paper is created (a second paper at the same reference is refused), not by the template loader. Changing a reference in the template later does not rename existing papers; it changes which reference completeness looks for.
- Two references are written by the Binder itself: `<area letter>-L` is the lead schedule it generates for an area (its title is always "Lead schedule: <area name>"), and `W-ADJ` in section W is the adjustment chain. The loader accepts them in `required` only in the section where they are generated and **refuses** them by name elsewhere (`D-L` in E, `W-ADJ` outside W). On a binder, if a hand-made paper already holds one of them, generation of that lead schedule or chain is refused there as a reused reference. To make a generated lead schedule a required paper, list `<area letter>-L` in that area.

**B5. Schedule III head ids (A3).**
- Spelled exactly as the Spine's `GET /api/tree` serves them. The loader trims surrounding spaces and changes nothing else.
- Ids only, never prefixes or patterns. Listing `BS.A` means the one head whose id is `BS.A`, not every id beginning with `BS.A`.
- A listed head covers itself and every descendant. Descent is read only from the `parent` field of the tree response: listing a parent assigns its whole branch; listing a leaf assigns that leaf alone.
- Any served head may be listed, whether or not the tree marks it `mappable`; only existence is checked.
- Area keys must be codes D–T of the file. **Refused** otherwise. Each area's `heads` must be a non-empty-string list. **Refused** otherwise.
- No id may appear twice anywhere in the file. **Refused** at load.
- Every id must exist in the tree. **Refused** by name when checked against the tree.
- After expansion, no head may fall under two areas, including a descendant listed under one area while its ancestor is listed under another. **Refused** by name.
- Mappable heads in no area are **reported**, not refused, so an area may be left to hand-made papers. Served heads whose parent is not itself served are also **reported**.
- The adjustment chain needs no map.

**B6. SA and other references (A4).** A list of non-blank text entries per required paper, for example `SA 315`, or a reference to another framework, an Act provision or a guidance note. The list may be empty. **Refused** if any entry is blank or not text. **Reported** while any required paper has none. Note on effect: the Binder screen's "Create" action for a missing paper prefills these references into the new-paper form together with the reference, section and title; the preparer may edit them before the paper is created, and they are saved on the paper. Papers already created keep the references they hold.

**B7. Objective and procedure wording (A6).** Non-blank text or absent, per area. Inserted into the generated lead schedule's objective and procedure; the preparer may still edit them. **Refused** if present and blank.

**B8. Draft status.** Each file's status text begins with "draft" (any letter case) and is shown as a warning on the Binders screen while it does. It is changed only after the chartered accountant's completed and dated confirmation in Table C*.5 selects "Approved", and the confirmation is recorded in `docs/architecture.md` under decision D15. **Refused** if the status text is blank.

**B9. The tree (A7).** A saved `GET /api/tree` response is a JSON object with a `heads` list; every head has a non-empty `id` and may carry `parent`, `label`, `side`, `depth` and `mappable`, parents before children. The Binder refuses a response without `heads` or with a head lacking an id. A head without `mappable` is treated as not mappable, so an edited or filtered export would distort the coverage report; the export must be unaltered. The check command uses it through `--tree <file>`, or reads the live tree with `--spine` from the configured `OAK_SPINE_URL`, GET only.

**B10. Check command.** `python -m oak_binder.templates_check [--tree FILE | --spine] [FILE...]` reports, per file, whether it loads, its placeholders and its area map; exits 0 when every file loads and no map is refused against the tree, 1 otherwise. Without a tree, the map's syntax is checked and the tree checks are skipped and said to be skipped.

**Validation after return.** Content is entered into the JSON file; the check command runs without and then with the tree; the backend test suite runs; the draft prefix is removed only for a file whose Table C*.5 is completed, dated and marked "Approved"; the confirmation is recorded. Existing binders change only in their completeness count, computed from the current template on each read.

## Part C. Fill-in forms, one per engagement type

Columns marked ★ are mandatory. Write "none" where the decision is that nothing applies; leave blank only where Part A marks the item optional.

### C1. Statutory audit (`statutory.json`)

**Table C1.1 — Areas D–T** (all 17 rows; name mandatory)

| Code | ★ Area name | Used in this engagement type (yes/no) | Lead schedule generated from the Spine (yes/no) | Schedule III head ids covered (exact ids, comma separated) | Objective wording (optional) | Procedure wording (optional) |
|---|---|---|---|---|---|---|
| D | | | | | | |
| E | | | | | | |
| F | | | | | | |
| G | | | | | | |
| H | | | | | | |
| I | | | | | | |
| J | | | | | | |
| K | | | | | | |
| L | | | | | | |
| M | | | | | | |
| N | | | | | | |
| O | | | | | | |
| P | | | | | | |
| Q | | | | | | |
| R | | | | | | |
| S | | | | | | |
| T | | | | | | |

**Table C1.2a — Required papers per area: decision** (all 17 rows mandatory; "none" is a complete answer for an area)

| Code | ★ Required papers in this area: "none", or "listed in C1.2b" |
|---|---|
| D | |
| E | |
| F | |
| G | |
| H | |
| I | |
| J | |
| K | |
| L | |
| M | |
| N | |
| O | |
| P | |
| Q | |
| R | |
| S | |
| T | |

**Table C1.2b — Required papers in areas D–T, one row per paper** (only for areas marked "listed" above; add rows as needed)

| ★ Reference | ★ Section (D–T) | ★ Title | SA or other references (optional) | Is this the generated lead schedule `<letter>-L`? (yes/no) |
|---|---|---|---|---|
| | | | | |
| | | | | |
| | | | | |
| | | | | |

**Table C1.3 — The six existing required papers** (sections fixed; titles to confirm or rename, see B1)

| Reference | Section (fixed) | Current title | ★ Confirm (yes) or approved replacement title | SA or other references (optional; earlier unconfirmed seeding listed in `docs/SA_REFERENCES_FOR_CA_REVIEW.md`) |
|---|---|---|---|---|
| A-1 | A · Acceptance | Acceptance and continuance | | |
| B-1 | B · Planning and risk | Planning and risk assessment | | |
| C-1 | C · Materiality | Materiality memo (specification's wording) | | |
| W-1 | W · Completion | Completion | | |
| X-1 | X · Report and opinion | Report and opinion | | |
| Z-1 | Z · EQR | Engagement quality review | | |

**Table C1.4 — Additional required papers outside areas D–T** (sections A, B, C, W, X, Z; optional)

| Reference | Section | Title | SA or other references (optional) |
|---|---|---|---|
| | | | |
| | | | |

**Table C1.5 — Confirmation** (completed and dated; the form has no signature field)

| Item | Entry |
|---|---|
| ★ Approval status, tick one: (a) Approved as completed above, enter into the template and remove draft status · (b) **Not approved yet — keep this template in draft status.** Option (b) is not an approval: nothing from this form is entered into the file, the form is kept for reference only | |
| ★ Does this engagement type carry Standards on Auditing references? (yes / no / other framework, name it) | |
| ★ Completed by (name; membership number if applicable) | |
| ★ Date | |
| Notes or conditions | |

### C2. Tax audit (`tax_audit.json`)

Answer every row afresh. The specification gives no reason to assume this engagement type shares another type's areas, papers or references.

**Table C2.1 — Areas D–T** (all 17 rows; name mandatory)

| Code | ★ Area name | Used in this engagement type (yes/no) | Lead schedule generated from the Spine (yes/no) | Schedule III head ids covered (exact ids, comma separated) | Objective wording (optional) | Procedure wording (optional) |
|---|---|---|---|---|---|---|
| D | | | | | | |
| E | | | | | | |
| F | | | | | | |
| G | | | | | | |
| H | | | | | | |
| I | | | | | | |
| J | | | | | | |
| K | | | | | | |
| L | | | | | | |
| M | | | | | | |
| N | | | | | | |
| O | | | | | | |
| P | | | | | | |
| Q | | | | | | |
| R | | | | | | |
| S | | | | | | |
| T | | | | | | |

**Table C2.2a — Required papers per area: decision** (all 17 rows mandatory; "none" is a complete answer)

| Code | ★ Required papers in this area: "none", or "listed in C2.2b" |
|---|---|
| D | |
| E | |
| F | |
| G | |
| H | |
| I | |
| J | |
| K | |
| L | |
| M | |
| N | |
| O | |
| P | |
| Q | |
| R | |
| S | |
| T | |

**Table C2.2b — Required papers in areas D–T, one row per paper** (add rows as needed)

| ★ Reference | ★ Section (D–T) | ★ Title | SA or other references (optional) | Is this the generated lead schedule `<letter>-L`? (yes/no) |
|---|---|---|---|---|
| | | | | |
| | | | | |
| | | | | |
| | | | | |

**Table C2.3 — The six existing required papers** (sections fixed; titles to confirm or rename)

| Reference | Section (fixed) | Current title | ★ Confirm (yes) or approved replacement title | SA or other references (optional) |
|---|---|---|---|---|
| A-1 | A · Acceptance | Acceptance and continuance | | |
| B-1 | B · Planning and risk | Planning and risk assessment | | |
| C-1 | C · Materiality | Materiality memo (specification's wording) | | |
| W-1 | W · Completion | Completion | | |
| X-1 | X · Report and opinion | Report and opinion | | |
| Z-1 | Z · EQR | Engagement quality review | | |

**Table C2.4 — Additional required papers outside areas D–T** (optional)

| Reference | Section | Title | SA or other references (optional) |
|---|---|---|---|
| | | | |
| | | | |

**Table C2.5 — Confirmation** (completed and dated)

| Item | Entry |
|---|---|
| ★ Approval status, tick one: (a) Approved as completed above, enter into the template and remove draft status · (b) **Not approved yet — keep this template in draft status.** Option (b) is not an approval: nothing from this form is entered into the file | |
| ★ Does this engagement type carry Standards on Auditing references? (yes / no / other framework, name it) | |
| ★ Completed by (name; membership number if applicable) | |
| ★ Date | |
| Notes or conditions | |

### C3. Bank branch audit (`bank_branch.json`)

Answer every row afresh for this engagement type.

**Table C3.1 — Areas D–T** (all 17 rows; name mandatory)

| Code | ★ Area name | Used in this engagement type (yes/no) | Lead schedule generated from the Spine (yes/no) | Schedule III head ids covered (exact ids, comma separated) | Objective wording (optional) | Procedure wording (optional) |
|---|---|---|---|---|---|---|
| D | | | | | | |
| E | | | | | | |
| F | | | | | | |
| G | | | | | | |
| H | | | | | | |
| I | | | | | | |
| J | | | | | | |
| K | | | | | | |
| L | | | | | | |
| M | | | | | | |
| N | | | | | | |
| O | | | | | | |
| P | | | | | | |
| Q | | | | | | |
| R | | | | | | |
| S | | | | | | |
| T | | | | | | |

**Table C3.2a — Required papers per area: decision** (all 17 rows mandatory; "none" is a complete answer)

| Code | ★ Required papers in this area: "none", or "listed in C3.2b" |
|---|---|
| D | |
| E | |
| F | |
| G | |
| H | |
| I | |
| J | |
| K | |
| L | |
| M | |
| N | |
| O | |
| P | |
| Q | |
| R | |
| S | |
| T | |

**Table C3.2b — Required papers in areas D–T, one row per paper** (add rows as needed)

| ★ Reference | ★ Section (D–T) | ★ Title | SA or other references (optional) | Is this the generated lead schedule `<letter>-L`? (yes/no) |
|---|---|---|---|---|
| | | | | |
| | | | | |
| | | | | |
| | | | | |

**Table C3.3 — The six existing required papers** (sections fixed; titles to confirm or rename)

| Reference | Section (fixed) | Current title | ★ Confirm (yes) or approved replacement title | SA or other references (optional) |
|---|---|---|---|---|
| A-1 | A · Acceptance | Acceptance and continuance | | |
| B-1 | B · Planning and risk | Planning and risk assessment | | |
| C-1 | C · Materiality | Materiality memo (specification's wording) | | |
| W-1 | W · Completion | Completion | | |
| X-1 | X · Report and opinion | Report and opinion | | |
| Z-1 | Z · EQR | Engagement quality review | | |

**Table C3.4 — Additional required papers outside areas D–T** (optional)

| Reference | Section | Title | SA or other references (optional) |
|---|---|---|---|
| | | | |
| | | | |

**Table C3.5 — Confirmation** (completed and dated)

| Item | Entry |
|---|---|
| ★ Approval status, tick one: (a) Approved as completed above, enter into the template and remove draft status · (b) **Not approved yet — keep this template in draft status.** Option (b) is not an approval: nothing from this form is entered into the file | |
| ★ Does this engagement type carry Standards on Auditing references? (yes / no / other framework, name it) | |
| ★ Completed by (name; membership number if applicable) | |
| ★ Date | |
| Notes or conditions | |

### C4. Internal audit (`internal.json`)

Answer every row afresh for this engagement type. State in C4.5 whether it carries Standards on Auditing references, another framework's references, or none.

**Table C4.1 — Areas D–T** (all 17 rows; name mandatory)

| Code | ★ Area name | Used in this engagement type (yes/no) | Lead schedule generated from the Spine (yes/no) | Schedule III head ids covered (exact ids, comma separated) | Objective wording (optional) | Procedure wording (optional) |
|---|---|---|---|---|---|---|
| D | | | | | | |
| E | | | | | | |
| F | | | | | | |
| G | | | | | | |
| H | | | | | | |
| I | | | | | | |
| J | | | | | | |
| K | | | | | | |
| L | | | | | | |
| M | | | | | | |
| N | | | | | | |
| O | | | | | | |
| P | | | | | | |
| Q | | | | | | |
| R | | | | | | |
| S | | | | | | |
| T | | | | | | |

**Table C4.2a — Required papers per area: decision** (all 17 rows mandatory; "none" is a complete answer)

| Code | ★ Required papers in this area: "none", or "listed in C4.2b" |
|---|---|
| D | |
| E | |
| F | |
| G | |
| H | |
| I | |
| J | |
| K | |
| L | |
| M | |
| N | |
| O | |
| P | |
| Q | |
| R | |
| S | |
| T | |

**Table C4.2b — Required papers in areas D–T, one row per paper** (add rows as needed)

| ★ Reference | ★ Section (D–T) | ★ Title | SA or other references (optional) | Is this the generated lead schedule `<letter>-L`? (yes/no) |
|---|---|---|---|---|
| | | | | |
| | | | | |
| | | | | |
| | | | | |

**Table C4.3 — The six existing required papers** (sections fixed; titles to confirm or rename)

| Reference | Section (fixed) | Current title | ★ Confirm (yes) or approved replacement title | SA or other references (optional) |
|---|---|---|---|---|
| A-1 | A · Acceptance | Acceptance and continuance | | |
| B-1 | B · Planning and risk | Planning and risk assessment | | |
| C-1 | C · Materiality | Materiality memo (specification's wording) | | |
| W-1 | W · Completion | Completion | | |
| X-1 | X · Report and opinion | Report and opinion | | |
| Z-1 | Z · EQR | Engagement quality review | | |

**Table C4.4 — Additional required papers outside areas D–T** (optional)

| Reference | Section | Title | SA or other references (optional) |
|---|---|---|---|
| | | | |
| | | | |

**Table C4.5 — Confirmation** (completed and dated)

| Item | Entry |
|---|---|
| ★ Approval status, tick one: (a) Approved as completed above, enter into the template and remove draft status · (b) **Not approved yet — keep this template in draft status.** Option (b) is not an approval: nothing from this form is entered into the file | |
| ★ Does this engagement type carry Standards on Auditing references? (yes / no / other framework, name it) | |
| ★ Completed by (name; membership number if applicable) | |
| ★ Date | |
| Notes or conditions | |

## Part D. Financial Spine tree (needed once)

The head ids in Tables C1.1 to C4.1 can be checked for syntax without the tree, but existence and overlap checks need the tree the Spine actually serves. `docs/SPINE_TREE_REQUEST.md` is the request to the Spine operator; record the outcome here.

| Item | Entry |
|---|---|
| ★ Saved `GET /api/tree` response attached (file name), **or** the Spine URL the Binder may read from (`OAK_SPINE_URL`) | |
| Spine version or date the tree was taken | |
| Supplied by, date | |

## Part E. What happens with the answers

1. For each engagement type whose Table C*.5 is completed, dated and marked "Approved", each answer is entered into the matching template file; nothing not on this form is added. A form marked "Not approved yet" changes nothing; its template stays in draft.
2. The check command runs on the file, then with the tree.
3. The backend test suite runs.
4. The draft prefix is removed only for a file whose Table C*.5 is completed, dated and marked "Approved".
5. The confirmation is recorded in `docs/architecture.md` under D15, and `docs/DECISIONS_PENDING.md` items 1–4 are closed for that engagement type.

Not covered by this form, by design: review levels (configured per binder, not per template), the Spine link itself, and everything the specification fixes.
