# Pass 2 · Stage E plan — Papers the Financial Spine produces

**31 October 2026, revised the same day after review (§12), for consistency (§14), and finally to proceed independently (§15, which governs where it differs from §9 or §13). Built 1 November 2026, steps E1–E6, as §15 says; architecture D32.** Stages A–D are built and verified
(D28–D31). Stage E covers the one generated-paper source that exists: the Financial Spine
(`oak_spine`, in `D:\CAF`), read-only through the Stage B client. Spec §3C names what it
produces: "Every lead schedule, and the adjustment chain."

Sections 1–3 separate what the specification says, what already exists, and what is proposed.
Section 9 lists the questions the specification does not answer with the options weighed;
**§15 records the decision taken on each**, since no further senior or chartered-accountant
input will be available and the Binder is built from the specification alone.

## 1. Explicit specification requirements

Verbatim from `docs/WORKING_PAPER_BINDER.md`:

| Where | Words | What it fixes |
|---|---|---|
| §1 | "the Financial Spine will produce more. The Binder is where all of it lands, gets reviewed, gets signed off, and gets locked." | Spine output lands in the Binder as papers that go through review and sign-off |
| §3A | "Lead schedule per area, tying to the Financial Spine, with the WPs beneath it." | One lead schedule per financial statement area (sections D–T); it ties to the Spine; working papers hang beneath it |
| §3C | "A paper produced by a module arrives complete, with its inputs and its citations, and nobody retypes anything." | Applies to the Spine as a source |
| §3C | Financial Spine → "Every lead schedule, and the adjustment chain" | Two kinds of paper: the lead schedules, and one paper carrying the adjustment chain |
| §3E | "Financial statement line → lead schedule → working paper → source document, clickable in both directions." | A lead schedule refers to its FS lines; working papers refer to it |
| §3B | the paper's fields, "Status: draft → prepared → in review → reviewed → signed off" | A lead schedule is an ordinary paper with the ordinary chain |
| §3D, §8.9 | "Every sign-off records who, when, and which version of the paper." | People sign the lead schedule off |
| §3F, §8.4 | "After assembly: nothing is deleted. A change creates a new version carrying reason, author and date, and the manifest records the amendment." | A post-assembly change is a reasoned new version: the Pass 1 amendment path, unchanged; Stage E offers no post-assembly regeneration (decision 15) |
| §3F, §8.3 | "Blocked by: unsigned papers, open review notes, broken references, missing required papers." | The four blockers; nothing else blocks by the spec's words |
| §4 | the data model | No table for lead schedules or Spine figures; `wp_version.body` is the immutable record |
| §7 | "Automatic drafting of conclusions. That is WorkMind, and it is gated." | The lead schedule's conclusion is a person's |

The spec does **not** say: what a lead schedule shows, how areas D–T map to Schedule III heads
(the CA's pending decision), who triggers generation, what happens when the Spine's figures
change, where the adjustment-chain paper sits, or what its reference is. Those are §9.

## 2. Existing functionality to reuse (inspected 31 Oct 2026)

**In the Binder**

- **Spine client (D29)**: `services/spine_client.py`, GET only, with `version`,
  `presentation` (Schedule III lines by stable `head_id`, current and prior figures),
  `balances`, `adjustments(status=…)` and `uncorrected` (the last three returned as JSON as
  the Spine serves them). The test double `tests/fake_spine.py` already answers all five.
- **Spine link (D29)**: `binder.spine_engagement_id` / `spine_version_id`; blockers
  `spine_version_unlocked`, `spine_version_missing`, `spine_unreachable`,
  `spine_version_not_verified`; the assembled event records the version's lock hash.
- **FS lines (D30)**: `services/fs_lines.py` reads the linked version's presentation lines;
  a reference to a line must name a `head_id`; the cross-reference map treats *the paper
  that refers to an FS line* as that line's lead schedule and draws the working papers that
  refer to it beneath (`services/xref_map.py`). Assembly records the lines it verified.
- **Generated-paper intake (D31)**: `services/generated.receive` validates, files a draft,
  writes `wp_generation` (source, module, run, payload, hash at intake); `papers.snapshot`
  embeds the provenance in every version body; module fields are locked
  (`papers.refuse_locked`); `source = "spine"` is already a legal value of the table's CHECK
  constraint and is refused by the service with "Stage E".
- **Papers**: creation, immutable versions, the sign-off chain, amendments with a reason
  after assembly (`assembly.amend`), attachments joining at prepare (D17).
- **Assembly and archive**: manifest from the database, named blockers, `produce` writing
  every version body (so provenance travels), access log.
- **Templates**: `templates/*.json` carry sections D–T with placeholder names and no
  required lead schedules; `docs/TEMPLATE_AUTHORING.md` items 1–2 hold the CA's pending
  decisions on area names and required papers; `templates_check` validates a file.

**In the Spine (read-only, `D:\CAF\backend\src\oak_spine`)**

| Endpoint | Serves | Used for |
|---|---|---|
| `GET /api/spine-versions/{id}` | version: `is_locked`, `hash`, `locked_at`, `performance_materiality`, `pm_source`, `prior_version_id`, adjustment counts | version identity and freshness |
| `…/presentation` | Schedule III Division I: balance sheet and P&L lines by `head_id`, `label`, `side`, `depth`, `current`, `prior`, `has_figures`; `status`, `provisional`, `hash` | the FS lines of an area |
| `…/balances` | the chain per ledger: unadjusted, reclassifications, corrections, adjusted, prior; `head_id` per ledger; grouped totals per head (`ledgers`, `unadjusted`, `adjusted`, `prior`) in the order the Spine serves them; `source` computed or stored; `hash` | the ledgers beneath each FS line of an area, with the Spine's own totals |
| `…/adjustments[?status=]` | each adjustment: `adjustment_id`, `kind` (reclass, correction), `status` (proposed, accepted, refused), `narration`, **`working_paper_ref`**, `finding_ref`, proposer and decider with times, `decision_note`, `lines[]` with `ledger_key`, `ledger_name`, `parent_chain`, `head_id`, `dr`, `cr` | the adjustment chain, and which adjustments touch an area |
| `…/uncorrected` | the uncorrected misstatements with measure and profit effect, the gross aggregate, performance materiality, headroom and the gate state | the adjustment-chain paper's second half |
| `GET /api/tree` | the Schedule III head tree: every head with its `id`, its explicit `parent` id (or none for a root), label, side, depth and `mappable`, listed "in Schedule III order, parents before children" | mapping heads to areas: the **only** source of parent–child relationships |

CAF's D30 is a constraint the Binder should honour: "the frontend does no arithmetic on
money: every figure … is a string the server produced". The Binder likewise copies the
Spine's figures and totals and adds nothing up.

The Spine's adjustments carry a free-text `working_paper_ref` ("Every adjustment opens its
working paper" in the Spine's spec; CAF notes nothing exists to open to there). That text is
the natural hook for the adjustment-chain paper to refer to the Binder's working papers.

## 3. Proposed design

### 3.1 Two kinds of Spine paper, both through the Stage D intake path

Generation is **pulled by the Binder** (the Spine never calls the Binder; it stays read-only
to us): a person on the Binder screen asks for the lead schedules or the adjustment chain, the
Binder reads the linked version from the Spine, builds the paper body and files it through
`services/generated.receive` with `source = "spine"`, `module = "oak_spine"`, so everything
Stage D guarantees holds: draft on arrival, provenance in every version body, locked module
fields, the archive carrying the inputs and citations.

| Kind | One per | Reference | Section | FS-line references written at generation |
|---|---|---|---|---|
| Lead schedule | every mapped area D–T, with or without figures (decision 13, §12.1) | `<area>-L` (decision 2) | the area | one `to_fs_line` per face line of the area (so the Stage C map shows it as the line's lead schedule) |
| Adjustment chain | binder | `W-ADJ` (decision 3) | W Completion (decision 3) | none; paper references to the working papers named by `working_paper_ref` where the ref matches a paper of the binder (decision 7) |

### 3.2 What a lead schedule contains

The spec says only "tying to the Financial Spine". Proposed content, all copied from the
Spine, nothing computed:

- **Header**: area code and name, the Spine engagement and version (id, label, lock time,
  hash), the Spine's `source` (stored or computed) and whether the version is locked.
- **Financial statement lines of the area**: each face line and sub-line of the area's
  heads from the presentation: `head_id`, label, current, prior.
- **Ledgers beneath each line** from the balances, per head in the order the Spine serves
  them (the Binder re-orders nothing): ledger name and
  chain, unadjusted, reclassifications, corrections, adjusted, prior; then the Spine's own
  per-head totals. (CAF D30: no arithmetic in the Binder.)
- **Adjustments touching the area**: every adjustment with a line whose `head_id` is in the
  area: id, kind, status, narration, `working_paper_ref`, amounts on the area's heads.
- **Rendering**: the structured data goes into the provenance block
  (`generated.spine`); a markdown rendering of the same tables goes into the paper's
  `result` field so the paper reads on screen and in the archive without the raw block
  (decision 4). `objective` and `procedure` are not the Spine's to produce: they are left
  for the preparer unless the template carries CA-approved wording, and they are not locked
  (decision 5, §12.5); `population_sample` carries the ledger count and the version;
  `conclusion` is empty for a person to write (§7). Where a head has no ledger entry or no
  served figure, the rendering says so in the Spine's own terms and asserts no figure
  (decision 13, §12.1).
- **Citations**: every figure cites the Spine version id and `head_id` (and ledger key for
  ledger rows); `inputs` records the version, area, head ids and the endpoints read.

### 3.3 What the adjustment-chain paper contains

- Every adjustment of the version (proposed, accepted, refused), with kind, status,
  narration, working paper and finding references, proposer and decider with times, decision
  note, and its lines (ledger, head, dr, cr).
- The uncorrected schedule as the Spine serves it: each misstatement with its measure and
  profit effect, the gross aggregate, performance materiality with its source, the headroom
  and the gate state.
- The same rendering rule as 3.2: structured block in provenance, markdown in `result`.
- Cross-references: for each `working_paper_ref` that equals a paper reference of this
  binder, a reference from the adjustment-chain paper to that paper (direction `to`); refs
  that match nothing are listed on the paper as "no paper of this binder" (information, not
  a blocker; decision 7).

### 3.4 Area mapping: the gap that gates "per area"

"Lead schedule per area" needs a map from Schedule III heads to sections D–T. That is the
CA's pending decision (TEMPLATE_AUTHORING items 1–2). Proposed mechanism, so the build is not
blocked by the decision:

- Each template JSON gains an optional `areas` block: `{"D": {"heads": ["BS.A.1", …]}, …}`,
  listing **Schedule III head ids only**, exactly as the Spine's tree spells them. There is
  **no textual prefix matching**: `"BS.A"` is read as the head whose id is `BS.A`, never as
  "every id starting with BS.A". A listed head **covers itself and every descendant** in the
  Spine's tree, where descent is read **exclusively from the `parent` field each head carries
  in the `GET /api/tree` response**: a head is a child of another when its `parent` equals
  that head's `id`, and for no other reason. The Binder derives nothing from the shape of an
  id (no dots, prefixes or depth arithmetic), so a tree the Spine restructures or renames is
  followed as served. Listing a parent is how a whole branch is assigned; listing a leaf
  assigns that leaf alone. Expansion and validation are in §12.6.
- The shipped templates carry an **empty** `areas` block, marked draft, exactly as the area
  names are placeholders today. Generation of lead schedules refuses with a named reason
  ("no area map for template statutory: see TEMPLATE_AUTHORING.md item 1") until the CA's map
  is entered. Tests use a test template with a full map against the Spine double.
- Nothing is invented: no head is assigned to any area by the Binder.

### 3.5 Freshness: when the Spine changes after generation

Every Spine paper records the version id and the version's `hash` (and the balances `hash`)
it was built from. The Binder compares that record with the binder's current link and the
Spine's current answer:

| Situation | What the Binder says | Where |
|---|---|---|
| Binder re-linked to another version while open (allowed by D29) | the paper is **stale**: built from version X, binder now on Y | paper screen banner, Binder screen's Spine-papers card, assembly |
| Linked version is unlocked (no hash) and its computed figures moved | only if decision 1(b) were chosen; under 1(a) no paper is generated from an unlocked version | same |
| Linked version locked, hash unchanged | current | — |
| Spine unreachable | freshness **not checked**, reason stated (the D30 pattern) | same |

Regeneration (decision 6) is the only way to update a Spine paper, since its module fields
are locked, and **it exists only while the binder is open** (decision 15, §12.3): it rewrites
the paper's fields from the Spine, returns it to draft, adds a new `wp_generation` row and
re-writes its FS-line references. Earlier versions and their provenance stay on file. After
assembly the link is frozen (D29) and a locked Spine version cannot change, so there is
nothing to regenerate from and the regenerate action is refused (409). The ordinary
post-assembly amendment path the specification requires (§3F, §8.4: a new version with
reason, author and date) stays exactly as built in Pass 1 and applies to a Spine paper's
unlocked fields (objective, procedure, conclusion) and attachments like any other paper.

Staleness **never blocks assembly** (decision 8, §15): the specification lists four blockers
and the Binder adds none. A stale paper is reported as information in the not-checked list,
on the Assembly screen and on the paper, and both the manifest and the paper's provenance
record which version each names, so the archive shows the difference.

### 3.6 Versioning, provenance and sign-off

Unchanged from Stage D: the paper arrives as a draft; a person prepares, a reviewer reviews,
a partner signs off; every version body carries `generated` with the full Spine block, so the
content hash covers every figure and citation; `content_hash_at_intake` covers the locked
fields; the archive's `versions/NNNN.json` carry it all. The person who asked for generation
is `received_by`; the Spine is the `module`; `run_id` is binder id, version id, Spine hash and
area (or `adjustments`) (decision 14, §12.2), unique per binder, so a repeated request on the
same unchanged locked version is refused as "one paper per run" naming the existing paper,
while a re-link gives a regeneration its own row.

### 3.7 Assembly and archive

- Blockers unchanged (unsigned, notes, broken references, missing required, the Stage B
  Spine blockers). A stale Spine paper is reported in `not_checked`, on the Assembly screen
  and on the paper; it is **never a blocker** (decision 8, §15).
- The manifest already records the linked version; no new key (keeps earlier hashes).
- The archive needs no new member: provenance is in the version bodies, `paper.json` says
  `generated_by: spine`. Optionally a `spine.json` member summarising the version, the lead
  schedules and their hashes (decision 9; not recommended, redundant).
- Cross-references written at generation are ordinary rows: the Stage C map draws the chain,
  and a vanished head is a broken reference as today.

## 4. Database changes

**None required.** `wp_generation` accepts `source = 'spine'` already; the FS-line references
are `xref` rows; the area map is a template file. If decision 8 adds a blocker it is computed,
not stored. No migration 0009.

## 5. Backend changes

| Area | Change |
|---|---|
| `services/spine_papers.py` (new) | `lead_schedule(session, client, binder, area)` and `adjustment_chain(session, client, binder)`: read the Spine, build the body and provenance block, call `generated.receive` with `source="spine"`, write the FS-line references; `status(session, client, binder)`: per Spine paper current / stale / not checked, areas with and without a lead schedule, heads in no area; `regenerate(session, client, binder, paper, *, user, now)` (open binders only; 409 after assembly, decision 15) |
| `services/generated.py` | accept `source="spine"` when called by `spine_papers` (not from the HTTP intake, which keeps refusing it so no outside caller can forge Spine papers); the `spine` block schema |
| `schemas/generated.py` | `SpineBlock`: version id, label, hash, locked_at, balances hash, area, lines[], ledgers[], adjustments[] (or the chain's adjustments[] and uncorrected) |
| `services/templates.py` | optional `areas` block, validated; `templates_check` reports it |
| `services/papers.py` | a regeneration path, open binders only, that may rewrite locked fields when the caller is `spine_papers` (the lock is against people, not the Spine) |
| `services/assembly.py` | stale Spine papers listed in `not_checked` as information, by paper reference with both version ids; never a blocker |
| `api/spine_papers.py` (new) | `GET /api/binders/{id}/spine-papers` (status), `POST /api/binders/{id}/spine-papers/lead-schedules` (body: `areas: ["D", …]` or all mapped), `POST /api/binders/{id}/spine-papers/adjustment-chain`, `POST /api/papers/{id}/regenerate` (open binders only; 409 once assembled); status reads access-logged on assembled files; CurrentUser is the requester |
| `schemas/spine_papers.py` (new) | status and request bodies |
| `api.ts` labels | none new: no new blocker kind |

## 6. Frontend changes

| Area | Change |
|---|---|
| `components/SpinePapersCard.tsx` (new, Binder screen) | the areas with a lead schedule (current / stale / not checked) and without; buttons "Generate lead schedules" (all or chosen areas) and "Generate adjustment chain"; the reason when generation is not possible (no link, no area map, unlocked version) |
| `components/GeneratedPanel.tsx` | a `spine` source block: version, hash, lock time; the lines and ledgers tables; the adjustments; a stale banner with "Regenerate" while the binder is open, and the plain statement of staleness once assembled |
| `pages/PaperPage.tsx` | the `result` markdown already renders; the panel above it |
| `pages/AssemblyPage.tsx` | the stale statement in the not-checked list (already rendered); nothing else |
| tests | card states; panel for a lead schedule and for the chain; stale banner; regenerate posts once |

## 7. Tests (backend, against `oak_binder_test` with the Spine double)

- Lead schedules generated for a test template with a full area map: one per mapped area
  with figures, the right section and reference, FS-line references to the area's face lines,
  provenance block equal to what the double served, markdown `result` containing every line
  and ledger figure verbatim, draft status, locked fields, human chain to sign-off.
- The Stage C map shows the generated paper as the line's lead schedule with working papers
  beneath.
- An area with no mapped heads, or a template with no area map: refused by name; an unlinked
  binder: refused; an unlocked version: per decision 1.
- Adjustment chain: every adjustment and the uncorrected schedule in the block and the
  markdown; references to matching working papers; non-matching refs listed.
- Freshness: re-link to another version → stale; Spine down → not checked; regenerate on an
  open binder → new generation row, draft, references rewritten; regenerate on an assembled
  binder → 409 with the reason (decision 15); one paper per run on an unchanged locked
  version. The Pass 1 amendment path still works on a Spine paper's unlocked fields after
  assembly (reason required, new version, `amended` event) and is covered by the existing
  amendment tests plus one case here.
- Assembly: a stale paper appears in `not_checked` with both version ids and assembly
  proceeds (no fifth blocker); archive carries the figures in every version body;
  hand-made papers and earlier binders unchanged; the HTTP intake still refuses
  `source = "spine"` from outside.
- The Spine double gains a richer `balances` fixture (several heads and ledgers across two
  areas) and an adjustments fixture with `working_paper_ref` values.

## 8. Dependencies, risks and ambiguities

| Item | Kind | Effect | Mitigation |
|---|---|---|---|
| Area map D–T (CA, TEMPLATE_AUTHORING 1–2) | dependency | without it no lead schedule can be placed; "per area" cannot be met | build the mechanism and tests with a test map; shipped map empty and refusing by name |
| Area names D–T (CA) | dependency | lead schedule titles would say "Financial statement area D" | same; titles follow the template's names |
| Required lead schedule per area (CA, item 2) | dependency | completeness view cannot count a missing lead schedule | template `required` entries once the map exists |
| Lead schedule narrative (objective, procedure) | ambiguity | the spec gives no wording; the Spine produces figures | not locked; the preparer writes them; CA-approved template wording inserted when it exists; no Binder-authored placeholder (decision 5, §12.5) |
| Unlocked linked version | risk | figures move under a generated paper; no hash to compare | decision 1: generate only from a locked version (recommended) |
| Payload size | risk | an area with thousands of ledgers may exceed the 1 MiB provenance cap | per-area papers keep it small; the cap applies and refuses by name; raise `OAK_MAX_PROVENANCE_BYTES` if the firm needs |
| Spine payload shape | risk | the Binder reads raw `balances`/`adjustments` JSON | parse into frozen records with unknown fields ignored, as the client does for versions; the double mirrors `oak_spine`'s builders |
| Arithmetic | risk | tempting to total figures in the Binder | copy the Spine's totals only (CAF D30) |
| `working_paper_ref` is free text | ambiguity | matching to paper references is by exact string | exact match only, misses listed, never guessed (decision 7) |
| Fifth blocker | spec tension | §3F lists four blockers | decision 8 |
| Materiality figures (P2-6a) | scope | the memo is the Materiality module's; its Spine figures are checked, not produced, by the Binder (D31) | out of Stage E unless decision 10 says otherwise |

## 9. Decisions weighed before coding (settled in §15)

| # | Question the spec does not answer | Options | Recommendation | Who |
|---|---|---|---|---|
| 1 | Generate from an unlocked version? | (a) locked only · (b) allowed, marked provisional, stale on any change | (a): figures have a hash; a locked Spine version never changes (CAF D25: unlocking inserts a successor), so with the link frozen after assembly (D29) a Spine paper can go stale only while the binder is open | decided (§15) |
| 2 | Lead schedule reference | `<area>-L` · `<area>-1` · the firm's convention | `<area>-L`, never reused; renameable in the template | decided (§15) |
| 3 | Adjustment-chain paper's section and reference | W Completion as `W-ADJ` · X Report · C Materiality (it compares with PM) | W Completion `W-ADJ`: it is a completion record | decided (§15) |
| 4 | Where the figures live on the paper | (a) provenance block + markdown tables in `result` · (b) provenance only, screen renders · (c) attach a CSV/XLSX the Binder writes | (a): readable in the archive without the Binder; (c) adds a Binder-authored file | decided (§15) |
| 5 | Objective and procedure of a Spine paper | (a) not locked: the Spine produces figures, not narrative, so the preparer writes them; approved wording in the template is inserted when present · (b) Binder-authored placeholder wording, locked | (a); see §12.5. The spec's only hard rule is the conclusion before sign-off (§2, §8.1). No wording is available: the slot ships empty | decided (§15) |
| 6 | Regeneration (open binders only, decision 15) | (a) always a new generation row: rewrites the paper's fields from the Spine and returns it to draft · (b) new paper with a new reference | (a): one lead schedule per area, history whole | decided (§15) |
| 7 | Adjustment `working_paper_ref` → cross-reference | exact match to a paper ref writes a reference; misses listed · no automatic references | exact match; misses listed as information | decided (§15) |
| 8 | Stale Spine paper at assembly | (a) information only, in the not-checked list and on the screens (within §3F's four blockers) · (b) a fifth, named blocker `spine_paper_stale` | **(a), final (§15).** The specification's four blockers stand and none is added; §12.4 keeps the consequences on record | decided |
| 9 | Archive `spine.json` summary member | yes · no | no: redundant with version bodies and the manifest | decided (§15) |
| 10 | Materiality memo's Spine figures | leave to the Materiality module (D31) · let the Binder fill them when a person creates the memo | leave to the module; out of Stage E | decided (§15) |
| 11 | Who may generate | any authenticated person · preparer-level and above | any authenticated person; the chain signs off | decided (§15) |
| 12 | Trigger | a person on the Binder screen · also on link change automatically | a person only; automatic generation would create papers nobody asked for | decided (§15) |
| 13 | Areas with a map whose heads have no ledger entries | (a) generate a lead schedule that states, per head, what the Spine answered (no ledger listed; the presentation figure as served or "no figure served"), distinguishing an explicit zero figure from the absence of a figure · (b) skip | (a): "per area" is met for every mapped area, nothing is silently absent, and no figure is asserted without the Spine's evidence; see §12.1 | decided (§15) |
| 14 | Run id for Spine papers | binder id + version id + Spine hash + area (unique per binder, changes only when the Spine changes) | yes; see §12.2 | decided (§15) |
| 15 | Post-assembly regeneration | (a) not offered: a locked version cannot change and the link is frozen, so nothing can be regenerated from · (b) offered as an amendment anyway | (a); see §12.3 | decided (§15) |

## 10. Stage-by-stage build (after decisions)

| Step | Builds | Done when |
|---|---|---|
| E1 Area map and Spine block | template `areas`, `templates_check`, `SpineBlock` schema, richer Spine double fixtures | templates and schema tests green |
| E2 Lead schedules | `spine_papers.lead_schedule`, intake with `source="spine"`, FS-line references, endpoint, status | generation tests green; map shows the chain |
| E3 Adjustment chain | `spine_papers.adjustment_chain`, references to working papers, endpoint | tests green |
| E4 Freshness and regeneration | `status`, stale detection, `regenerate` on open binders and its 409 once assembled, staleness in `not_checked` only | tests green; archive test green |
| E5 Screens | Spine-papers card, panel block, stale banner, blocker label | vitest, tsc, build green |
| E6 Docs | D32, README section and endpoint rows, TEMPLATE_AUTHORING `areas`, PASS2_PLAN status, DECISIONS_PENDING | reviewed |

## 11. Safety for the build

Only `oak_binder_test`; `D:\CAF` read-only; the live `oak_binder` untouched; no migration
(none needed); migrations 0001–0008 untouched; no Drive change; nothing committed or pushed
without approval; Stages F and G not started.

## 12. Clarifications after review — 31 October 2026

Each item says what the specification requires, what is decided technically, and what still
needs the senior's or the chartered accountant's approval.

### 12.1 Area coverage: one lead schedule per area

*Specification.* §3A: "Lead schedule per area". The areas are sections D–T (§3A). Which areas
an engagement type uses, and their names, are the CA's (TEMPLATE_AUTHORING 1–2, pending).

*How every required area is represented.*

| Area state | What the Binder does |
|---|---|
| Mapped, with figures | generates the lead schedule (3.2) |
| Mapped, heads present with figures of zero (the Spine serves `"0.00"` for a line or a ledger) | generates the lead schedule with those figures **as served**, line by line and ledger by ledger: a zero is a Spine figure like any other and is quoted, not summarised |
| Mapped, a head with **no ledger entries** in the balances (the head is in the tree but no ledger of the version carries it) | generates the lead schedule all the same (decision 13), stating for that head exactly what the Spine answered: "the balances of version X list no ledger under head H", and showing the presentation line's `current` and `prior` **as served**: the string if one is served, or "no figure served" if the Spine serves none. The Binder never writes a zero or the word nil for a head the Spine did not give a figure for |
| Mapped, every head without a ledger entry | the same, head by head; the paper exists, is signed off like any other, and the completeness view counts it |
| Not mapped (the CA has not assigned heads to it) | cannot be generated; the Spine-papers status lists the area as "no map" with the pointer to TEMPLATE_AUTHORING item 1; if the template requires a lead schedule in that area, the completeness view shows the missing required paper, so assembly is blocked by the spec's own fourth blocker until the map arrives or a person files the paper by hand |
| Area the firm does not use in this engagement type | the template requires no paper in it (TEMPLATE_AUTHORING item 1); nothing is generated and nothing is missing |

No head is assigned to an area by the Binder; coverage equals the CA's map, and every gap is
shown rather than skipped.

### 12.2 Run id uniqueness across binders

*Verified.* Migration 0008's index `uq_wp_generation_source_run` is unique on
`(source, run_id)` **across all binders**. The plan's first draft, version hash plus area, would
therefore collide the moment two binders link the same Spine version and both generate the
lead schedule for area D: the second would be refused as "one paper per run".

*Technical decision (14).* The run id of a Spine paper is
`<binder_id>/<version_id>/<spine_hash>/<area or 'adjustments'>`:

- unique per binder, so several binders on one version never collide;
- unchanged while the Spine is unchanged, so a duplicate request for the same area on the
  same locked version is refused as "one paper per run" with the existing paper named
  (idempotent, no second paper, no second row);
- different whenever the binder is re-linked or the version's hash differs, so a regeneration
  gets its own row and the history stays whole (12.3).

For the unlocked case (if decision 1 were (b)) there is no hash; the balances endpoint's own
`hash` would stand in, and a changed computed figure changes it.

### 12.3 Regeneration and history

*Specification.* §4: `wp_version` immutable; §3F: after assembly nothing is deleted and a
change is a new version with reason, author and date.

*What is preserved, exactly.*

| Record | Before assembly | After assembly |
|---|---|---|
| `wp_generation` rows | append-only: a regeneration adds a row with its own `run_id`, `received_by`, `received_at`, `payload`, `content_hash_at_intake`; earlier rows stay | not applicable (12.3, last paragraph) |
| `wp_version` rows | untouched; regeneration rewrites the live `wp` fields, returns the paper to draft, and the next prepare writes version N+1 whose body embeds the **latest** generation row; versions 1..N keep the body and hash they were signed with, each embedding the generation row current at its time | untouched |
| `xref` rows (FS-line references) | references to lines the new version lacks are removed and new ones added, as any open-binder reference change | cannot be removed (spec 3F; `xrefs.remove` refuses) |
| Content hashes | every version's `content_hash` is over its own body and recomputes for ever; `content_hash_at_intake` on each generation row covers the locked fields as delivered that time | unchanged |

*Why there is no post-assembly regeneration (decision 15).* With decision 1 (locked versions
only): a locked Spine version never changes (CAF D25: unlocking it inserts a successor version
and leaves the locked one as it was), and the Binder's link is frozen after assembly (D29,
`spine_link.set_link` requires an open binder). So after assembly there is nothing new to
regenerate from. Spine papers can go stale only while the binder is open, by re-linking, and
regeneration happens there, before assembly. This also avoids a trap the first draft did not
see: after assembly a reference to a vanished FS line could not be removed (spec 3F), would be
a broken reference, and would block re-assembly for ever. Should the firm later want a binder
to move to a new Spine version after assembly, that is a decision for a later stage, not Stage E.

### 12.4 Stale Spine papers at assembly — decided: information only

*Specification.* §3F and §8.3 list exactly four blockers: unsigned papers, open review notes,
broken references, missing required papers. A stale Spine paper is none of them. **No fifth
blocker is added** (decision 8, §15); option (a) is built. The table stays as the record of
what was weighed.

| | (a) Information only | (b) Fifth blocker `spine_paper_stale` |
|---|---|---|
| Spec | within the four blockers | an addition to §3F |
| What assembly does | proceeds; the not-checked list and the Assembly screen say "lead schedule D-L was built from Spine version X; the binder is linked to Y" and the archive carries both facts (manifest names Y, version body names X) | refuses by name until the paper is regenerated and signed off again |
| Consequence | a frozen file can carry a lead schedule whose figures are not the linked version's; an experienced auditor can see it, from the paper's provenance and the manifest, but the file does not stop it | the file is internally consistent at the price of a re-sign-off whenever the link moved after generation |
| Partial cover from the existing blockers | if the new version lacks a head the lead schedule refers to, that is a **broken reference** and blocks under the spec's own rule; same head ids with different figures are not caught | — |

Decision: (a). The specification's blocker list is exhaustive and the Binder does not extend
it. The cost noted above is accepted and mitigated: the not-checked list, the Assembly screen
and the paper all name both versions, the manifest and the version body each record theirs,
and a head the linked version lacks is still caught by the spec's own broken-reference
blocker.

### 12.5 Objective and procedure without invented wording

*Specification.* §2: "The WP template forces objective → procedure → result → conclusion. A WP
missing a conclusion cannot be signed off." The only hard rule is the conclusion; `objective`
and `procedure` are nullable in the model and the spec names no wording for a lead schedule.

*Technical decision (5a).* The Spine produces figures, not narrative. So for Spine papers the
locked fields are those the Spine actually produced: `title`, `section`, `sa_refs` (if the
template supplies them), `population_sample` and `result`. `objective` and `procedure` are
**not locked**: they arrive empty and the preparer writes them, exactly as on a hand-made
paper, before preparing. The Binder authors no audit narrative.

*Approved wording, when it exists.* The template's `areas` block may carry CA-approved
`objective` and `procedure` text per area (and for the adjustment chain). When present it is
inserted at generation and marked in provenance as "template wording, approved <date>"; the
preparer may still edit it. Until the CA supplies it, the fields are empty and the paper
screen says so. Nothing marked "draft wording" is ever written by the Binder.

### 12.6 Area mapping: nothing invented, validated, gaps communicated

- **Shipped templates carry an empty `areas` block.** No Schedule III head is assigned to any
  section by the Binder. The template `status` already says the files are draft pending the
  CA; the check command repeats it.
- **Expansion rule.** For each area, the covered set is the union, over its listed head ids,
  of that head and all its descendants in the Spine's tree as served by `GET /api/tree`.
  Descendants are found by following the `parent` field of the served heads (children are
  the heads whose `parent` is the id in hand, and so on), never by comparing id strings or
  using `depth`. The tree is read from the Spine when the map is validated and when a paper
  is generated; the tree version the Spine reports is recorded in the paper's provenance. A ledger
  belongs to an area when its `head_id` (from the balances endpoint) is in the covered set; a
  presentation line belongs when its `head_id` is in the set.
- **Validation of a CA-supplied map** (`templates_check`, and at load with a Spine
  configured): (1) syntax: `areas` is an object keyed by section codes of the template, each
  with a `heads` list of non-blank strings, no id listed twice anywhere; (2) existence: every
  listed id is a head of the live tree (unknown ids are refused by name); (3) no overlap after
  expansion: the covered sets of any two areas are disjoint, so a listed descendant of another
  area's listed ancestor is refused by name, as is the same id in two areas; (4) coverage
  report: mappable heads in no area are listed, not refused, since the firm may leave an area
  to a hand-made paper. Without a configured Spine the command runs (1) only and says the
  tree checks were skipped; at load without a Spine the map is accepted syntactically and
  the tree checks run on first use.
- **Communication of a missing map**: the Binder screen's Spine-papers card says "no area map
  for template <name>; see TEMPLATE_AUTHORING item 1" and offers no generation; the
  Spine-papers status endpoint returns the unmapped areas and unassigned heads; the template
  check prints them; the completeness view shows any required lead schedule as missing.

### 12.7 Adjustment chain: as served, no arithmetic

Confirmed against `oak_spine` (read-only): `GET …/adjustments` returns every adjustment with
`kind` (reclass, correction), `status` (**proposed, accepted, refused**: all three are
listed and kept), narration, `working_paper_ref`, `finding_ref`, proposer, decider, decision
note, and lines with ledger, head, dr and cr; `GET …/uncorrected` returns the misstatements
with measure and profit effect, the gross aggregate, performance materiality with its source,
the headroom and the gate state, every amount a string the Spine produced. The Binder stores
both answers verbatim in the provenance block, renders them into markdown line by line, and
performs **no sum, net, rounding or comparison**: totals, aggregate, headroom and gate state
are the Spine's strings. The same rule holds for the lead schedules (3.2): per-head totals are
the balances endpoint's own. This mirrors CAF's D30.

### 12.8 Test coverage added to §7

- **Several binders on one Spine version**: two binders linked to the same locked version each
  generate area D; both succeed; the run ids differ by binder; the generation rows and papers
  are distinct.
- **Duplicate generation requests**: the same area on the same unchanged version is refused as
  "one paper per run" naming the existing paper; no second paper or row; the response is the
  same on every repeat.
- **Zero figures and absent figures**: a head whose ledgers the double serves at `"0.00"`
  renders `"0.00"` verbatim; a head with no ledger entry renders the sentence naming the
  version and head and the presentation figure as served, and renders "no figure served"
  when the double serves `null`; the words "nil" and "0" never appear unless the double
  served them. An unmapped area is listed as "no map" and, when required by the template,
  as a missing required paper.
- **Regeneration history**: generate, prepare, review, sign off; re-link to another version;
  status says stale; regenerate; the paper is a draft with a second generation row; versions 1–3
  keep their bodies and hashes with the first row embedded; prepare writes version 4 with the
  second row; FS-line references follow the new version's heads. On an assembled binder the
  regenerate action is refused with 409 and nothing changes.
- **Archive reproducibility**: assemble and produce twice with the Spine up, then with it down
  and timing out; every `versions/NNNN.json` and `cross_references.json` member is
  byte-identical across the runs; every version's `content_hash` recomputes from its body; the
  manifest's hash recomputes from the manifest; `paper.json` says `generated_by: spine`.
- **No arithmetic**: every figure in the markdown `result` is a verbatim string from the
  double's payload; a test mutates one figure in the double and asserts the rendered paper
  changes only where the double did.
- **Outside intake still refuses `source = "spine"`** over HTTP.

## 13. Approval map (superseded by §15)

No further senior or chartered-accountant decision will be available. Every item below is
settled in §15 with a conservative default consistent with the specification; the items that
needed data rather than a decision (the area map, area names, required papers, wording) are
recorded there as **limitations**: configurable, shipped empty, never invented.

| Was to be decided by | Items | Now |
|---|---|---|
| Specification, no decision | one lead schedule per area; ties to the Spine; working papers beneath; the chain signs it off; four blockers; nothing deleted after assembly; conclusion before sign-off | unchanged |
| Technical | 1, 2, 4, 6, 9, 10, 12, 13, 14, 15 | decided, §15 |
| Senior | 3, 7, 8, 11 | decided by default, §15 |
| Chartered accountant | area map and names; wording; required lead schedules | limitations, §15 |

## 14. Consistency revision — 31 October 2026

Three inconsistencies found in review, fixed in the sections named:

1. **Post-assembly regeneration removed from Stage E** (decision 15). §3.5 no longer describes
   an amendment-style regeneration; §5 drops the amendment reason from the regenerate service
   and endpoint, which refuse an assembled binder with 409, and makes the stale blocker
   conditional on decision 8(b); §6 drops the post-assembly reason field from the stale banner;
   §7 and §12.8 test the refusal instead of the amendment; §1's reading of §3F, decision 6 and
   step E4 in §10 say the same. The Pass 1 amendment path required
   by spec §3F and §8.4 is untouched and still applies to a Spine paper's unlocked fields and
   attachments after assembly.
2. **Area map prefixes defined** (§3.4, §12.6). Head ids only, spelled as the Spine's tree
   spells them; no string-prefix matching; a listed head covers itself and its descendants by
   the tree's parent links; validation in four numbered steps, with the no-overlap check run
   after expansion. No mapping is shipped.
   *Corrected later the same day (item 5): the earlier parenthesis in §3.4, that a parent id
   is the id before the last dot, was an assumption about the Spine's internal construction
   and is withdrawn.*
3. **Nil figures distinguished** (§12.1, §12.8, decision 13). An explicit `"0.00"` from the
   Spine is quoted as served; a head with no ledger entry is described as exactly that, with the
   presentation figure as served or "no figure served"; the Binder never writes a zero or "nil"
   the Spine did not serve.
4. **Residual first-draft wording aligned** (§3.1, §3.2, §3.5, §3.6, §3.7, §6, §8): the
   lead-schedule row now says every mapped area; §3.2 and the §8 risk row follow decision 5
   (no placeholder wording, fields not locked); §3.5's unlocked row is marked as moot under
   decision 1(a); §3.6 carries the per-binder run id of decision 14; §3.7 and §6 make the
   stale blocker conditional on the senior's decision 8(b).
5. **Tree relationships from the Spine only** (§2, §3.2, §3.4, §12.6). Parent–child
   relationships between Schedule III heads are read exclusively from the explicit `parent`
   field in the `GET /api/tree` response, which also lists heads "parents before children".
   The Binder derives nothing from an id's dots or depth, and keeps the Spine's own serving
   order for heads and ledgers rather than computing a "tree order" of its own.

## 15. Decisions taken to proceed independently — 31 October 2026

*As built (1 Nov 2026), refusals follow the Binder's error conventions: 409 for a state the
binder is in (not open, not linked, version not locked) and for one paper per run, a reference
in use or nothing left to generate; 503 for no Spine or one that cannot answer; 404 for a
version the Spine no longer has (the Stage B convention); 422 for an area-map problem, an
unmapped area, an unknown area code or a hand-made paper offered for regeneration.*

No further senior or chartered-accountant input is available; the Binder is built from the
original specification alone. Each decision below is the most conservative reading of the
specification's words, with its reason. Each is also recorded in `docs/DECISIONS_PENDING.md`
as an assumption. Nothing that needs audit knowledge or firm data is invented: those items are
limitations, listed at the end.

| # | Decision | Reason |
|---|---|---|
| 1 | Lead schedules and the adjustment chain are generated **only from a locked Spine version** | a locked version has a hash and never changes (CAF D25), so provenance is verifiable for ever; D29 already blocks assembly on an unlocked version, so an unlocked generation could never be assembled |
| 2 | Lead schedule reference is **`<area>-L`**; a template may rename it later | §3B needs a stable, never-reused reference; `-L` collides with no spec-named paper and reads as "lead" |
| 3 | The adjustment-chain paper is **one paper in section W Completion, reference `W-ADJ`** | W is a spec section (§3A) and the chain, with the uncorrected schedule against performance materiality, belongs to completion; no new section or procedure is invented |
| 4 | Figures live in the **provenance block and as markdown tables in `result`** | §7: papers are "structured fields plus markdown"; the archive reads without the Binder; the version hash covers both |
| 5 | **`objective` and `procedure` are not locked and arrive empty**; the template has a slot for approved wording that ships empty | the Spine produces figures, not narrative; §2's only hard rule is the conclusion before sign-off; the Binder authors no audit text |
| 6 | Regeneration **rewrites the paper from the Spine as a new generation row** and returns it to draft; never a new paper | one lead schedule per area (§3A) with the whole history on file (§4 append-only) |
| 7 | `working_paper_ref` → cross-reference by **exact string match** to a paper reference of the binder; misses listed on the paper as information | never guess (your instruction); §3E references are facts, not inferences |
| 8 | A stale Spine paper is **information only, never a blocker** | §3F and §8.3 list four blockers; the Binder adds none |
| 9 | **No `spine.json`** archive member | redundant with version bodies and the manifest (§8.5, §8.6) |
| 10 | The materiality memo's Spine figures stay the **Materiality module's** to supply (D31) | §3C assigns the memo to that module; the Binder checks, it does not produce |
| 11 | **Any authenticated user may generate**; the existing preparer, reviewer and sign-off chain follows | §3D names the chain; the spec names no further gate on who starts a paper |
| 12 | Generation is **started by a person** on the Binder screen, never automatically on a link change | automatic generation would create papers nobody asked for and nobody reviewed |
| 13 | A mapped area whose heads have **no ledger entry still gets its lead schedule**, stating per head what the Spine answered; a served `"0.00"` is quoted as served; "no figure served" when none is served | §3A: per area; no figure is asserted without the Spine's evidence |
| 14 | Run id is **binder id / version id / Spine hash / area** | migration 0008's uniqueness is per source across binders (verified); several binders may share a version |
| 15 | **No post-assembly regeneration**; the Pass 1 amendment path (§3F) applies to a Spine paper's unlocked fields and attachments as to any paper | after assembly the link is frozen (D29) and a locked version cannot change, so nothing exists to regenerate from |

**Limitations: what cannot be populated without data the firm has not supplied**

| Item | State in Stage E | Effect, stated on screen and in the template check |
|---|---|---|
| Schedule III heads → areas D–T (TEMPLATE_AUTHORING item 1) | `areas` block in every shipped template is **empty**; the mechanism, expansion and validation (§3.4, §12.6) are built and tested with a test map | no lead schedule can be generated for any area of a shipped template until a map is entered; the Spine-papers card and status say "no area map for template <name>" |
| Area names D–T | placeholders "Financial statement area D" … remain | a generated lead schedule's title would carry the placeholder name until the template is edited |
| Required lead schedule per used area (item 2) | **not added** to any template | the completeness view cannot count a missing lead schedule; adding one would invent an audit requirement |
| Approved wording for objective and procedure | slot exists, **empty** | the preparer writes both before preparing, as on a hand-made paper |
| SA references on generated papers | none seeded, as for every paper | the field is available on the paper |

The adjustment-chain paper needs none of these and can be generated for any binder linked to
a locked version.
