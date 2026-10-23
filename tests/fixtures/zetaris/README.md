# Recorded Zetaris responses

**Recorded from Arpon's local Zetaris instance** (version 2.4.3.1) on **2026-10-23**,
by read-only queries, so the adapter's parser is tested against a real envelope rather
than a guess.

**Provenance matters here.** These are one instance's responses on one day, on one
Zetaris version — not a published contract. If your own instance returns a different
shape, that is a finding worth recording, not a reason to bend the parser: add your own
fixture alongside these and note the difference in `docs/DECISIONS.md`. The two rows in
`show_lightning_databases.json` are the sample databases that shipped with **his**
install, so a fresh install may list something else. No secrets and no personal data: these are `SELECT` literals and a catalogue
listing. `timeUsed` is stripped because it is a latency measurement, not part of the
shape we parse.

## The envelope

```json
{
  "headers": ["col", ...],     // column names, positionally aligned with each row
  "data":    [["v", ...], ...], // rows as positional lists
  "total":   <row count>,
  "timeUsed": <ms>             // stripped from these fixtures
}
```

**Every value is a string.** `SELECT 1` yields `"1"`, `2.5` yields `"2.5"`, `true`
yields `"true"`. The adapter must cast before any numeric comparison, and the
Evaluator must cast before re-deriving a cited number.

| Fixture | Query | Why it is here |
|---|---|---|
| `select_1.json` | `SELECT 1` | the minimal success envelope |
| `select_typed_columns.json` | four columns of differing type | proves every value arrives as a string |
| `show_lightning_databases.json` | `SHOW LIGHTNING DATABASES` | a catalogue listing uses the same envelope as a SELECT |
| `empty_result.json` | a `WHERE` that matches nothing | zero rows is not an error |
