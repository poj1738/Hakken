"""MedTrace domain pack -- medication reconciliation across four siloed systems.

Everything in this package is **pure**: no I/O, no model calls, no Zetaris, no
clock. Inputs are harmonised rows and reference data; outputs are findings.
That boundary is what makes the clinical logic testable against
`data/synthetic/ground_truth.json` instead of against a live stack.

Owner: Arpon (see `docs/PLAN_2026-10-24.md` section 1). Arnav's pipeline imports
these functions and never reimplements them; Anshu never touches this package.

Import from the modules directly, not from this file:

    from app.domain.packs.medtrace.types import SourceRow, FusedMed
    from app.domain.packs.medtrace.identity import link_identity
    from app.domain.packs.medtrace import queries

Module map (PLAN 2.5):

| module        | what it owns                                              |
|---------------|-----------------------------------------------------------|
| `types`       | every shared dataclass and enum. **Frozen shared file.**  |
| `queries`     | the vetted Lightning SQL templates Q_REF, Q0-Q4           |
| `parse`       | Zetaris envelope -> typed rows. The only place we cast.   |
| `identity`    | Fellegi-Sunter linkage, bands, lookalike guards           |
| `normalise`   | free text / codes -> one `MedStatement`                   |
| `coverage`    | which sources were found, and what absence means          |
| `supply`      | dispensing arithmetic: run-out, PDC                       |
| `fuse`        | trust-weighted resolution into the BPMH grid              |
| `detect`      | discrepancy detection                                     |
| `safety`      | APINCHS classification and the human-review gate          |
| `triage`      | ranking, and what is never flagged                        |
| `trust`       | the (source, attribute) priors seeded into H-MEM          |
"""
