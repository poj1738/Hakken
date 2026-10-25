# Pre-existing components

Anything created before the build window opened (**2026-10-22 00:00 UTC**) must be
declared here. Open-source libraries do not need declaring.

| Component | Origin | Date | How it is used |
|---|---|---|---|
| H-MEM specification + conformance vectors | `github.com/Meterless/Meterless` (Apache-2.0) | pre-existing | Read-only reference in gitignored `.refs/`. Our Python implementation is written during the window; the official `vectors.json` is copied into `tests/engines/vectors/` with an Apache-2.0 attribution header. |
| World Model specification, reference implementation + conformance runner | `github.com/Meterless/Meterless` (Apache-2.0), commit `1742dec` | pre-existing | **Ported to Python during the window** (`app/engines/world_model/`, 25 Oct). The TypeScript reference `reference/src/*.ts` was translated module by module, and the runner's 8 inline checks one for one (`tests/engines/test_world_model_conformance.py`). Every ported file carries an Apache-2.0 attribution header. The reference itself stays in gitignored `.refs/`. |
| Zetaris getting-started repo | `github.com/zetaris/getting-started` | pre-existing | Read-only reference for the REST call shape and the REST-table registration recipe. Not shipped. |
| `zetaris-platform` Docker install | Sponsor-provided | installed 2026-10-12 | The local Zetaris instance. Infrastructure, not part of our submission. |
| `NY_TAXI` sample database (15 tables) | Shipped with the sponsor's Zetaris install | pre-existing | Present on the instance before the build window. **Declared, not used** unless explicitly chosen later; our own data lives in separate Lightning databases. |
| `TPCDS_DB` sample database (308 tables) | Shipped with the sponsor's Zetaris install | pre-existing | As above: present on the instance, declared for completeness. |

| PBS schedule data (public API v3) | `data-api.health.gov.au/pbs/api/v3`, Department of Health | pre-existing; **fetched 2026-10-24**, schedule_code 4751 | Real `pbs_code`, pack sizes and repeats joined into our hand-built lexicon, plus an ATC cross-check. The `_meta` copyright permits use and redistribution with copyright retained but **not modification**, so no value is altered, the raw snapshot stays gitignored, and only a ≤200-row attributed sample is committed. See `docs/DATA_LICENCES.md` §1. |
| PBS Item Report (`data.gov.au`) | Department of Health, **CC BY 3.0 AU** | pre-existing; fetched 2026-10-24 (2016 YTD resource) | Real prescription volumes supply `dos_weight`, joined on PBS item code. Gitignored. See `docs/DATA_LICENCES.md` §2. |
| TGA Medicine Shortage Reports export | Therapeutic Goods Administration | pre-existing; fetched 2026-10-24 | **Used for Q4 "known shortage" labels.** Non-commercial hackathon use cleared by our consultant on 25 Oct; parsed locally, gitignored, never committed (`docs/DATA_LICENCES.md` §4). |
| `carltonnorthern/nicknames` (Apache-2.0) | GitHub / PyPI | pre-existing | **Cited by `docs/DATA_SPEC.md` §10.2, not used.** Our nickname table is hand-written for Australians born 1936–1966; nothing was downloaded or vendored. |

**Everything in `app/`, `datasvc/`, `scripts/`, `tests/`, `data/reference_src/`, `web/`
and `docs/` was written inside the build window.** `data/reference/` is generated and
gitignored; `data/reference_src/` is our own hand-built source data.

As of this commit no pre-existing **code** of our own is included. The external
**data** sources above are declared, and every licence is recorded in
`docs/DATA_LICENCES.md`.
