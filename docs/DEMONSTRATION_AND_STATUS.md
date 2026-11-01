# Working Paper Binder — demonstration sequence and status for the senior

**1 November 2026.** Everything below refers to the module as specified in
`WORKING_PAPER_BINDER.md` (Pass 1 and Pass 2, §6). Evidence: `docs/ACCEPTANCE_MATRIX.md` and
`docs/PASS2_COMPLETION_REPORT.md`.

## 1. Demonstration sequence (about twenty minutes)

Set-up, once, in three terminals from `D:\WORKING PAPER BINDER` (the Spine and WorkMind do not
exist yet, so their test doubles are served locally; the backend uses `oak_binder_test` and the
local attachment store, never the Drive vault or the live database):

```powershell
backend\.venv\Scripts\python.exe -m tests.local_stubs --spine-port 8010 --workmind-port 8012
powershell -NoProfile -File scripts\dev_backend_with_doubles.ps1
cd frontend; fnm exec --using=22 -- npm run dev
```

Open <http://127.0.0.1:3001>. A fully worked binder, `ACCEPT-2026-11-01`, is already in the
test database for the read-only parts; the sequence creates a fresh one for the live parts.

| # | Step | What to point out (spec) |
|---|---|---|
| 1 | Binders screen: choose "Statutory audit", enter an engagement name and the report date, Create | the four index templates (§3A); the template is marked draft with its placeholders listed; the 60-day and 7-year clocks start from the report date (§2, §3F, §3G) |
| 2 | Binder screen: the index shows six required papers missing, "blocks assembly" | completeness view as a blocking count (§3A) |
| 3 | Review levels card: enter `senior, partner`, Save | levels configurable per engagement (§3D) |
| 4 | Financial Spine card: engagement `11111111-1111-4111-8111-111111111111`, Load versions, choose "1 · Final · locked", Save link | the binder ties to a locked Spine version; an unlocked one would block assembly (§3A, §3F) |
| 5 | Spine papers card: "Generate lead schedules (4)", then "Generate adjustment chain" | lead schedule per area and the adjustment chain, figures as the Spine served them; the areas come from the Spine's tree because the template has no map yet (§3C) |
| 6 | Open D-L: the generated panel (version, hash, what was served, freshness "current"); locked fields; write objective, procedure and conclusion; Save | papers that generate themselves; nobody retypes; the conclusion is a person's (§3C, §7) |
| 7 | Index: Create beside A-1, Create paper; fill objective, procedure, result, conclusion; Save | the working paper's fields; SA references prefilled from the index (§3B) |
| 8 | Prepare, Submit for review, Review as senior, Review as partner | the status chain; each step records who, when and which version (§3B, §3D, §8.9) |
| 9 | Before signing off: raise a review note, Assign, Respond; try Sign off | an open note blocks sign-off (§3D, §8.2); then Clear and Sign off |
| 10 | Cross-references: add "this paper refers to D-L" | references in and out, on both papers (§3B, §3E) |
| 11 | Attach a file (from the file picker) with identifying characteristics | native format, SHA-256, identifying characteristics of items tested (§2, §3G) |
| 12 | Binder screen: record a discussion with a TCWG participant and a departure | the records that are easy to forget (§3H) |
| 13 | Assembly & retention: blockers are named (the remaining unsigned papers); complete them through the API or the screen; Assemble | the four named blockers; Assemble freezes, hashes, writes the manifest (§3F, §8.3, §8.5) |
| 14 | Verify hashes; Produce file (zip); open the archive | one-action production in native format with manifest and audit trail (§3G, §8.6) |
| 15 | Open a signed-off paper, edit with an amendment reason, Save as amendment | after assembly nothing is deleted; a change is a new version with its reason (§3F, §8.4) |
| 16 | The referencing paper shows "superseded", Confirm; Assembly: Re-assemble | a superseded target blocks until confirmed (§3E); re-assembly records a new hash |
| 17 | Cross-reference map screen | FS line → lead schedule → working paper → source document, clickable (§3E, screen 4) |
| 18 | Review notes screen; Assembly screen's access log; Purge withheld until retention | screens 3 and 5; who opened the file after assembly; purge only after seven years (§3G, §3H, §8.7) |

Optional, through the API (`/docs`): deliver `backend/tests/fixtures/generated/sampling.json`
to `POST /api/binders/{id}/generated-papers` and open the paper: formula and seed printed on it
(§8.8); deliver `workmind.json`: filed only because the WorkMind double reports the run accepted.

## 2. Status report for the senior

The Working Paper Binder specified in `WORKING_PAPER_BINDER.md` is built, tested and verified
against every clause of the specification's sections 2 to 8. Pass 1 (the SA 230 file) and
Pass 2 (review notes, cross-reference map, generated papers, the logs, WorkMind) are complete;
the acceptance matrix marks every requirement PASS on the current build, and every user
workflow has been walked in the browser as well as proven by tests.

- 404 backend tests and 88 frontend tests pass; lint, strict type checks and the production
  build are clean; migrations 0001–0010 are applied to the test database only, and the live
  database has never been touched.
- Four source modules named by the specification (Financial Spine, Materiality, Sampling,
  Analytical Review) and WorkMind do not exist as running systems. Their contracts are defined,
  the integrations are built and tested against local doubles, and the screens show them
  working; none is a live connection yet.
- The index templates carry exactly what the specification names. Area names, required papers
  per area, SA references and a firm map of Schedule III heads are the firm's to supply; forms
  for them are ready (`docs/TEMPLATE_CONTENT_REQUEST.md`), and the module works without them
  through a default map derived from the Spine's own tree.
- Decisions the specification left open were taken conservatively and are recorded, each
  reversible, in `docs/architecture.md` (D1–D41) and `docs/DECISIONS_PENDING.md`.

Nothing outside the specification was added. The remaining work is the firm's content and the
go-live settings, not development.

## 3. Features implemented

- Index templates for the four engagement types; standard sections A–T, W, X, Z; completeness as a blocking count.
- The working paper with every specified field, a stable reference, the five-status chain, immutable versions recording preparer, reviewer and signer with times; markdown fields; SA references prefilled from the index.
- Review notes raised → assigned → responded → cleared; an open note blocks sign-off and assembly.
- Review levels configurable per engagement (preparer first, then the binder's levels, then sign-off), frozen once a level review exists.
- Attachments in native format with SHA-256 and identifying characteristics, stored locally or in the firm's Google Drive folder; downloads verified against the hash; removal only before assembly.
- Cross-references to papers, financial-statement lines and documents, in and out; broken targets block assembly; a superseded (amended) target blocks until confirmed; the cross-reference map screen and its archive member.
- Financial Spine link to a locked version; lead schedule per area (template map or derived default) and the adjustment chain, with figures as served, freshness and regeneration.
- Generated-paper intake for Materiality, Sampling and Analytical Review (formula and seed printed, Spine figures checked); WorkMind papers filed after the run is read back as accepted; module fields locked, conclusions always a person's.
- Discussions log (including TCWG), departures log, post-assembly access log, all append-only.
- Assembly with the 60-day countdown, named blockers, manifest and file hash, amendments with reason, re-assembly; verification; one-action production of the complete archive; seven-year retention and recorded purge.
- Identity from a development setting or an authenticating proxy; append-only enforcement at the database; test doubles and local stub servers for the systems that do not exist.

## 4. Limitations to disclose

1. **No live module.** Spine, WorkMind, Materiality, Sampling and Analytical Review are integrated against contracts and local doubles; none is connected to a running system.
2. **Template content** is the specification's words only: generic area names in the index, six required papers, no SA references, identical templates per engagement type. Generated lead schedules carry the Spine's own head labels.
3. **Reviewer identity is recorded, not enforced**; the specification states no rule about who may review at which level.
4. **One development identity** (`OAK_AUTH=dev`): every role shows the same user until the firm's proxy identity is configured (`OAK_AUTH=header`).
5. **Go-live items** are the firm's: applying the migrations to the live database, the OAuth consent screen status and custody of the secrets folder, the proxy and TLS.
6. **The demonstration data** lives in `oak_binder_test`, shared with the test suite and preserved by it.
