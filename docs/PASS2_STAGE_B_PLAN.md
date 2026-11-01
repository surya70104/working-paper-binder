# Pass 2 Stage B plan — the Spine link

**31 October 2026. Built the same day as D29 with the six decisions below confirmed; migration 0007 applied to `oak_binder_test`.** Source for the Spine
facts: a read-only reading of `D:\CAF\backend\src\oak_spine` (API modules, the version
store, the presentation module, settings, application factory) and its frontend
configuration. Nothing in CAF was changed.

## 1. What the Financial Spine exposes (read-only inspection)

The Spine is a FastAPI service, `oak_spine`, under `/api`, run with
`uvicorn oak_spine.main:app` on port 8000 (its frontend proxies `/api` to
`http://127.0.0.1:8000`). It has **no authentication**: the acting user comes from its own
`OAK_DEV_USER` setting, exactly as the Binder's dev mode. It has no CORS middleware, which
does not matter for a server-to-server call. Errors are JSON: `{"detail": {"code": "…",
"message": "…"}}`, with 404 `engagement.not_found` / `spine_version.not_found`, 409
`spine.locked`, 422 refusals, 503 `database.unavailable`.

Endpoints the Binder needs, all `GET`, all read-only:

| Endpoint | Returns | Fields the Binder uses |
|---|---|---|
| `/api/health` | `{status, version}` | reachability |
| `/api/engagements/{id}` | `{id, entity_id, financial_year_end, label, created_at}` | existence, label, year end |
| `/api/engagements/{id}/spine-versions` | list, newest first, of version records | choosing a version |
| `/api/spine-versions/{id}` | one version record with adjustment counts | lock state, hash |
| `/api/spine-versions/{id}/presentation` | Schedule III presentation: `status` (`ready`/`blocked`), `is_locked`, `provisional`, `hash`, `balance_sheet.lines[]`, `profit_and_loss.lines[]`, `notes`, `rounding` | the financial-statement lines (Stage C) |
| `/api/spine-versions/{id}/balances` | the chain: ledgers with unadjusted, reclass, correction and adjusted balances, grouped totals, `hash` | lead schedules (Stage E) |
| `/api/spine-versions/{id}/adjustments?status=` | adjustments with lines, `working_paper_ref`, status | the adjustment chain paper (Stage E) |
| `/api/spine-versions/{id}/uncorrected` | uncorrected misstatements, aggregate, gate | the adjustment chain paper (Stage E) |

**The version record** (`version_json`): `version_id`, `engagement_id`, `entity_id`,
`base_import_id`, `version_no`, `label`, `supersedes_id`, `supersede_reason`,
`prior_version_id`, `performance_materiality` (decimal string or null), `pm_source`,
`is_locked`, `locked_by`, `locked_at`, `hash`, `tree_version`, `snapshot_sha256`,
`created_by`, `created_at`, `adjustments` ({proposed, accepted, refused} or null).

**A presentation line** (`_line`): `head_id` (the stable Schedule III head identifier),
`parent`, `depth`, `label`, `item`, `note`, `side`, `basis`, `mappable`, `current`,
`prior`, `signed_current`, `signed_prior`, `rounded_current`, `rounded_prior`,
`has_figures`. Computed subtotal lines carry `id` instead of `head_id`. The presentation is
`provisional` until the version is locked, and `blocked` while any ledger with a balance has
no head.

Two Spine facts shape the design: a **locked version is immutable and carries a hash**
(after a lock, balances come from stored rows and every read answers the same); an unlocked
version is recomputed on each read. And the Spine's own notes say an adjustment names a
working paper "but nothing exists to open to": the Binder is the other end of that link,
which Stage E uses.

## 2. How a binder links to the Spine

- **One binder, one engagement, one version.** Two nullable columns on `binder`:
  `spine_engagement_id` and `spine_version_id`, both UUIDs the Spine issued. Nullable, so
  every existing binder is unaffected and a binder without a Spine stays as it is.
- **Set through `PATCH /api/binders/{id}`** with either or both. The Binder verifies against
  the Spine before saving: the engagement exists; the version exists and belongs to that
  engagement; and (decision 1 below) whether it must be locked.
- **While the binder is open the link may change** (the team may move to a newer locked
  version). **After assembly it is frozen**: changing it is refused like any other
  post-assembly change, since the manifest will record it (see next point) and Stage C's
  FS-line checks depend on it.
- **The manifest records the link** once set: `spine: {engagement_id, version_id,
  version_hash, locked_at}`, keyed only when present, the same device as the logs, so
  already-assembled files keep their hash. Re-assembly after a link change therefore follows
  automatically.
- **Nothing in the Binder's database copies Spine data.** Figures are read when needed and
  the version hash recorded at assembly is what proves which Spine state the file tied to.

## 3. The read-only HTTP client

`services/spine_client.py`, the same shape as the Drive adapter: a small class over an
`httpx.Client`, a protocol for the test double, typed results.

```
class SpineClient:
    health() -> SpineHealth
    engagement(engagement_id) -> SpineEngagement            # 404 → NotFound
    versions(engagement_id) -> list[SpineVersion]
    version(version_id) -> SpineVersion                      # 404 → NotFound
    presentation(version_id) -> SpinePresentation            # Stage C
    balances(version_id) -> dict                              # Stage E
    adjustments(version_id, status=None) -> list[dict]        # Stage E
    uncorrected(version_id) -> dict                           # Stage E
```

- Built from settings by `build_spine_client(settings)`; returns `None` when
  `OAK_SPINE_URL` is unset, and every Spine-dependent feature then reports "no Spine
  configured" rather than failing.
- Every call is a `GET`; the class has no method that can write. A test asserts the double
  saw no non-GET request.
- Results are small frozen dataclasses with the fields the Binder uses; unknown fields are
  ignored, so Spine additions do not break the Binder.

## 4. Authentication, timeouts, errors

- **Authentication**: the Spine has none today. Design for an optional bearer credential,
  `OAK_SPINE_CREDENTIAL`, sent as `Authorization: Bearer …` when set, never logged; empty by
  default. When the Spine gains authentication the setting is already there.
- **Transport**: `OAK_SPINE_URL` must be `http://` or `https://` with a host; production
  requires `https://` unless the host is loopback (decision 2). Timeout 10 s connect, 30 s
  read; the presentation and balances of a large version are the slowest calls.
- **Errors**, mapped once in the client and nowhere else:
  - transport fault, timeout, 5xx, 429 → `StoreUnavailable`-style 503, named
    `SpineUnavailable`, with the operation and status, never the URL's credential;
  - 404 → `NotFound` with the Spine's `code` ("No engagement … exists");
  - 401/403 → `SpineUnavailable` saying the Spine refused the credential;
  - any other 4xx → `Invalid` with the Spine's message;
  - a body that is not the expected JSON → `SpineUnavailable` ("unexpected answer").
- **Retries**: none in Stage B. A read that fails is reported; the user retries. (A single
  retry on connect errors can be added later without changing callers.)
- **Isolation**: the Binder never imports Spine code or reads its database; the only coupling
  is the HTTP contract above, pinned by the test double's fixtures, which are copied from
  the Spine's actual response shapes.

## 5. Migration 0007 (additive; not run until approved)

```
ALTER TABLE binder ADD COLUMN spine_engagement_id uuid NULL;
ALTER TABLE binder ADD COLUMN spine_version_id    uuid NULL;
ALTER TABLE binder ADD CONSTRAINT ck_binder_spine_version_needs_engagement
    CHECK (spine_version_id IS NULL OR spine_engagement_id IS NOT NULL);
```

No foreign keys (the ids live in another database), no index (one binder per engagement
is a Spine-side fact, not enforced here; decision 3), no default. Downgrade drops the
constraint and the two columns. Migrations 0001–0006 untouched. The application role's
existing `UPDATE` on `binder` covers it. Tests: the offline SQL render (`test_migration_sql`)
gains the two columns and the constraint; `test_models` adds them to the binder's field set.

## 6. API and screen

- `PATCH /api/binders/{id}` accepts `spine_engagement_id` and `spine_version_id` (nullable;
  both may be cleared while open). Verified against the Spine before saving.
- `GET /api/binders/{id}/spine`: the link plus a live read of the Spine: engagement label and
  year end, version label, `is_locked`, `locked_at`, `hash`, adjustment counts, and
  `reachable: false` with the reason when the Spine cannot be read. Access-logged on an
  assembled binder like every other read.
- `GET /api/spine/engagements/{id}/versions`: a pass-through list so the screen can offer
  the versions to choose from.
- Binder screen: a "Financial Spine" card showing the link, with a picker (engagement id
  typed, versions listed from the Spine) while the binder is open.
- Assembly screen: the Spine line in the manifest table when present.

## 7. Test cases against a mock Spine (`tests/fake_spine.py`, `httpx.MockTransport`)

The double serves fixtures shaped exactly like the Spine's responses, records every call,
and can be told to answer 404, 503, 401, a timeout, or a non-JSON body.

Client:
1. Each method hits the documented path with `GET` only; no other verb is ever sent.
2. 404 → `NotFound` carrying the Spine's message; 5xx and transport faults → 503 with no
   credential in the text; 401 → "refused the credential"; non-JSON → "unexpected answer".
3. The bearer header is sent only when `OAK_SPINE_CREDENTIAL` is set, and its value never
   appears in any error or `repr`.
4. `build_spine_client` returns `None` without `OAK_SPINE_URL`; settings refuse a URL
   without scheme or host; production refuses plain `http://` to a non-loopback host.

Link (API, `oak_binder_test`):
5. Setting the engagement alone, then the version; the version must belong to the
   engagement; an unknown id is a 404 named by the Spine; the constraint
   `version needs engagement` holds at the database.
6. Decision 1 behaviour: an unlocked version is refused, or accepted with a warning.
7. The link cannot change after assembly (409), can be cleared while open.
8. `GET /spine` reports `reachable: false` and the reason when the double answers 503, and
   the binder is otherwise usable; the read is access-logged on an assembled binder.
9. The manifest carries `spine` only when a link exists; a binder assembled without a link
   keeps its recorded hash (the demo binder case); linking after assembly is refused, so no
   hash moves without re-assembly.
10. Nothing in Pass 1 changes: the existing suites run unchanged.

Screen (vitest):
11. The Spine card shows the link and the version's lock state; the picker lists versions
    from the mocked endpoint; the card says "no Spine configured" when the API says so;
    an assembled binder shows the link read-only.

## 8. Decisions needed before coding

1. **Must the linked version be locked?** Recommendation: a binder may link to an unlocked
   version while it is open (the team works alongside the Spine), but **assembly requires a
   locked version**, as a named blocker, because an unlocked version's figures and FS lines
   can still change under the file. Alternative: refuse unlocked versions at link time.
2. **Transport in production**: require `https://` for a non-loopback Spine host? Recommended
   yes.
3. **One binder per Spine engagement?** The Binder already enforces one binder per
   engagement name; whether two binders may point at one Spine engagement is a firm
   question. Recommendation: allow, no constraint, since the Spine does not care and a
   re-opened engagement may legitimately get a second binder.
4. **Which process authenticates?** Today none. Confirm the Binder may call the Spine over
   the loopback interface on the same host in development, and that an eventual Spine
   credential will be a bearer token (so `OAK_SPINE_CREDENTIAL` is the right shape).
5. **Clearing the link.** Allowed while open (recommended), never after assembly.
6. **The `to_fs_line` field in Stage C** will hold the Spine's `head_id` (stable) rather than
   free text once a binder is linked; existing free-text lines stay as they are, flagged
   "not checked". Confirm this reading now so Stage B's client exposes `head_id` and `label`.
