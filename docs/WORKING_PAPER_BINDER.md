# Working Paper Binder — SA 230

**Module spec · OAK Audit · 28 October 2026**
Whhoohh Path LLP

---

## 1. What it is

The outlet. Materiality, Sampling and Analytical Review already produce output that nothing
catches; the Financial Spine will produce more. The Binder is where all of it lands, gets
reviewed, gets signed off, and gets locked.

**One sentence:** every figure in the audit report traces to a working paper, every working paper
names who prepared it and who reviewed it, and the whole file freezes 60 days after the report
date and survives seven years.

---

## 2. What SA 230 actually requires

Build to these, not to a feature list. Each becomes a testable requirement.

| Requirement | What the module must do |
|---|---|
| Sufficient record for an **experienced auditor with no previous connection** to understand the nature, timing and extent of procedures, the results, and the conclusions | The WP template forces objective → procedure → result → conclusion. A WP missing a conclusion cannot be signed off. |
| **Who performed the work and when; who reviewed it and when** | Preparer and reviewer are fields, captured at sign-off, not typed. |
| **Identifying characteristics of items tested** | The sample record carries invoice numbers, voucher refs, dates — not "20 items selected". |
| **Significant matters, discussions, and with whom** | A discussions log per engagement, including TCWG, with date and participants. |
| **Departures from a relevant requirement** | A departure record: which requirement, why, and the alternative procedure performed. |
| **Assembly of the final file within 60 days** of the report date | A countdown, an Assemble action, and a hard lock. |
| **Retention not shorter than 7 years** from the report date | A retention clock, native-format storage, and purge only after it expires. |
| **No deletion before retention ends; post-assembly changes recorded** | After assembly nothing is deleted. Changes create a new version with reason, author and date. |

**Also binding:** the NFRA audit-file circular of 16 December 2025 — 60-day assembly, seven-year
retention **in native format**, and production within **7 days** of a request. That last one is a
build requirement: there must be a one-action export of the complete file.

Firm-level retention policy sits under **SQC 1**. Not SQM 1 — ICAI deferred SQM 1 and SQM 2
indefinitely on 31 March 2026.

---

## 3. Feature set

### A · File structure
- Index template per engagement type — statutory, tax audit, bank branch, internal.
- Standard sections: **A** acceptance · **B** planning and risk · **C** materiality · **D–T**
  financial statement areas · **W** completion · **X** report and opinion · **Z** EQR.
- Lead schedule per area, tying to the Financial Spine, with the WPs beneath it.
- **Completeness view** — which required papers are missing, per section, as a blocking count.

### B · The working paper
Fields: reference (stable, never reused) · title · section · SA reference(s) · objective ·
procedure performed · population and sample · result · conclusion · prepared by + date ·
reviewed by + date · status · attachments · cross-references in and out.

Status: `draft → prepared → in review → reviewed → signed off`.

### C · Papers that generate themselves
The differentiator. A paper produced by a module arrives complete, with its inputs and its
citations, and nobody retypes anything.

| Source | Paper it produces |
|---|---|
| Materiality | The materiality memo, with the benchmark, the band and the figures from the spine |
| Sampling | The sampling paper, **with the formula and the seed printed on it** |
| Analytical Review | The variance paper, current year against prior, with the thresholds used |
| Financial Spine | Every lead schedule, and the adjustment chain |
| WorkMind agent runs | One paper per accepted run, carrying the run id, the inputs and the source-row citations |

### D · Review
- **Review notes**: raised → assigned → responded → cleared.
- **A paper with an open review note cannot be signed off.** Hard rule.
- Levels: preparer → senior → manager → partner → EQR, configurable per engagement.
- Every sign-off records who, when, and which version of the paper.

### E · Cross-referencing
- Financial statement line → lead schedule → working paper → source document, clickable in both
  directions.
- **Broken-reference detection** — a reference pointing at a deleted or superseded paper is
  surfaced, and blocks assembly.

### F · Assembly
- Assembly deadline = report date + 60 days, shown as a countdown from the day the report is
  dated.
- **Assemble** freezes every paper, computes a file hash, and writes a manifest listing every
  paper with its own hash.
- Blocked by: unsigned papers, open review notes, broken references, missing required papers.
- After assembly: nothing is deleted. A change creates a new version carrying reason, author and
  date, and the manifest records the amendment.

### G · Retention and production
- Seven-year clock from the report date, per engagement.
- **Native format** — the original xlsx, pdf and csv, not a flattened print.
- **Produce file** — one action, full file plus manifest plus the audit trail, as a single
  archive. This is the 7-day NFRA obligation, and it should take seven seconds.
- Purge only after retention expires, and the purge writes its own record.

### H · Records that are easy to forget
- **Discussions log** — significant matters, with whom, when. Including TCWG.
- **Departures log** — requirement, reason, alternative procedure.
- **Access log** — who opened the file after assembly.

---

## 4. Data model

```
binder            engagement · template · report_date · assembly_due · assembled_at
                  · assembly_hash · retention_until · state

wp                binder · ref · section · title · sa_refs[] · objective · procedure
                  · result · conclusion · status · current_version

wp_version        wp · version · body · prepared_by · prepared_at · reviewed_by
                  · reviewed_at · content_hash · amendment_reason   — immutable

wp_attachment     wp_version · vault_doc_id · identifying_chars · sha256

xref              from_wp · to_wp | to_fs_line | to_vault_doc · direction

review_note       wp · raised_by · assigned_to · text · state · responded_at · cleared_by

discussion        binder · date · participants[] · matter · outcome
departure         binder · requirement · reason · alternative_procedure · approved_by
access_log        binder · user · action · at        — post-assembly only
```

**Append-only:** `wp_version`, `review_note`, `discussion`, `departure`, `access_log`. Updates and
deletes fail at the database.

---

## 5. Screens

1. **Binder** — the index tree, completeness per section, assembly countdown.
2. **Working paper** — the paper, its versions, attachments, cross-references, sign-off.
3. **Review notes** — what is open, raised by whom, assigned to whom, blocking what.
4. **Cross-reference map** — FS line to paper to document, with broken links flagged.
5. **Assembly & retention** — the blockers, the Assemble action, the manifest, Produce file.

---

## 6. Build it in two passes

**Pass 1 — SA 230 compliant, 7 person-weeks.** Index and templates · the WP record with
preparer/reviewer sign-off · attachments from the vault · completeness view · assembly with the
60-day clock and the lock · retention clock · produce-file export.

That is a defensible audit file. A firm can use it on a live engagement.

**Pass 2 — the rest, 8 person-weeks.** Review notes workflow · cross-reference map and broken-link
detection · generated papers from Materiality, Sampling, Analytical Review and the Spine · the
discussions and departures logs · WorkMind run papers.

**Total 15 pw.** Pass 1 alone is worth shipping; pass 2 is what makes it better than a folder.

---

## 7. Not in v1

- A rich document editor. Papers are structured fields plus markdown plus attachments. Anyone
  who wants Word can attach one.
- E-signature. Sign-off is an authenticated action with a timestamp, which is what SA 230 asks
  for.
- Group audit files across component auditors (SA 600). Separate module.
- Automatic drafting of conclusions. That is WorkMind, and it is gated.

---

## 8. Acceptance

1. A paper without a conclusion cannot be signed off.
2. A paper with an open review note cannot be signed off.
3. Assembly is blocked by unsigned papers, open notes, broken references or missing required papers — each named.
4. After assembly, a delete fails and an edit creates a new version with a reason.
5. The assembly manifest lists every paper with its hash, and re-computing the file hash reproduces it.
6. Produce-file returns the complete file in native formats plus the manifest, in one action.
7. The retention date is report date + 7 years, and purge before it fails.
8. A sampling paper generated by the Sampling module carries its formula and its seed.
9. Every sign-off records user, timestamp and paper version.
