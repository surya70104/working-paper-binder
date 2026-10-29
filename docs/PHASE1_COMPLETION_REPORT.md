# Working Paper Binder — SA 230 · Phase 1 completion report

**Date:** 29 October 2026, revised the same day after the review-note workflow (D21) and the
index-template validation · **Project:** `D:\WORKING PAPER BINDER` (standalone; not part of CAF)
**Basis:** `docs\WORKING_PAPER_BINDER.md` (spec), decisions D1–D21 in `docs\architecture.md`

## 1. Verdict

Phase 1 (spec §6, Pass 1) is **implemented and verified, with two unresolved items**. It is
not 100 % complete: one acceptance criterion is partly satisfied because broken-reference
detection depends on Pass 2 cross-reference data that does not exist, and attachments use a
local store because no vault exists to integrate with. Everything else Pass 1 names,
including the review-note workflow, is built, tested against a real PostgreSQL database, and
most of it has been exercised in the browser.

## 2. Stages completed

| Stage | Delivered |
|---|---|
| 1 | Standalone git project, folder layout, spec copy, architecture notes, ignore rules |
| 2 | Backend (Python 3.11, FastAPI, SQLAlchemy, Alembic) and frontend (React, TypeScript, Vite, Tailwind) configuration; settings guards that refuse any database but the Binder's own |
| 3 | Separate databases and roles (`oak_binder`, `oak_binder_test`, `oak_binder_owner`, `oak_binder_app`), migration 0001: `binder`, `wp`, `wp_version`, `wp_attachment`; append-only `wp_version` enforced by trigger and grants; clocks and sign-off rules as database CHECKs |
| 4 | Index templates per engagement type, binders with completeness and the 60-day/7-year clocks, working papers with every spec field, immutable version history, the sign-off chain draft → prepared → in review → reviewed → signed off, each step an authenticated action writing a version with actor and time |
| 5 | Binder list, Binder and Working paper screens; markdown fields rendered through a sanitiser |
| 6 | Attachments (native format, SHA-256, write-once local store), assembly with named blockers, manifest and reproducible file hash, post-assembly amendments with reason/author/date, verification with tamper detection, retention gating and auditable purge, one-action produce-file archive with checksums, the Assembly & retention screen; migration 0002 (`binder_event`, attachment ownership, purged state) |
| 7 | Review notes from the spec's own record: raised → assigned → responded → cleared, append-only, each step with actor and time; an open note blocks the paper's sign-off and the binder's assembly, named per paper; the Review notes screen; migration 0003 (`review_note`). Index-template loader enforces spec §3A and §3B structure and reports placeholder content |

## 3. Test results (run 29 October 2026)

| Check | Result |
|---|---|
| Backend suite against `oak_binder_test` | 141 passed, 1 skipped (the database-rebuild test, off by default), 0 failed |
| Backend lint (ruff), format (ruff format), types (mypy strict) | pass, 57 source files |
| Frontend unit tests (vitest) | 42 passed, 9 files, 0 failed |
| TypeScript typecheck and production build | pass |

Each spec §8 acceptance item that falls in Pass 1 has a named test; see §5 below.

## 4. Demonstrated in the browser

Against `oak_binder_test`, on binder ENG-2026-001 (evidence: the event table and version rows):

- Binder list and creation; report date set, showing assembly due 2026-12-27 and retention
  until 2033-10-28 (report date + 60 days, + 7 years).
- Working paper creation for every required paper, markdown Read/Edit views, the full
  sign-off chain, and the version history (C-1 reached version 10).
- A CSV attachment uploaded with identifying characteristics, downloaded byte-identical,
  and carried in the version body.
- Assembly at 12:31 with a manifest and file hash; produce-file at 12:49 (32 members);
  an amendment of C-1 with a reason at 12:59; re-assembly at 15:56 recording the previous
  hash; produce-file again (36 members).
- A stale-screen defect found during testing (buttons re-enabled before the reload) was
  fixed across all screens with regression tests.

Not demonstrated in the browser, by design: purge after the retention date. It is verified by
an automated test with an injected date; no development clock override exists.

## 5. Acceptance criteria (spec §8)

| # | Criterion | Status | Evidence |
|---|---|---|---|
| 1 | A paper without a conclusion cannot be signed off | **Satisfied** | service rule, database CHECK, screen; `test_sign_off_requires_a_conclusion` |
| 2 | A paper with an open review note cannot be signed off | **Satisfied** | real notes (migration 0003); `test_open_note_blocks_sign_off_until_cleared`: raised, assigned and responded all block, cleared releases |
| 3 | Assembly blocked by unsigned papers, open notes, broken references, missing required papers, each named | **Partly satisfied** | unsigned papers, open notes and missing papers: named, tested (`test_open_note_blocks_assembly_by_name`); broken references: reported as *not checked*, dependent on Pass 2 cross-reference data (D21) |
| 4 | After assembly a delete fails and an edit creates a new version with a reason | **Satisfied** | `test_after_assembly_edits_need_a_reason_and_deletes_fail`; browser amendment at version 7 |
| 5 | Manifest lists every paper with its hash; recomputing the file hash reproduces it | **Satisfied** | `test_assemble_freezes_the_file_with_a_manifest_and_hash`, `test_verify_reproduces_every_hash_and_detects_tampering` |
| 6 | Produce-file returns the complete file in native formats plus the manifest, in one action | **Satisfied** | `test_produce_file_is_one_archive_with_native_files_manifest_and_trail`; two archives produced in the browser |
| 7 | Retention date is report date + 7 years, and purge before it fails | **Satisfied** | database CHECK; `test_purge_is_refused_before_retention_and_recorded_after` |
| 8 | A sampling paper generated by the Sampling module carries its formula and seed | **Not applicable to Pass 1** | generated papers are Pass 2 |
| 9 | Every sign-off records user, timestamp and paper version | **Satisfied** | each sign-off step writes an immutable `wp_version` row with its actor and time |

## 6. Unresolved items

**Pass 1 items that cannot be closed yet**

1. **Broken-reference blocker** (§3E, §3F, §8.3). Reported as *not checked* on the Assembly
   screen. A cross-reference can point at a paper, a Spine FS line or a vault document (§4);
   papers are never deleted and a foreign key forbids a dangling paper id, so only references
   to the Spine and to a vault can break, and neither exists. Dependent on Pass 2
   cross-reference data (D21).
2. **Vault integration** (§6 "attachments from the vault"). **Not completed because no vault
   was found**: a read-only search on 29 October 2026 of this project, the Financial Spine
   (`D:\CAF`), the OAK notes and every project document on `D:\` found no vault module, API
   or credentials. Attachments are kept in a local write-once, content-addressed store
   outside the web root, re-hashed on every read; `vault_doc_id` holds the store key, and
   the store sits behind one interface so a vault can replace it without a schema change
   (D7, D17).

**Closed since the first version of this report**

- **Review-note workflow** (§3D, §4, §5.3, §8.2, §8.3): built as migration 0003 and
  verified; see stage 7 above and D21. The review-note stub no longer exists.
- **Index-template structure** (§3A, §3B): the loader now refuses any file that lacks a
  standard section, renames a spec-named section, or has repeated, blank or malformed
  required papers; 28 tests. The content remains placeholder (see below).

**Other open points, outside the Pass 1 definition**

- Access log of who opened the file after assembly (§3H): spec §6 assigns it to neither pass;
  not built; the `produced` event records exports. Needs a decision.
- Index template content: section names and the six required papers come from the spec's
  own words; the 17 areas D–T carry generic names, no template requires a paper in any
  area, and the four templates share one required list. Marked draft for chartered
  accountant review; the template API reports these placeholders. Not approved by anyone.
- One development identity (`OAK_DEV_USER`): preparer, reviewer and signer are the same
  person in a demo. Real authentication is a production-hardening decision (D8).
- Configurable review levels beyond preparer and reviewer (§3D): Pass 2.

## 7. Database and project safety

- The live `oak_binder` database has **never been migrated or written**: 0 tables, confirmed
  by read-only probe after every stage.
- `oak_binder_test` is at migration 0003. Migrations 0001 and 0002 were never edited after
  they were applied to a database holding data; Stage 6 changes went into 0002 and review
  notes into 0003, both additive. Before 0002 was applied a `pg_dump` was taken
  (`D:\oak_binder_test_before_stage6.dump`, 16,505 bytes, verified with `pg_restore --list`
  and a row count of its data section); its validity was re-checked before 0003.
- The test suite preserves what it finds: schema is only upgraded, every test runs in a
  rolled-back transaction, engagement names carry random suffixes, attachment tests use a
  temporary folder, and the destructive rebuild test runs only with `OAK_TEST_REBUILD=yes`.
  Row counts were identical before and after every suite run (latest: 2 binders, 7 papers,
  28 versions, 1 attachment, 5 events, 0 review notes).
- **CAF (`D:\CAF`) was never modified**: its working tree showed 0 changes and the same HEAD
  commit at every check. Its databases, roles and `.env` were never read for credentials or
  connected to.
- No password or `.env` value was printed or stored outside the git-ignored `backend\.env`.

## 8. Not yet done, administratively

- Nothing is committed: the repository on branch `main` holds all Stage 1–6 work as
  untracked files. A first commit is the next administrative step.
- No browser end-to-end test suite exists; screens are unit-tested with a mocked API, and
  the API is tested against the real database.
