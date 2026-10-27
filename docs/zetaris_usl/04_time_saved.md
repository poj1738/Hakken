# 2a — How the USL saved time versus a hand-coded approach

## The comparison we actually ran (bonus)

We took one USL question — *for each high-risk class, how many medicine lines and patients
does each source hold?* — and answered it a second time by hand, in Python, straight from the
raw sources (`datasvc`), with no Zetaris at all:
[`scripts/handcoded_comparison.py`](../../scripts/handcoded_comparison.py). It is a fair
hand-coded version: it fetches all six sources, maps each silo's own field names, resolves
three coding systems plus a brand fallback, matches ATC codes to APINCHS by longest prefix, and
aggregates. Its size is measured from the file, between `BEGIN`/`END` markers.

<!-- BEGIN generated -->
<sub>Measured 2026-10-27T07:55:43+00:00 UTC by `scripts/handcoded_comparison.py` · [`results/2a_handcoded_comparison.json`](results/2a_handcoded_comparison.json)</sub>

**Question:** Lines and distinct patient IDs per APINCHS high-risk class and source.

|  | USL | Hand-coded |
|---|---|---|
| Code to answer this question | 1 SQL statement | 51 lines of Python |
| One-time setup | 43 lines of activation SQL (reused by every query) | none (but nothing is reused) |
| Manual mapping steps at question time | 0 | 11 |
| Runtime | 19.11 s | 0.34 s |
| Result | 15 rows | 15 rows |
| Identical results | yes |  |

**The hand-coder's mapping steps** (each a fact about the sources that someone must know and keep current):

1. Know each silo's endpoint and envelope ({'records': [...]}) -- 6 sources
2. Map each silo's patient-ID field: emr.mrn, gp.gp_pid, pharmacy.cust_no, patient.intake_id
3. Map each silo's medicine-code field: emr.amt_mp_code, gp.amt_code, pharmacy.pbs_code
4. Know EMR codes are AMT medicinal products (lexicon.amt_mp)
5. Know GP codes are AMT medicinal product PACKS (lexicon.amt_mpp), not amt_mp
6. Know pharmacy codes are PBS item codes (lexicon.pbs_code), and that pbs_code is not unique
7. Know private scripts carry no PBS code and must resolve by brand, case-insensitively
8. Know patient interview lines carry no code and cannot be resolved by code
9. Build one lookup per coding system from the lexicon
10. Match ATC to APINCHS by the LONGEST matching prefix
11. Aggregate lines and distinct patient IDs per (class, source)
<!-- END generated -->

## What the numbers say

**The USL saved the mapping, not the arithmetic.** Answering this one question by hand is
not hard. What is hard is the eleven things you must *know* to answer it correctly, and seven of
them are facts about the sources that nobody writes down: that the GP codes AMT **packs** while
the hospital codes AMT **products**; that a PBS code is not unique in the lexicon; that private
scripts carry no PBS code at all and only match by brand; that the longest ATC prefix wins. Get
one wrong and the answer is quietly wrong — the GP-pack one alone would drop every GP line from
the result without an error.

In the USL those facts are written **once**, in one activation query
([`07_usl_activate_medication_statement.sql`](../../data/zetaris/usl/07_usl_activate_medication_statement.sql)),
and every later question is a single `SELECT` against `medication_statement`. Our own app shows
the cost of not having that: MedTrace's normaliser
([`normalise.py`](../../app/domain/packs/medtrace/normalise.py)) carries the same mapping
knowledge in Python, separately from the USL. <!-- TEAM: add how long that took us, if we want to claim it -->

**Where the hand-coded approach still wins, today: speed at this size.** On ~14,000 rows of
local JSON, plain Python answered in well under a second; the USL query took about 19 seconds,
because it re-reads the REST-backed views through `explode()` on every query and we have not
materialised the USL. We did not measure `MATERIALIZE USL` (no storage target was configured,
and the Zetaris reference repo lists it as untested too). For an interactive agent, that
latency matters — which is why MedTrace's per-run queries still read the cached SchemaStore
views, and why it is the first item in [06](06_killer_requirement.md).

## Time saved, honestly framed

| | Hand-coded | USL |
|---|---|---|
| First question | write the mapping (≈ the 51 lines above) | write the activation (43 lines of SQL) — about the same |
| Each *new* question across the sources | re-apply or re-import all 11 mapping steps | one `SELECT` |
| A source changes its coding (e.g. GP moves to AMT products) | find every script that assumed packs | change one `CASE` in one activation query |
| Data-quality checks | write and schedule each check | `REGISTER DQ` once; `RUN DQ` returns counts, `SHOW DQ INVALID RECORD` the rows |

The saving is in the second question onwards, and in not getting the mapping wrong.
