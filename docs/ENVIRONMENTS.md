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
| **Caveat** | Docker and Nightshift were **shut down after that run**, so the result is stale until re-run. `gh` is not installed on this machine. Python is 3.12 while CI pins 3.11. |

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

**Not set up yet.**

| | |
|---|---|
| **OS / RAM** | not recorded |
| **Zetaris** | none → use `SAMPLE_MODE=true` until set up |
| **Nightshift** | none |
| **Last preflight** | never run |

Start at `docs/ONBOARDING.md`. Same as above — services are not required to work on
the adapters, engines or schemas.

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
