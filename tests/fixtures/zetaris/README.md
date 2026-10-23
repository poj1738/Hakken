# Recorded Zetaris responses

Captured from a **real local Zetaris 2.4.3.1 instance on 2026-10-23** by a read-only
query, so the adapter's parser is tested against the actual envelope rather than a
guess. No secrets and no personal data: these are `SELECT` literals and a catalogue
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
