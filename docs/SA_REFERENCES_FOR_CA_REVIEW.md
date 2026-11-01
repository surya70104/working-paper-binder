# SA references on required papers — for chartered accountant review

**Status: proposed, not confirmed. Nothing on this page is in the shipped templates.**

The specification gives every working paper an "SA reference(s)" field (§3B, `sa_refs[]` in
§4) but never maps a standard to a paper. Until 31 October 2026 the four index templates
seeded the required papers with the standard numbers below. They came from general knowledge
of the Standards on Auditing, not from the specification, and the differences between
engagement types were not explained in the files. They were removed from the templates on
31 October 2026 so that nothing unconfirmed ships; the field itself is unchanged and a
preparer can enter references on any paper.

## What was seeded, by template

| Required paper | Statutory | Bank branch | Tax audit | Internal |
|---|---|---|---|---|
| A-1 Acceptance and continuance | SA 210, SA 220 | SA 210, SA 220 | SA 210, SA 220 | none |
| B-1 Planning and risk assessment | SA 300, SA 315 | SA 300, SA 315 | SA 300, SA 315 | none |
| C-1 Materiality memo | SA 320 | SA 320 | SA 320 | none |
| W-1 Completion | none | none | none | none |
| X-1 Report and opinion | SA 700 | SA 700 | none | none |
| Z-1 Engagement quality review | SA 220 | SA 220 | SA 220 | none |

The unexplained differences: the tax audit template carried no SA 700 on its report paper,
and the internal audit template carried no references at all. Both may be right (a tax audit
report is not an SA 700 opinion; an internal audit is not an SA engagement), but no one
confirmed them.

## What the chartered accountant is asked to decide

1. For each engagement type, which Standards on Auditing (or other standards, guidance notes
   or Act provisions) each required paper should carry; the template's list prefills the
   new-paper form when the paper is created from the index.
2. Whether the tax audit and internal audit templates should carry SA references at all, or
   references to other frameworks.
3. Whether W-1 Completion should carry a reference.

## How the decision is applied

Enter the confirmed references in the `sa_refs` list of each required paper in the template
file, run `python -m oak_binder.templates_check` from `backend\`, and follow
`docs\TEMPLATE_AUTHORING.md`. Papers already created on existing binders keep whatever
references they hold. The template's references prefill the new-paper form when a missing
paper is created from the index, where the preparer may edit them before creating, so the
template affects papers created from the index afterwards.
