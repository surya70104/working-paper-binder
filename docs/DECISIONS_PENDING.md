# Decisions pending — Working Paper Binder, Pass 1

**31 October 2026.** Pass 1 is built and verified. These are the points the specification
leaves to people. Each names who decides, what the Binder does meanwhile, and where the
detail is. Nothing here is implemented as if decided.

## Chartered accountant

| # | Decision | Meanwhile | Detail |
|---|---|---|---|
| 1 | Names for financial statement areas D–T, per engagement type | Generic names; templates marked draft; Binders screen warns | `docs\TEMPLATE_AUTHORING.md` |
| 2 | Required papers per engagement type, including a lead schedule per used area | Six required papers, one per spec-named section | same |
| 3 | The five derived titles (A-1, B-1, W-1, X-1, Z-1); only "Materiality memo" is the spec's wording | Used as placeholders | same |
| 4 | SA references on required papers | None seeded; field available on every paper | `docs\SA_REFERENCES_FOR_CA_REVIEW.md` |

## Senior (engagement lead)

| # | Decision | Meanwhile | Detail |
|---|---|---|---|
| 5 | "Superseded paper" (spec §3E): is it a target paper amended after the reference was made, and should it block assembly or only warn? | Surfaced as information on the reference and in the archive; never blocks | D26 addendum in `docs\architecture.md` |
| 6 | Cross-reference `direction` read as `to` / `from` (this paper refers to the target / the target refers to this paper) | In use; both directions clickable | D26 |
| 7 | Access log reading of "opened": any read of an assembled or purged file's content, identity required, binder list not logged | In use | D25 |

## Firm (deployment and operations)

| # | Decision | Meanwhile | Detail |
|---|---|---|---|
| 8 | OAuth consent screen to "In production" (a Testing-status refresh token expires after seven days) | Development use only | README "Google Drive vault", D27 |
| 9 | Custody of `backend\secrets`: under the full `drive` scope the token reaches the whole Google account | Folder git-ignored, owner-only where the OS allows | D27 |
| 10 | Keep or remove the local attachment copies now in Drive | Kept | D27 |
| 11 | Authenticating reverse proxy, identity provider, `OAK_TRUSTED_PROXIES`, TLS | `OAK_AUTH=dev` in development; production refuses it | README "Identity", D24 |
| 12 | Applying migrations 0001–0005 to the live `oak_binder` at go-live | Never touched: 0 tables | README "Database" |

## Pass 2 (spec §6), not decisions

Checking cross-references to FS lines, lead schedules from the Spine, the cross-reference map
screen, generated papers, discussions and departures logs, configurable review levels,
WorkMind papers.
