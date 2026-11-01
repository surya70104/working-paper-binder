# Review-level policy request

**Working Paper Binder (SA 230) · questions for the firm on who may review at which level · 1 November 2026**

## Cover note

**Status (1 November 2026, D39): optional input.** The specification states no rule on who may
review at which level, so the Binder records and does not enforce; this stands unless the firm
answers below. Nothing waits for an answer.

This request comes from the Working Paper Binder project at `D:\WORKING PAPER BINDER`. It is not written on behalf of the firm or any engagement partner. It asks the firm to decide a policy the specification leaves open; nothing has been built on an assumed answer.

## What exists today

The specification (§3D) says: "Levels: preparer → senior → manager → partner → EQR, configurable per engagement", and (§3D, §8.9) that every sign-off records who, when and which version. The Binder implements this (architecture D33, migration 0009):

- Each binder carries an ordered list of review levels after the preparer, set while the binder is open and frozen for good once any level review is recorded.
- Each level review records the reviewer's identity, the time, the level and the paper version, append-only at the database.
- The paper becomes reviewed only after the last configured level; sign-off is unchanged.

What it does **not** do, by design and recorded as assumptions 24 and 25 in `docs/DECISIONS_PENDING.md`: it does not check **who** records a level. Identities are plain strings, taken from the development setting or from the header an authenticating proxy sets (D24). The Binder has no role model, no directory and no rule about one person acting at several levels or the preparer reviewing their own paper. The specification states no such rule, so none was invented.

## Why the firm must decide

Any enforcement would encode a firm policy: which people count as senior, manager, partner or EQR for an engagement, and what is forbidden. Building it on a guess would silently refuse legitimate reviews or permit ones the firm forbids. The questions below are what the Binder needs in order to build enforcement without inventing it. Every answer may be "no rule"; that is a valid policy and the Binder then stays as it is.

## Questions

Columns marked ★ need an answer for enforcement to be built at all; the others refine it.

| # | Question | Mandatory or optional | Answer |
|---|---|---|---|
| 1 | ★ Should the Binder enforce who may review at a given level at all, or only record who did (as now)? | Mandatory | |
| 2 | ★ If enforced, how does the Binder learn a person's role for an engagement: (a) a list of identities per level on each binder, entered with the levels; (b) an attribute the authenticating proxy sends with the identity; (c) a firm directory the Binder reads; (d) something else | Mandatory if 1 is "enforce" | |
| 3 | ★ May the preparer of a paper's current version record a level review on that paper? | Mandatory if 1 is "enforce" | |
| 4 | ★ May one person record more than one level on the same paper version? | Mandatory if 1 is "enforce" | |
| 5 | Must the person who records the EQR level be outside the engagement team, and if so how is "engagement team" known to the Binder? | Optional | |
| 6 | May the person who signs off be the same person who recorded the last level review? (Today sign-off is a separate step with no identity rule.) | Optional | |
| 7 | On a violation, should the Binder refuse the action, or record it and flag it for the partner? | Mandatory if 1 is "enforce" | |
| 8 | Should the role lists (if 2a) freeze with the levels at the first level review, or remain editable by someone in particular? | Optional | |
| 9 | Do any of these rules differ by engagement type (statutory, tax audit, bank branch, internal)? | Optional | |

## What the Binder would build on the answers

Only what the answers require, with no defaults of its own: for 2a, a per-binder list of identities per level alongside the existing levels, with the same freeze rule unless 8 says otherwise; for 2b, reading a named header attribute under `OAK_AUTH=header`; a refusal (409, by name) or a recorded flag per 7; tests for every rule. A migration would be needed for 2a; none for 2b. Nothing changes for binders whose levels are already frozen unless the firm says so.

## Completion

| Item | Entry |
|---|---|
| Answered by (name, role) | |
| Date | |
| Not decided yet — keep recording only (this is not an approval of any rule) | |
