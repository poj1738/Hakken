# Data sources

Every source: origin, licence, synthetic or not, the subset used, and how to
regenerate it. **Synthetic or open data only** — no real personal, clinical or
financial records. Licences in full: `docs/DATA_LICENCES.md`. The synthetic data
model: `docs/DATA_SPEC.md`.

## Status (25 Oct)

| Source | Origin | Licence | Synthetic? | Subset | Regenerate with |
|---|---|---|---|---|---|
| Four patient silos: hospital EMR, GP, pharmacy, patient interview | `scripts/generate_synthetic.py`, seeded | Ours | **Yes** — every patient, medicine and discrepancy is generated | 200 patients (100 tune, 100 held-out), ~13,900 rows, plus `data/synthetic/ground_truth.json` | `make synth` (needs the lexicon first) |
| Replay fixtures for `SAMPLE_MODE` | Recorded from the generator through the same harmonised view Zetaris serves | Ours; the lexicon fixture carries PBS values under `tests/fixtures/medtrace/PBS_COPYRIGHT.txt` | Yes, apart from the PBS values | 13 patients' Q1–Q3, Q0 admissions, Q_REF reference tables | `make synth` |
| PBS schedule (public API v3) | Department of Health | Redistribution allowed with copyright retained; **no modification** (`DATA_LICENCES.md` §1) | No, real | Schedule 4751 (Oct 2026): `items`, `item-atc-relationships`; codes, pack sizes and repeats for our ~100 medicines, copied verbatim | `make data` (rate-limited, ~8 min) |
| PBS Item Report | `data.gov.au` | CC BY 3.0 AU (§2) | No, real | 2016 YTD volumes, joined on item code for `dos_weight` | **Manual download** to `data/reference/raw/pbs_item_report_2016.csv`, then `make lexicon` (no script fetches it) |
| Medicine, high-risk and nickname tables | `data/reference_src/*.csv`, hand-built from `DATA_SPEC.md` | Ours (§3) | Reference, not patient data | 108 products, 40 APINCHS rows, 167 nickname pairs | Committed; `make lexicon` builds the served lexicon |
| TGA Medicine Shortage Reports | Therapeutic Goods Administration | **Unconfirmed** (§4) | No, real | Parsed locally; **not committed, not served, not registered** | `scripts/load_tga_shortages.py`, then `register_sources.py --with-tga` once licensed |

`data/reference/` and `data/synthetic/silos/` are gitignored, so a fresh clone
builds them with `make lexicon && make synth`, no network needed. Without a PBS fetch
the generator uses the committed lexicon (real codes), so the committed fixtures come
out byte-identical; CI checks this on every push. The replay fixtures are committed, so `SAMPLE_MODE` and
the test suite work without either.

## Declaration

No patient data existed before the build window opened (2026-10-22 00:00 UTC). The
generator is seeded and deterministic, so any reviewer can reproduce the exact
dataset from the committed script. The external reference data (PBS, TGA) predates
the window as public data and is declared in `docs/PREEXISTING.md`.
