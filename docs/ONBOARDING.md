# Onboarding

For Anshuman and Arnav, or anyone picking this up cold. About 20 minutes, most of it
waiting on Docker.

**Read `CLAUDE.md` first** — it holds the hard rules (the ones that can disqualify us)
and the team workflow. This page is only about getting a working machine.

## 1. Clone and install

```bash
git clone https://github.com/poj1738/Hakken.git
cd Hakken
make setup
```

`make setup` creates `.venv`, installs the pinned dependencies, and installs the
pre-commit secret-scan hook. Confirm it worked:

```bash
make test        # expect: 52 passed
```

That passes with no credentials and no services. If it doesn't, stop and say so in
`docs/HANDOFF.md` rather than working around it.

## 2. Your own credentials

```bash
cp .env.example .env
```

Then fill it in with **your own** tokens. `.env` is gitignored and the pre-commit hook
blocks it — do not work around either.

**Also create your own `CLAUDE.local.md`** (gitignored) for notes true only on your
machine: where your Zetaris lives, your Nightshift lane names, your last preflight
result. Keep that out of `CLAUDE.md`, which is shared and must hold only what is true
on every machine. Then add a short summary to your section of `docs/ENVIRONMENTS.md`
so the team knows who can run what — **no credentials in either file.**

**Nobody shares credentials.** Not in chat, not in an issue, not in a PR. Each person
runs their own Zetaris and Nightshift. If a token is ever exposed, rotate it.

| Variable | Where you get it |
|---|---|
| `ZETARIS_API_KEY` | Zetaris web UI → **Management → API Tokens → +**. Shown in plaintext **once**. |
| `ZETARIS_ORG_ID` | Zetaris UI → **Management → Organisation** → the numeric **ID** field (`1` on a local install). |
| `METERLESS_RUNTIME_TOKEN` | **Nightshift → Console** → API key. |
| `METERLESS_BASE_URL` | Nightshift → Console. Default `http://127.0.0.1:8088/v1`. |

**The NVIDIA key goes nowhere near this repo.** It lives only in
**Nightshift → Setup → Providers**. Never in `.env`, code, logs, the README, or any
submission material.

## 3. Run your own Zetaris and Nightshift

Both run **on your host**, not in our `docker-compose.yml`. Follow the event's
**Participant Setup Guide** for each; the short version:

- **Zetaris** — the sponsor's `zetaris-platform` Docker bundle. `docker compose pull`
  (the driver image is large), then `docker compose up -d`, then `./verify.sh`.
  Web UI `http://localhost:3000`, REST API `http://localhost:8888/api/v1.0`.
  **Never call port 8889** — it is internal.
  Quitting Docker only *stops* the containers; the volumes persist, so your API key and
  data survive a restart. **Do not run `docker compose down -v` or `docker system
  prune`** — that is what actually destroys the install.
- **Nightshift** — install the app, put your NVIDIA key in **Setup → Providers**, and
  copy the Runtime URL and token from **Console**.

Then check everything at once:

```bash
make preflight
```

Expect **22 pass / 0 fail**. It prints only variable *names*, never values, so its
output is safe to paste into a handoff entry.

## 4. If you cannot run the services

You can still contribute. Set `SAMPLE_MODE=true` in your `.env`.

Honest caveat: **sample mode is not implemented yet** (it is Phase 2). Today it changes
nothing. What *does* work without services is `make test` and the whole test suite —
which is how CI runs too, with no `.env` and no network at all. So you can write and
test the adapters, engines and schemas without Zetaris or Nightshift; you just cannot
verify a live call.

## 5. Your first change

```bash
git pull origin main
git checkout -b <yourname>/<topic>
```

Read `PROGRESS.md` and the latest 3 entries in `docs/HANDOFF.md` — the session-start
hook prints both automatically, or run `bash scripts/session_start.sh`.

**Claim your task in a handoff entry before you start it**, so two people don't build
the same adapter. Roles are not assigned.

At session end: `make test`, `python3 scripts/secret_scan.py --all`, update
`PROGRESS.md`, add a `docs/HANDOFF.md` entry, log the session in
`docs/AI_TOOLS_USAGE.md`, push, and open a PR. Merge to `main` only when CI is green.

## Where things are

| Looking for | File |
|---|---|
| The rules, and the team workflow | `CLAUDE.md` |
| What state the project is in | `PROGRESS.md` |
| What happened in previous sessions | `docs/HANDOFF.md` |
| What to build next | `TODO.md` |
| Why something was done a certain way | `docs/DECISIONS.md` |
| What the sponsor APIs actually require | `docs/REFERENCE_NOTES.md` |
| Real recorded Zetaris responses | `tests/fixtures/zetaris/` |
