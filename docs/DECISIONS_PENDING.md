# Decisions pending — Working Paper Binder

**31 October 2026; updated 1 November 2026 at the close of Pass 2.** Pass 1 and Pass 2 are
built and verified. These are the points the specification leaves to people. Each names who
decides, what the Binder does meanwhile, and where the detail is. Nothing here is implemented
as if decided; items 13–28 record the readings Pass 2 took when no decision was available.

**Pass 2 completion work, 1 November 2026 (D39):** no input from any person is expected. Every item below
that blocked a feature has been closed by a conservative technical decision on the
specification alone (items 5, 13 and the lead-schedule side of 1–2; D36–D38). What remains
here is optional: answers would refine defaults the Binder now works without.

## Chartered accountant

| # | Decision | Meanwhile | Detail |
|---|---|---|---|
| 1 | Names for financial statement areas D–T, per engagement type | Generic section names; templates marked draft; Binders screen warns. *Lead schedules carry the Spine's head labels through the derived area map (D38)* | `docs\TEMPLATE_AUTHORING.md` |
| 2 | Required papers per engagement type, including a lead schedule per used area | Six required papers, one per spec-named section. *Lead schedules generate per derived area without being required (D38); a template may require `<area>-L`* | same |
| 3 | The five derived titles (A-1, B-1, W-1, X-1, Z-1); only "Materiality memo" is the spec's wording | Used as placeholders | same |
| 4 | SA references on required papers | None seeded; field available on every paper | `docs\SA_REFERENCES_FOR_CA_REVIEW.md` |

## Senior (engagement lead)

| # | Decision | Meanwhile | Detail |
|---|---|---|---|
| 5 | "Superseded paper" (spec §3E) | **Decided (D36, 1 Nov 2026):** a target amended after the reference was made is superseded; it blocks assembly as a broken reference until a person confirms the reference against the current version, recorded with who, when and which version | D36 in `docs\architecture.md` |
| 6 | Cross-reference `direction` read as `to` / `from` (this paper refers to the target / the target refers to this paper) | In use; both directions clickable | D26 |
| 7 | Access log reading of "opened": any read of an assembled or purged file's content, identity required, binder list not logged | In use | D25 |

## Firm (deployment and operations)

| # | Decision | Meanwhile | Detail |
|---|---|---|---|
| 8 | OAuth consent screen to "In production" (a Testing-status refresh token expires after seven days) | Development use only | README "Google Drive vault", D27 |
| 9 | Custody of `backend\secrets`: under the full `drive` scope the token reaches the whole Google account | Folder git-ignored, owner-only where the OS allows | D27 |
| 10 | Keep or remove the local attachment copies now in Drive | Kept | D27 |
| 11 | Authenticating reverse proxy, identity provider, `OAK_TRUSTED_PROXIES`, TLS | `OAK_AUTH=dev` in development; production refuses it | README "Identity", D24 |
| 12 | Applying migrations 0001–0009 to the live `oak_binder` at go-live | Never touched: 0 tables | README "Database" |

## Review-level policy (firm) — questions put, 1 November 2026

The Binder records who reviewed at each level and enforces nothing about who may (assumptions
24–25). Enforcement needs a firm policy the specification does not state; the exact questions
are in `docs\REVIEW_LEVEL_POLICY_REQUEST.md`. Nothing is built on an assumed answer.

| # | Decision | Meanwhile | Detail |
|---|---|---|---|
| 29 | Whether the Binder enforces who may review at a level at all, and how it learns a person's role (per-binder lists, a proxy attribute, a directory) | recorded only; any identity may record any level | `docs\REVIEW_LEVEL_POLICY_REQUEST.md` questions 1–2 |
| 30 | Whether the preparer may review their own paper, and whether one person may record several levels on one version | no rule | questions 3–4 |
| 31 | EQR independence, sign-off identity, refusal versus flag, freezing of role lists, differences by engagement type | no rule | questions 5–9 |

## Pass 2 completion work (1 November 2026) — decisions taken on the specification alone (D36–D39)

| # | Decision | Reason | Built as |
|---|---|---|---|
| 32 | A superseded paper target blocks assembly until confirmed | spec §3E says it blocks; papers are never deleted, so superseded means amended | `broken_reference` blocker; `POST /api/xrefs/{id}/confirm`; migration 0010 (D36) |
| 33 | A reference made to a draft paper takes the target's first version as its baseline | preparing a referenced draft is not a change to what was referenced | no blocker until the first prepared content changes (D36) |
| 34 | WorkMind papers are filed only after the run is read back as accepted; 503 without a WorkMind | spec §3C "one paper per accepted run"; only WorkMind knows | `services/workmind_client.py`, local double, migration 0010 (D37) |
| 35 | A default area map is derived from the Spine's tree when the template has none: each root's children, in served order, as areas D–T, named by the Spine's labels | spec §3A's lead schedule per area must work without a firm map; the tree is the only non-invented grouping | `area_map.derive`, `map_source` on the status, provenance `area_map_source` (D38) |
| 36 | Objective, procedure and result are not made mandatory at sign-off; only the conclusion is | spec §8.1 names only the conclusion; Spine papers arrive with those fields for the preparer | unchanged workflow, reading recorded (D39) |

## Pass 2 Stage D (generated papers, D31)

| # | Decision | Meanwhile | Detail |
|---|---|---|---|
| 13 | WorkMind: how an *accepted run* is verified | **Decided (D37, 1 Nov 2026):** read back from the configured WorkMind (`GET /api/runs/{run_id}`); filed only when `accepted`; 503 without a WorkMind; tested against the local double, no live WorkMind exists | D37; `docs\GENERATED_PAPER_INTAKE.md` |
| 14 | Service identities for the modules (`OAK_INTAKE_IDENTITIES`) and whether an intake credential is used | No intake under header auth until identities are listed | README "Generated papers" |

## Pass 2 Stage E (Spine-produced papers, D32) — assumptions taken without further input

**Built 1 November 2026 (steps E1–E6) exactly as the assumptions below say; architecture D32.**

**31 October 2026.** No further senior or chartered-accountant decision will be available.
Stage E proceeds on the original specification alone; each assumption below is the most
conservative reading of its words, built as stated, and recorded here so that anyone later can
see what was assumed and why (detail: `docs\PASS2_STAGE_E_PLAN.md` §15).

| # | Assumption | Reason | Built as |
|---|---|---|---|
| 15 | Spine papers come only from a locked Spine version | a locked version has a hash and never changes; an unlocked one cannot be assembled (D29) | generation refused by name on an unlocked version |
| 16 | Lead schedule reference `<area>-L`; adjustment chain `W-ADJ` in section W Completion | spec §3A/§3B: stable references in spec sections; no new section | fixed, renameable in the template later |
| 17 | A stale Spine paper is information, never a blocker | spec §3F, §8.3 list exactly four blockers | `not_checked` entry with both version ids |
| 18 | `working_paper_ref` matches a paper reference by exact string only; misses are listed | never guess | reference written only on an exact match |
| 19 | Objective and procedure of a Spine paper are not locked and arrive empty | the Spine produces figures, not narrative; no wording is invented | the preparer writes them |
| 20 | Any authenticated user may generate; the ordinary chain signs off | spec §3D names the chain and no further gate | no extra permission |
| 21 | Areas with mapped heads but no ledger entries still get a lead schedule saying so in the Spine's terms | spec §3A per area; no figure asserted without evidence | per-head statement, figures as served |
| 22 | No post-assembly regeneration | link frozen after assembly (D29); locked version immutable | refused by name (409, "the binder is assembled") on an assembled binder; Pass 1 amendments unchanged |

**Limitations, not assumptions** (data the firm has not supplied; nothing is invented):

| Item | State | Effect |
|---|---|---|
| Schedule III heads → areas D–T | configurable `areas` block, shipped empty | no lead schedule can be generated for a shipped template until a map is entered; the screen and the template check say so |
| Area names D–T | placeholders | lead schedule titles carry the placeholder until the template is edited |
| Required lead schedule per used area | not added | completeness cannot count a missing lead schedule |
| Approved objective and procedure wording | slot empty | the preparer writes both |

## Pass 2 Stage F (review levels, D33) — assumptions taken without further input

**Built 1 November 2026.** Spec §3D names the levels and "configurable per engagement" and
nothing more; these are the readings taken, built as stated.

| # | Assumption | Reason | Built as |
|---|---|---|---|
| 23 | The preparer is always level one and is not configured | spec §3B makes preparation the first transition and records "prepared by + date" on the version | read from the prepared version; "preparer" refused in the list |
| 24 | Roles are recorded, never enforced | identities are strings; the Binder has no role model and the spec defines none | the level is stored with whoever reviewed it |
| 25 | No rule against one person at several levels, or the preparer reviewing | the spec states none | no new refusal |
| 26 | The configuration freezes binder-wide at the first level review, for good | a level could otherwise vanish under a paper mid-review; spec §3F's spirit | 409 at the service; a database trigger |
| 27 | No default levels per engagement type | templates are the firm's and carry no such data | per binder only |
| 28 | The archive's `reviews.json` sits outside the manifest | earlier assembly hashes must stand (spec §8.5) | manifest unchanged |

## Pass 2 (spec §6): built, and what remains for the firm and the chartered accountant

**Built (1 November 2026, D28–D34; `docs\PASS2_COMPLETION_REPORT.md`):** discussions and
departures logs (A); the Financial Spine link (B); FS-line checking and the cross-reference map
screen, also in the archive (C, G); the generated-paper intake with its per-source contract
(D); lead schedules and the adjustment chain produced from the Spine (E); configurable review
levels (F). The review notes workflow was built in Pass 1 (D21).

**Remaining, by owner.** None is code this project can write without the data or the module it
needs; each is stated above or in the completion report, and nothing is described as done.

| Owner | Item | Meanwhile |
|---|---|---|
| Chartered accountant | Items 1–4 above: area names D–T, required papers (including a lead schedule per used area), derived titles, SA references | placeholders; templates marked draft |
| Chartered accountant | The Schedule III head → area map per template (`areas` block, `docs\TEMPLATE_AUTHORING.md`) and the approved objective and procedure wording for lead schedules | shipped empty: no lead schedule can be generated until a map is entered; the screen says so |
| Senior | Items 5–7 above | in use as stated |
| Firm | Items 8–12 above, and 14 (module identities, intake credential) | development settings only |
| Firm, when the modules exist | Connecting Materiality, Sampling and Analytical Review to the intake; WorkMind's accepted-run verification (item 13) | the contract is defined and tested with example deliveries; WorkMind is refused (501) |
| Firm | Which identities may act at which review level, if roles are to be enforced (items 24–25) | levels are recorded with whoever reviewed |
