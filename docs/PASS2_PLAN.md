# Pass 2 implementation plan — Working Paper Binder, SA 230

**31 October 2026, plan for review. Status 1 November 2026: every stage A–G is built, verified
and closed (D28–D34); the completion report is `PASS2_COMPLETION_REPORT.md`.** Source:
`D:\WORKING_PAPER_BINDER.md` (the copy in `docs` is identical). Pass 1 is complete and pushed
(`eb5c9de`, `009db43`). The stage sections below keep the plan as written, with each stage's
built state marked in its heading.

## 1. What the specification says Pass 2 is

Spec §6: "**Pass 2 — the rest, 8 person-weeks.** Review notes workflow · cross-reference map and
broken-link detection · generated papers from Materiality, Sampling, Analytical Review and the
Spine · the discussions and departures logs · WorkMind run papers."

Reading every section of the spec, the Pass 2 features and their exact requirements are:

| # | Feature | Where the spec says it | Exact requirement |
|---|---|---|---|
| P2-1 | Review notes workflow | §3D, §4, §5.3, §8.2 | raised → assigned → responded → cleared; open note blocks sign-off; screen 3 |
| P2-2 | Review levels | §3D | "Levels: preparer → senior → manager → partner → EQR, configurable per engagement" |
| P2-3 | Cross-reference map | §5.4, §3E | screen: "FS line to paper to document, with broken links flagged"; the chain "financial statement line → lead schedule → working paper → source document, clickable in both directions" |
| P2-4 | Broken-link detection, complete | §3E, §3F, §8.3 | a reference to a deleted or superseded paper is surfaced and blocks assembly; includes FS-line targets once the Spine is linked |
| P2-5 | Lead schedules | §3A, §3C | "Lead schedule per area, tying to the Financial Spine, with the WPs beneath it"; the Spine produces "every lead schedule, and the adjustment chain" |
| P2-6 | Generated papers | §3C | a paper from a module "arrives complete, with its inputs and its citations, and nobody retypes anything" |
| P2-6a | Materiality memo | §3C | "with the benchmark, the band and the figures from the spine" |
| P2-6b | Sampling paper | §3C, §8.8 | "with the formula and the seed printed on it"; acceptance 8: "carries its formula and its seed" |
| P2-6c | Variance paper | §3C | "current year against prior, with the thresholds used" |
| P2-6d | Spine papers | §3C | "every lead schedule, and the adjustment chain" |
| P2-7 | WorkMind run papers | §3C | "one paper per accepted run, carrying the run id, the inputs and the source-row citations" |
| P2-8 | Discussions log | §2, §3H, §4 | `discussion · binder · date · participants[] · matter · outcome`; "significant matters, with whom, when. Including TCWG"; append-only |
| P2-9 | Departures log | §2, §3H, §4 | `departure · binder · requirement · reason · alternative_procedure · approved_by`; "which requirement, why, and the alternative procedure performed"; append-only |

Out of scope by the spec itself (§7): a rich editor, e-signature, group audits (SA 600),
automatic drafting of conclusions.

## 2. What already exists (Pass 1) and what each feature needs from it

| Feature | Already built | Must be extended |
|---|---|---|
| P2-1 Review notes | **Complete in Pass 1** (migration 0003, D21): chain, blocks, screen 3 | nothing; re-verify only |
| P2-2 Review levels | sign-off chain draft → prepared → in review → reviewed → signed off; one reviewer per version | the chain, the version record, the paper screen |
| P2-3 Map | cross-references with paper and document targets, in and out, clickable | a new screen and one aggregating endpoint |
| P2-4 Broken links | paper and document targets checked; FS lines "not checked" | FS-line checking against the Spine |
| P2-5 Lead schedules | templates with areas D–T (unnamed); papers; attachments | a paper generator fed by the Spine; area names from the CA |
| P2-6, P2-7 Generated papers | papers with versions, content hash, attachments, sign-off | an intake path that writes a complete paper with provenance |
| P2-8, P2-9 Logs | append-only pattern (triggers, grants), events, produce archive | two new tables, routes, screen sections, archive members |

## 3. What the sibling modules actually are (read-only inspection, 31 Oct 2026)

- **The Financial Spine exists**: `D:\CAF` (package `oak_spine`, API on port 8000). It exposes,
  read-only for our purposes: engagements; spine versions; balances; the Schedule III
  presentation (the financial statement lines); adjustments and the uncorrected schedule;
  ratios; prior year; lock state. It records performance materiality on a version "from a
  working paper, or the materiality module". Its own notes say an adjustment names a working
  paper but "nothing exists to open to" — that is the Binder's side of the link.
- **Materiality, Sampling, Analytical Review and WorkMind do not exist** anywhere on `D:\`
  (no code, no API). The Spine's decision D20 says the materiality module "does not exist
  yet". The Binder can therefore define and test the *contract* those papers must satisfy,
  and connect the Spine now; the other three connect when they exist.
- The Binder stays standalone: it will talk to the Spine over HTTP only, through one
  configured base URL, never by importing its code or reading its database.

## 4. Dependencies between features

```
CA names areas D–T  ──►  P2-5 lead schedules  ──►  P2-3 map (lead-schedule level)
Spine link (base URL, engagement ↔ binder)  ──►  P2-4 FS-line checking  ──►  P2-3 map (FS-line level)
                                            ──►  P2-5, P2-6a, P2-6d (figures from the Spine)
Generated-paper intake (P2-6 core)  ──►  P2-6a/b/c/d, P2-7 (one contract each)
P2-8, P2-9 logs: no dependency
P2-2 review levels: no dependency, but a design decision (see §8)
```

## 5. Stages, in order

Each stage is additive, tested against `oak_binder_test` only, and leaves Pass 1 behaviour
unchanged. No migration runs until the stage is approved.

### Stage A — Discussions and departures logs (P2-8, P2-9) — **built 31 Oct 2026 (D28)**

- **Database**: migration 0006, two tables exactly as spec §4 names them, plus the
  bookkeeping every append-only table here has (`recorded_by`, `recorded_at`):
  `discussion (binder, date, participants[], matter, outcome)` and
  `departure (binder, requirement, reason, alternative_procedure, approved_by)`.
  Append-only by the existing trigger and SELECT/INSERT-only grants.
- **API**: `POST/GET /api/binders/{id}/discussions`, `POST/GET /api/binders/{id}/departures`.
  Identity required to record. Refused on a purged binder. Allowed after assembly? See §8.
- **Screens**: two sections on the Binder screen (screen 1), since spec §5 gives the logs no
  screen of their own.
- **Produce**: `discussions.json` and `departures.json` in the archive, and both in the audit
  trail.
- **Tests**: database rules (append-only, non-blank), API, archive, screen.

### Stage B — Spine link (foundation for P2-4, P2-5, P2-6a, P2-6d) — **built 31 Oct 2026 (D29)**

- **Settings**: `OAK_SPINE_URL` (optional; everything Spine-related is off when unset) and
  `OAK_SPINE_CREDENTIAL` if the Spine requires one (it has none today).
- **Client**: `services/spine_client.py`, read-only calls over HTTP with a test double, the
  same pattern as the Drive adapter: engagement, versions, presentation lines, balances,
  adjustments, lock state. Never writes to the Spine.
- **Database**: migration 0007, two nullable columns on `binder`: `spine_engagement_id` and
  `spine_version_id` (the version the file ties to; see §8 for whether it must be locked).
- **API**: `PATCH /api/binders/{id}` accepts the Spine engagement and version; `GET
  /api/binders/{id}/spine` shows the link and the Spine's status.
- **Screen**: the link on the Binder screen.
- **Tests**: client against the double; link validation; nothing else changes.

### Stage C — FS-line checking and the cross-reference map (P2-4, P2-3) — **built 31 Oct 2026 (D30)**

- **Checking**: a reference `to_fs_line` must name a presentation line of the linked Spine
  version; at assembly it is re-checked, and a line that no longer exists is a
  `broken_reference` blocker like the others. The "not checked" line on the Assembly screen
  disappears once a binder is linked; unlinked binders keep it.
- **Map**: `GET /api/binders/{id}/xref-map` returns the chain FS line → lead schedule →
  working paper → source document, with broken and amended links flagged; screen 4 at
  `#/binders/{id}/xref-map`, every node clickable (paper screens, attachment downloads,
  and the Spine's own screen for a line if the Spine offers a URL).
- **Tests**: checking with a linked and an unlinked binder; map shape; screen.

### Stage D — Generated-paper intake (P2-6 core, P2-6b, P2-7 contracts) — **built 31 Oct 2026 (D31; decisions in `PASS2_STAGE_D_PLAN.md` §11)**

- **Mechanism**: `POST /api/binders/{id}/generated-papers`. The body carries the paper's
  fields (reference, section, title, SA references, objective, procedure, population and
  sample, result, conclusion) plus `source` (materiality, sampling, analytical_review, spine,
  workmind), `run_id`, `inputs` and `citations`. The Binder writes the paper and its first
  version with the provenance inside the version body, so the content hash covers the
  inputs and citations and nothing can be retyped. Attachments may come with it.
- **Per-source rules the spec states**, enforced at intake: a sampling paper is refused
  without `formula` and `seed` (§8.8); a variance paper without `thresholds`; a materiality
  memo without `benchmark`, `band` and the Spine figures; a WorkMind paper without `run_id`,
  `inputs` and `source_row_citations`, and only for an *accepted* run.
- **Storage**: no new table; provenance lives in the immutable version body. One nullable
  column on `wp`, `generated_by` (the source), so the index can show which papers were
  generated (migration 0008; see §8 if you prefer no column).
- **Screen**: the paper screen shows "Generated by … run … on …" and the inputs and
  citations read-only.
- **Tests**: every rule; a generated sampling paper carries its formula and seed in its
  version body and its produced archive (acceptance 8.8).
- Sampling, Analytical Review and WorkMind connect to this endpoint when they exist; until
  then the contract is tested with fixtures.

### Stage E — Papers the Spine produces (P2-5, P2-6d, P2-6a figures) — **built 1 Nov 2026 (D32; plan, decisions and limitations in `PASS2_STAGE_E_PLAN.md`)**

- **Lead schedules**: one paper per area, generated from the Spine's grouped balances for the
  linked version, through the Stage D intake. Needs the CA's area names and the mapping of
  Schedule III groups to areas D–T (`docs/DECISIONS_PENDING.md` items 1–2); the mechanism
  can be built and tested against the double before the names arrive.
- **Adjustment chain**: one paper carrying the Spine's adjustments and the uncorrected
  schedule for the linked version.
- **Materiality figures**: the memo's "figures from the spine" come from the same client;
  the benchmark and band come from the Materiality module when it exists.
- **Refresh**: a generated paper is regenerated as a new version (reason: "Spine version
  changed"), never edited in place, so the history stays whole.

### Stage F — Review levels (P2-2) — **built 1 Nov 2026 (D33; design 1, migration 0009)**

- **Design** (one of two, your choice in §8): (1) a per-binder ordered list of levels, each
  level recording its reviewer and time on the version, with sign-off allowed only after
  the last level; or (2) keep the two-step chain and record the level name on each review.
- **Database**: migration 0009: `binder.review_levels[]` and, for design (1), a
  `wp_review` table (version, level, reviewer, at), append-only.
- **API and screen**: the paper's sign-off panel shows the levels and which are done.

### Stage G — Close-out — **built 1 Nov 2026 (D34; no schema change)**

Produce archive carries the logs, the map and provenance; assembly blockers unchanged
except FS-line references; docs D28–D31; completion report for Pass 2.

*As built:* the archive gains `cross_reference_map.json`, the map in the shape
`GET /api/binders/{id}/xref-map` serves, built from the recorded references and the FS lines
the assembly recorded (D30), so it is byte-identical with the Spine up, failing, timing out or
unconfigured; it sits outside the manifest and the file hash. `tests/test_api_close_out.py`
proves the whole member inventory (Pass 1 and Pass 2), the map's equality with the endpoint,
the manifest and hash untouched, and the blocker inventory exactly the spec's four plus D17's
`report_not_dated` and D29's four Spine-link kinds: Stages C–G added none. Stale wording in
this plan, the README and `DECISIONS_PENDING.md` corrected; `PASS2_COMPLETION_REPORT.md`
written; D34 added to `architecture.md`.

## 6. Database changes (all additive; each approved before it was written, applied to `oak_binder_test` only)

| Migration | Adds | Stage |
|---|---|---|
| 0006 | `discussion`, `departure`, append-only | A |
| 0007 | `binder.spine_engagement_id`, `binder.spine_version_id` | B |
| 0008 | `wp_generation` (append-only provenance; decision 2) | D |
| 0009 | `binder.review_levels[]`, `wp_review` | F |

Nothing in migrations 0001–0005 changes. The live `oak_binder` is not touched.

## 7. Backend APIs and frontend screens, by stage

| Stage | New endpoints | Screens |
|---|---|---|
| A | discussions and departures, list and record | Binder screen sections |
| B | Spine link on the binder; Spine status | Binder screen link |
| C | `xref-map` | new screen 4 |
| D | `generated-papers` intake | paper screen provenance block |
| E | `GET /api/binders/{id}/spine-papers`; `POST …/spine-papers/lead-schedules`; `POST …/spine-papers/adjustment-chain`; `POST /api/papers/{id}/regenerate`; `freshness` on a Spine paper's `generated` | Binder screen Spine papers card; generated panel's Spine block, freshness banner and Regenerate |
| F | `review_levels` on `PATCH /api/binders/{id}`, `review_levels_frozen` on the binder; the existing `POST /api/papers/{id}/review` records the next level; `review_chain` on the paper; `reviews.json` in the archive | paper sign-off panel chain and "Review as <level>"; Binder screen Review levels card |

## 8. Points that need your decision before the stage that uses them

1. **Logs after assembly** (Stage A). The spec says nothing is deleted after assembly and
   changes are versioned; a discussion recorded after assembly is new evidence, not a
   change. Proposal: allowed, recorded as an event, and the binder must be re-assembled
   before production (as for amendments). Confirm. *Built as proposed (D28).*
2. **TCWG** (Stage A). "Including TCWG" — proposal: a `with_tcwg` flag on the discussion, or
   TCWG as a named participant. Choose. *Built: TCWG is a role written after the
   participant's name; no field added (D28).*
3. **Which Spine version a binder ties to** (Stage B). Proposal: the engagement's locked
   version, with unlocked versions refused for assembly. Confirm. *Built: an unlocked
   version may be linked while the work goes on; assembly needs a locked one (D29).*
4. **Spine authentication** (Stage B). The Spine has no authentication today; when it gets
   one, the Binder needs a credential setting. Confirm the Binder may call the Spine
   read-only over HTTP on the same host. *Built: GET-only client, optional bearer credential
   `OAK_SPINE_CREDENTIAL`, redacted everywhere (D29).*
5. **Provenance column** (Stage D). `wp.generated_by` is not in spec §4. Alternative: derive
   from the version body only, with no column. Choose. *Built: no column on `wp`; the
   append-only `wp_generation` table (migration 0008) and the provenance block in every
   version body (D31).*
6. **Status of a generated paper on arrival** (Stage D). Proposal: it arrives prepared, with
   the module named as preparer, since "nobody retypes anything"; a person reviews and
   signs off. Alternative: it arrives in draft. Choose. *Built: it arrives as a draft; a
   person prepares, and the chain follows (D31, Stage D decision 1).*
7. **Review levels design** (Stage F). Design (1) or (2) above. *Decided 1 Nov 2026: design
   (1), with the preparer as the fixed first level from the prepared version and the
   configuration frozen binder-wide at the first level review (D33).*
8. **Area names and Schedule III mapping** (Stage E). CA decision already pending
   (`DECISIONS_PENDING.md` items 1–2); Stage E cannot finish without it. *Resolved as a
   limitation, 1 Nov 2026: the mechanism is built and tested; the shipped templates carry an
   empty map and no lead schedule can be generated until the firm enters one (D32).*
9. **The three absent modules.** Confirm that Sampling, Analytical Review and WorkMind are
   to be met by the intake contract only, with real connections later. *Built so: the
   contract is defined and tested with example deliveries; WorkMind deliveries are validated
   and refused (501) until the module exists; no module is connected (D31).*

## 9. What stays the same

Everything Pass 1 verified: identity, access log, cross-reference direction, assembly
blockers for papers, notes and documents, retention and purge, the Drive vault, the
templates. Every stage adds; none rewrites.
