# Working Paper Binder — architecture and agreed decisions

Decisions are numbered and dated. A decision is changed by adding a new one that supersedes
it, not by editing the old one. Requirements come from `WORKING_PAPER_BINDER.md` only.

## D1 · Standalone project — 28 Oct 2026

The Binder lives at `D:\WORKING PAPER BINDER`, in its own git repository, with its own
virtual environment, `.env`, database and roles. It never reads or modifies the Financial
Spine project at `D:\CAF`, its databases (`oak_spine`, `oak_spine_test`), its roles
(`oak_owner`, `oak_app`) or its `.env`. Integration is Pass 2 work and goes through APIs.

## D2 · Stack mirrors the Financial Spine — 28 Oct 2026

Backend: Python 3.11, FastAPI, SQLAlchemy 2, Alembic, psycopg 3. Frontend: React 19,
TypeScript, Vite, Tailwind. Tests: pytest and hypothesis; vitest and Playwright.
Reason: one skill set and one database server across OAK modules, and a clean path for the
Pass 2 integrations.

## D3 · Ports — 28 Oct 2026

API on 8001, frontend on 3001, so the Binder and the Spine (8000, 3000) can run together.

## D4 · Node through fnm — 28 Oct 2026

Node 22 is selected with fnm. `frontend/.node-version` pins it; scripts call Node through
fnm so the system Node 18 on PATH is never used by accident.

## D5 · Separate databases and roles — 28 Oct 2026

Two databases on the existing PostgreSQL 16 server: `oak_binder` and `oak_binder_test`.
Two roles: `oak_binder_owner` (migrations) and `oak_binder_app` (the running API, no DDL).
Each role has CONNECT only on the Binder databases. The create script checks that none of
these names exist and stops without changing anything if one does. It is run once, by a
person, as the PostgreSQL superuser; passwords are set in psql afterwards and never written
to a file in this repository. Connection strings live only in `backend\.env`, which git
ignores.

## D6 · Append-only at the database — 28 Oct 2026

Spec §4 lists `wp_version`, `review_note`, `discussion`, `departure` and `access_log` as
append-only, with updates and deletes failing at the database. Two layers enforce it:
UPDATE and DELETE are revoked from `oak_binder_app` on these tables, and a BEFORE UPDATE OR
DELETE trigger raises an error, so even the owner role cannot change or remove a row.
Pass 1 creates `wp_version`; the others arrive with their Pass 2 features under the same
rule.

## D7 · Attachments in a local write-once store — 28 Oct 2026

Pass 1 has no vault. Attachments are stored on disk under `var\attachments`, outside the
web root and ignored by git, keyed by their SHA-256. Bytes are never altered (native format,
spec §3G). Files are served by id, never by path, with a size limit and an allowed-type
list; the hash is re-checked on read. Nothing overwrites a stored file; after assembly
nothing deletes one. `wp_attachment` keeps the spec's fields; `vault_doc_id` holds the local
store's id for now. The store sits behind one interface so the vault can replace it in
Pass 2 without a schema change.

## D8 · Development identity — 28 Oct 2026

Until real authentication exists, `OAK_DEV_USER` in `backend\.env` (default
`dev@localhost`) names the current user. Every sign-off records that user, the server
timestamp and the paper version (spec §8.9). The lookup is one replaceable function.
Before production use: real authentication replaces it, the application refuses to start
in production mode if `OAK_DEV_USER` is set, and all traffic runs over HTTPS.

## D9 · Preparer and reviewer follow the specification — 28 Oct 2026

Preparer and reviewer are captured at sign-off, not typed (spec §2). The specification
does not say whether one person may do both, so no such rule is added.

## D11 · Data model choices — 28 Oct 2026

Spec §4 names the fields; these are the choices it leaves open, each reversible by one
migration.

- **Text plus CHECK, not PostgreSQL enum types**, for template, state, status and section.
  Adding a value is one migration line; the values are exactly the spec's.
- **One binder per engagement**: `engagement` is unique. The spec's clocks are "per
  engagement", and two files for one audit would break that.
- **The two clocks are database rules**: `assembly_due = report_date + 60 days` and
  `retention_until = report_date + 7 years` are CHECK constraints (spec 3F, 3G, 8.7). They
  are set together with the report date and can never disagree with it.
- **Assembled means frozen**: `state = 'assembled'` requires a report date, `assembled_at`
  and a 64-hex `assembly_hash`; `open` requires both to be empty (spec 3F).
- **`population_sample`** is a column on `wp`: spec 3B lists "population and sample" as a
  field even though §4's model omits it.
- **`wp_attachment` carries `filename`, `media_type` and `size_bytes`** beyond the four spec
  fields. Without them the native-format file (spec 3G) cannot be produced again.
- **`created_at`** on `binder` and `wp`, a plain timestamp; `wp_version` has `prepared_at`.
- **Every foreign key is ON DELETE RESTRICT.** Nothing cascades in an audit file. Because
  `wp_version` rows cannot be deleted, a paper that has a version cannot be deleted either.
- **Sign-off requires a conclusion at the database** (spec 8.1):
  `ck_wp_signed_off_has_conclusion`.
- **Reference never reused**: unique on `(binder_id, ref)` at the database. The rest of the
  rule, that a paper is never deleted so its reference cannot come back, is application
  behaviour in Stage 4.

## D12 · A sign-off is a new version row — 28 Oct 2026

`wp_version` is immutable, so a reviewer cannot be written onto the row the preparer
created. Each sign-off inserts a new `wp_version` carrying the preparer, the reviewer when
there is one, the snapshot `body` and its `content_hash`. "Every sign-off records who, when
and which version" (spec 8.9) is then a property of the rows, not of application logging.
`content_hash` is SHA-256 over canonical JSON (sorted keys, no whitespace), so it can be
recomputed years later (spec 8.5).

## D13 · What append-only enforcement does and does not cover — 28 Oct 2026

Two database layers on `wp_version` (migration 0001): a BEFORE UPDATE OR DELETE row
trigger and a BEFORE TRUNCATE statement trigger that raise an integrity error for any role,
and table rights for `oak_binder_app` of SELECT and INSERT only. Not covered: a superuser,
or the table's owner `oak_binder_owner`, can disable the trigger or drop the table. That is
why the API never runs as the owner, migrations are the only thing that does, and the
superuser password stays with the person who runs `scripts\db\02_create.sql`.

## D14 · The sign-off workflow — 28 Oct 2026

The five statuses of spec 3B map onto four actions, each an authenticated request (D8):

| Action | From → to | Writes |
|---|---|---|
| prepare | draft → prepared | version N: preparer and time |
| submit | prepared → in review | nothing |
| review | in review → reviewed | version N+1: preparer copied from N, reviewer and time |
| sign off | reviewed → signed off | version N+2: preparer and reviewer copied, signer and time |

Sign-off has two gates: a non-blank conclusion (spec 8.1, also a database CHECK) and no
open review notes (spec 8.2). When this was written the note count was a stub returning
zero; since D21 (migration 0003) it counts real review notes. "Who, when and which
version" for every sign-off (spec 8.9) is one immutable row: `wp_version` carries
`prepared_by/at`, `reviewed_by/at` and `signed_off_by/at`, and the database requires the
signer and time to move together and a sign-off to follow a review. (Superseding the first
draft of this decision, under which the final step wrote no row of its own.)

Two further database rules close gaps found in review: a paper in any status past draft
must point at a version (`ck_wp_status_needs_version`), and `current_version` must be a
real version of that paper (`fk_wp_current_version`). The services therefore insert and
flush a version before moving the paper to it.

Any content edit returns the paper to draft: the sign-offs on file refer to earlier
versions, which stay in `wp_version` untouched, so the history shows what was signed and
what changed afterwards. An edit that changes nothing leaves the status alone. The
reference cannot be edited at all. Review refuses a paper whose content no longer matches
the prepared version's hash, which the edit rule makes unreachable through the API but
keeps the invariant explicit.

Edits, new papers and the report date are refused once a binder is assembled. The
post-assembly amendment (new version with reason, author and date, recorded in the
manifest, spec 3F) arrives with the assembly stage, since it needs the manifest.

## D15 · Index templates and completeness — 28 Oct 2026

The four templates are JSON files in `oak_binder/templates`, one per engagement type,
validated on load. Each lists the spec's standard sections with the spec's names, and one
required paper per section the spec names (acceptance, planning and risk, materiality,
completion, report and opinion, EQR), with the SA numbers for those subjects. D–T carry no
required papers: the spec names no areas, and lead schedules come from the Spine in Pass 2.
Each file is marked draft for chartered accountant review before live use; no audit
content beyond the spec's own words was invented.

Completeness (spec 3A) counts required references that have no paper at all. Papers are
not created automatically from the template: the index shows the empty slot, and creating
the paper at that reference fills it. The count is what will block assembly.

## D16 · Requirements explicitly deferred at the close of Stages 4 and 5 — 28 Oct 2026

Recorded so that the code, the README and the status report say the same thing.

| Requirement | Spec | Deferred to | Depends on |
|---|---|---|---|
| An open review note blocks sign-off | 3D, 8.2 | Done (D21, migration 0003) | — |
| Review levels preparer → senior → manager → partner → EQR, configurable per engagement | 3D | Pass 2 | A per-binder levels list and a sign-off record per level. Pass 1 has the two sign-offs spec 6 names plus the final lock. |
| Required papers per engagement type, and the names of areas D–T | 3A | Production hardening | Chartered accountant review of the four template files; the mechanism is complete. |
| Real authentication; distinct preparer and reviewer identities | 7, D8 | Production hardening | An authentication decision. One replaceable function. |
| Markdown rendering of paper fields | 7 | Done (Stage 5 follow-up) | `marked` renders, `DOMPurify` sanitises every fragment before it reaches the DOM; tests cover rendering and neutralised script, handlers, `javascript:` links, frames, forms and styles. |
| Lead schedules tying to the Spine, with papers beneath them | 3A, 3C | Pass 2 | The Spine integration. |
| Attachments, assembly, manifest, retention, produce-file | 3B, 3F, 3G, 8.3–8.7 | Done in Stage 6 (D17–D20) | — |
| Attachments "from the vault" | 6 | Blocked: no vault exists | A search on 29 Oct 2026 of this project, `D:\CAF`, the OAK notes and every project document found no vault module, API or credentials. The local write-once store (D7, D17) stands in, behind one interface. |
| Broken-reference blocker on assembly | 3E, 3F, 8.3 | Pass 2 (D21) | The `xref` table, the Spine link and a document store. Shown as *not checked* on the Assembly screen. |
| Access log: who opened the file after assembly | 3H, 4 | Unassigned: spec 6 lists it in neither pass | A decision. Not built; the `produced` event records exports only. |

## D17 · Stage 6: attachments, assembly, amendments — 29 Oct 2026

- **Migration 0002, not an edit of 0001.** 0001 is applied to a database that holds data,
  so every Stage 6 schema change is a new, reversible migration.
- **An attachment belongs to the paper**, not to a version: `wp_attachment.wp_id` is
  required, `wp_version_id` is set at the next prepare (the version at which the file first
  became part of the signed record). A preparer attaches evidence before signing; the spec's
  version-only link made that impossible. Every version body lists the paper's attachments
  by hash, so a version's content hash covers its evidence, and the same bytes are stored
  once and refused twice on one paper.
- **Local store, not a vault.** No vault exists in this project or in the Spine. Files live
  under `OAK_ATTACHMENTS_DIR` at `<sha256[:2]>/<sha256>`, written atomically, never
  overwritten, re-hashed on every read; a mismatch is refused, not served. `vault_doc_id`
  holds the store key. Accepted types: xlsx, xls, csv, pdf, docx, txt, png, jpg.
- **Blockers are named** (spec 8.3): each missing required reference, each paper not signed
  off with its status, and an undated report. When this was written two spec blockers were
  reported as *not checked*, never as clear: open review notes and broken cross-references.
  Open review notes became a real, named blocker in D21; broken cross-references remain
  *not checked*.
- **The manifest is built from the database alone**: the binder, then every paper in
  reference order with its current version, content hash and attachments by hash; no
  timestamps. The file hash is the SHA-256 of the canonical manifest JSON, so it is
  reproducible (spec 8.5). The manifest is stored with the `assembled` event.
- **`binder_event` is append-only** (same trigger function and grants as `wp_version`):
  assembled, amended, purged, produced. It is the audit trail the produce-file export
  carries. The spec's post-assembly access log (3H) is not this table and is not built.
- **After assembly** the sign-off chain still runs, because an amended paper must be signed
  off again; what is refused is an edit without a reason, a new paper, a report-date change
  and any attachment removal. An amendment writes a new version carrying reason, author and
  date, returns the paper to draft, and writes an `amended` event (spec 3F, 8.4). The file
  stays assembled on its old hash until re-assembled; re-assembly records the previous hash.
- **Verify** recomputes every version hash from its body, every stored file's SHA-256, and
  the recorded manifest's hash against the recorded file hash, and says whether the file as
  it now stands still matches the assembled manifest.

## D18 · Purge destroys content and keeps the hashed skeleton — 29 Oct 2026

Purge (spec 3G, 8.7) is refused before `retention_until` and for anything but an assembled
file. After the date it deletes every attachment row of the binder and the stored files no
other row references, sets the state to `purged`, and writes a `purged` event with actor,
time and counts. Paper and version rows remain, with their content hashes and sign-off
metadata: they are append-only and the application role cannot delete them, and keeping
the skeleton lets the firm show what the file contained and that it was destroyed on time.
Full row destruction, if ever wanted, is a deliberate owner-role maintenance script.

## D19 · Produce file — 29 Oct 2026

One GET returns one zip (spec 3G, 8.6): `manifest.json`, `binder.json`, `audit_trail.json`,
and per paper its fields, every version with sign-off metadata, and attachments as the
original bytes under their original names, plus `CHECKSUMS.sha256` over every member.
Only an assembled, unpurged file can be produced; each production writes a `produced` event
with the archive's own hash. `verify_archive` re-hashes every member and matches each
attachment to the manifest.

## D20 · Stage 6 verification and what Pass 1 still lacks — 29 Oct 2026

Migration 0002 was applied to `oak_binder_test` once, after a verified pg_dump, through the
test fixture that only upgrades. The database suite ran in full against it; the two failures
were test-side (a constraint-name expectation and a renamed helper) and pass after
correction. In the browser the binder ENG-2026-001 was assembled, produced, amended with a
reason, re-assembled with the previous hash recorded, and produced again; the event table
holds those five records.

Not verified in the browser, by design: purge after the retention date. The automated test
injects a date past retention; no development clock override exists, so a real binder
cannot be purged early. The live `oak_binder` has never been migrated.

Pass 1 as spec 6 defines it was, at this point, complete except for the two assembly
blockers that depend on Pass 2 tables (open review notes, broken references), reported as
*not checked*. D21 then built review notes (migration 0003), leaving broken references as
the one deferred blocker. The access log of spec 3H is assigned to neither pass by spec 6
and is not built; it is a decision rather than a Pass 1 gap.

## D21 · Review notes built; broken references deferred — 29 Oct 2026

**Review notes** (spec 3D, 4, 5.3, 8.2, 8.3) are built from the spec's own record,
`review_note: wp · raised_by · assigned_to · text · state · responded_at · cleared_by`, as
migration 0003, additive. The table is append-only like `wp_version`, so a note's life is a
sequence of rows sharing one `note_id`, one per step, and its current state is the latest
step. The chain is the spec's arrow, strictly: raised → assigned → responded → cleared; a
step out of order is refused. A note is open until it is cleared. An open note blocks the
paper's sign-off (`papers.sign_off`) and the binder's assembly, where it is named per paper
(`assembly.blockers`). The spec names no rule about who may clear a note, so none exists.
Notes may be raised on a signed-off paper and on an assembled binder; they then block
re-assembly until cleared. Screen 3 lists what is open, who raised it, who holds it and what
it blocks.

**Broken-reference blocking** (spec 3E, 3F, 8.3) stays deferred, and the Assembly screen
says so as *not checked*. A cross-reference can point at a paper, a Spine FS line or a vault
document (spec 4). Papers are never deleted and a foreign key forbids a dangling paper id,
so a paper-to-paper reference cannot break; the references that can break point at the
Spine and at a vault, neither of which exists. Building the `xref` table now would add a
blocker that is structurally unable to detect anything. It arrives with Pass 2.

Acceptance 8.2 is therefore satisfied; 8.3 is satisfied for unsigned papers, open notes and
missing papers, and deferred for broken references.

## D22 · Produce-file hardening — 30 Oct 2026

Four findings from the Pass 1 quality review, all in `services\produce.py` and the
attachment download:

- **Review notes travel with the file.** Each paper's folder carries
  `review_notes.json`, every note with every step, and `audit_trail.json` lists each
  note step as an entry alongside the binder events, in time order. Spec 3G asks for the
  complete file plus the audit trail; review notes are part of both.
- **Paper folders cannot collide.** A reference is made file-safe for its folder name; a
  reference that collapses to a name already used gets a short id suffix, and
  `binder.json` carries the reference-to-folder map. Attachment names were already
  de-duplicated; paper folders now are too.
- **No production between an amendment and re-assembly.** Spec 8.5 requires the manifest
  to list every paper with its hash and spec 8.6 requires the produced archive to be the
  complete file plus that manifest. After an amendment the recorded manifest no longer
  describes the papers, so an archive built then would describe itself wrongly. Production
  is refused with a message to re-assemble; the assembly status carries
  `matches_recorded_manifest` and the screen withholds the Produce link while it is false.
  Refusal was chosen over a warning flag because a file produced for a regulator must be
  internally consistent.
- **Downloads are marked `nosniff`.** The media type comes from the extension; the header
  stops a browser from guessing another type from the bytes, so an upload is never
  rendered as a page.

## D10 · Pass 1 first — 28 Oct 2026

Build order follows spec §6, Pass 1: index and templates · the WP record with
preparer/reviewer sign-off · attachments · completeness view · assembly with the 60-day
clock and the lock · retention clock · produce-file export. The schema leaves room for
Pass 2 tables but does not build their features. Each acceptance item in spec §8 that
falls in Pass 1 becomes a named test before the feature is written.
