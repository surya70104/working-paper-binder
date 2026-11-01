# OAK Audit · Working Paper Binder — SA 230

The outlet for the audit file. Every figure in the audit report traces to a working paper,
every working paper names who prepared it and who reviewed it, and the whole file freezes
60 days after the report date and survives seven years.

- Specification: [docs/WORKING_PAPER_BINDER.md](docs/WORKING_PAPER_BINDER.md) — the only
  source of requirements. Nothing is built that the specification does not ask for.
- Agreed decisions: [docs/architecture.md](docs/architecture.md)

This is a standalone project. It does not read from, write to, or depend on the Financial
Spine project at `D:\CAF`, its databases or its credentials. Integration with the Spine,
Materiality, Sampling and the vault is Pass 2 work and will go through APIs only.

## Layout

| Folder | Contents |
|---|---|
| `backend/` | Python 3.11 · FastAPI · SQLAlchemy · Alembic |
| `backend/src/oak_binder/models/` | Database tables: binder, binder_event, wp, wp_version, wp_attachment, review_note, access_log, xref, discussion, departure, wp_generation, wp_review |
| `backend/src/oak_binder/schemas/` | Request and response shapes |
| `backend/src/oak_binder/api/` | Routers: templates, binders, working papers, attachments, assembly and export, review notes, cross-references, discussions and departures, Spine link, generated papers, Spine papers |
| `backend/src/oak_binder/services/` | Templates and area maps, completeness, sign-off and review levels, review notes, attachments and the Drive vault, cross-references, FS lines and the map, assembly, retention, produce file, access log, records, Spine client and link, generated-paper intake, Spine papers |
| `backend/src/oak_binder/templates/` | Index templates per engagement type, as data; authoring guide in `docs/TEMPLATE_AUTHORING.md` |
| `backend/alembic/` | Migrations, including the append-only triggers |
| `backend/tests/` | Acceptance tests from spec §8, unit, database and API tests |
| `frontend/` | React · TypeScript · Vite · Tailwind · vitest · marked + DOMPurify for markdown |
| `scripts/db/` | One-time database and role creation scripts, run by a person as superuser |
| `scripts/` | Windows helper scripts |
| `docs/` | Specification and architecture notes |
| `var/` | Local runtime data: attachments, exports. Ignored by git. Never committed. |

## Ports and tools

| Item | Value |
|---|---|
| API | <http://localhost:8001> |
| Frontend | <http://localhost:3001> |
| Python | 3.11, virtual environment at `backend\.venv` |
| Node | 22, selected through fnm (`.node-version` in `frontend/`) |
| Database | PostgreSQL 16 on localhost, databases `oak_binder` and `oak_binder_test` |

## Build stages

| Stage | Contents | Status |
|---|---|---|
| 1 | Git, folder structure, spec copy, README, architecture notes, .gitignore | done |
| 2 | Backend and frontend package configuration, `.env.example`, Alembic, test tooling | done |
| 3 | Database create scripts, Pass 1 data model, migration 0001, append-only enforcement, tests | done; proven on `oak_binder_test` |
| 4 | Index templates, binders with completeness and the clocks, working papers, version history, the sign-off workflow (API) | done |
| 5 | The Binder and Working paper screens | done |
| 6 | Attachments, assembly with the lock and manifest, amendments, retention and purge, produce-file export, the Assembly screen | done; migration 0002 applied to `oak_binder_test`, suite green, assembly and production exercised in the browser |
| 7 | Review notes: raised → assigned → responded → cleared; an open note blocks sign-off and assembly; the Review notes screen | done; migration 0003 applied to `oak_binder_test`, suite green |
| 8 | Pass 1 completion: header-based authentication (`OAK_AUTH`), the post-assembly access log (spec §3H), cross-references with broken-reference blocking (spec §3E), completeness and purge-state fixes, draft-template warning | done; migrations 0004 and 0005 applied to `oak_binder_test`, suites green (D24–D26) |
| 19 | Acceptance audit (D40): every clause of spec sections 2–8 proven by `tests/test_acceptance_spec.py` and the feature modules, every user workflow walked in the browser against the Spine and WorkMind doubles served over HTTP (`tests/local_stubs.py`, `scripts/dev_backend_with_doubles.ps1`), four screen defects fixed with tests, matrix in `docs/ACCEPTANCE_MATRIX.md` | done; no schema change |
| 18 | Pass 2 completion work on the specification alone (D36–D39): a reference to a superseded (amended) paper blocks assembly until a person confirms it against the current version, recorded on the reference (migration 0010); WorkMind papers are filed only after the run is read back as accepted from a configured WorkMind, verified against a stated contract and a local double; a default area map derived from the Spine's tree makes lead schedules work when the template has none; readings and the live-versus-local status recorded | done; migration 0010 applied to `oak_binder_test` |
| 17 | Post-Pass 2 follow-up (D35): the Binder screen prefills the index template's SA references into the new-paper form and saves them with the paper; the template loader refuses a generated reference (`<area>-L`, `W-ADJ`) required outside the section it is generated in, and the check command lists the generated papers a template requires; the review-level policy questions, the template content request and the Spine tree request written for the firm | done; no schema change |
| 16 | Pass 2 Stage G: close-out. The archive gains `cross_reference_map.json`, screen 4's map built from the recorded references and the FS lines the assembly recorded, so it is the same whether or not the Spine answers; tests prove the full archive inventory (Pass 1 and Pass 2 members), the map's equality with the endpoint, and that the assembly blocker inventory is unchanged; stale documentation corrected; `docs/PASS2_COMPLETION_REPORT.md` | done; no schema change (D34) |
| 15 | Pass 2 Stage F: review levels configurable per engagement (spec §3D): the preparer always first from the prepared version, the binder's levels in order each recorded with reviewer, time, level and version in append-only `wp_review`, the paper reviewed only after the last level, sign-off unchanged, the configuration frozen for good once any level review exists (service and database trigger), the whole chain in the archive | done; migration 0009 applied to `oak_binder_test` (D33) |
| 14 | Pass 2 Stage E: papers the Financial Spine produces (spec §3A, §3C): one lead schedule per mapped area and one adjustment chain (`W-ADJ`) per binder, generated by a person from the linked, locked Spine version through the Stage D intake, figures exactly as served, FS-line and working-paper references written by the Binder as `oak_spine`, freshness (current, stale, not checked) and regeneration on open binders, the Spine-papers card and the generated panel's banner; area map configurable in templates, shipped empty | done; no schema change (D32) |
| 13 | Pass 2 Stage D: generated-paper intake (spec §3C): one endpoint, per-source rules from the spec's words, papers filed as drafts with their provenance in every version body, module fields locked, migration 0008 (`wp_generation`, append-only), WorkMind contract defined and refused until the module exists | done; migration 0008 applied to `oak_binder_test` (D31) |
| 12 | Pass 2 Stage C: FS-line references checked against the linked Spine version's presentation lines by stable `head_id`, a vanished or unknown line as a named `broken_reference` blocker, the not-checked list emptied once lines can be read, the Cross-reference map screen (screen 4) | done; no schema change (D30) |
| 11 | Pass 2 Stage B: the Financial Spine link, read-only client with an optional bearer credential, migration 0007 (nullable engagement and version on the binder), an unlocked linked version as a named assembly blocker, the link in the manifest | done; migration 0007 applied to `oak_binder_test` (D29) |
| 10 | Pass 2 Stage A: discussions and departures logs (spec §3H), append-only, on the Binder screen and in the archive | done; migration 0006 applied to `oak_binder_test` (D28) |
| 9 | Google Drive as the vault (spec §6 "attachments from the vault"): adapter behind the storage protocol, one-time consent, migration of local attachments, proxy-identity hardening | done; consent, folder check and the migration of the one local attachment run against `oak_binder_test`; vault mode verified on the development backend (D27) |

Pass 1 scope (spec §6): index and templates · the working paper record with preparer and
reviewer sign-off · attachments · completeness view · assembly with the 60-day clock and the
lock · retention clock · produce-file export.

## Setup on Windows

Everything below runs from `D:\WORKING PAPER BINDER` in PowerShell unless a step says
otherwise. Nothing is installed system-wide: Python packages go into `backend\.venv`, Node
packages into `frontend\node_modules`. Both folders are ignored by git.

### Backend

Create the virtual environment and install the package with its development tools:

```powershell
py -3.11 -m venv backend\.venv
backend\.venv\Scripts\python.exe -m pip install -e "backend[dev]"
```

Create your local configuration. Open `backend\.env` afterwards and replace every
`CHANGE_ME`. Database passwords are set in Stage 3, when the databases exist; until then the
placeholders are fine because nothing connects.

```powershell
Copy-Item backend\.env.example backend\.env
```

Then, from `D:\WORKING PAPER BINDER\backend`:

| Task | Command |
|---|---|
| Run the tests (database tests skip until `OAK_TEST_DATABASE_URL` is set) | `.venv\Scripts\python.exe -m pytest` |
| Lint | `.venv\Scripts\python.exe -m ruff check .` |
| Format check | `.venv\Scripts\python.exe -m ruff format --check .` |
| Type check | `.venv\Scripts\python.exe -m mypy` |
| Show migration SQL without connecting | `.venv\Scripts\python.exe -m alembic upgrade head --sql` |
| Check the index template files (or draft files by path) | `.venv\Scripts\python.exe -m oak_binder.templates_check` |
| Run the API on port 8001 | `.venv\Scripts\python.exe -m uvicorn oak_binder.main:create_app --factory --reload --port 8001` |

The health check is at <http://localhost:8001/api/health> and the interactive API page at
<http://localhost:8001/docs>.

### Frontend

Node 22 is required and is selected through fnm. `frontend\.node-version` pins it, and
`frontend\.npmrc` makes npm refuse any other version, so the system Node 18 cannot be used
by accident. Either activate fnm once per shell:

```powershell
fnm env --use-on-cd | Out-String | Invoke-Expression
```

or prefix each command with `fnm exec --using=22 --`. From `D:\WORKING PAPER BINDER\frontend`:

| Task | Command |
|---|---|
| Install packages (once, and after `package.json` changes) | `npm install` |
| Run the tests | `npm test` |
| Type check | `npm run typecheck` |
| Start the dev server on port 3001 | `npm run dev` |
| Production build into `frontend\dist` | `npm run build` |

The dev server proxies `/api` to the backend on 8001, so start the backend first and open
<http://127.0.0.1:3001>.

### Database: one-time creation, run by a person

The Binder uses two databases of its own on the PostgreSQL 16 server, `oak_binder` and
`oak_binder_test`, and two roles, `oak_binder_owner` (migrations) and `oak_binder_app` (the
API). They are created once by `scripts\db\02_create.sql`, run as the `postgres` superuser.
The script checks that none of the four names exist and stops without changing anything if
one does. It never drops anything and never refers to any other project's databases or roles.

First, the read-only pre-check. It shows who you are connected as and whether the names are
free. psql asks for the superuser password; nothing is stored.

```powershell
& "C:\Program Files\PostgreSQL\16\bin\psql.exe" -h localhost -p 5432 -U postgres -d postgres -f scripts\db\01_check_names.sql
```

Then the creation script. It prints each stage as it goes.

```powershell
& "C:\Program Files\PostgreSQL\16\bin\psql.exe" -h localhost -p 5432 -U postgres -d postgres -f scripts\db\02_create.sql
```

Then, in psql, set the two passwords. psql hides what you type and sends only a hash.

```powershell
& "C:\Program Files\PostgreSQL\16\bin\psql.exe" -h localhost -p 5432 -U postgres -d postgres -c "\password oak_binder_owner" -c "\password oak_binder_app"
```

Put the passwords into `backend\.env`, replacing `CHANGE_ME`, and uncomment the two
`OAK_TEST_*` lines so the database tests run. Then apply the migration from `backend\`:

```powershell
.venv\Scripts\python.exe -m alembic upgrade head
```

### What the database enforces

Migration 0001 creates the four Pass 1 tables (spec §4): `binder`, `wp`, `wp_version`,
`wp_attachment`. Rules that live in the database, not only in code:

- `wp_version` is append-only. A trigger refuses UPDATE, DELETE and TRUNCATE for every role,
  and the application role has only SELECT and INSERT on it.
- A paper cannot be `signed_off` without a conclusion (spec §8.1).
- A paper past draft must point at a real version of itself, and a version's signer and
  time move together and only after a review.
- `assembly_due` is exactly report date + 60 days and `retention_until` exactly report date
  + 7 years, or all three are empty (spec §3F, §3G, §8.7).
- An assembled binder has a report date, an assembly timestamp and a SHA-256 file hash.
- A reference is unique within a binder; one binder per engagement; no cascading deletes.

`tests\test_db_rules.py` proves each rule against `oak_binder_test`; those tests are skipped
until `OAK_TEST_DATABASE_URL` is set. `tests\test_migration_sql.py` checks the migration's
SQL without any database.

### The API so far

Interactive documentation is at <http://localhost:8001/docs> when the API runs.

| Method and path | What it does |
|---|---|
| `GET /api/templates`, `GET /api/templates/{name}` | The four index templates: sections and required papers |
| `POST /api/binders`, `GET /api/binders` | Create a binder from a template (optionally dated); list binders |
| `GET /api/binders/{id}` | The binder with its index tree, completeness count and assembly countdown |
| `PATCH /api/binders/{id}` | Set or clear the report date; both clocks follow |
| `POST /api/binders/{id}/papers` | Create a working paper; the reference is unique and immutable; `sa_refs` optional, prefilled by the Binder screen from the index template's required entry |
| `GET /api/papers/{id}`, `PATCH /api/papers/{id}` | Read a paper with its versions, attachments and cross-references; edit its content (returns it to draft) |
| `GET /api/papers/{id}/versions` | The immutable version history |
| `POST /api/papers/{id}/prepare`, `/submit`, `/review`, `/sign-off` | The workflow: draft → prepared → in review → reviewed → signed off |
| `POST /api/papers/{id}/attachments` (multipart) | Attach a native-format file with its identifying characteristics; after assembly, with an amendment reason |
| `GET /api/attachments/{id}`, `GET …/content`, `DELETE /api/attachments/{id}` | Read, download (hash re-checked), remove before assembly |
| `GET /api/binders/{id}/assembly` | State, named blockers, what is not checked, manifest, retention, events, the access log |
| `POST /api/binders/{id}/assemble` | Freeze the file: manifest and SHA-256 file hash; re-assemble after amendments |
| `GET /api/binders/{id}/verify` | Recompute every hash and compare with what was recorded |
| `GET /api/binders/{id}/produce` | One zip: manifest, binder, audit trail, access log, discussions and departures logs, the cross-reference map, every paper with its versions, review notes, review chain, cross-references and attachments, checksums |
| `POST /api/binders/{id}/purge` | After retention: destroy attachment content, record the purge |
| `POST /api/papers/{id}/review-notes`, `GET …/review-notes` | Raise a review note on a paper; list its notes |
| `POST /api/review-notes/{id}/assign`, `/respond`, `/clear` | The chain raised → assigned → responded → cleared, in order only |
| `GET /api/binders/{id}/review-notes` | Screen 3: what is open, raised by whom, assigned to whom, blocking what |
| `GET`/`POST /api/binders/{id}/discussions`, `GET`/`POST /api/binders/{id}/departures` | The discussions and departures logs (spec §3H): list, record; after assembly a reason is required |
| `GET /api/binders/{id}/spine`; `PATCH /api/binders/{id}` with `spine_engagement_id` / `spine_version_id` | The Financial Spine link: what the binder ties to and what the Spine says now; set, change or clear while open |
| `GET /api/spine/engagements/{id}`, `GET …/versions` | Read-through to the Spine for choosing a version (503 when no Spine is configured) |
| `GET /api/binders/{id}/fs-lines` | The financial-statement lines a reference may name: the linked Spine version's presentation lines by `head_id`, or why there are none |
| `GET /api/binders/{id}/xref-map` | Screen 4: FS line → lead schedule → working paper → source document, with broken and amended links flagged |
| `POST /api/papers/{id}/xrefs`, `GET …/xrefs`, `DELETE /api/xrefs/{id}`, `POST /api/xrefs/{id}/confirm` | Cross-references (spec §3E): add one with exactly one target, list in and out with the check result, remove before assembly; confirm a reference whose target paper was amended since (a superseded target blocks assembly until confirmed or removed; D36) |
| `POST /api/binders/{id}/generated-papers` | Generated-paper intake (spec §3C): a module delivers a complete paper with its inputs and citations; filed as a draft with its provenance (422 per-source rule, 409 reused run, assembled binder or a WorkMind run that is not accepted, 413 over the size cap, 404 a WorkMind run unknown to WorkMind, 503 no WorkMind configured or none answering; D37) |
| `GET /api/papers/{id}/generation` | Where a generated paper came from (404 for a hand-made one); for a Spine paper, its `freshness` |
| `GET /api/binders/{id}/spine-papers` | Stage E status: whether Spine papers can be generated and why not, the linked version, each area D–T with its lead schedule's state (`none`, `current`, `stale`, `not_checked`), the adjustment chain's state, area-map problems and unassigned heads, and `map_source`: the template's map, one derived from the Spine's tree when the template has none (D38), or none |
| `POST /api/binders/{id}/spine-papers/lead-schedules` | Generate lead schedules from the linked, locked Spine version: body `{"areas": ["D", …]}`, or `{"areas": null}` for every mapped area without one. Refusals follow the Binder's conventions: 409 when the binder is not open, not linked or its version is not locked, and for one paper per run, a reference in use or nothing left to generate; 503 when no Spine is configured or it cannot answer; 404 when the Spine no longer has the version; 422 for an area-map problem, an unmapped area or an unknown area code |
| `POST /api/binders/{id}/spine-papers/adjustment-chain` | Generate the binder's one adjustment-chain paper `W-ADJ` in section W |
| `POST /api/papers/{id}/regenerate` | Rebuild a Spine paper from the linked, locked version on an open binder: the Spine's fields rewritten, the person's kept, a new provenance row, only Binder-owned references moved; returns the paper with `regeneration.references` (409 once assembled, unlinked, on an unlocked version or on an unchanged version; 503 when the Spine cannot answer; 422 for a hand-made paper) |
| `PATCH /api/binders/{id}` with `review_levels` | Stage F: the review levels after the preparer, in order, or `null` for the Pass 1 chain; 422 for a blank, repeated or `preparer` entry; 409 once any level review exists in the binder or once assembled. `GET /api/binders/{id}` returns `review_levels` and `review_levels_frozen` |
| `POST /api/papers/{id}/review` (unchanged path) | With levels configured, records the next pending level's review of the prepared version by the caller; the paper stays in review until the last level, then becomes reviewed. `GET /api/papers/{id}` returns `review_chain`: preparer, each level and sign-off with done, by, at and version, the next level and whether the configuration is frozen |

Rules enforced in the workflow: a sign-off needs a conclusion; an open review note blocks
sign-off (real notes, migration 0003; see "Review notes" below); steps run only in order;
every step writes an immutable version naming its actor and time; an assembled binder
refuses edits without an amendment reason. The screens at <http://127.0.0.1:3001> cover
binders, one binder, one working paper, the binder's review notes, and assembly and
retention.

### Attachments, assembly, retention and production (Stage 6)

- **Attachments** are kept behind a storage protocol (D23). `OAK_STORE=local`, the default,
  is a write-once store under `var\attachments` (`OAK_ATTACHMENTS_DIR`), outside anything a
  web server serves, named by SHA-256. `OAK_STORE=vault` is the firm's **Google Drive**
  folder (D27; see "Google Drive vault" below).
  On every row the store's document id (`vault_doc_id`) and the Binder's own SHA-256 are
  kept apart; every read re-hashes the bytes and refuses a mismatch, whichever store serves
  them. Identical bytes are stored once; a purge deletes a document only when no paper in
  any binder still references it. An attachment
  belongs to the paper and joins the signed record at the next prepare; each version body
  lists the paper's attachments by hash.
- **Assembly** is blocked by named items: each missing required paper, each paper not signed
  off, each paper with open review notes, each broken cross-reference, an undated report.
  A reference to a paper or to a document is checked (D26); a reference to a
  financial-statement line cannot be followed without the Spine and is shown as *not
  checked*, with the count of such references. Assemble records a manifest and a
  SHA-256 file hash that anyone can recompute from the manifest. After assembly a change needs an amendment reason and
  writes a new version plus an event; nothing is deleted; re-assembly records the new hash
  with the previous one.
- **Retention**: purge is refused before the retention date. After it, purge destroys the
  attachment content and records the purge; paper and version rows stay with their hashes
  (D18). **The content is purged; the metadata remains.**
- **Produce file**: one zip with the manifest, the binder, the audit trail (binder events,
  every review-note step and every access), the access log, every paper with its versions,
  review notes, cross-references and attachments in native format, and a checksum list
  (D19, D22, D25, D26). Paper folders are made unique even when
  two references sanitise alike. Production is refused between an amendment and the next
  re-assembly, because the recorded manifest would no longer describe the file; the Assembly
  screen says so and withholds the link.
- **Attachment downloads** carry `X-Content-Type-Options: nosniff` so a browser never
  guesses a type from the bytes.
- The **Assembly & retention** screen (spec screen 5) is reached from the Binder screen.

How Stage 6 is verified: `tests\test_api_attachments.py`, `tests\test_api_assembly.py` and
`tests\test_db_rules_stage6.py` cover spec §8.3 to §8.7 against `oak_binder_test`, including
tamper detection on a stored file and on a produced archive; `frontend\tests\AssemblyPage.test.tsx`
covers the screen. Purge after the retention date is verified by the automated test with an
injected clock only; there is no development clock override, so a real binder cannot be purged
before its seven years are up.

### Review notes

Spec §3D: raised → assigned → responded → cleared, each step an authenticated action written
as an append-only row (migration 0003). A note is open until cleared. **An open note blocks
the paper's sign-off and the binder's assembly**, and the Assembly screen names the paper
and the count. Notes are raised and worked on the Working paper screen; the Review notes
screen (spec screen 3) lists what is open across the binder, who raised it, who holds it and
what it blocks. `tests\test_api_review_notes.py` covers every transition, each out-of-order
refusal, and both blocks; `tests\test_db_rules_review_notes.py` covers the append-only rules.

### Google Drive vault (D27)

The vault is one Google Drive folder the firm created by hand, reached through the Drive
REST API with a Desktop OAuth client. `services\google_drive.py` implements the storage
protocol: the document id is Drive's file id, the Binder's SHA-256 stays on every row and is
re-checked on every read, uploads are verified against Drive's checksum and then locked with
Drive's read-only restriction, and nothing ever calls the update-content endpoint.

**Permissions, stated plainly.** A folder a person created is not reachable with the narrow
`drive.file` scope (that scope covers only files the application created or a person picked
for it in Google's picker), so the consent asks for the full `drive` scope. **That scope
technically lets the token read, change and delete anything in the consenting Google
account's Drive.** The application confines itself to the vault folder: every file it creates
has the folder as its only parent and carries an application marker; every read, existence
check and delete first fetches the file's metadata and refuses anything not filed by the
Binder in that folder; it never lists, searches or touches other files, and the test double
asserts so. The confinement is the application's discipline, not Google's enforcement: anyone
who obtains the refresh-token file has the whole Drive. Keep `backend\secrets` on the server
only, with owner-only permissions, and revoke the consent at myaccount.google.com if it is
ever exposed. Drive's read-only restriction is likewise soft: a person with edit rights can
lift it, and the Binder's hash check is what catches a changed file.

**Setting it up**, in this order, with `OAK_STORE` left at `local` until the last step:

1. In Google Cloud: the Drive API enabled, a Desktop OAuth client downloaded to
   `backend\secrets\google-oauth-client.json`, and the OAuth consent screen **In production**
   (while it is in Testing, Google expires refresh tokens after seven days).
2. In `backend\.env`: `OAK_VAULT_URL`, `OAK_VAULT_CONTAINER` (the folder id),
   `OAK_VAULT_CLIENT_FILE` and `OAK_VAULT_CREDENTIAL` as in `.env.example`.
3. `python -m oak_binder.vault_login`: opens the Google consent in the browser, saves the
   refresh token to the credential file, then reads the folder and prints its name. It fails
   with a plain reason if the folder is not visible or writable. `--check` repeats only the
   folder check; `--no-browser` prints the URL instead of opening it.
4. `python -m oak_binder.vault_migrate` (dry run) then `--apply`: uploads every local
   attachment once, verifies it by hash, rewrites `wp_attachment.vault_doc_id` and
   `xref.to_vault_doc` from the local key to the Drive id, and keeps the local files. Version
   bodies and manifests list attachments by hash, so nothing signed changes.
5. Set `OAK_STORE=vault` and restart.

Tests: `tests\test_google_drive.py` (the adapter against a Drive double), `tests\test_storage.py`
(the storage contract over local, stand-in and Drive), `tests\test_api_drive_store.py` (upload,
download, verify, produce and purge through Drive), `tests\test_vault_migrate.py`,
`tests\test_secrets_hygiene.py`. None reaches the network; no test reads the secrets folder.

### Discussions and departures logs (Pass 2, Stage A)

Spec §2, §3H, §4: `discussion · binder · date · participants[] · matter · outcome` and
`departure · binder · requirement · reason · alternative_procedure · approved_by`, both
append-only (migration 0006, D28). Entries are recorded on the Binder screen and never
edited. "Including TCWG" is met by the participants list: write the role after the name,
for example "R. Mehta (TCWG, Audit Committee Chair)"; no field was added for it. After
assembly an entry needs an amendment reason, writes an `amended` event with author, date and
reason, and, because the logs are part of the manifest once any exist, the file must be
re-assembled before it is produced again. A purged binder takes none. Reads of an assembled
file's logs are in the access log; the archive carries `discussions.json` and
`departures.json`. Tests: `tests\test_api_records.py`, `tests\test_db_rules_records.py`,
`frontend\tests\BinderRecords.test.tsx`.

### Financial Spine link (Pass 2, Stage B)

Spec §3A ties the file to the Financial Spine. `OAK_SPINE_URL` names the Spine's service root
(for example `http://127.0.0.1:8000`); unset means no Spine, and every Spine-dependent feature
says so. The Binder only ever reads the Spine (`services\spine_client.py`, GET only, with an
optional bearer credential `OAK_SPINE_CREDENTIAL` that is never printed; production requires
`https://` unless the Spine is on the loopback interface). A binder links to one Spine
engagement and one of its versions (migration 0007, two nullable columns, D29); the ids are
verified against the Spine when set, the link may change or be cleared while the binder is
open, and it is frozen with the file after assembly. An unlocked linked version, a version the
Spine no longer has, and a Spine that cannot be read are named assembly blockers, never
silently clear. The manifest records the engagement and version ids only when a link exists,
so files assembled without one keep their hash; the assembled event records the version's lock
hash and time. Tests: `tests\test_spine_client.py` (against a Spine double, no network),
`tests\test_api_spine_link.py`, `frontend\tests\SpineLinkCard.test.tsx`.

### Generated papers (Pass 2, Stage D)

*Completion work (D37):* a WorkMind delivery is filed only after the Binder reads the run back from the
configured WorkMind (`OAK_WORKMIND_URL`, optional `OAK_WORKMIND_CREDENTIAL`, GET
`/api/runs/{run_id}`) and it reports `accepted`; the verification is recorded on the paper's
provenance. No WorkMind is connected here: the contract is tested against the local double in
`tests/fake_workmind.py`. Unconfigured, the delivery is refused with 503 and nothing is filed.

Spec §3C: "A paper produced by a module arrives complete, with its inputs and its citations,
and nobody retypes anything." `POST /api/binders/{id}/generated-papers` takes the paper's
fields exactly as a person would type them plus a `generated` block: `source` (materiality,
sampling, analytical_review, workmind, spine), `module`, optional `module_version` and
`run_id`, `generated_at`, `inputs`, `citations`, and one source block carrying what the spec
names for that source and nothing else: the memo's benchmark, band and Spine figures; the
sampling paper's formula and seed; the variance paper's current and prior periods and the
thresholds used; WorkMind's source-row citations. Rules, from the spec's words (D31):

- the paper arrives as a **draft**; a person prepares it and the chain signs off, so the
  preparer and reviewer are people (spec §2, §8.9);
- the module's fields (title, section, SA references, objective, procedure, population and
  sample, result) are **locked**: a change is refused and the module named; the **conclusion
  stays a person's** (spec §7). Materiality, Sampling and Analytical Review may deliver a
  conclusion; a WorkMind conclusion is refused;
- a **sampling** paper's formula and seed must appear verbatim in its text ("printed on it",
  §3C, §8.8) and in the block;
- a **materiality** memo's Spine figures are checked against the binder's linked Spine version
  (mismatch refused); for an unlinked binder they are kept and marked *not checked*;
- **WorkMind** deliveries are validated in full and then refused (501) until the module exists
  and an accepted run can be verified; **Spine** papers arrive in Stage E;
- `run_id` is required for WorkMind, optional otherwise, and unique within its source: one
  paper per run (409); intake after assembly is refused (409); `inputs` and `citations` are
  kept verbatim within `OAK_MAX_PROVENANCE_BYTES` (default 1 MiB, 413 above); the source blocks
  refuse unknown keys.

Provenance lives in the append-only `wp_generation` table (migration 0008: source, module,
run, generated at, who delivered it and when, the whole block, the module fields' content hash
at intake) and is embedded as `generated` in **every version body** of the paper, so the
content hash covers the inputs and citations and the archive's `versions/NNNN.json` carry
them; `paper.json` gains `generated_by`. Hand-made papers gain no key, so every earlier hash is
unchanged. Who may deliver: when `OAK_INTAKE_CREDENTIAL` is set the module presents it as a
bearer; under `OAK_AUTH=header` only identities in `OAK_INTAKE_IDENTITIES` may deliver and
none listed means no intake. Supporting attachments are uploaded separately through the
existing attachment API after intake creates the draft paper, but before the preparer completes
preparation; the preparer reviews the generated content and its supporting attachments together
before proceeding (decision 10). The paper screen shows a read-only "Generated by" panel; the
index marks generated papers. The contract with worked examples is in
`docs\GENERATED_PAPER_INTAKE.md`; the fixtures under `backend\tests\fixtures\generated` are
those examples. Tests: `tests\test_api_generated.py`, `tests\test_db_rules_generation.py`,
`frontend\tests\GeneratedPanel.test.tsx`.

### Review levels (Pass 2, Stage F)

Spec §3D: "Levels: preparer → senior → manager → partner → EQR, configurable per engagement";
§3B fixes the statuses draft, prepared, in review, reviewed, signed off; §8.9: every sign-off
records who, when and which version. Decision D33.

- **The chain is always preparer, then the binder's configured review levels in order, then
  sign-off.** The preparer is level one by §3B and is read from the prepared version's own
  immutable record (`prepared_by`, `prepared_at`, version); it is never configured, and a list
  that names it is refused. A binder with **no configured levels keeps the Pass 1 chain**: one
  review, then sign-off, with no level-review row written.
- **Configuration**: `review_levels` on the binder, set through `PATCH /api/binders/{id}` and the
  Binder screen's Review levels card, while the binder is open. The specification's names
  (senior, manager, partner, EQR) are offered as the placeholder; the firm chooses per
  engagement. Entries are non-blank, unique and at most ten.
- **Each level review** (`POST /api/papers/{id}/review`, the existing action) records the next
  pending level for the current prepared version in `wp_review`: reviewer identity, time, level
  and version, append-only at the database (migration 0009). The paper stays **in review** until
  the last configured level; that reviewer is then the reviewed version's `reviewed_by`, and the
  sign-off step, its conclusion rule and its open-note rule are unchanged. Sign-off before the
  last level is refused because the status is still in review.
- **Permanent freeze.** The configuration can change until the first level review is recorded on
  any paper of the binder. From then on it is frozen for good: the service answers 409, and a
  database trigger refuses the update even outside the API, so a chain can never lose a level
  under a paper mid-review. After assembly the binder is frozen anyway (spec §3F). A
  configuration mistake discovered after the first review is completed as configured; there is
  no override.
- **Amendments.** An amended paper returns to draft and runs the whole chain again for its new
  version: preparer, every level, sign-off. Earlier level reviews stay on file against the
  version they reviewed; nothing is modified or deleted.
- **Archive.** Each paper's `reviews.json` lists the binder's configured levels and one cycle per
  prepared or amended version: the preparer, every level review with reviewer, time, level and
  version, the reviewed version and the signed-off version. It sits outside the manifest, so
  every earlier assembly hash stands; the manifest is unchanged.
- **Screens.** The paper screen's sign-off panel lists the chain with done and pending steps and
  labels the action "Review as <level>"; the Binder screen's Review levels card edits the list
  while it may change and otherwise shows it read-only with the reason.
- **Limitations, stated as such.** Identities are strings and the Binder has no role model, so
  a level is recorded with whoever reviewed it and no role is enforced; the specification states
  no rule against one person reviewing several levels or the preparer reviewing, and none is
  added; templates carry no default levels. Tests: `tests\test_db_rules_review_levels.py`,
  `tests\test_api_review_levels.py`, `frontend\tests\ReviewLevels.test.tsx`.

### Spine papers (Pass 2, Stage E)

Spec §3A: "Lead schedule per area, tying to the Financial Spine, with the WPs beneath it";
§3C: the Financial Spine produces "Every lead schedule, and the adjustment chain". Stage E builds
both from the binder's linked Spine version, through the Stage D intake with `source = "spine"`,
so every Stage D guarantee holds: the paper arrives as a **draft**, a person prepares and the
chain signs off, the provenance travels in every version body, and the Spine's fields are
locked. Decision D32 records the design and the fifteen decisions taken; the assumptions behind
them are in `docs\DECISIONS_PENDING.md` and `docs\PASS2_STAGE_E_PLAN.md` §15.

- **Who and from what.** Any authenticated user asks on the Binder screen's **Spine papers**
  card; the Spine is never written to. Generation needs an open binder linked to a **locked**
  Spine version the Spine can serve. Every refusal says why, by name: not open, not linked, no
  Spine configured, the version unlocked or unreadable, no area map for the template, an area
  without heads, or a map the Spine's tree refuses.
- **Lead schedules**, one per mapped area D–T, reference `<area>-L`, title "Lead schedule:
  <area name>". The paper carries, exactly as the Spine served them, the area's financial
  statement lines with current and prior figures, every ledger row under the area's heads with
  its unadjusted, reclassification, correction, adjusted and prior figures, the Spine's own
  per-head totals, the heads with no ledger entry, and the adjustments with a line under the
  area's heads. The same tables are rendered as markdown in `result`. The Binder adds nothing
  up, rounds nothing and nets nothing; where the Spine served no ledger or no figure the paper
  says so in those words ("no figure served") and never writes a zero or "nil" it was not
  given. `objective` and `procedure` arrive empty, or with the template's approved wording, and
  stay a person's to write, as does `conclusion`; `title`, `section`, `sa_refs`,
  `population_sample` and `result` are locked. One FS-line reference is written per
  presentation line of the area, so the Cross-reference map draws the paper as the line's lead
  schedule. The paper's `population_sample` is a sentence the Binder writes, not a Spine
  figure: the version's label, id and hash and counts of the rows served (ledger rows, heads
  with no ledger entry, financial statement lines, adjustments); for the chain, counts of
  adjustments by status and of uncorrected items. It is locked with the Spine's fields.
- **The adjustment chain**, one per binder, `W-ADJ` in section W Completion: every adjustment
  of the version in every status (proposed, accepted, refused) with its lines, the working
  papers the adjustments name, and the uncorrected schedule as the Spine served it, rendered
  without interpretation. A working-paper reference that **exactly** equals a paper reference
  of the binder becomes a cross-reference from `W-ADJ` to that paper; a name that matches no
  paper is listed on the paper as information, never guessed, never a blocker.
- **Area map.** Which Schedule III heads each area covers is the firm's to say, in the
  template's `areas` block (`docs\TEMPLATE_AUTHORING.md`). Ids are head ids only, spelled as
  the Spine's `GET /api/tree` serves them; a listed head covers itself and every descendant,
  found **only** by following the tree's `parent` field, never by the shape of an id. The
  loader checks syntax; against the tree, every id must exist, no two areas may cover the same
  head after expansion, and mappable heads in no area are reported. **Every shipped template
  carries an empty map**: no lead schedule can be generated for a shipped template until the
  firm enters one, and the card, the status endpoint and the template check say so by name.
  The adjustment chain needs no map.
- **References the Binder writes** are created by `oak_spine`; the person who asked is the
  provenance row's `received_by`. That marker is how a Binder-written reference is told apart
  from one a person typed.
- **Freshness.** A Spine paper records the version id and hash it was built from. The status,
  the paper and the generated panel report `current` when the binder's link and the Spine's
  current answer still match, `stale` when the binder was re-linked to another version (or the
  hash moved, which a locked version never does), and `not_checked` with the reason when the
  Spine cannot answer. Reading a Spine paper (`GET /api/papers/{id}` or `…/generation`)
  costs one Spine read of the linked version to fill `generated.freshness`; a hand-made
  paper or another module's costs none. A stale paper is **information, never a blocker**: it is listed in the
  assembly status's not-checked list as "Spine paper <ref>: … (information; regenerate while the
  binder is open)" and assembly proceeds under the specification's four blockers, unchanged.
- **Regeneration**, on an open binder only (`POST /api/papers/{id}/regenerate`): the Spine's
  fields are rewritten from the linked version, the paper returns to draft, a new provenance
  row is appended with the new run id, and the person's objective, procedure and conclusion and
  every earlier version are kept. Only a reference the Binder reliably owns (created by
  `oak_spine` and pointing at a target an earlier Spine block of the paper named) is removed
  when the new version no longer serves its target; every other reference is kept, and a kept
  one whose target is gone is listed for a person's review. What was added, removed, kept and
  left for review is recorded in the provenance row's `inputs.regeneration` and returned. A
  repeat on an unchanged version is refused as one paper per run. After assembly the link is
  frozen and a locked version cannot change, so regeneration is not offered; the Pass 1
  amendment path still applies to the paper's unlocked fields and attachments.
- **One paper per run.** The run id is binder id, version id, Spine hash and area (or
  `adjustments`): unique per binder, so several binders may share a version; unchanged while
  the Spine is unchanged, so a duplicate request names the existing paper.
- **Screens.** The Binder screen's Spine papers card lists each mapped area and the chain with
  state badges and generate buttons, the linked version, the reasons generation is not possible,
  map problems and unassigned heads; the generated panel on the paper shows the version, the
  shape of what was served, a freshness banner and, while the binder is open, Regenerate with
  the reference changes.
- **Limitations, not invented.** Shipped area maps are empty; area names D–T are placeholders;
  no required lead schedule per area is added to any template; the wording slots for
  objective and procedure are empty; no SA references are seeded. Nothing here needs a database
  change. Tests: `tests\test_area_map.py`, `tests\test_spine_tree.py`, `tests\test_spine_block.py`,
  `tests\test_templates_areas.py`, `tests\test_api_spine_papers.py`,
  `tests\test_api_adjustment_chain.py`, `tests\test_api_spine_regeneration.py`,
  `frontend\tests\SpinePapersCard.test.tsx`, `frontend\tests\GeneratedPanelSpine.test.tsx`.

### Cross-references

Spec §3B, §3E, §4 `xref · from_wp · to_wp | to_fs_line | to_vault_doc · direction`. A
reference is written on one paper and names exactly one target: another paper of the same
binder, a financial-statement line (free text until the Spine exists), or a document attached
in this binder, by its store id. `direction` says which way it reads: `to`, this paper refers
to the target; `from`, the target refers to this paper. The Working paper screen shows the
paper's references in and out: paper targets are clickable in both directions, a document
target links to the attachment it is filed as, and the paper carrying that document sees the
reference coming in. References
are added and removed while the binder is open and are frozen with the file at assembly.
**A broken reference blocks assembly, named per paper** (spec §3E, §3F, §8.3): a document
target that no paper of the binder carries any more is broken; a paper target is checked to
be a paper of the same binder; an FS-line target cannot be checked and is listed as *not
checked*. References are not part of the manifest hash, so an already-assembled file still
matches its recorded manifest after migration 0005. **FS-line targets** (Stage C, D30): once
the binder is linked to a Spine version whose statements can be read, a reference must name
one of its presentation lines by the Spine's stable `head_id` (the screen offers a picker and
shows the label); a line the version does not have, including free text written before the
binder was linked, is a named `broken_reference` blocker, and the Assembly screen's not-checked
list is empty. Unlinked binders keep free-text lines as *not checked*. The **Cross-reference
map** (screen 4, `#/binders/{id}/xref-map`) shows FS line → lead schedule → working paper →
source document, every node clickable, with broken and amended links flagged, papers deeper
than the three drawn levels listed as *further down a chain*, and papers tied to no line
listed apart from those. Assembly records the lines it verified against with the assembled
event, and the produced archive's cross-reference records are built from that record, so the
file is the same whether or not the Spine answers at production. A paper target whose content changed
since the reference was made is flagged on the reference as information (spec §3E
"superseded", reading pending with the senior), never as a blocker. Decision D26; tests in
`tests\test_api_xrefs.py` and `tests\test_db_rules_xref.py`.

### Access log

Spec §3H, §4 `access_log · binder · user · action · at`, post-assembly only, append-only
(migration 0004, D25). Every read of an assembled or purged binder is recorded: the binder,
a paper, its versions, its review notes, its cross-references, an attachment's details or
bytes, the binder's review notes, the assembly status, a verification, a production. Reads of
an open binder are not logged. Because the log must say who, a read of an assembled file
requires an identity and is refused without one. The Assembly screen lists the log; the
produced archive carries it as `access_log.json` and in the audit trail. Tests in
`tests\test_api_access_log.py` and `tests\test_db_rules_access_log.py`.

### Identity

`OAK_AUTH=dev` (default outside production) takes the identity from `OAK_DEV_USER`.
`OAK_AUTH=header` takes it from the header an authenticating reverse proxy sets after signing
the user in (`OAK_AUTH_HEADER`, default `X-Authenticated-User`). The header is believed only
when the request's peer address is in `OAK_TRUSTED_PROXIES` (a comma-separated list of IPs or
networks; required in production, so a client that reaches the API directly cannot name
itself), when it appears exactly once (a proxy that appends rather than replaces would leave
a client's copy in front), and when its value is a plausible name (at most 254 printable
characters). Otherwise a request that needs an identity is refused with 401. The peer address
is the socket peer, so run uvicorn without `--proxy-headers`: the proxy must be the peer.
The Binder verifies nothing about the person itself; which proxy or identity provider the
firm uses is its decision (D24). Every response carries `Cache-Control: no-store`,
`X-Content-Type-Options: nosniff` and `Referrer-Policy: no-referrer`. Production refuses
`OAK_AUTH=dev`. Tests in `tests\test_identity.py`, `tests\test_security_headers.py` and
`tests\test_config.py`.

### Demonstration

`docs/DEMONSTRATION_AND_STATUS.md` holds the demonstration sequence, the status report for the
senior, the list of features implemented and the limitations to disclose; `docs/ACCEPTANCE_MATRIX.md`
is the clause-by-clause acceptance against the specification.

### Browser checks with the local doubles

The Spine and WorkMind do not run here. For a browser walk-through, serve the test doubles over
HTTP and point a development backend at them; the backend then uses `oak_binder_test` and the
local attachment store, never the Drive vault (D40):

```powershell
backend\.venv\Scripts\python.exe -m tests.local_stubs --spine-port 8010 --workmind-port 8012
powershell -NoProfile -File scripts\dev_backend_with_doubles.ps1
```

`.claude/launch.json` carries the same three servers (doubles, backend, frontend) for the
desktop app's preview. The locked Spine version is `aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa` of
engagement `11111111-1111-4111-8111-111111111111`; the accepted WorkMind run is
`wm-run-example-7f3a`. Nothing served by the doubles is live data.

### Test database and browser-demo data

The test suite shares `oak_binder_test` with browser demos and preserves what it finds:
it only ever upgrades the schema, runs every test in a rolled-back transaction, and gives
every engagement it creates a random suffix. Destroying and rebuilding the test database
requires `OAK_TEST_REBUILD=yes`. Before a schema upgrade, a backup is still wise:

```powershell
& "C:\Program Files\PostgreSQL\16\bin\pg_dump.exe" -h localhost -p 5432 -U oak_binder_owner -d oak_binder_test -F c -f "D:\oak_binder_test_backup.dump"
```

### Deferred at the close of Stages 4 and 5

Recorded in full as decision D16 in [docs/architecture.md](docs/architecture.md).

- **Review notes** are now built (migration 0003, D21); the earlier stub is gone.
- **Configurable review levels** beyond preparer and reviewer (spec §3D) are built
  (Pass 2 Stage F, migration 0009, D33); see "Review levels" above.
- **Template content** is placeholder-level pending chartered accountant review; the
  authoring guide is `docs/TEMPLATE_AUTHORING.md`, the previously seeded SA references are
  held for review in `docs/SA_REFERENCES_FOR_CA_REVIEW.md`, and every open decision is on
  one page in `docs/DECISIONS_PENDING.md`. Section
  names and the six required papers come from the specification's own words; areas D to T
  are unnamed and all four templates are nearly identical.
- **One development identity** in `dev` mode (D8). Preparer, reviewer and signer are whatever
  `OAK_DEV_USER` says, so a browser walk-through shows one person in every role. `header`
  mode (D24) gives each request the identity the proxy presents.
- **Access log** (spec §3H, §4): built in Stage 8 (D25).

### Markdown in working papers

The five long fields (objective, procedure performed, population and sample, result,
conclusion) accept markdown (spec §7): paragraphs, lists, emphasis, links and tables. The
Working paper screen has a Read view that renders them and an Edit view with plain
textareas; a paper opens in Read once it has left draft. Rendering uses `marked`, and every
rendered fragment passes through `DOMPurify` before it reaches the page, so script tags,
event handlers, `javascript:` links, frames, forms and inline styles in a field are removed.
`frontend\tests\markdown.test.tsx` checks both the rendering and the neutralising.

### Configuration guards

Two rules are enforced by the settings module and covered by `backend\tests\test_config.py`:

- A database URL is accepted only if it names `oak_binder` or `oak_binder_test`. A URL
  pointing at any other database, including the Financial Spine's, is refused before any
  connection is attempted.
- With `OAK_ENV=production`, `OAK_AUTH` must be `header`, `OAK_TRUSTED_PROXIES` must name the
  proxy, `OAK_DEV_USER` must be unset and the database must be `oak_binder`. The application
  refuses to start otherwise.
- `OAK_AUTH=header` needs a non-blank `OAK_AUTH_HEADER`; `OAK_STORE=vault` needs the three
  `OAK_VAULT_*` values and, until an adapter exists, refuses to start.
