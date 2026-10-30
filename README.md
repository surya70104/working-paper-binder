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
| `backend/src/oak_binder/models/` | Database tables: binder, wp, wp_version, wp_attachment |
| `backend/src/oak_binder/schemas/` | Request and response shapes |
| `backend/src/oak_binder/api/` | Routers: binders, working papers, attachments, assembly, export |
| `backend/src/oak_binder/services/` | Templates, completeness, sign-off, assembly, retention, produce file |
| `backend/src/oak_binder/templates/` | Index templates per engagement type, as data |
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
| `POST /api/binders/{id}/papers` | Create a working paper; the reference is unique and immutable |
| `GET /api/papers/{id}`, `PATCH /api/papers/{id}` | Read a paper with its versions; edit its content (returns it to draft) |
| `GET /api/papers/{id}/versions` | The immutable version history |
| `POST /api/papers/{id}/prepare`, `/submit`, `/review`, `/sign-off` | The workflow: draft → prepared → in review → reviewed → signed off |
| `POST /api/papers/{id}/attachments` (multipart) | Attach a native-format file with its identifying characteristics; after assembly, with an amendment reason |
| `GET /api/attachments/{id}`, `GET …/content`, `DELETE /api/attachments/{id}` | Read, download (hash re-checked), remove before assembly |
| `GET /api/binders/{id}/assembly` | State, named blockers, what is not checked (Pass 2), manifest, retention, events |
| `POST /api/binders/{id}/assemble` | Freeze the file: manifest and SHA-256 file hash; re-assemble after amendments |
| `GET /api/binders/{id}/verify` | Recompute every hash and compare with what was recorded |
| `GET /api/binders/{id}/produce` | One zip: manifest, binder, audit trail, every paper, version and attachment, checksums |
| `POST /api/binders/{id}/purge` | After retention: destroy attachment content, record the purge |
| `POST /api/papers/{id}/review-notes`, `GET …/review-notes` | Raise a review note on a paper; list its notes |
| `POST /api/review-notes/{id}/assign`, `/respond`, `/clear` | The chain raised → assigned → responded → cleared, in order only |
| `GET /api/binders/{id}/review-notes` | Screen 3: what is open, raised by whom, assigned to whom, blocking what |

Rules enforced in the workflow: a sign-off needs a conclusion; an open review note blocks
sign-off (real notes, migration 0003; see "Review notes" below); steps run only in order;
every step writes an immutable version naming its actor and time; an assembled binder
refuses edits without an amendment reason. The screens at <http://127.0.0.1:3001> cover
binders, one binder, one working paper, the binder's review notes, and assembly and
retention.

### Attachments, assembly, retention and production (Stage 6)

- **Attachments** are kept in a local write-once store under `var\attachments`
  (`OAK_ATTACHMENTS_DIR`), outside anything a web server serves, named by SHA-256. **Vault
  integration has not been done, because no vault exists**: a search of this project, the
  Financial Spine (`D:\CAF`), the OAK notes and every project document on 29 October 2026
  found no vault module, API or credentials (D16). The store sits behind one interface so a
  vault can replace it without a schema change (D17). Files are served by id, re-hashed on
  every read, and a mismatch is refused. An attachment
  belongs to the paper and joins the signed record at the next prepare; each version body
  lists the paper's attachments by hash.
- **Assembly** is blocked by named items: each missing required paper, each paper not signed
  off, each paper with open review notes, an undated report. Broken cross-references are
  Pass 2 and are shown as *not checked*: cross-reference data (spec §3E, §4 `xref`) does
  not exist yet, so nothing can be detected (D21). Assemble records a manifest and a
  SHA-256 file hash that anyone can recompute from the manifest. After assembly a change needs an amendment reason and
  writes a new version plus an event; nothing is deleted; re-assembly records the new hash
  with the previous one.
- **Retention**: purge is refused before the retention date. After it, purge destroys the
  attachment content and records the purge; paper and version rows stay with their hashes
  (D18). **The content is purged; the metadata remains.**
- **Produce file**: one zip with the manifest, the binder, the audit trail (binder events
  and every review-note step), every paper with its versions, review notes and attachments
  in native format, and a checksum list (D19, D22). Paper folders are made unique even when
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

Still outside Pass 1: the broken-reference blocker (Pass 2, shown as *not checked*; D21
explains why it cannot detect anything until the Spine and a document store exist), and the
post-assembly access log of spec §3H, which §6 assigns to neither pass and which is not
built. The `produced` event records every export.

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
- **Configurable review levels** beyond preparer and reviewer (spec §3D) are Pass 2.
- **Template content** is placeholder-level pending chartered accountant review. Section
  names and the six required papers come from the specification's own words; areas D to T
  are unnamed and all four templates are nearly identical.
- **One development identity** (D8). Preparer, reviewer and signer are whatever
  `OAK_DEV_USER` says, so a browser walk-through shows one person in every role.
- **Access log of who opened the file after assembly** (spec §3H, §4): listed in neither pass
  by spec §6, not built. Needs a decision before it is scheduled.

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
- With `OAK_ENV=production`, `OAK_DEV_USER` must be unset and the database must be
  `oak_binder`. The application refuses to start otherwise.
