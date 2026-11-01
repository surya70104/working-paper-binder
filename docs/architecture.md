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
completion, report and opinion, EQR). D–T carry no required papers: the spec names no
areas, and lead schedules come from the Spine in Pass 2. Each file is marked draft for
chartered accountant review before live use; no audit content beyond the spec's own words
was invented.

*31 Oct 2026.* The SA numbers the required papers had carried since this decision were
removed: they came from general knowledge of the standards, not from the specification, and
the differences between engagement types were unexplained. They are held for the chartered
accountant in `docs/SA_REFERENCES_FOR_CA_REVIEW.md`; the loader now also reports required
papers without references as a placeholder. `python -m oak_binder.templates_check` checks
the shipped files or draft files by path, and `docs/TEMPLATE_AUTHORING.md` explains the
format and what remains the firm's to supply.

Completeness (spec 3A) counts required references that have no paper at all. Papers are
not created automatically from the template: the index shows the empty slot, and creating
the paper at that reference fills it. The count is what will block assembly.

## D16 · Requirements explicitly deferred at the close of Stages 4 and 5 — 28 Oct 2026

Recorded so that the code, the README and the status report say the same thing.

| Requirement | Spec | Deferred to | Depends on |
|---|---|---|---|
| An open review note blocks sign-off | 3D, 8.2 | Done (D21, migration 0003) | — |
| Review levels preparer → senior → manager → partner → EQR, configurable per engagement | 3D | Done (D33, migration 0009): a per-binder ordered list, the preparer first from the prepared version, one append-only review row per level and version, sign-off after the last level, the list frozen once a level review exists | — |
| Required papers per engagement type, and the names of areas D–T | 3A | Production hardening: the specification carries no names for D–T and no per-type lists, so nothing more can be filled from it (re-checked 30 Oct 2026) | Chartered accountant review of the four template files; the mechanism is complete and reports the placeholders. |
| Real authentication; distinct preparer and reviewer identities | 7, D8 | Done (D24): `OAK_AUTH=header` trusts an authenticating proxy; production refuses `dev` | The firm's choice of proxy or identity provider; nothing in the Binder depends on it. |
| Markdown rendering of paper fields | 7 | Done (Stage 5 follow-up) | `marked` renders, `DOMPurify` sanitises every fragment before it reaches the DOM; tests cover rendering and neutralised script, handlers, `javascript:` links, frames, forms and styles. |
| Lead schedules tying to the Spine, with papers beneath them | 3A, 3C | Done (D32): generated per mapped area from the linked, locked Spine version, with FS-line references so the map draws the chain; the adjustment chain likewise | The firm's area map and area names (TEMPLATE_AUTHORING items 1–2): shipped templates carry none, so no lead schedule can be generated until a map is entered. |
| Attachments, assembly, manifest, retention, produce-file | 3B, 3F, 3G, 8.3–8.7 | Done in Stage 6 (D17–D20) | — |
| Attachments "from the vault" | 6 | Done (D27): Google Drive adapter behind the D23 protocol; vault mode off until the consent, folder check and migration have run | The firm's one-time consent and the consent screen's production status. |
| Broken-reference blocker on assembly | 3E, 3F, 8.3 | Done (D26, D30): paper, document and, for a binder linked to a Spine version, FS-line targets are checked and a broken one blocks by name; FS lines of an unlinked binder stay *not checked* | — |
| Access log: who opened the file after assembly | 3H, 4 | Done (D25, migration 0004) | — |

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
missing papers, and deferred for broken references. (Superseded in part by D26, which builds
`xref` and checks paper and document targets; FS-line targets remain unchecked.)

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

## D23 · Attachment storage behind a protocol; vault-ready, no vault chosen — 30 Oct 2026

No vault has been identified (D16). To let one plug in the day it is confirmed, without a
schema change, attachment storage now sits behind a four-method protocol in
`services\attachments.py`: `put(data, filename, media_type) -> doc_id`, `read(doc_id)`,
`exists(doc_id)`, `delete(doc_id)`.

- **Key and hash are separate.** `vault_doc_id` is the key the store knows a document by;
  `sha256` is the Binder's own hash computed at upload. For the local store the two are
  equal; for a vault the key will be whatever opaque id it returns. Every read, in
  download, verification and production, goes through `verified_read`, which re-hashes what
  the store returns and refuses a mismatch. The integrity rule no longer depends on the
  backend.
- **`LocalAttachmentStore`** is the previous behaviour unchanged: content-addressed,
  write-once, atomic writes, under `OAK_ATTACHMENTS_DIR`.
- **`InMemoryVaultStore`** behaves like a vault for tests: opaque ids, no
  content-addressing, and a way to alter a document behind the Binder's back. Not for
  production.
- **Identical bytes are stored once** in any store: an upload whose hash already has a row
  reuses that row's document id. A purge deletes a document only when no row anywhere still
  references its id, so evidence shared with another binder survives.
- **`OAK_STORE`** selects the store, `local` by default. `vault` requires `OAK_VAULT_URL`,
  `OAK_VAULT_CREDENTIAL` and `OAK_VAULT_CONTAINER`, generic names rather than a product,
  and the application refuses to start on `vault` until an adapter exists. No adapter is
  written: the product, its API and its authentication are unconfirmed, and inventing them
  would be worse than waiting.
- **What the adapter will need to do**, read off the protocol: store bytes and return an id,
  fetch bytes by id, confirm existence, delete after retention. Nothing else in the Binder
  changes. The storage contract tests in `tests\test_storage.py` run against the local store
  and the stand-in; they are the acceptance tests for the adapter.

## D24 · Identity from an authenticating proxy — 30 Oct 2026

Spec 7 asks for authenticated actions; spec 6 names no identity provider, and inventing one
(a user table, passwords, sessions) would be requirements the spec does not contain. The
Binder therefore takes its identity from an **authenticating reverse proxy**, the
identity-aware-proxy pattern: the proxy signs the user in with whatever the firm already
uses and places the identity in one request header. `OAK_AUTH` selects the source:

- `dev`: the fixed identity in `OAK_DEV_USER` (D8). For development and tests. Refused in
  production by the settings guard, as `OAK_DEV_USER` already was.
- `header`: the value of `OAK_AUTH_HEADER` (default `X-Authenticated-User`), trimmed. Without
  it, any action that records a person, and any read of an assembled file (D25), is refused
  with 401 rather than recorded under an empty name.

The Binder verifies nothing about the person itself. One module, `identity.py`, is the whole
mechanism, so a different scheme later replaces one module. Tests cover both modes, trimming,
the 401, the 503 in dev mode without a user, and the production guard.

**Hardening, same day (security review).** A header is only as trustworthy as its route in,
so header mode now checks the route, not just the value:

- `OAK_TRUSTED_PROXIES`: the header is believed only when the request's peer address is in
  this list of IPs or networks. Empty means any peer, for development; production refuses
  an empty list, because an API reachable directly would let anyone name themselves. The
  peer is the socket address, never a forwarded header: uvicorn runs without
  `--proxy-headers`, and the proxy must be the peer.
- The header must appear exactly once. A proxy that appends instead of replacing would
  leave a client-sent copy in front of its own; two copies are refused.
- The value must be a plausible name: non-blank, at most 254 characters, no control or
  non-space whitespace characters.
- Every response carries `Cache-Control: no-store`, `X-Content-Type-Options: nosniff` and
  `Referrer-Policy: no-referrer`, so audit-file content is neither cached by an intermediary
  nor type-guessed by a browser, whatever the route.
- The optional identity on a read of an open binder goes through the same checks
  (`optional_user`), so a spoofed header never reaches the access log by that route either.

Still the firm's: TLS termination and the proxy's own authentication, which no application
setting can supply.

## D25 · Access log: every read of an assembled file — 30 Oct 2026

Spec 3H and 4 define `access_log · binder · user · action · at`, post-assembly only, as an
SA 230 requirement; spec 6 schedules it in neither pass. With Pass 1 otherwise complete it is
built now, as migration 0004, additive and append-only like `wp_version` (trigger plus
SELECT/INSERT-only grants). Interpretations, stated rather than assumed:

- **"Opened" means any read of the file's content** once the binder is assembled or purged:
  the binder (`binder`), a paper (`paper <ref>`), its versions (`versions of <ref>`), its
  review notes (`review notes of <ref>`, `review note of <ref>`), its cross-references
  (`cross-references of <ref>`), an attachment's details or bytes
  (`attachment <name> of <ref> (details)`, `attachment <name> of <ref>`), the binder's review
  notes (`review notes`), the assembly status (`assembly status`), a verification (`verify`),
  a production (`produce`). The `action` column carries that label. The binder list is an
  index of engagements, not the file, and is not logged. Reads of an open binder are
  ordinary work and are not logged. (The versions, notes, cross-references and
  attachment-details reads were added in the same-day acceptance review.)
- **A read of an assembled file requires an identity.** The log must say who, so the read
  is refused without one (401 in header mode, 503 in dev mode without `OAK_DEV_USER`), the
  same rule as for an action that records a person. A read of an open binder needs none.
- The reading of the Assembly screen that lists the log is itself logged; the list is read
  after the row is written, so the reader sees their own visit.
- The produced archive carries the log twice: as `access_log.json`, and merged into
  `audit_trail.json` with kind `access`, so the single time-ordered trail shows events, note
  steps and reads together. The archive produced at a given moment holds the log up to that
  moment; the `produce` row itself is written after the archive is built.

## D26 · Cross-references and broken-reference detection — 30 Oct 2026

Spec 4 defines `xref · from_wp · to_wp | to_fs_line | to_vault_doc · direction`; spec 3B asks
for "cross-references in and out" on the paper; spec 3E and 3F make a broken reference a
named assembly blocker. D21 deferred all of it because nothing could then break. Pass 1 is
now closed instead by building the table (migration 0005, additive) and checking whatever
the data allows:

- **One target per row**, enforced by a CHECK: another paper, an FS line (free text, at most
  200 characters, until the Spine exists), or a document by its store id (`vault_doc_id`,
  now exposed on the attachment record for this purpose). A paper target must be a paper of
  the same binder and never the paper itself.
- **`direction` is read as the way the reference points**: `to`, the paper it is written on
  refers to the target; `from`, the target refers to that paper. "In and out" on a paper are
  read from both ends: rows written on the paper and rows pointing at it, each turned the
  right way round. The spec gives the field no value set; this is the interpretation chosen,
  stated here. "Clickable in both directions" (spec 3E) holds for every target that exists
  here: a paper target links to the paper and appears on it; a document target links to the
  attachment it is filed as, and the paper carrying that document sees the reference coming
  in (same-day review). An FS line has nowhere to link until the Spine exists.
- **What is checked**: a document target is broken when no paper of the binder carries that
  document any more (its only attachment was removed); re-attaching the same bytes anywhere
  in the binder mends it. A paper target is re-checked to be a paper of the same binder;
  papers are never deleted and the foreign key forbids a dangling id, so the check exists so
  that the blocker list says what was checked. A broken reference is a `broken_reference`
  blocker named by the referring paper, and assembly is refused.
- **What is not checked**: an FS-line target, since the Spine is not part of this product.
  The Assembly screen lists this as *not checked* with the count of such references in the
  file, never counting them as clear.
- **References are frozen with the file.** They are added and removed only while the binder
  is open (the application role holds the four ordinary rights on `xref`; the service refuses
  changes after assembly, since spec 3F says nothing is deleted after it). They are **not part
  of the manifest or its hash**: the manifest hashes content, a reference is a pointer between
  pieces of content, and including it would have made every binder assembled before this
  migration stop matching its recorded manifest. The produced archive lists each paper's
  references, with their check result, as `papers/<folder>/cross_references.json`.
- The cross-reference **map** screen (spec screen 4, "FS line to paper to document") stays
  Pass 2 with the Spine, as spec 6 places it.
- **"Superseded paper" (31 Oct 2026).** Papers are never deleted or replaced here, so the
  only reading the data supports is a target paper whose content changed after the
  reference was made. That is now surfaced on the reference, on the screen and in the
  archive, as information: the content hash of the target's version at the time of the
  reference is compared with its current version, so a review or sign-off of unchanged
  content does not count. It is not an assembly blocker; whether it should be is the
  senior's call (`docs/DECISIONS_PENDING.md`, item 5).

## D27 · Google Drive is the vault — 30 Oct 2026

The firm named its vault: one Google Drive folder, *Working Paper Binder Vault*, in a personal
Google account, with a Desktop OAuth client. Spec 6's "attachments from the vault" is built
on the D23 protocol with no schema change: ``vault_doc_id`` holds Drive's file id, the row's
``sha256`` stays the Binder's own hash, and ``verified_read`` re-hashes every read as before.

**Scope.** The narrow ``drive.file`` scope reaches only files the application created or a
person picked for it in Google's picker; a hand-made folder is outside it, and an upload into
it answers 404. Using the firm's existing folder therefore needs the full ``drive`` scope,
which technically grants the token read, write and delete over the whole account's Drive.
Stated here and in the README so nobody mistakes the application's discipline for a Google
guarantee. Two alternatives were offered and declined: a dedicated Google account for the
vault, and letting the Binder create its own folder under ``drive.file``.

**Confinement by the adapter.** Every file the Binder creates has the vault folder as its
only parent and ``appProperties.oak_binder=attachment`` plus the SHA-256. Every read, exists
and delete first fetches metadata and refuses a file that is not in the folder, not marked,
trashed, or a folder. The adapter never calls list or search, never calls the update-content
endpoint, and never touches a file id it did not create or was not given by a Binder row. The
Drive double records calls, and tests assert no list call and no call on a file outside the
folder, including during purge.

**Write-once.** A resumable upload, then verification against Drive's ``sha256Checksum`` when
reported, its ``md5Checksum`` otherwise, or a read-back when neither; then Drive's
read-only content restriction. An upload that fails verification or locking is deleted and
refused, so nothing unverified stays. The restriction is soft (an editor can lift it), which
is why the hash check on every read remains the integrity rule.

**Credentials.** The client JSON and the refresh-token file live under the git-ignored
``backend/secrets``; the token file is written atomically with owner-only permissions where
the OS allows. Their contents never reach logs, errors or responses: token-endpoint failures
report only a status and what to do, dataclasses holding them redact their ``repr``, and tests
assert no token string appears in any error. A refresh token obtained while the consent
screen is in Testing status expires after seven days; the screen must be In production.

**Consent.** ``python -m oak_binder.vault_login`` runs the installed-application flow with
PKCE on a loopback redirect, saves the refresh token, then fetches the folder's metadata and
reports its name and whether the account can add children: a wrong id, a folder the account
cannot see, or a trashed folder fails there rather than at the first upload. It works with
``OAK_STORE=local``, so the consent and the folder check happen before vault mode is on.

**Migration.** ``python -m oak_binder.vault_migrate`` is a dry run by default; ``--apply``
uploads each local document once (however many rows share it), verifies it by hash after
upload and again by reading it back, rewrites ``wp_attachment.vault_doc_id`` and
``xref.to_vault_doc`` together, and commits per document so an interrupted run resumes.
Version bodies and manifests list attachments by hash, never by id, so no signed content and
no recorded assembly hash changes. Local files are kept as a second copy. The live
``oak_binder`` database holds no rows and is not touched by this work.

**Failure.** Transport faults, quota refusals and 5xx answers become ``StoreUnavailable``
(HTTP 503): an upload or a production fails whole, never half-written.

## D28 · Pass 2 Stage A: the discussions and departures logs — 31 Oct 2026

Spec 2 and 3H require a discussions log ("significant matters, with whom, when. Including
TCWG") and a departures log ("requirement, reason, alternative procedure"); spec 4 gives the
two records field for field and lists both as append-only. Built as migration 0006 with
exactly those fields plus ``recorded_by`` and ``recorded_at``, append-only by the same
trigger and grants as ``wp_version``.

Decisions taken with the engagement lead on 31 Oct 2026:

- **Entries are allowed after assembly** and follow the post-assembly rule (spec 3F, 8.4):
  a reason is required, an ``amended`` event records author, date and reason, and the file
  must be re-assembled before it is produced again. The reason lives on the event, not on
  the record, so the two tables stay as spec 4 names them.
- **Re-assembly is forced by the manifest, not by a flag.** The manifest lists the logs,
  entry by entry, so a new entry changes the file hash, ``matches_recorded_manifest`` turns
  false, production is refused and ``assemble`` accepts the re-assembly. The keys appear
  only once any entry exists, so every file assembled before this stage keeps the manifest
  and hash it recorded; the demo binder still verifies.
- **TCWG is a role written after the participant's name**, for example "R. Mehta (TCWG,
  Audit Committee Chair)". The spec defines no structure for it; no field was added.
- ``outcome`` and ``approved_by`` may be empty when an entry is recorded, since an outcome
  or an approval may follow; because entries are never edited, the later fact is a new entry.
- A purged binder takes no entries. Reads of an assembled file's logs are access-logged
  (``discussions``, ``departures``). The archive carries both logs as their own members.

## D29 · Pass 2 Stage B: the Financial Spine link — 31 Oct 2026

Spec 3A ties lead schedules to the Financial Spine; spec 3C has the Spine produce lead
schedules and the adjustment chain; spec 3E names financial-statement lines as reference
targets. The Spine exists (`D:\CAF`, `oak_spine`, a FastAPI service on port 8000 with no
authentication); the other source modules do not. Stage B is the link, nothing more.

Decisions taken with the engagement lead on 31 Oct 2026:

- **One binder, one engagement, one version.** Two nullable UUID columns on `binder`
  (migration 0007), no foreign keys (the ids belong to the Spine's database), one check that
  a version needs an engagement. Existing binders are untouched. Several binders may point
  at one Spine engagement.
- **Read-only over HTTP.** `services/spine_client.py` is GET-only; the test double records
  every call and the tests assert no other verb is ever sent. The Binder never imports Spine
  code or reads its database. `OAK_SPINE_URL` unset means no Spine; features then say so.
- **Transport.** 10 s connect, 30 s read. Production requires `https://` unless the Spine
  is on the loopback interface. An optional bearer credential (`OAK_SPINE_CREDENTIAL`) is
  sent when set and redacted everywhere; the Spine has no authentication today.
- **Errors mapped once.** Transport faults, timeouts, 429 and 5xx become `SpineUnavailable`
  (503); 404 becomes `NotFound` with the Spine's message; 401/403 says the credential was
  refused; other 4xx become `Invalid`; a non-JSON body is "an unexpected answer".
- **Linking is verified against the Spine**: the engagement must exist and the version must
  belong to it. The link may be set, changed or cleared while the binder is open; clearing
  the engagement clears the version. After assembly it is frozen with the file.
- **An unlocked version may be linked while the work goes on, but assembly needs a locked
  one.** `spine_version_unlocked` is a named blocker; so are `spine_version_missing` (the
  Spine no longer has it), `spine_unreachable` (it cannot be read) and
  `spine_version_not_verified` (a version is linked but no Spine is configured). Never
  silently clear.
- **The manifest records the link** (`spine: {engagement_id, version_id}`) only when one
  exists, so every file assembled without a link keeps its recorded hash. The manifest stays
  deterministic and needs no network; the assembled event records the version's lock hash
  and time, read from the Spine at that moment.
- Stage C will make `to_fs_line` name the Spine's stable presentation-line `head_id` for a
  linked binder, with the label kept for display; the client already exposes both.

## D30 · Pass 2 Stage C: FS-line checks and the cross-reference map — 31 Oct 2026

Spec 3E: "financial statement line → lead schedule → working paper → source document,
clickable in both directions", and broken references block assembly; spec 5.4: the map
screen "with broken links flagged". With the Spine link (D29) the FS-line end of the chain
can now be checked. No schema change: ``xref.to_fs_line`` already holds text, and for a
linked binder that text is the Spine's stable presentation-line ``head_id``.

- **Lines come from the linked version's presentation** (`services/fs_lines.py`), keyed by
  ``head_id``, label kept for display. They are available only when the binder is linked
  to a version, the Spine can be read, and the statements are ready; otherwise the reason is
  stated and FS-line references are *not checked*, as before.
- **Once lines are available, a new FS-line reference must name one of them** (422
  otherwise, with the lines endpoint named), and an existing reference that names no line,
  whether free text from before the link or a line the version lost, is a ``broken_reference``
  blocker by the referring paper. The Assembly screen's not-checked list is empty for such a
  binder; for an unlinked or unreadable one it says why, with the count.
- **The map is built from the references alone.** A paper that refers to an FS line is the
  lead schedule for that line (spec 3A); papers that refer to the lead schedule sit beneath
  it, to a depth of three; each paper's document references are its source documents. Papers
  deeper than the three drawn levels are listed apart as *further down a chain* (their links
  checked and counted like any other), and papers reachable from no line apart from those, so
  nothing is hidden and nothing is mislabelled. Every node links to its
  paper or attachment, so the chain is clickable both ways. Broken and amended links carry
  the same reasons the paper screen shows; the counts head the screen.
- Reads of the lines and the map on an assembled file are access-logged (``FS lines``,
  ``cross-reference map``). **Assembly records the lines it verified against** with the
  assembled event (``details.fs_lines``: version id, lock state, every line with its label
  and figures), outside the manifest so the file hash is unchanged. Production reads that
  record, so the archive's per-paper cross-reference records carry the line label and the
  check result exactly as verified, whether or not the Spine answers at the time. A binder
  assembled before the record existed, or without a readable Spine version, reads the Spine
  at production as before. The blocker and the screen name a broken FS-line target once,
  followed by the reason.
- Lead schedules generated from the Spine (spec 3C) arrived with Stage E (D32); a hand-made
  paper that refers to a line is still drawn as its lead schedule.

## D31 · Pass 2 Stage D: generated-paper intake — 31 Oct 2026

Spec 3C: "A paper produced by a module arrives complete, with its inputs and its citations,
and nobody retypes anything", with one line per source; spec 8.8: a generated sampling paper
"carries its formula and its seed"; spec 7: conclusions are not drafted automatically. None of
Materiality, Sampling, Analytical Review or WorkMind exists (CAF's D20 says as much for
materiality), so the Binder defines the contract, checks presence and shape of exactly what
the spec names, keeps the rest verbatim and assumes no semantics. Decisions taken after a
conflict review against the spec (``docs/PASS2_STAGE_D_PLAN.md`` §11):

- **One endpoint, one contract** (`schemas/generated.py`): the paper's fields plus a
  ``generated`` block with source, module, run, time, ``inputs``, ``citations`` and one strict
  source block (unknown keys refused). ``inputs`` and ``citations`` are opaque, size-capped.
- **Arrives as a draft** (`services/generated.receive`): a person prepares and the chain
  signs off, so 8.9's "user" is a person and the module is never ``prepared_by``.
- **Provenance is an append-only record** (`wp_generation`, migration 0008): one row per
  intake, with the module fields' content hash at intake. ``papers.snapshot`` embeds the latest
  row as ``body["generated"]`` in every version, so the version hash covers the inputs and
  citations and the archive carries them in ``versions/NNNN.json``; ``paper.json`` gains
  ``generated_by``. Hand-made papers gain no key: no earlier hash moves.
- **Module fields are locked** (``LOCKED_FIELDS``; `papers.refuse_locked`, also on
  post-assembly amendments): "nobody retypes anything". The **conclusion stays a person's**;
  Materiality, Sampling and Analytical Review may deliver one, WorkMind may not (spec 7).
- **Per-source rules**: sampling's formula and seed must appear verbatim in the paper's text
  ("printed on it"); the memo's Spine figures must come from the binder's linked version,
  else refused; unlinked, they are kept and marked ``not_checked`` (the D30 pattern); the
  variance paper names both periods and its thresholds; WorkMind names its run and source-row
  citations, is validated in full, and is then **refused with 501** until the module exists
  and an accepted run can be verified; ``spine`` is Stage E.
- **One paper per run**: ``run_id`` required for WorkMind, optional otherwise, unique within
  its source when given (partial unique index). **No intake after assembly**; regeneration of
  an existing paper is Stage E's new-version-with-reason case (spec 3F).
- **Who may deliver**: the authenticated identity is ``received_by``; an optional
  ``OAK_INTAKE_CREDENTIAL`` bearer; under header auth only ``OAK_INTAKE_IDENTITIES``, none
  listed meaning no intake. **Attachments** (decision 10, clarified after the attachment-
  workflow investigation): Supporting attachments are uploaded separately through the existing attachment API after intake creates the draft paper, but before the preparer completes preparation. The preparer must be able to review the generated content and its supporting attachments before proceeding. An attachment row belongs to its paper (D17), so
  nothing can attach before intake creates the paper; the files join version 1 at the
  preparer's prepare. No staging table or second attachment lifecycle exists.
- Screen 2 shows a read-only "Generated by" panel (source block, run, delivery, inputs and
  citations behind a toggle) and disables the locked fields; screen 1 marks generated papers.

## D32 · Pass 2 Stage E: papers the Financial Spine produces — 1 Nov 2026

Spec 3A: "Lead schedule per area, tying to the Financial Spine, with the WPs beneath it"; spec
3C: the Spine produces "Every lead schedule, and the adjustment chain"; spec 3E: the chain FS
line → lead schedule → working paper → source document. Built in six steps (E1–E6; plan and
history in ``docs/PASS2_STAGE_E_PLAN.md``) on the specification alone, since no further senior
or chartered-accountant input was available: every open question was settled with the most
conservative reading of the spec's words (plan §15) and each assumption is recorded in
``docs/DECISIONS_PENDING.md`` (items 15–22). Nothing the firm has not supplied is invented.

- **Two kinds of paper, pulled by a person** (`services/spine_papers.py`): one lead schedule
  per mapped area D–T (`<area>-L`) and one adjustment chain per binder (`W-ADJ`, section W
  Completion), generated from the binder's linked, **locked** Spine version only (decision 1:
  a locked version has a hash and never changes, CAF D25). Both go through the Stage D intake
  with ``source = "spine"`` and an internal flag the HTTP endpoint never sets, so the Stage D
  guarantees hold and no outside caller can deliver a Spine paper. Any authenticated user may
  generate (decision 11); the paper arrives as a draft and the ordinary chain signs it off.
- **Figures exactly as served** (CAF D30 honoured): every amount is accepted only as the
  Spine's string or as absent; the block (`schemas/generated.SpineBlock`) types figures as
  text, so a number the Binder computed cannot enter it. Lines, ledgers, the Spine's own
  per-head totals, the adjustments touching the area and the uncorrected schedule are rendered
  into ``result`` without a sum, netting, rounding or comparison; a head with no ledger entry
  or no served figure is described in those words ("no figure served") and never as nil or
  zero (decision 13). ``population_sample`` is the one Binder-written sentence on a Spine
  paper: the version's label, id and hash and counts of the rows served (never a figure), so
  the paper says what it rests on; it is locked with the Spine's other fields.
- **The area map is the firm's** (`services/templates.py` ``areas``, `services/area_map.py`):
  head ids only, as the Spine's tree spells them; a listed head covers itself and every
  descendant found exclusively through the ``parent`` field each head carries in
  ``GET /api/tree``, never through the shape of an id (an earlier draft derived the parent from
  the id's last dot; withdrawn). Validation: syntax at load; against the served tree, every id
  exists, no overlap after expansion, and mappable heads in no area are reported. **Shipped
  templates carry an empty map**, stated by name on the card, in the status and by
  `templates_check` (which reads a tree only when given ``--tree FILE`` or ``--spine``).
- **Locked fields narrower for Spine papers** (``SPINE_LOCKED_FIELDS``): the Spine produced
  figures, not narrative, so ``objective`` and ``procedure`` are not locked and arrive empty
  unless the template carries approved wording (decision 5); ``title``, ``section``,
  ``sa_refs``, ``population_sample`` and ``result`` are locked; the conclusion is a person's.
- **References the Binder writes** (FS lines from a lead schedule; working papers named by
  adjustments, matched by exact text, decision 7) are created by ``oak_spine``; the person who
  asked is the provenance row's ``received_by``. That marker, with the target's presence in an
  earlier Spine block of the same paper, is the only reliable test of Binder ownership.
- **Freshness** (`spine_papers.freshness`): the recorded version id and hash against the
  binder's link and the Spine's current answer, ids and hashes only; ``current``, ``stale``
  (re-linked, or hash moved) or ``not_checked`` (Spine unreachable), on the status, the paper
  (``generated.freshness``) and the screens; filling it costs one Spine read of the linked
  version each time a Spine paper is read, accepted so the paper screen has one source of
  truth. A stale paper is **information, never a blocker**
  (decision 8): the specification's four blockers stand; the assembly status's not-checked list
  names it with both versions.
- **Regeneration** (`spine_papers.regenerate`, open binders only, decision 15): rewrites the
  Spine's fields, returns the paper to draft, appends a provenance row with the new run id,
  keeps the person's objective, procedure and conclusion and every earlier version, and moves
  only Binder-owned references whose target the new version lacks; everything else is kept and
  a kept reference with a vanished target is listed for review. Added, removed, kept and
  for-review targets are recorded in ``inputs.regeneration`` and returned. After assembly the
  link is frozen (D29) and a locked version cannot change, so there is nothing to regenerate
  from; the Pass 1 amendment path (spec 3F) is unchanged.
- **One paper per run** (decision 14): run id ``<binder>/<version>/<hash>/<area|adjustments>``,
  unique per binder under migration 0008's per-source index, so several binders may share a
  version and a duplicate request names the existing paper.
- **Screens**: the Binder screen's Spine papers card (areas, chain, states, reasons, generate)
  and the generated panel's Spine block, freshness banner, Regenerate and reference changes.
- **Decisions 1–15** (plan §15): locked only; ``<area>-L``; ``W-ADJ`` in W; figures in
  provenance and markdown; objective and procedure unlocked and empty; regeneration as a new
  row; exact-match references; stale as information; no archive summary member; the memo's
  Spine figures left to the Materiality module; any authenticated user; person-triggered;
  ledgerless areas still get a lead schedule; the run id above; no post-assembly regeneration.
- **Limitations**: empty area maps and placeholder area names; no required lead schedule per
  area in any template; empty wording slots; no SA references seeded. No schema change.

## D33 · Pass 2 Stage F: review levels, configurable per engagement — 1 Nov 2026

Spec 3D: "Levels: preparer → senior → manager → partner → EQR, configurable per engagement."
Everything else that governs the build already stands: spec 3B's five statuses, spec 3D and
8.9's "who, when, and which version" on every sign-off, 8.1 and 8.2 on sign-off, and spec 4's
immutable ``wp_version`` with its single ``reviewed_by``. Built on migration 0009.

- **The preparer is level one and is not a new record.** Spec 3B makes preparation the first
  status transition and names "prepared by + date"; ``papers.prepare`` already writes the
  preparer's identity, time and version into the immutable prepared version (D12, D14). Stage F
  presents that row as the first step of the chain wherever the chain appears, refuses
  "preparer" in the configuration, and writes no duplicate.
- **One append-only row per level review** (`wp_review`: paper, the prepared version reviewed,
  level, reviewer, time; unique per version and level). The existing review action records the
  next pending level for the current prepared version; the paper stays ``in_review`` until the
  last configured level, whose reviewer becomes the reviewed version's ``reviewed_by`` (spec 4's
  single field read as the final reviewer). The sign-off step is untouched. A binder without
  configured levels writes no row and runs the Pass 1 chain exactly as before.
- **Configuration per binder** (``binder.review_levels``, nullable text array; null or empty
  means the Pass 1 chain), changeable while the binder is open and no level review exists for
  any of its papers. **Permanent freeze**: once one does, the service refuses (409) and a
  database trigger (`oak_binder_review_levels_frozen`) refuses the update too, so a level can
  never be removed under a paper mid-review (the case that motivated the rule: senior and
  manager done, partner removed, paper reviewed without the partner). No unfreeze: a mistake
  after the first review is completed as configured. After assembly the binder is frozen anyway.
- **Cycles.** Level reviews belong to the prepared version they reviewed. An edit or amendment
  returns the paper to draft; the next prepare starts a new cycle with no levels done, and the
  earlier rows stay as history. The archive's per-paper ``reviews.json`` lists the configured
  levels and one cycle per prepared or amended version: preparer, level reviews, reviewed and
  signed-off versions. It is outside the manifest, so earlier assembly hashes stand.
- **Screens**: the paper's sign-off panel shows the chain and labels the action with the next
  level; the Binder screen's Review levels card edits the list while it may change.
- **Decisions taken on the specification alone**: the preparer as the fixed first level; no role
  enforcement, since identities are strings and no role model exists; no rule about one person
  at several levels or the preparer reviewing, since the spec states none; freeze binder-wide at
  the first level review; no template-level defaults; the archive member outside the manifest.
- **Limitations**: roles are recorded, not verified; configured names are free text with the
  spec's four offered as the placeholder; no default per engagement type.

## D34 · Pass 2 Stage G: close-out — 1 Nov 2026

Pass 2 as spec 6 lists it is built (D28–D33) and this decision closes it with one archive
member, a verification of the whole, and the documentation brought level with the code. No
schema change; migrations 0001–0009 untouched; nothing committed by the stage itself.

- **`cross_reference_map.json` in the produce archive.** Spec 3E and screen 4 define the map
  (FS line → lead schedule → working paper → source document, broken and amended links
  flagged); spec 3G wants the complete file in native formats, and a map that lives only on a
  screen is not in the file. The member is `XrefMapOut` as `GET /api/binders/{id}/xref-map`
  serves it, built by the same `xref_map.build` from the recorded references and the FS lines
  the assembly recorded (D30's `fs_lines` snapshot, with the Spine fallback only for a file
  assembled before D30). So the member is byte-identical whether the Spine answers, fails,
  times out or is not configured, and production never calls the Spine for it. It sits
  outside the manifest and the file hash, like every Pass 2 member, so every earlier assembly
  hash stands and `verify` is unchanged.
- **The archive inventory, proven.** `tests/test_api_close_out.py` assembles a binder that
  uses every Pass 2 feature (logs, Spine link, lead schedule and adjustment chain, a sampling
  paper from the intake with its provenance, two review levels, references of every kind) and
  checks that the archive carries manifest, binder, audit trail, access log, discussions,
  departures, the map and checksums at the top, and per paper the record, every version with
  the embedded provenance, review notes, the review chain and cross-references; that the map
  equals the endpoint and is unchanged with the Spine down; and that the manifest and hash are
  what assembly recorded.
- **The blocker inventory is unchanged and now pinned by a test**: the spec's four
  (`unsigned_paper`, `open_review_notes`, `broken_reference`, `missing_required_paper`),
  D17's `report_not_dated`, and D29's four Spine-link kinds (`spine_version_unlocked`,
  `spine_version_missing`, `spine_unreachable`, `spine_version_not_verified`). Stages C–G added
  none; staleness, unmatched adjustment references and unchecked FS lines are information.
- **Documentation corrected, not rewritten**: the Pass 2 plan's header no longer says nothing is
  built and its open points record what was built; the README's stage table, layout table,
  produce row and the "deferred" note; `DECISIONS_PENDING.md` separates what Pass 2 built from
  what remains for the firm and the chartered accountant. `PASS2_COMPLETION_REPORT.md` is the
  report, written to the Pass 1 report's pattern.
- **Limitations carried forward, stated as such**: Materiality, Sampling and Analytical Review
  exist as a contract only, no module is connected; WorkMind is refused; the shipped area maps
  are empty and area names are placeholders, so no lead schedule can be generated until the
  firm enters a map; no required lead schedule per area; empty wording slots; no SA references;
  review-level roles are recorded, not enforced.

## D35 · Post-Pass 2 follow-up: what could still be finished without the firm — 1 Nov 2026

After Pass 2 closed (D34) the remaining items were sorted into what the project can finish on
the specification alone and what needs the firm, a chartered accountant or a module that does
not exist. Built here, all small and all without inventing content:

- **SA references prefilled from the index** (spec 3B lists "SA reference(s)" among the
  paper's fields; spec 3A's index names the required papers). The Binder screen's Create
  action for a missing paper already prefilled reference, section and title; it now also
  prefills the template's `sa_refs` into an editable field on the new-paper form and sends them
  with the create request, which the backend already accepted. Shipped templates carry no
  references, so today the field prefills empty; the mechanism waits for the chartered
  accountant's list (DECISIONS_PENDING item 4). Tests on both sides; the three documents that
  had said the copy was "not yet" made now describe the behaviour.
- **Generated references in templates** (D32). A template may require `<area>-L` or `W-ADJ` so
  that the generated lead schedule or adjustment chain fills the slot. The loader now refuses
  such a reference in any section other than the one the Binder generates it in, by name,
  since a paper there could never satisfy the requirement; the check command lists the
  generated papers a template requires. No shipped file is affected.
- **Review-level policy**: no enforcement was added. Who may review at which level is a firm
  policy the specification does not state (assumptions 24–25); the exact questions are in
  `docs/REVIEW_LEVEL_POLICY_REQUEST.md` and DECISIONS_PENDING items 29–31. The Binder would
  build only what the answers require, with no defaults of its own.
- **Vault**: the Google Drive adapter (D27) is complete and `OAK_STORE=vault` is the
  development setting; the refresh token and client file are in `backend/secrets`, one local
  attachment copy remains in `var/attachments`. No token was refreshed and nothing was deleted
  in this follow-up; the firm's items 8–10 stand. `vault_login --check` reads the folder
  through a short-lived access token held in memory and writes no file; it was not run because
  it still exchanges the refresh token with Google, which the owner asked not to happen without
  permission.
- **Not built, and said so**: connections to Materiality, Sampling, Analytical Review and
  WorkMind (the modules do not exist; the contract is `docs/GENERATED_PAPER_INTAKE.md`), the
  templates' content and area maps (`docs/TEMPLATE_CONTENT_REQUEST.md`,
  `docs/SPINE_TREE_REQUEST.md`), and anything that would encode a firm policy.

## D10 · Pass 1 first — 28 Oct 2026

Build order follows spec §6, Pass 1: index and templates · the WP record with
preparer/reviewer sign-off · attachments · completeness view · assembly with the 60-day
clock and the lock · retention clock · produce-file export. The schema leaves room for
Pass 2 tables but does not build their features. Each acceptance item in spec §8 that
falls in Pass 1 becomes a named test before the feature is written.
