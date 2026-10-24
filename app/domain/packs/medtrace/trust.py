"""Source-by-attribute trust priors, seeded into H-MEM (PLAN 2.5).

The insight these numbers encode: **no source is simply more reliable than
another.** Each knows a different thing.

- The **pharmacy** knows what was *handed over* -- exact brand, strength and
  form, with a date. It has no directions field at all (PLAN 2.2), so it is
  nearly mute on frequency.
- The **GP** knows what was *intended*, and holds it longest. The same longevity
  makes its "active" flag the main source of stale listings.
- The **patient** knows what they *actually swallow*, including the things no
  system records -- OTC, complementary, "half a tablet because it made me dizzy"
  -- and is the weakest source on names, strengths and formulations.
- The **EMR admission chart** is a transcription made under time pressure at the
  moment of admission. It is authoritative on route and on what the hospital is
  now giving, and it is precisely where omissions appear.

These are **priors, not measurements.** They are our clinical judgement, written
down so it can be argued with, and they are the seed H-MEM moves from as
pharmacists confirm and reject findings (`POST /feedback` -> helpful +0.05,
not_helpful -0.03, wrong -0.20). The generator plants *hidden* per-source
per-attribute error rates (PLAN 2.7) that these priors deliberately do not
match, so the learning curve in `scripts/eval.py` measures something real
instead of a value we pre-loaded with the answer.

The seven values marked `[PLAN 2.5]` are quoted verbatim from the plan so the
seed matches the agreed contract; the rest fill the grid out on the same
reasoning.
"""

from __future__ import annotations

#: Trust for a `(source, attribute)` pair we have no prior for. Deliberately
#: neutral: an unlisted pair should neither win nor lose a fusion contest, it
#: should make `fuse` abstain and ask.
DEFAULT_TRUST = 0.5

#: `(source, attribute) -> prior in 0..1`. Keys use `types.TrustAttribute`.
SOURCE_TRUST_PRIORS: dict[tuple[str, str], float] = {
    # -- Hospital EMR: the admission chart and the last discharge summary ------
    ("emr", "existence"): 0.65,
    ("emr", "daily_dose"): 0.70,
    ("emr", "frequency"): 0.80,   # the one source that writes bd/tds explicitly
    ("emr", "release"): 0.75,
    ("emr", "route"): 0.90,       # route is charted properly nowhere else
    ("emr", "strength"): 0.75,
    ("emr", "intended_dose"): 0.70,
    ("emr", "actually_taking"): 0.40,   # what is prescribed, not what is taken
    ("emr", "name"): 0.90,        # registration-grade demographics
    ("emr", "admission_chart"): 0.60,   # [PLAN 2.5] where omissions live
    # -- GP practice summary ---------------------------------------------------
    ("gp", "existence"): 0.60,    # [PLAN 2.5] stale listings
    ("gp", "daily_dose"): 0.70,
    ("gp", "frequency"): 0.70,
    ("gp", "release"): 0.60,
    ("gp", "route"): 0.50,
    ("gp", "strength"): 0.75,
    ("gp", "intended_dose"): 0.75,      # [PLAN 2.5] the prescriber's intent
    ("gp", "actually_taking"): 0.45,
    ("gp", "name"): 0.80,         # nicknames and previous surnames live here
    # -- Community pharmacy dispensing ----------------------------------------
    ("pharmacy", "existence"): 0.85,    # [PLAN 2.5] it was actually handed over
    ("pharmacy", "daily_dose"): 0.55,   # inferred from qty/days_supply, not stated
    ("pharmacy", "frequency"): 0.40,    # no directions field at all (PLAN 2.2)
    ("pharmacy", "release"): 0.85,      # brand + form is unambiguous
    ("pharmacy", "route"): 0.70,
    ("pharmacy", "strength"): 0.90,     # [PLAN 2.5]
    ("pharmacy", "intended_dose"): 0.50,
    ("pharmacy", "actually_taking"): 0.70,   # collecting it is behaviour, not ingestion
    ("pharmacy", "name"): 0.60,         # one free-text "SMITH, Margaret" field
    # -- Patient or carer interview -------------------------------------------
    ("patient", "existence"): 0.65,     # the only source for OTC and complementary
    ("patient", "daily_dose"): 0.40,
    ("patient", "frequency"): 0.45,
    ("patient", "release"): 0.20,       # nobody knows if their oxycodone is CR
    ("patient", "route"): 0.40,
    ("patient", "strength"): 0.30,
    ("patient", "intended_dose"): 0.35,
    ("patient", "actually_taking"): 0.80,    # [PLAN 2.5] the ground truth for adherence
    ("patient", "name"): 0.50,          # [PLAN 2.5]
}
