# Kickoff prompt for a teammate's coding agent

Anshuman and Arnav: paste the block below into your coding agent (Claude Code, or
whatever you use) with this repo as the working directory — or before cloning, and it
will clone for you. It is deliberately self-contained, because your agent cannot read
this repo until it has cloned it.

Keep this file in sync if the setup changes. Everything in the block is also true in
`CLAUDE.md`, `docs/ONBOARDING.md` and `docs/ENVIRONMENTS.md`, which are the canonical
sources once you are cloned.

---

````text
You are my coding agent for a hackathon project. Read this whole brief before running
anything, then follow it in order. Stop and ask me before anything it marks as "ask
first". Do not start building features.

## 0. What this project is

Team Hakken's entry in the Open Agent Hackathon 2026 (GenAI.Works, online). Three
people: Anshuman, Arpon, Arnav. Hard deadline 2026-10-27 23:45 UTC (Wed 28 Oct
10:45 AEDT, Sydney time). Repo: https://github.com/poj1738/Hakken — it is PRIVATE,
and I have write access.

It is a multi-agent system with four sponsor requirements that are
disqualification-level, not nice-to-haves:

1. Zetaris is the data layer and must be load-bearing: agents get facts by sending
   SQL to Zetaris over its REST API, never by reading files directly.
2. A Meterless engine (H-MEM or World Model) must be implemented and working in a
   user-facing feature, with a passing conformance test. Mentioning it, copying a
   prompt, or adding an unused dependency fails the rule.
3. Meterless Nightshift must be the app's primary AI provider — every model call
   goes through it.
4. NVIDIA Nemotron models are reached only through Nightshift. The NVIDIA API key
   lives ONLY in the Nightshift app's settings, never in the repo, .env, logs,
   README, video or slides.

> **Superseded (25 Oct): Track 1 chosen — MedTrace.** This is the original Phase 0
> kickoff prompt, kept for the record. Current state: `PROGRESS.md`; plan:
> `docs/PLAN_2026-10-24.md`.

The track has NOT been chosen yet. The repo is a deliberately track-agnostic
template, so choosing a track later means writing a "domain pack" (data sources,
prompts, output schema) rather than rewriting plumbing.

Current state: Phase 1. Only two things are built — a preflight script and a config
layer. There is no agent, no data pipeline, no engine, no UI. Do not be fooled by the
directory structure: most modules are deliberate stubs that raise NotImplementedError
rather than fake a result. Nothing in this repo pretends to work.

## 1. Clone it and get oriented

    git clone https://github.com/poj1738/Hakken.git
    cd Hakken

The repo is private, so this needs my GitHub credentials. If it fails, tell me and
stop — I may need to authenticate (gh auth login, or an SSH key). Do not try other
URLs or a different account.

Then read these, in this order, and summarise them back to me before doing anything
else:

  1. CLAUDE.md          — the rules. Hard rules, working agreement, team workflow,
                          and the API behaviour that holds on every machine.
  2. PROGRESS.md        — what state the project is actually in right now.
  3. docs/HANDOFF.md    — the latest 3 entries. What the last person did, what broke,
                          what they need.
  4. TODO.md            — what to build next, ordered by judging impact.
  5. docs/ONBOARDING.md — setup, in more detail than this brief.
  6. docs/DECISIONS.md  — why things are the way they are. Read before "improving"
                          anything; several entries exist because an obvious-looking
                          approach was tried and failed.

Two more worth reading when you touch the relevant area:
  - docs/REFERENCE_NOTES.md — what the sponsor APIs actually require, including
    gotchas discovered by observation.
  - docs/ENVIRONMENTS.md    — who on the team can run which services.

A note on how to read those docs: a claim marked "[live — Arpon's machine, 23 Oct]"
was observed on ONE machine on ONE day. It is a data point, not a guarantee. It may
not reproduce for us. Re-verify before depending on it, and never edit someone else's
observation — add your own.

## 2. Make it run (no credentials needed)

    make setup      # creates .venv, installs pinned deps, installs a pre-commit hook
    make test       # expect: 52 passed

Those 52 tests pass with no credentials, no services and no network — that is exactly
how CI runs them. If they do not pass, stop and tell me; do not work around it.

When the repo opens in Claude Code there is a committed SessionStart hook
(.claude/settings.json → scripts/session_start.sh) that prints branch, divergence from
origin/main, uncommitted files, progress status and the latest handoff entries. You may
be asked to approve it running. It is read-only and never touches the network.

## 3. What has to be downloaded or installed

Required for the basics:
  - Python 3.11 — CI pins 3.11. Another teammate is on 3.12; if something passes
    locally and fails in CI, suspect that first.
  - git.
  - Node 20+ — only needed to run the sponsors' official TypeScript conformance
    runners for comparison. Not needed for our Python tests.

Needed only to run the live services (optional at first — see step 4):
  - Docker Desktop, for Zetaris.
  - The sponsor's zetaris-platform Docker bundle, from the event's Participant Setup
    Guide. Ask me for it. Warning: `docker compose pull` downloads a multi-GB driver
    image and takes a while. Zero containers before `docker compose up -d` is NORMAL,
    not a broken install.
  - The Meterless Nightshift app.
  - An NVIDIA API key, which goes ONLY into Nightshift's Setup → Providers screen.
    Never into this repo.

Needed to read the sponsor specs (IMPORTANT — a fresh clone does NOT have these):
  `.refs/` is gitignored, so the reference material is absent after cloning. If we
  work on the engines or the adapters, clone it yourself, into `.refs/` so it stays
  ignored:

      git clone --depth 1 https://github.com/zetaris/getting-started.git .refs/zetaris
      git clone --depth 1 https://github.com/Meterless/Meterless.git .refs/meterless

  The Meterless repo holds the H-MEM and World Model specs and, more importantly,
  their conformance suites. Where a spec's prose and its conformance runner disagree,
  the runner wins — there is already a documented case of this in docs/DECISIONS.md.

Optional: the `gh` CLI, for opening PRs and checking CI from the terminal.

## 4. Credentials, and what to do without them

    cp .env.example .env

Fill it with MY OWN tokens:
  - ZETARIS_API_KEY  — created in the Zetaris web UI: Management → API Tokens → "+".
                       Shown in plaintext once.
  - ZETARIS_ORG_ID   — Zetaris UI: Management → Organisation → the numeric ID field.
  - METERLESS_RUNTIME_TOKEN and METERLESS_BASE_URL — from Nightshift → Console.

Rules about credentials, which you must not break:
  - Never commit .env. It is gitignored and a pre-commit hook blocks it. Do not work
    around either.
  - Never print, echo or paste a secret value anywhere — not into a file, a commit, a
    PR, an issue, or your own output. Refer to secrets by variable name only.
  - Nobody on this team shares tokens. Each person uses their own.
  - The NVIDIA key never goes in .env or the repo. Nightshift only.

Then, once the services are running:

    make preflight     # read-only; checks tooling, env var NAMES, Zetaris, Nightshift

It prints only variable names, never values, so its output is safe to share. It also
writes .state/preflight.json (gitignored) — do NOT copy that result into any shared
doc; put a one-line summary in my section of docs/ENVIRONMENTS.md instead.

If I cannot run the services yet, that is fine and not blocking: `make test` works
without them, which is how CI runs. Note honestly that SAMPLE_MODE is NOT implemented
yet (it is Phase 2 work), so setting it changes nothing today. You can still write and
test adapters, engines and schemas — you just cannot verify a live call.

Also create a CLAUDE.local.md (gitignored) for notes true only on my machine — where
my Zetaris lives, my Nightshift lane names, my last preflight result — and add a short
summary to my section of docs/ENVIRONMENTS.md so the team knows who can run what. No
credentials in either file.

## 5. Hard prohibitions — ask first, or do not do it at all

  - NEVER start, stop, restart, reconfigure or delete any Zetaris stack. No
    `docker compose` commands in a zetaris-platform folder. Never create, fetch or
    rotate API keys. Each teammate manages their own install. Talk to Zetaris only
    over its REST API using the settings in .env. If it is unreachable, say so and
    STOP — do not try to fix it.
  - Never call Zetaris port 8889. It is internal.
  - Do not commit directly to main. Work on a branch named <myname>/<topic>.
  - Do not start Phase 2 or later work until the team has chosen the track. That
    decision is still open and is the blocking item in TODO.md.
  - Ask first before: installing system packages, running anything that creates or
    drops objects in Zetaris, rewriting git history, or deleting files.
  - Never invent model ids, table names, endpoints or response fields. Discover them
    (GET /v1/models, SHOW/DESCRIBE, a recorded real response) and record them in
    docs/DECISIONS.md.
  - No hardcoded outputs, no fake agents, no hand-written traces, no mocked sponsor
    integrations presented as real. This is a disqualification rule. Outputs must
    change with inputs.
  - Only synthetic or open data. No real personal, clinical or financial records.

## 6. How to work, start to finish

At session start:

    git pull origin main

then read PROGRESS.md and the latest 3 entries in docs/HANDOFF.md (the SessionStart
hook prints both; otherwise run `bash scripts/session_start.sh`).

While working:
  - Branch: `git checkout -b <myname>/<topic>`.
  - Claim your task in a docs/HANDOFF.md entry BEFORE starting it, so two people do
    not build the same thing. Roles are not assigned.
  - Smallest working slice first: run it, read the logs, test, then refine.
  - Every external call gets a timeout and a fallback. Every loop is bounded.

At session end, in this order:

    make test                              # must be green
    python3 scripts/secret_scan.py --all   # must be clean

then update PROGRESS.md (current state only — overwrite it), add an entry to
docs/HANDOFF.md (append-only, newest first, using the template in that file — fill
every field, including "Broken" and "Needs from teammates"), log the session in
docs/AI_TOOLS_USAGE.md, push the branch, and open or update a PR. Merge to main only
when CI is green.

If you change any of these shared files, say so BOTH in your handoff entry and in the
PR description, because a teammate will hit a conflict or silently depend on it:
app/schemas.py, app/config.py, .env.example, CLAUDE.md, requirements.txt, Makefile,
.github/workflows/ci.yml.

## 7. Be honest

Claim only what the code and the tests actually show. If something is unverified, say
unverified. If a service is down, say it is down and stop rather than inventing a way
around it. If you observe behaviour that contradicts a doc, record your observation
with the date and whose machine, and tell me — do not quietly overwrite what is there.

## First task

Do steps 1 and 2 only: clone, read the six documents, run `make setup` and `make test`.
Then report back to me with (a) a summary of what this project is and what state it is
actually in, (b) whether the 52 tests passed, (c) what is still missing on my machine
from step 3, and (d) what you think the most useful thing I could pick up is, given the
track has not been chosen. Do not write any feature code yet.
````
