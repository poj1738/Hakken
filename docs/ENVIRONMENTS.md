# Environments

Who can run what. **Shared on purpose** — when something only reproduces on one
machine, this is how we find out whose, and who to ask.

`CLAUDE.md` holds only what is true everywhere. Detailed personal notes go in your own
`CLAUDE.local.md` (gitignored). This file is the short, shared summary.

**Keep your own section current.** A stale "verified" line is worse than an empty one,
because someone will plan around it. Update it whenever you run `make preflight`, and
put the date on it.

> Credentials are never recorded here. No tokens, no keys, no URLs with keys in them.
> Each person uses their own, in their own local `.env`.

---

## Arpon

| | |
|---|---|
| **OS / RAM** | macOS (Darwin 24.6.0), Apple Silicon. Python 3.12.8, Node 23.11, Docker 29.9.2. RAM: not recorded. |
| **Zetaris** | **Local** — sponsor's `zetaris-platform` Docker bundle. REST `localhost:8888/api/v1.0`, org `1`. Carries the install's pre-existing `NY_TAXI` + `TPCDS_DB` sample data. |
| **Nightshift** | **Own**, at `127.0.0.1:8088/v1`, build `m1-m4`. NVIDIA key in Setup → Providers. Lanes: `deep-reasoner`, `fast-tools`, `deep-verifier` — all cloud Nemotron, 0 local. |
| **Last preflight** | **2026-10-23 — 22 pass / 0 fail.** Both services were up; `meterless/auto` answered by `nvidia/nemotron-3.5-super-vl-120b-a12b`. |
| **Tooling** | `gh` 2.103.0, authenticated as `poj1738` (24 Oct) — so PRs and CI checks can be driven from the terminal here. |
| **MedTrace registered** | **Yes, 2026-10-24.** All 8 views live and verified: `medtrace.{emr,gp,pharmacy,patient_report,med_lexicon,apinchs,nicknames,all_sources}`. `SELECT COUNT(*) FROM medtrace.all_sources` = **4,825**, matching `datasvc` exactly. Re-check with `python3 scripts/register_sources.py --verify-only`. |
| **datasvc reachability** | **Proven 2026-10-24.** `host.docker.internal:8100` returns HTTP 200 in ~20 ms from both `zetaris-api-1` and `zetaris-driver-1`, and a real REST table at that URL fetches our data. The MinIO/Parquet and Postgres-over-JDBC fallbacks are retired. **`datasvc` must be running for a cache refresh or a re-register** — `.venv/bin/python -m uvicorn datasvc.main:app --host 0.0.0.0 --port 8100`. |
| **Query timings** | Q_REF 0.17–0.64 s · Q0 0.33 s · **Q1 1.84 s** · Q2 1.86 s · Q3 1.72 s. A whole run costs ~6 s of Zetaris. |
| **Leftover** | `medtrace_spike` is an empty SchemaStore container from the morning's spike. There is no SQL path to drop a container, so it needs the Data Explorer. Cosmetic. |
| **Caveat** | Python is 3.12 while CI pins 3.11 — if something passes locally and fails in CI, suspect that first. |

## Anshuman

**Not set up yet.**

| | |
|---|---|
| **OS / RAM** | not recorded |
| **Zetaris** | none → use `SAMPLE_MODE=true` until set up |
| **Nightshift** | none |
| **Last preflight** | never run |

Start at `docs/ONBOARDING.md`. You do not need either service to contribute: the test
suite runs with no `.env` and no network, which is exactly how CI runs it.

## Arnav

| | |
|---|---|
| **OS / RAM** | Windows 11 Pro, 15 GB RAM. Hakken runs inside **WSL2 Ubuntu 24.04** (`~/Hakken`), WSL capped at 10 GB / 4 CPUs. Python 3.11.17 (matches CI), Docker 29.9.2 (Docker Desktop, WSL integration on). No Node. `gh` 2.45 in WSL. |
| **Zetaris** | **Local** — sponsor's `zetaris-platform` bundle under Docker Desktop. REST `localhost:8888/api/v1.0` (reachable from WSL), org `1`. Pre-existing `NY_TAXI` + `TPCDS_DB` sample data. |
| **Nightshift** | **Own**, Windows edition. The runtime listens on Windows `127.0.0.1:8088` only, so WSL reaches it through a `netsh portproxy` on the WSL adapter address — `METERLESS_BASE_URL` points there, not at `127.0.0.1`. 18 `meterless/*` routes. |
| **Last preflight** | **2026-10-25 — 20 pass / 2 fail / 1 warn.** Zetaris all green; Nightshift `online`, `meterless/auto` answered by `nvidia/nemotron-3.5-lightning-30b-a3b`. Fails: Node not installed; Auto Detect (probes localhost ports only — expected with the portproxy). |
| **MedTrace registered** | **Yes, 2026-10-25.** `register_sources.py --apply`: 28/28 statements, all 8 views verified (`medtrace.all_sources` = **13,856** = datasvc). `make verify` exits 0, and live Q1 = fixtures for P0001–P0006. Through `app/adapters/zetaris.py`: lexicon 224 entries, Q0 1,326 rows / 200 patients in 0.7 s, Q1 for MRN0000015 219 rows in 5.1 s, identical to `Q1__P0015.json`. |
| **datasvc reachability** | **Works from WSL with no workaround.** datasvc runs inside WSL on `0.0.0.0:8100`, and `host.docker.internal:8100` returns 200 from `zetaris-api-1` and `zetaris-driver-1` in <0.2 s. datasvc must be running for `make refresh` or a re-register. |
| **Tooling** | `gh` authenticated with write access, so PRs and CI can be driven from the terminal. |
| **Caveats (Windows)** | (1) Clone **inside WSL**, not under `/mnt/c` — a Windows clone gets CRLF line endings that break the bash scripts. (2) WSL `networkingMode=mirrored` broke Docker Desktop's port forwarding to Zetaris (`localhost:3000` dropped every connection), so it is off. (3) Without mirrored mode WSL cannot see Windows `127.0.0.1`, hence the portproxy; its address can change after a reboot. |

---

## Options, if a local install is not practical

- **Zetaris:** local Docker (what Arpon runs), a shared AWS/Cloud instance if the
  organisers provide one, or none — in which case set `SAMPLE_MODE=true`.
  Honest caveat: **sample mode is not implemented yet** (Phase 2), so today it changes
  nothing; `make test` is what works without services.
- **Nightshift:** your own local install, or reaching a teammate's over something like
  Tailscale. If you share a runtime, the owner's lane configuration applies, not
  yours — so do not write code that depends on a lane name existing.
- **Never share a token to work around a missing install.** Everyone uses their own.
