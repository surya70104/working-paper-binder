# Working Paper Binder — SA 230 · Pass 1 completion report

**Date:** 30 October 2026, final (fifth revision) ·
**Project:** `D:\WORKING PAPER BINDER` (standalone; not part of CAF) ·
**Basis:** `docs\WORKING_PAPER_BINDER.md` (identical to `D:\WORKING_PAPER_BINDER.md`),
decisions D1–D27 in `docs\architecture.md`

## 1. Verdict

**Pass 1 as spec §6 defines it is complete and verified**, including attachments from the
vault, which is now the firm's Google Drive folder. Every Pass 1 feature exists, every Pass 1
acceptance criterion (§8.1–§8.7, §8.9) holds, and the records of §3H and the authenticated
action of §7 are built. The items that remain are not code this project can write: template
content for a chartered accountant, Spine-dependent checks that §6 places in Pass 2, and the
firm's deployment decisions. Section 6 lists each with its owner. Nothing was invented for
sections D–T, and no external approval is claimed.

## 2. Pass 1 requirements, item by item

| Spec | Requirement | Status | Where |
|---|---|---|---|
| §3A, §6 | Index template per engagement type; standard sections A, B, C, D–T, W, X, Z | Done; content beyond what the spec names is draft (CA review) | `templates/*.json`, `services/templates.py`, Binders screen warning |
| §3A | Completeness view: missing required papers per section as a blocking count | Done | `services/binders.build_index`, Binder screen |
| §3A | Lead schedule per area tying to the Spine | Pass 2 (Spine) | — |
| §3B, §4 | The working paper with every field; stable reference; status chain | Done | `models/wp.py`, `services/papers.py`, Working paper screen |
| §3B | Cross-references in and out | Done | `services/xrefs.py`, `CrossReferences.tsx` |
| §3D, §8.2 | Review notes; open note blocks sign-off | Done (built ahead of Pass 2) | migration 0003, `services/review_notes.py` |
| §3D | Every sign-off records who, when, which version | Done | immutable `wp_version` rows |
| §3E, §8.3 | Broken-reference detection blocks assembly | Done for paper and document targets; FS lines *not checked* until the Spine exists | `assembly.blockers`, `xrefs.broken` |
| §3F | 60-day countdown; Assemble freezes, hashes, writes manifest; named blockers; amendments with reason, author, date | Done | `services/assembly.py`, Assembly screen |
| §3G, §8.7 | 7-year retention; native format; one-action produce; purge only after retention, recorded | Done | `services/retention.py`, `services/produce.py` |
| §3H, §4 | Access log, post-assembly, append-only | Done | migration 0004, `services/access.py` |
| §4 | Append-only `wp_version`, `review_note`, `access_log` at the database | Done | triggers and grants in migrations 0001, 0003, 0004 |
| §5 | Screens 1, 2, 3, 5 | Done | frontend pages |
| §5 | Screen 4, cross-reference map | Pass 2 (§6) | — |
| §6 | Attachments from the vault | **Done: Google Drive** (D27), verified on `oak_binder_test` | `services/google_drive.py`, `vault_login.py`, `vault_migrate.py` |
| §7 | Sign-off as an authenticated action | Done: dev identity, or a trusted-proxy header (D24) | `identity.py`, `config.py` |
| §2 / NFRA | Production of the complete file in one action, native formats | Done | produce-file archive |

## 3. Tests and checks (final run, 30 October 2026)

| Check | Result |
|---|---|
| Backend suite against `oak_binder_test` (231 collected) | **230 passed, 1 skipped** (database-rebuild test, off by default), 0 failed |
| Backend format (ruff format), lint (ruff), types (mypy strict) | pass, 79 source files |
| Frontend unit tests (vitest) | **48 passed**, 10 files |
| TypeScript typecheck and production build | pass |

One test was corrected in this final pass: the migration dry-run test asserted over every
attachment row in the shared test database and tripped on the migrated demo row; it now
asserts over its own rows only.

## 4. Browser verification (development servers, `oak_binder_test`)

Performed in the app's browser pane against the frontend on port 3001 and the backend on
port 8001, the latter running in vault mode:

- **Binders screen**: both demo binders listed; the New binder form shows the template
  draft warning with its three placeholder findings. Created `BROWSER-CHECK-2026-10-30`
  (statutory). Set the report date to 2026-10-30: assembly due 2026-12-29 with 60 days left,
  retain until 2033-10-30.
- **Binder screen**: six missing required papers shown per section as a blocking count;
  "Create" beside C-1 prefilled the New working paper form; the paper was created.
- **Working paper screen**: conclusion entered and saved; the sample CSV attached through
  the API (the browser pane cannot pick files) appeared with its identifying characteristics
  and hash; Prepare, Submit for review, Review and Sign off ran in order, writing versions 1,
  2 and 3 with preparer, reviewer and signer and their timestamps; the status reads Signed
  off · version 3. Review notes and cross-references sections present and empty.
- **Assembly screen, new binder**: the five remaining missing papers named as blockers,
  Assemble offered, the not-checked line for FS-line references, retention date, no events.
- **Assembly screen, ENG-2026-001**: nothing blocks, manifest of six papers with the C-1
  attachment, Verify hashes and Produce file (zip) offered, Access log section present.
- **Review notes screen, ENG-2026-001**: no open notes, cleared notes available.

Not done in the browser: attaching through the file picker (API used instead) and assembling
the new binder (it lacks five required papers; assembly and production were verified on
ENG-2026-001 through the API).

## 5. Google Drive vault verification (`oak_binder_test` only)

- Consent completed by the firm; the saved token's account owns the vault folder; the folder
  id in `.env` was corrected from a two-character transcription error found by a
  name-filtered lookup; `vault_login --check` reports the folder reachable and writable.
- The one local attachment was migrated: uploaded once, verified on Drive's SHA-256 and on an
  independent download; the local copy kept.
- With `OAK_STORE=vault` on the development backend (worker restarted 21:16): 21 API checks
  passed, including download with matching hash, verification of every recorded hash, a
  produced archive that verifies with the Drive bytes inside, and purge refused before
  retention and on an open binder with nothing changed.
- The browser-check attachment uploaded through the running backend landed in the vault
  folder, marked, locked, with Drive's SHA-256 equal to the recorded hash and to an
  independent download.
- Final state: 2 attachment rows, both in the vault folder, locked, hashes matching on
  Drive, on download and in the database; the migrated one also matches its local copy. The
  adapter made no list or search call. Nothing was deleted from Drive or disk.

## 6. Remaining items, with owners

**Chartered accountant / senior**

1. Index-template content: names for areas D–T, required papers per engagement type, SA
   references. The spec supplies none; the files hold exactly what it names and are marked
   draft. A draft list was sent to the senior on 30 October; no reply is recorded here.
2. Confirmation of three stated interpretations: the access log's reading of "opened"
   (D25), the cross-reference `direction` field (D26), and what "superseded paper" should
   mean for broken-reference detection, since papers are never deleted here.

**Firm, deployment**

3. OAuth consent screen set to "In production" (a Testing-status refresh token expires after
   seven days); custody of `backend\secrets`, which under the full `drive` scope reaches the
   whole Google account; whether to keep the local attachment copies.
4. The authenticating reverse proxy and identity provider, `OAK_TRUSTED_PROXIES`, TLS.
5. Applying migrations 0001–0005 to the live `oak_binder` when going live. It has never been
   touched: 0 tables.

**Pass 2 (spec §6)**

6. Checking cross-references to FS lines, lead schedules per area, the cross-reference map
   screen, generated papers, discussions and departures logs, configurable review levels,
   WorkMind papers.

## 6a. Independent follow-up (31 October 2026)

Done without senior or firm input, adding no audit content: a template authoring guide
(`docs/TEMPLATE_AUTHORING.md`); a template check command
(`python -m oak_binder.templates_check`); the unconfirmed SA references removed from the four
templates and held in `docs/SA_REFERENCES_FOR_CA_REVIEW.md`; informational detection of a
cross-reference target amended since the reference was made, never a blocker; and the
one-page `docs/DECISIONS_PENDING.md`. The cross-reference direction and the access log are
unchanged. Backend 233 passed, 1 skipped; frontend 48 passed; lint, mypy strict, typecheck
and build clean. Not committed.

## 7. Safety record

- Live `oak_binder`: 0 tables, no `alembic_version`, confirmed by read-only probe after the
  final run. Every migration and every test ran against `oak_binder_test` only, and the
  migration utility asserted the database name before writing.
- `D:\CAF`: 0 changes, HEAD `d11246f` as at the start; never read for credentials.
- No password, token or `.env` value was printed; the secrets folder is git-ignored and
  untracked, proven by a test.
- `oak_binder_test` holds the two demo binders, the browser-check binder created today, and
  the rows written by browser use; the test suite's own rows are rolled back.

## 8. Commit

This revision is committed on `main` together with the Pass 1 completion work (the hash is
in `git log`). Nothing is pushed.
