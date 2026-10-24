# Working rules for this repo

Team Hakken — Open Agent Hackathon 2026. **Hard deadline 2026-10-27 23:45 UTC**
(Wed 28 Oct 10:45 AEDT). Time is the scarcest resource: ship the smallest working
vertical slice, then improve.

## Hard rules (violating any of these can disqualify us)

1. **Zetaris is the data layer and must be load-bearing.** Agents get facts by sending
   SQL to Zetaris over its REST API, never by reading files directly.
2. **Meterless, two separate requirements.**
   - *Engine:* at least one Meterless engine implemented and working in a
     **user-facing feature**, with a passing conformance test we can show. Mentioning
     it, copying a prompt or adding an unused dependency fails the rule.
   - *Power:* **Nightshift is the primary AI provider.** Every model call in the
     product goes through it.
3. **NVIDIA:** Nemotron is reached *through Nightshift*. The NVIDIA API key lives
   **only** in Nightshift → Setup → Providers — never in our code, `.env`, logs,
   README, video or slides. Traces must show which model handled each request.
4. **AI coding tools:** we build with **Claude Code**. This file is the single source
   of our working rules — no mirrored rules file, because a copy drifts and then
   misleads. Cursor is not used; the official resources disagree on whether it is
   mandatory, and we declare what we actually used rather than what looks compliant.
   What the AI Usage Policy requires is an **honest declaration** — log every session
   in `docs/AI_TOOLS_USAGE.md`.
5. **Secrets only from environment variables.** `.env` is gitignored; only
   `.env.example` is committed. Never print, log or echo a secret value, and never
   read `.env` back into the chat. Refer to secrets by variable name only.
6. **No hardcoded outputs, no fake agents, no hand-written traces, no mocked sponsor
   integrations presented as real.** Outputs must change with inputs.
   `output_examples/` must come from real runs.
7. **Data:** open or synthetic only. No real personal, clinical or financial records.
   Document every source: origin, licence, subset, how to regenerate. Anything
   prepared before 2026-10-22 00:00 UTC must be declared.
8. **Judges have limited time:** `POST /run` and `python run.py` both work, Docker
   builds, a run finishes in 5–10 min CPU-only, ≥3 sample inputs with real outputs,
   and **`SAMPLE_MODE=true` runs real agent logic with no Zetaris, no Nightshift and
   no network**.
9. **Responsible AI:** input validation, stated limitations, a human-review gate for
   high-risk outputs, and a clear "not medical advice / synthetic data" disclaimer.

## Working agreement

- **Read-only first.** Ask before anything that creates or drops objects in Zetaris,
  installs system packages, rewrites git history or deletes files.
- **Never start, stop, restart, reconfigure or delete any Zetaris stack** — no
  `docker compose` commands in a `zetaris-platform` folder — and **never create, fetch
  or rotate API keys.** Each teammate manages their own Zetaris install. Talk to
  Zetaris only over its REST API, using the settings in `.env`. If it is unreachable,
  **say so and stop**; do not try to fix it.
- **Never invent** model ids, table names, endpoints or response fields. Discover them
  (`GET /v1/models`, `SHOW …`/`DESCRIBE …`, a recorded real response) and record them
  in `docs/DECISIONS.md`.
- **The conformance suite beats the prose.** Where an engine's spec and its
  conformance runner disagree, the runner wins; document the discrepancy and never
  weaken a check to make it pass.
- Every external call has a timeout and a fallback. Every loop is bounded.
- Smallest working slice first: run it, read the logs, test, then refine.
- Commit often with clear messages, on a feature branch per phase. The pre-commit
  secret scan must pass (`make scan`).
- Keep `docs/DECISIONS.md` (decision, why, date) and `TODO.md` ordered by judging impact.
- **Be honest in the README:** claim only what the code and traces show.

## Team workflow

Three people, different hours, one five-day deadline. The cost of getting this wrong is
two people building the same adapter, or a silent conflict in `app/schemas.py`.

### At session start

```bash
git pull origin main
```

Then read **`PROGRESS.md`** (current state, what is blocked, what is next) and the
**latest 3 entries in `docs/HANDOFF.md`**. The SessionStart hook prints all of this
automatically — if it did not run, run `bash scripts/session_start.sh` yourself.

### While working

- Work on a branch named **`<name>/<topic>`** — for example `arpon/zetaris-adapter`.
  Never commit directly to `main`.
- **Claim your task in a handoff entry before starting it**, so nobody duplicates work.
- **Never commit `.env`.** It is gitignored and the pre-commit hook blocks it; do not
  work around either.

### At session end

Run these, in order:

```bash
make test                       # must be green
python3 scripts/secret_scan.py --all   # must be clean
```

Then:

1. Update **`PROGRESS.md`** — it holds current state only; overwrite it.
2. Add an entry to **`docs/HANDOFF.md`** — append-only, newest first, using the
   template in that file. Fill every field; "Broken: nothing" is a useful sentence.
3. Log the session in **`docs/AI_TOOLS_USAGE.md`**.
4. Push your branch and open or update a PR:
   ```bash
   git push -u origin <name>/<topic>
   gh pr create --fill        # or update the existing PR
   ```
5. Merge to `main` only when **CI is green**.

### Shared files — say so twice

If you change any of these, call it out **in your handoff entry and in the PR
description**, because a teammate will either hit a conflict or silently depend on it:

`app/schemas.py` · `app/config.py` · `.env.example` · `CLAUDE.md` ·
`requirements.txt` · `Makefile` · `.github/workflows/ci.yml`

### Credentials are personal

Everyone runs their own Zetaris and Nightshift and uses their own tokens in their own
local `.env`. **Never share a token, and never paste one into a chat, an issue or a PR.**
If one is exposed, rotate it. New teammates start at `docs/ONBOARDING.md`.

## Facts about your own setup live elsewhere

Facts about any one person's setup live in `docs/ENVIRONMENTS.md` or `CLAUDE.local.md`.
**Never assume your own Zetaris/Nightshift works; run `make preflight`.**

This file is shared by Anshuman, Arpon and Arnav, so it must contain only what is true
on every machine. Anything observed on one machine — whether a service is up, which
Nightshift lanes exist, which model ids a runtime returns, a preflight result — belongs
in `CLAUDE.local.md` (gitignored, yours alone) or in your section of
`docs/ENVIRONMENTS.md` (shared, so the team knows who can run what).

## API behaviour that holds everywhere

These come from the sponsors' published contracts and reference repos, not from one
machine's state. Where a behaviour was observed rather than documented, the source and
date are recorded in `docs/DECISIONS.md` and `docs/REFERENCE_NOTES.md` — check there
before relying on it, and re-verify on your own machine.

**Zetaris**
- Lightning SQL only. **One statement per call, no trailing semicolon**, qualified
  names (`<source>.<table>`).
- **Never call port 8889** — it is internal on a local install.
- Values come back as **strings** (`"1"`, `"2.5"`, `"true"`). Cast before comparing.
- **Escape string literals with a backslash (`\'`), never a doubled quote (`''`).**
  `''` does not escape in Lightning SQL — it ends one literal and starts another, and
  adjacent literals concatenate, so `'O''Brien'` becomes `OBrien`. Quotes stay
  balanced and nothing raises, so a name with an apostrophe silently matches **zero
  rows**. Use `app.domain.packs.medtrace.queries.sql_literal()` rather than building
  literals by hand.
- `SHOW DATASOURCES` does not list REST or file registrations — use
  `SHOW LIGHTNING DATABASES` and `SHOW TABLES IN <db>`.
- `CREATE SCHEMASTORE CONTAINER` has no `IF NOT EXISTS`; a re-run fails on a duplicate.
- A REST table may re-call its source on every query — `CACHE TABLE` after registering.

**Meterless Nightshift**
- Normalise any pasted URL to `<host>/v1`; **never produce `/v1/v1`**.
- `Authorization: Bearer <token>` on every call, `meterless-app` on every request,
  `meterless-scope: user` on chat. The placeholder `rt-local` is rejected.
- **`GET /v1/models` decides status**, not `/healthz`: 401/403 → `unauthorized`,
  200 with `meterless/*` ids → `online`, anything else → `offline`.
- **180 s timeout** — a cold model load can take minutes.
- **Never send a tight `max_tokens`** — hidden reasoning tokens can make a one-word
  answer cost ~45 completion tokens, and a small budget fails as
  `<model>_empty_response`, which looks like an outage.
- Record **which model actually answered** from the response body, not from the route
  requested. Lane routing is an *intent*, not a guarantee.
- An upstream provider failure arrives as **our** 502 — read `error.meterless_detail`
  before blaming our own code.

**Both**
- From inside a container use `host.docker.internal`, not `localhost`.

## Current plan
Roles and today's plan: docs/PLAN_2026-10-24.md. Read it before starting work.
