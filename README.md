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
| `POST /api/binders/{id}/papers` | Create a working paper; the reference is unique and immutable |
| `GET /api/papers/{id}`, `PATCH /api/papers/{id}` | Read a paper with its versions, attachments and cross-references; edit its content (returns it to draft) |
| `GET /api/papers/{id}/versions` | The immutable version history |
| `POST /api/papers/{id}/prepare`, `/submit`, `/review`, `/sign-off` | The workflow: draft → prepared → in review → reviewed → signed off |
| `POST /api/papers/{id}/attachments` (multipart) | Attach a native-format file with its identifying characteristics; after assembly, with an amendment reason |
| `GET /api/attachments/{id}`, `GET …/content`, `DELETE /api/attachments/{id}` | Read, download (hash re-checked), remove before assembly |
| `GET /api/binders/{id}/assembly` | State, named blockers, what is not checked, manifest, retention, events, the access log |
| `POST /api/binders/{id}/assemble` | Freeze the file: manifest and SHA-256 file hash; re-assemble after amendments |
| `GET /api/binders/{id}/verify` | Recompute every hash and compare with what was recorded |
| `GET /api/binders/{id}/produce` | One zip: manifest, binder, audit trail, every paper, version and attachment, checksums |
| `POST /api/binders/{id}/purge` | After retention: destroy attachment content, record the purge |
| `POST /api/papers/{id}/review-notes`, `GET …/review-notes` | Raise a review note on a paper; list its notes |
| `POST /api/review-notes/{id}/assign`, `/respond`, `/clear` | The chain raised → assigned → responded → cleared, in order only |
| `GET /api/binders/{id}/review-notes` | Screen 3: what is open, raised by whom, assigned to whom, blocking what |
| `POST /api/papers/{id}/xrefs`, `GET …/xrefs`, `DELETE /api/xrefs/{id}` | Cross-references (spec §3E): add one with exactly one target, list in and out with the check result, remove before assembly |

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
matches its recorded manifest after migration 0005. A paper target whose content changed
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
