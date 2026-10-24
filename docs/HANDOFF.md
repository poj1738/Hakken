# Handoff log

**Append-only. Newest first.** Add an entry at the end of every working session, above
the previous one. Never edit or delete someone else's entry — if something was wrong,
say so in a new entry.

Why it exists: three people on a five-day deadline, working at different hours. The
only way the next person starts from where you left off instead of rediscovering it is
if you write down what broke and what you need.

Copy this template:

```markdown
### YYYY-MM-DD HH:MM AEDT · <name> · <branch>

**Did:**
**Changed shared files:**
**Broken:**
**Needs from teammates:**
**Next:**
```

Fill every field, including the awkward ones. "Broken: nothing" is a useful sentence.
**Changed shared files** means anything a teammate will hit a conflict on or silently
depend on: `app/schemas.py`, `app/config.py`, `.env.example`, `CLAUDE.md`,
`requirements.txt`, `Makefile`, CI. If you changed one, say so here *and* in the PR.

---

### 2026-10-24 15:10 AEDT · Arpon · arpon/skeleton

**Did:** PLAN step 3b, the MedTrace domain-pack skeleton, brought forward ahead of
steps 1 and 2 because Arnav is blocked on it. `app/domain/packs/medtrace/` now has
`types.py` (final), all ten modules from PLAN 2.5 with their real signatures and
docstrings, `queries.py` with Q_REF and Q0–Q3 **written as real Lightning SQL**,
`SOURCE_TRUST_PRIORS` filled in, and a local `decide()` at 0.85/0.82 with a TODO to
swap in World Model's. 104 new tests; 160 total green, secret scan clean.

Six places where the plan and the repo disagreed, each resolved in favour of the repo
and each documented in the module it affects:

1. **`SqlResult` did not exist.** PLAN 2.5 types `rows_from_sql(result: SqlResult)`
   against a name that is nowhere in the repo. Defined in `types.py` from the envelope
   already recorded in `tests/fixtures/zetaris/`, because `parse.py` consumes it and
   `app/adapters/zetaris.py` is Arnav's file — the shape is the contract between us.
   `timeUsed` is **optional**: the fixtures strip it, so requiring it would fail every
   `SAMPLE_MODE` replay.
2. **No `DISTINCT`, no window functions, no `JOIN`s, no subqueries in any template.**
   `REFERENCE_NOTES` 1.2 says a second reference to a `UNION ALL`-of-`explode()` view
   fails outright, and `medtrace.all_sources` is exactly that shape; `DISTINCT` over
   one is listed in PLAN 2.1 as an unproven spike; and a 2-table `JOIN` took 91 s
   (`DECISIONS.md`, 24 Oct). So Q0 and Q1 do one flat scan and **deduplicate in
   Python**. This refines PLAN 2.4, which assumed one record per row for both.
   Returning 60 rows instead of 8 is free; a second query is 4–91 s.
3. **Per-source views carry the harmonised columns; `all_sources` is a plain
   `UNION ALL`.** PLAN 2.3 reads as though the renaming happens in `all_sources`, but
   then PLAN 2.1's fallback ("if the union fails, query the 4 views separately") would
   need every template rewritten. With the harmonising pushed down one level it is a
   one-line change. `register_sources.py` (step 6) will follow this.
4. **The trust-attribute vocabulary in PLAN 2.5 is inconsistent.** `fuse` is typed
   `trust: dict[tuple[str, str], float]` over the fused attributes (existence,
   daily_dose, frequency, release, route) but the example priors name `strength`,
   `intended_dose`, `actually_taking`, `name` and `admission_chart`. Resolved by
   declaring `types.TrustAttribute` as the union of both, keeping all seven of the
   plan's example values **verbatim** so the H-MEM seed matches what we agreed. A test
   asserts those seven.
5. **PLAN 2.5 names `DiscrepancyType`, `FusedValue`, `GateResult` and the notice types
   without defining them.** Defined from PLAN 2.6, plus a `Notice` model.
6. **Q4 (`q_shortages`) is deliberately not written.** `medtrace.tga_shortages` is not
   registered and nobody has seen its columns, so writing SQL against it would be
   inventing an endpoint. It raises with a pointer to PLAN 3, Monday.

Two bugs the tests caught in my own code before it shipped, both now regression-tested:

- `q_identity_candidates` built its surname prefix by stripping punctuation, so
  `O'Brien` became `OBRI` and `UPPER(name_family) LIKE 'OBRI%'` never matched
  `O'BRIEN`. **Every apostrophe and hyphen surname would have dropped out of the
  candidate set silently** — invisible in testing, and a missed link shows the
  pharmacist one fewer source. The prefix now keeps the characters a surname really
  contains and stops at the first one that is not letter/apostrophe/hyphen/space, which
  also means `%` and `_` can never reach a `LIKE` pattern as wildcards.
- `NotRequired[int]` is **silently ignored** under `from __future__ import
  annotations`: the annotation stays a string and `__required_keys__` reports the key
  as required anyway. `SqlResult` is split across two classes with `total=False`
  instead, which is a class flag and is honoured. Worth knowing before anyone writes
  another optional-key TypedDict in this repo.

**Changed shared files:** **new** `app/domain/packs/medtrace/types.py` — the frozen
shared file from PLAN 1. Nothing else shared was touched: `app/schemas.py`,
`app/config.py`, `.env.example`, `requirements.txt`, `Makefile`, `CLAUDE.md` and CI are
all unchanged. `jellyfish` is **not** in `requirements.txt` yet — nothing imports it
while the bodies are stubs; it arrives with step 7.

**Broken:** Nothing. Every stub raises `NotImplementedError("Arpon: <file>")`, so a
missing piece names its owner rather than returning `None`. Unproven, in order of how
much rests on it: whether the Zetaris containers can reach `host.docker.internal:8100`
at all (step 1, next); whether the union view registers, caches and queries; and
whether the harmonised views accept these templates against real data. **No SQL in
`queries.py` has been run against Zetaris yet** — it is written to the recorded
envelope and the documented dialect rules, not measured.

**Needs from teammates:**
- **Arnav** — import from `app.domain.packs.medtrace.*` now; do not write your own
  stubs. `queries.py`, `identity.decide()` and `trust.SOURCE_TRUST_PRIORS` are real and
  usable today; everything else raises and wants a fixture-backed fallback **in your
  own code**. Don't edit anything under `app/domain/`. The signature table in
  `tests/unit/test_medtrace_skeleton.py` is the contract — if you need a signature
  changed, ask me rather than editing it, since the test exists to stop exactly that
  drift. When World Model lands, `identity.decide` becomes a delegation to yours; the
  thresholds are already the same numbers, and a test pins both edges inclusive.
- **Anshu** — the vocabulary your grid renders is `types.EvidenceState` (three-valued:
  `unknown` must look different from `absent_in_scope`), `types.DiscrepancyType` (11)
  and `types.NoticeType` (6).

**Next:** PLAN step 1 — Zetaris up, then the `host.docker.internal:8100` reachability
spike, and message Arnav either way. Then step 2 (reference build). Step 3
(`DATA_SPEC.md`) Arpon is writing by hand, not in this session.


### 2026-10-24 11:15 AEDT · Arpon · arpon/team-workflow

**Did:** Separated shared rules from per-machine facts. `CLAUDE.md` had grown a "Known
environment facts" block that was really *my laptop's* state — Zetaris up, preflight
green, observed model ids — presented as if true for everyone. Replaced it with
provider/API behaviour that holds anywhere, and moved the machine-specific half out.
Also tightened the Zetaris rule: nobody starts, stops, reconfigures or deletes any
Zetaris stack, and nobody creates or rotates API keys — each person manages their own
install and we talk to it only over REST.

New: `CLAUDE.local.md` (gitignored) for my own machine notes, `docs/ENVIRONMENTS.md`
with a section per person, and a `.state/preflight.json` output from `make preflight`.
Every "verified"/"works" claim in `PROGRESS.md`, `docs/DECISIONS.md`,
`docs/REFERENCE_NOTES.md` and `README.md` now says **where and when** — all of them
read "Arpon's machine, 23 Oct". The Zetaris fixtures are marked as recorded from my
instance, with a note that a different shape on your instance is a finding to record,
not a reason to bend the parser.

**Changed shared files:** `CLAUDE.md` (Zetaris rule rewritten; machine facts removed;
new "Facts about your own setup live elsewhere" + "API behaviour that holds everywhere"
sections), `.gitignore` (`CLAUDE.local.md`), `scripts/preflight.py` (saves
`.state/preflight.json`, new `--no-save`), `PROGRESS.md`, `README.md`,
`docs/DECISIONS.md`, `docs/REFERENCE_NOTES.md`, `docs/ONBOARDING.md`,
`tests/fixtures/zetaris/README.md`. New: `docs/ENVIRONMENTS.md`.

**Broken:** Nothing. 52 tests green, secret scan clean, `make preflight` 19/19 on my
machine just now (services came back up). Caveat: `gh` still not installed here, so the
PR has to be opened through the GitHub web UI and I cannot watch CI from the terminal.

**Needs from teammates:** Anshuman and Arnav — fill in your section of
`docs/ENVIRONMENTS.md` and create your own `CLAUDE.local.md`. Do **not** put
credentials in either. You do not need Zetaris or Nightshift to start: `make test` runs
with no `.env` and no network, which is how CI runs it.

**Next:** Still blocked on the **track decision** — see `TODO.md`. Nothing in Phase 2
should start before that, and roles remain unassigned.

---

### 2026-10-24 09:30 AEDT · Arpon · arpon/team-workflow

**Did:** Set up the team workflow, no features. Removed `.cursor/` and every reference
to it, so `CLAUDE.md` is now the single source of rules (a mirrored rules file drifts
and then misleads). Added this handoff log, `PROGRESS.md`, a SessionStart hook that
orients you automatically, GitHub Actions CI, and `docs/ONBOARDING.md`. Merged the
Cursor note into `docs/AI_TOOLS_USAGE.md`.

**Changed shared files:** `CLAUDE.md` (new "Team workflow" section; rule 4 rewritten
for Claude Code), `metadata.json` (`cursor.used: false`), `README.md`,
`docs/SPONSOR_TECH.md`, `docs/AI_TOOLS_USAGE.md`. New: `.claude/settings.json`,
`scripts/session_start.sh`, `.github/workflows/ci.yml`, `PROGRESS.md`,
`docs/HANDOFF.md`, `docs/ONBOARDING.md`. Deleted: `.cursor/`.

**Broken:** Nothing. 52 tests green, secret scan clean. Two caveats: `gh` is not
installed on this machine, so the PR could not be opened from the terminal and the
session-start hook skips its PR section gracefully. CI has not run before this push, so
its first run on this branch is also its first real test.

**Needs from teammates:** Roles are not assigned — nothing here allocates work. Each
person needs their own Zetaris API key and Nightshift Runtime token in their own local
`.env`; see `docs/ONBOARDING.md`. Nobody shares credentials.

**Next:** The blocking decision is still **which track** — see `TODO.md`. Both Phase 2
adapters are unblocked and contract-complete the moment that lands.
