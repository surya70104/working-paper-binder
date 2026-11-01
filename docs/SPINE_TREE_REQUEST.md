# Request to the Financial Spine operator

**Working Paper Binder (SA 230) · request for a Schedule III tree export · 1 November 2026**

**To:** the operator of the Financial Spine (the OAK Audit sibling module)
**From:** the Working Paper Binder project, `D:\WORKING PAPER BINDER`

**What is requested.** One export of the Financial Spine's Schedule III head tree: the full response of `GET /api/tree`, saved as a JSON file, unaltered. The Binder reads this endpoint read-only; it never writes to the Spine.

**Why.** The Binder's index templates map Schedule III heads to financial statement areas so that lead schedules can be generated from a locked Spine version. The chartered accountant chooses the head ids from this tree, and the Binder's check command validates a template against it: every listed id must exist, and no head may fall under two areas after expansion through the tree's `parent` field. Without the export, only the syntax of a map can be checked.

**What the export must contain.** The response exactly as served: a JSON object with a `heads` list, each head carrying `id`, `parent` (absent or null for a root), `label`, `side`, `depth` and `mappable`, in the Spine's own order (parents before children), plus any top-level fields the Spine includes. Please do not edit, filter or reformat it. The Binder treats a head without `mappable` as not mappable, so a filtered file would distort its coverage report.

**Please also state.**

| Item | Entry |
|---|---|
| Date and time the export was taken | |
| Spine build or version it came from | |
| Whether the tree is expected to change before the templates go live | |
| Alternatively, whether the Binder may read the live tree, and at which base URL (`OAK_SPINE_URL`); the Binder would send GET requests only | |

**Where it goes.** The file is used by `python -m oak_binder.templates_check --tree <file>` in the Binder project and attached to Part D of the template content request (`docs/TEMPLATE_CONTENT_REQUEST.md`). It contains no figures, engagement data or credentials, only the head structure.
