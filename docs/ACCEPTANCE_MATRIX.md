# Acceptance matrix — Working Paper Binder against `WORKING_PAPER_BINDER.md`

**1 November 2026 (D40).** Every requirement of sections 2–8 of the specification, with the
implementation that meets it, the API, screen and database model involved, the test that proves
it, and what was exercised in the browser. "PASS" is given only where the behaviour is
implemented and verified on this build. Evidence: `backend/tests/test_acceptance_spec.py`
(eighteen clause tests and one end-to-end workflow test, all against `oak_binder_test` with the
Spine and WorkMind doubles), the feature test modules named per row, the frontend component
tests, and a browser walk-through of binder `ACCEPT-2026-11-01` on the development servers with
the doubles served over HTTP (`tests/local_stubs.py`).

Abbreviations: API paths are under `/api`; screens are 1 Binder, 2 Working paper, 3 Review
notes, 4 Cross-reference map, 5 Assembly & retention; models are the tables of spec §4.

## Section 2 — what SA 230 requires

| Requirement | Implementation | API · screen · model | Proof | Browser | Status |
|---|---|---|---|---|---|
| Record an experienced auditor can follow: objective → procedure → result → conclusion; no sign-off without a conclusion | `services/papers.py` fields and `sign_off` rule | `PATCH /papers/{id}`, `POST …/sign-off` · screen 2 · `wp`, `wp_version` | `test_spec_2_record_forces_…`; `test_api_papers::sign_off_requires_a_conclusion` | A-1 fields entered and saved; sign-off hint shown while blocked | PASS |
| Who performed and reviewed, and when, captured at sign-off, not typed | identities from `identity.py`, written by `prepare`/`review`/`sign_off` | `POST …/prepare`, `/submit`, `/review`, `/sign-off` · screen 2 · `wp_version` (`prepared_by/at`, `reviewed_by/at`, `signed_off_by/at`) | `test_spec_2_who_performed_…`; `test_api_papers::full_sign_off_records_who_when_and_which_version`; `test_identity.py` | A-1 and D-L chains show preparer, senior, partner, sign-off with times and versions | PASS |
| Identifying characteristics of items tested | `population_sample` field; `identifying_chars` on attachments | `POST /papers/{id}/attachments` · screen 2 · `wp`, `wp_attachment` | `test_spec_2_identifying_characteristics_…`; `test_api_attachments.py` | attachment listed with "FY26 sales register rows 1-2" and hash | PASS |
| Discussions log incl. TCWG; departures log | `services/records.py` (D28) | `GET/POST /binders/{id}/discussions`, `…/departures` · screen 1 · `discussion`, `departure` | `test_spec_3h_…`; `test_api_records.py`; `test_db_rules_records.py` | both recorded from the Binder screen, shown with recorder and time | PASS |
| Assembly within 60 days: countdown, Assemble, hard lock | `services/binders.py` clocks, `services/assembly.py` | `PATCH /binders/{id}` (report date), `POST …/assemble` · screens 1, 5 · `binder` | `test_spec_2_sixty_day_…`; `test_clocks.py`; `test_api_assembly.py` | "Assembly due 2026-11-29: 28 days left"; Assemble locked the file | PASS |
| Retention ≥ 7 years, native format, purge only after | `services/retention.py`, `services/produce.py`, stores | `GET …/produce`, `POST …/purge` · screen 5 · `binder.retention_until`, `wp_attachment` | `test_spec_3g_…`; `test_api_assembly::purge_is_refused_before_retention_and_recorded_after` | "Retain until 2033-09-30"; purge offered only after retention | PASS |
| No deletion before retention; post-assembly changes versioned with reason, author, date | `assembly.amend`, DB triggers, delete refusals | `PATCH /papers/{id}` with `amendment_reason`, `DELETE /attachments/{id}` 409 · screen 2 · `wp_version.amendment_reason`, `binder_event` | `test_spec_2_nothing_is_deleted_…`; `test_api_assembly::after_assembly_edits_need_a_reason_and_deletes_fail` | D-L amended with a reason from the screen (version 4), event "amended" on the trail | PASS |
| NFRA: one-action production of the complete file | `services/produce.py` | `GET /binders/{id}/produce` · screen 5 | `test_spec_3g_…`; `test_api_close_out.py` | "Produce file (zip)" link; archive fetched and inspected: 8 top-level members, 13 paper folders, native CSV byte-identical | PASS |

## Section 3A — file structure

| Requirement | Implementation | API · screen · model | Proof | Browser | Status |
|---|---|---|---|---|---|
| Index template per engagement type (statutory, tax audit, bank branch, internal) | `templates/*.json`, `services/templates.py` | `GET /templates`, `GET /templates/{name}` · screen 1 (creation form) · `binder.template` | `test_spec_3a_…`; `test_templates.py` | four types offered on the Binders screen | PASS (content beyond the spec's words is placeholder; see Gaps) |
| Standard sections A, B, C, D–T, W, X, Z | `models.SECTIONS`, loader | — · screens 1, 2 · `wp.section` check | `test_models::sections_are_a_to_t_w_x_z` | section list in every form | PASS |
| Lead schedule per area, tying to the Spine, with the WPs beneath it | `services/spine_papers.py`, `services/area_map.py` (D32, D38) | `GET /binders/{id}/spine-papers`, `POST …/lead-schedules` · screens 1, 4 · `wp`, `wp_generation`, `xref` | `test_spec_3a_…`; `test_api_spine_papers.py`; `test_area_map.py` | four lead schedules generated from the Spine-papers card (derived map); map screen shows line → D-L → A-1 | PASS |
| Completeness view: missing required papers per section as a blocking count | `services/binders.build_index` | `GET /binders/{id}` · screen 1 · `binder`, template | `test_api_binders::completeness_counts_…`; `test_spec_3f_…` (`missing_required_paper` blocker) | "Missing required papers: 6 (blocks assembly)" then 0 | PASS |

## Section 3B — the working paper

| Requirement | Implementation | API · screen · model | Proof | Browser | Status |
|---|---|---|---|---|---|
| Every field: reference, title, section, SA refs, objective, procedure, population and sample, result, conclusion, prepared by/date, reviewed by/date, status, attachments, cross-references in and out | `models/wp.py`, `schemas/papers.py` | `POST /binders/{id}/papers`, `GET /papers/{id}` · screen 2 · `wp`, `wp_version`, `wp_attachment`, `xref` | `test_spec_3b_…`; `test_api_papers::create_paper_with_every_spec_field` | every field on the paper screen | PASS |
| Reference stable, never reused | unique constraint, immutable on edit | 409 on reuse, 422 on change · screen 2 · `uq_wp_binder_ref` | `test_spec_3b_…`; `test_api_papers::reference_is_unique_and_immutable` | — | PASS |
| Status chain draft → prepared → in review → reviewed → signed off | `WpStatus`, `services/papers.py` | the four actions · screen 2 · `wp.status` | `test_spec_3b_…`; `test_api_papers::steps_only_run_in_order` | chain walked on A-1 and D-L | PASS |
| SA references from the index | prefill on Create (D35) | `POST /binders/{id}/papers` with `sa_refs` · screen 1 | `test_api_binders::the_index_carries_the_template_sa_refs_…`; `BinderPage.test.tsx` | A-1 created from the prefilled form | PASS |

## Section 3C — papers that generate themselves

| Requirement | Implementation | API · screen · model | Proof | Browser | Status |
|---|---|---|---|---|---|
| A module's paper arrives complete with inputs and citations; nobody retypes | intake contract, locked fields (D31) | `POST /binders/{id}/generated-papers`, `GET /papers/{id}/generation` · screen 2 (generated panel) · `wp_generation` | `test_spec_3c_…`; `test_api_generated.py` | sampling and WorkMind papers delivered to the running backend; generated panel shows provenance; locked fields disabled | PASS (local: fixtures and doubles; no live module) |
| Materiality: benchmark, band, figures from the Spine | per-source rule; figures checked against the linked version | same · `wp_generation.spine_figures` | `test_spec_3c_…` (verified); `test_api_generated::materiality_figures_are_checked_…` | — | PASS (local) |
| Sampling: formula and seed printed on it | per-source rule | same | `test_spec_8_…` (8.8); `test_api_generated::a_sampling_paper_carries_its_formula_and_seed_printed_on_it` | D-3 shown with seed in the population field | PASS (local) |
| Analytical Review: current vs prior with thresholds | per-source rule | same | `test_spec_3c_…`; `test_api_generated::analytical_review_needs_both_periods_and_thresholds` | — | PASS (local) |
| Financial Spine: every lead schedule and the adjustment chain | `services/spine_papers.py` (D32) | `POST …/spine-papers/lead-schedules`, `…/adjustment-chain`, `POST /papers/{id}/regenerate` · screens 1, 2 · `wp_generation`, `xref` | `test_spec_3c_…`; `test_api_spine_papers.py`, `test_api_adjustment_chain.py`, `test_api_spine_regeneration.py` | D-L … G-L and W-ADJ generated from the card; D-L panel shows Spine version, counts, freshness "current" | PASS (local Spine double; no live Spine configured) |
| WorkMind: one paper per accepted run with run id, inputs, source-row citations | run read-back (D37) | same intake · `wp_generation.run_verification` | `test_spec_3c_…`; `test_api_generated::a_workmind_paper_is_filed_only_for_a_run_workmind_reports_as_accepted` | D-5 delivered against the WorkMind double; panel shows "Run verified: accepted by manager@firm" | PASS (local double; no live WorkMind) |

## Section 3D — review

| Requirement | Implementation | API · screen · model | Proof | Browser | Status |
|---|---|---|---|---|---|
| Review notes raised → assigned → responded → cleared | `services/review_notes.py` | `POST /papers/{id}/review-notes`, `POST /review-notes/{id}/assign|respond|clear`, `GET /binders/{id}/review-notes` · screens 2, 3 · `review_note` | `test_spec_3d_…`; `test_api_review_notes.py`; `test_db_rules_review_notes.py` | all four steps taken on A-1 from the paper screen; screen 3 lists state | PASS |
| An open note blocks sign-off (hard rule) | `sign_off` check | 409 · screen 2 | `test_spec_3d_…`, `test_spec_8_…` (8.2) | "1 open review note: … cannot be signed off (SA 230)" shown; sign-off succeeded after clearing | PASS |
| Levels preparer → senior → manager → partner → EQR, configurable per engagement | `services/review_levels.py` (D33) | `PATCH /binders/{id}` `review_levels`, `POST /papers/{id}/review` · screens 1, 2 · `binder.review_levels`, `wp_review` | `test_spec_3d_…`; `test_api_review_levels.py`; `test_db_rules_review_levels.py` | levels set to senior, partner on the Binder screen; "Review as senior", "Review as partner" on the paper | PASS |
| Every sign-off records who, when, which version | immutable version rows, `wp_review` rows | screen 2 version table · `wp_version`, `wp_review` | `test_spec_3d_…`; `test_spec_8_…` (8.9) | version table and chain on A-1 | PASS |

## Section 3E — cross-referencing

| Requirement | Implementation | API · screen · model | Proof | Browser | Status |
|---|---|---|---|---|---|
| FS line → lead schedule → working paper → source document, clickable both ways | `services/xref_map.py` (D30) | `GET /binders/{id}/xref-map`, `GET …/fs-lines` · screen 4 (links to papers and documents), screen 2 (in and out) · `xref` | `test_spec_3e_…`; `test_api_xref_map.py`; `XrefMapPage.test.tsx` | map screen: BS.A.1 → D-L → A-1; paper screens show out/in | PASS |
| Broken-reference detection: deleted or superseded target surfaced and blocks assembly | `services/xrefs.py` broken + superseded (D26, D36) | blockers on `GET …/assembly`; `POST /xrefs/{id}/confirm` · screens 2, 5 · `xref.confirmed_*` | `test_spec_3e_…`; `test_api_xrefs.py` | after D-L's amendment A-1 showed "superseded …" and "1 broken — blocks assembly"; Confirm cleared it | PASS |

## Section 3F — assembly

| Requirement | Implementation | API · screen · model | Proof | Browser | Status |
|---|---|---|---|---|---|
| Deadline = report date + 60 days, countdown | `services/binders.py` | `GET /binders/{id}` · screens 1, 5 · `binder.assembly_due` | `test_clocks.py`; `test_spec_2_sixty_day_…` | countdown on both screens | PASS |
| Assemble freezes every paper, computes a file hash, writes a manifest with every paper's hash | `services/assembly.assemble` | `POST …/assemble`, `GET …/verify` · screen 5 · `binder.assembly_hash`, `binder_event` | `test_spec_3f_…`; `test_api_assembly.py`; `test_spec_8_…` (8.5); `test_session_scope.py` and `AssemblyPage.test.tsx` (state shown at once after Assemble, D41) | manifest table with 13 papers and hashes; "Every recorded hash reproduces"; assembled state shown immediately after the fix | PASS |
| Blocked by unsigned papers, open notes, broken references, missing required papers | `assembly.blockers` | `GET …/assembly` blockers · screen 5 | `test_spec_3f_…`; `test_spec_8_…` (8.3); `test_api_close_out::the_blocker_inventory_…` | blockers named on screen 5 during the walk-through | PASS |
| After assembly nothing deleted; changes are new versions with reason, author, date; manifest records the amendment | `assembly.amend`, events | `PATCH` with reason, `DELETE` 409 · screens 2, 5 · `wp_version`, `binder_event` | `test_spec_2_nothing_is_deleted_…`; `test_api_assembly::attaching_after_assembly_is_an_amendment` | amendment, "amended" event, re-assembly with a new hash | PASS |

## Section 3G — retention and production

| Requirement | Implementation | API · screen · model | Proof | Browser | Status |
|---|---|---|---|---|---|
| Seven-year clock per engagement | `binder.retention_until` | `GET /binders/{id}` · screens 1, 5 | `test_clocks::retention_is_seven_years_after_the_report_date` | shown | PASS |
| Native format, not a flattened print | stores keep the uploaded bytes; archive carries them | `GET /attachments/{id}/content`, produce · screen 2 · `wp_attachment.sha256` | `test_spec_3g_…`; `test_api_attachments::upload_preserves_bytes_and_records_the_hash` | archive's CSV byte-identical to the upload | PASS |
| Produce file: full file + manifest + audit trail in one archive | `services/produce.py` | `GET …/produce` · screen 5 | `test_spec_3g_…`; `test_api_close_out.py` | link present; archive inspected | PASS |
| Purge only after retention; the purge writes its own record | `services/retention.py`, `assembly.purge` | `POST …/purge` · screen 5 · `binder_event` | `test_spec_3g_…`; `test_api_assembly::purge_is_refused_…` | button withheld "once retention expires" | PASS |

## Section 3H — records

| Requirement | Implementation | API · screen · model | Proof | Browser | Status |
|---|---|---|---|---|---|
| Discussions log, including TCWG | `services/records.py` | `…/discussions` · screen 1 · `discussion` | `test_spec_3h_…` | recorded with "R. Mehta (TCWG, Audit Committee Chair)" | PASS |
| Departures log | same | `…/departures` · screen 1 · `departure` | `test_spec_3h_…` | recorded | PASS |
| Access log: who opened the file after assembly | `services/access.py` (D25) | every read after assembly · screen 5 · `access_log` | `test_spec_3h_…`; `test_api_access_log.py` | screen 5 lists "assembly status", "binder", "verify" reads with user and time | PASS |

## Section 4 — data model

| Requirement | Implementation | Proof | Status |
|---|---|---|---|
| Tables `binder`, `wp`, `wp_version`, `wp_attachment`, `xref`, `review_note`, `discussion`, `departure`, `access_log` with the listed fields | `models/*.py`, migrations 0001–0010 | `test_spec_4_…`; `test_models::every_spec_field_is_a_column`; `test_migration_sql::upgrade_creates_every_model_table_with_every_column` | PASS |
| Append-only `wp_version`, `review_note`, `discussion`, `departure`, `access_log`: updates and deletes fail at the database | `oak_binder_append_only()` triggers and grants | `test_spec_4_…` (triggers present, truncate refused); `test_db_rules*.py` (row-level refusals with real rows) | PASS |
| Immutable `wp_version` | same | `test_db_rules::wp_version_update_is_refused` and siblings | PASS |

## Section 5 — screens

| Screen | Component | Proof | Browser | Status |
|---|---|---|---|---|
| 1 Binder: index tree, completeness, countdown | `pages/BinderPage.tsx` | `BinderPage.test.tsx`; `test_spec_5_…` | walked | PASS |
| 2 Working paper: paper, versions, attachments, cross-references, sign-off | `pages/PaperPage.tsx` and components | `PaperPage.test.tsx`, `CrossReferences.test.tsx`, `ReviewNotes.test.tsx`, `GeneratedPanel*.test.tsx`, `ReviewLevels.test.tsx` | walked (A-1, D-L) | PASS |
| 3 Review notes: open, by whom, assigned, blocking what | `pages/ReviewNotesPage.tsx` | `ReviewNotes.test.tsx` | opened | PASS |
| 4 Cross-reference map with broken links flagged | `pages/XrefMapPage.tsx` | `XrefMapPage.test.tsx` | opened | PASS |
| 5 Assembly & retention: blockers, Assemble, manifest, Produce file | `pages/AssemblyPage.tsx` | `AssemblyPage.test.tsx` | walked (assemble, verify, re-assemble) | PASS |

## Section 6 — the two passes

Pass 1 and Pass 2 features are all present (sections above). Pass 2's module connections exist
as tested contracts and doubles, not live links: see Gaps.

## Section 7 — not in v1

| Statement | How the build honours it | Proof | Status |
|---|---|---|---|
| No rich document editor: structured fields plus markdown plus attachments | markdown rendered and sanitised; native attachments | `markdown.test.tsx`; `PaperPage.test.tsx` | PASS |
| No e-signature: sign-off is an authenticated action with a timestamp | identity required (503 without one), time recorded | `test_spec_7_…`; `test_identity.py` | PASS |
| No group audit files (SA 600) | not built | — | PASS (by omission) |
| No automatic drafting of conclusions | WorkMind conclusion refused (422); the conclusion field is a person's | `test_spec_7_…`; `test_api_generated::module_fields_are_locked_and_the_conclusion_stays_human` | PASS |

## Section 8 — acceptance criteria

| # | Criterion | Proof | Status |
|---|---|---|---|
| 1 | No sign-off without a conclusion | `test_spec_8_…`; `test_api_papers::sign_off_requires_a_conclusion` | PASS |
| 2 | No sign-off with an open review note | `test_spec_8_…`; `test_api_review_notes::open_note_blocks_sign_off_until_cleared` | PASS |
| 3 | Assembly blocked by unsigned papers, open notes, broken references, missing papers, each named | `test_spec_8_…`; `test_api_assembly::assembly_is_blocked_by_named_items` | PASS |
| 4 | After assembly a delete fails and an edit creates a new version with a reason | `test_spec_8_…`; `test_api_assembly::after_assembly_edits_need_a_reason_and_deletes_fail` | PASS |
| 5 | Manifest lists every paper with its hash; recomputing the file hash reproduces it | `test_spec_8_…`; `test_api_assembly::verify_reproduces_every_hash_and_detects_tampering` | PASS |
| 6 | Produce-file returns the complete file in native formats plus the manifest, in one action | `test_spec_8_…`; `test_api_assembly::produce_file_is_one_archive_with_native_files_manifest_and_trail` | PASS |
| 7 | Retention date = report date + 7 years; purge before it fails | `test_spec_8_…`; `test_api_assembly::purge_is_refused_before_retention_and_recorded_after` | PASS |
| 8 | A sampling paper carries its formula and its seed | `test_spec_8_…`; `test_api_generated::a_sampling_paper_carries_its_formula_and_seed_printed_on_it` | PASS |
| 9 | Every sign-off records user, timestamp and paper version | `test_spec_8_…`; `test_api_papers::full_sign_off_records_who_when_and_which_version` | PASS |

## User workflows, end to end

`test_every_user_workflow_end_to_end` runs the whole list against `oak_binder_test`; the browser
walk-through repeated it on the development servers (binder `ACCEPT-2026-11-01`, kept in
`oak_binder_test` like the earlier demo binders).

| Workflow | Backend proof | Browser |
|---|---|---|
| Create a binder | end-to-end test | created from the Binders screen with report date |
| Create and edit working papers | end-to-end test | A-1 from the prefilled index entry; fields edited and saved |
| Prepare and review papers | end-to-end test | A-1 and D-L through preparer, senior, partner, sign-off |
| Raise, assign, respond to and clear review notes | end-to-end test | all four on A-1; sign-off blocked until cleared |
| Manage attachments | end-to-end test (upload, download, delete refused after assembly) | listed with hash and identifying characteristics; upload itself through the API, since the browser pane cannot pick a file |
| Generate and verify papers | end-to-end test | lead schedules and adjustment chain generated from the card; sampling and WorkMind papers delivered to the running backend and shown with provenance and run verification |
| Create and confirm cross-references | end-to-end test | A-1 → D-L added; superseded after D-L's amendment; confirmed from the screen |
| Record discussions and departures | end-to-end test | both recorded from the Binder screen |
| Assemble and lock the binder | end-to-end test | assembled from screen 5; manifest and hash shown |
| Create amendments | end-to-end test | D-L amended with a reason (version 4); re-assembled with a new hash |
| Produce and verify the complete archive | end-to-end test | "Verify hashes" reproduced every hash; archive fetched and inspected |
| Enforce retention and purge restrictions | end-to-end test (409 before, purge after) | purge withheld until retention |
| Record post-assembly access | end-to-end test | access log on screen 5 |

## Gaps, stated honestly

1. **No live module exists.** Financial Spine, WorkMind, Materiality, Sampling and Analytical
   Review are integrated against stated contracts and local doubles only. `OAK_SPINE_URL` and
   `OAK_WORKMIND_URL` are unset in development; the doubles served the browser walk-through.
   The integrations are tested; they are not live.
2. **Template content is the specification's words only.** Areas D–T are generic in the index
   (lead schedules carry the Spine's labels through the derived map), the six required papers
   are the spec's, SA references are empty, and all four engagement types are identical apart
   from their names. The mechanism to change this is complete; the content is not in the spec.
3. **No reviewer-identity rule.** Levels are recorded with whoever reviewed; the specification
   states no rule, so none is enforced.
4. **Development identity is one user.** `OAK_AUTH=dev` names one person for every role, so the
   browser walk-through shows `dev@localhost` at every step; production requires the proxy
   identity (D24).
5. **Found and fixed (D41):** the stale "State: open" after Assemble was a backend race, the
   request's commit landing after the response had been sent, so the screen's reload could read
   the binder row before the commit and the event rows after it. Reproduced on the development
   backend (one of six immediate reads), fixed by committing before the response
   (`scope="function"` on the session dependency), pinned by `tests/test_session_scope.py`, and
   guarded on the screen (an action's own answer is applied; a reload with fewer events is
   ignored). Five trials after the fix read the assembled state every time.
6. **Browser limitation, not a product gap:** file uploads were sent through the API because
   the browser pane cannot operate a file picker; the attachment list, hashes and removal rules
   were checked on the screen.

Fixed during this audit (all with tests): the Spine-papers card did not refetch after the link
was saved on the same screen; the cross-references panel still said FS lines are never checked;
the locked-fields note on a Spine paper claimed objective and procedure were locked; the
Assembly screen showed an empty "Not checked:" heading. One finding about the suite itself: it had
relied on no demo row in the shared test database holding the fixtures' run ids or evidence
bytes; the walk-through filed both, 22 tests failed, and the helpers now make evidence bytes
unique per session and run ids unique per call.

Final smoke test (1 November 2026, before the demonstration): all five screens opened on the
walk-through binder, the sampling paper's panel showed its formula and seed, the WorkMind
paper's panel showed "Run verified: accepted by manager@firm", and two texts were corrected: the
Binders screen doubled the "draft:" prefix on the template warning, and the template
placeholder still said no lead schedule could be generated without a firm map (the derived map
of D38 now applies). Both with tests.
