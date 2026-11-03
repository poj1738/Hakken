# Data map

A screen in the MedTrace UI, and a presenter view of the same diagram. Every number is a Zetaris query made when the page loads. Offline, `SAMPLE_MODE` replays the envelopes in `tests/fixtures/medtrace/MAP_*.json`. Those files were written by `scripts/record_data_map.py` from a live run. Nothing in the screen, the fixtures, or the tests is a typed-in count.

## What the screen shows

`GET /data-map/queries` returns the catalogue and runs no SQL. The page then calls `GET /data-map/query/{id}` once per entry, in catalogue order, and never in parallel. A node, bar, or log row changes when that response arrives.

1. The sources diagram: the four clinical systems, the PBS lexicon, the ACSQHC high-risk classes, and TGA shortages (dashed, optional). They meet the semantic layer `medtrace_usl`, which MedTrace reads by SQL. The four clinical systems are labelled with the `all_sources` count. TGA is not part of that merge; if its query fails the node says "not registered".
2. High-risk medicine lines by source, from the grouped query. The patient interview has no coded risk class, so a source that the query does not return is shown as no high-risk lines, with a note that patients describe medicines in their own words.
3. Data quality: the count of medicine lines whose strength is not a real product, the name of the registered rule `strength_is_a_real_product`, and the `SELECT` that was actually sent. The adapter refuses `RUN DQ`, so the screen uses the same predicate as `data/zetaris/usl/08_usl_dq_strength_is_a_real_product.sql`.
4. A log of each statement: time, label, rows, latency, and the SQL folded underneath. A replayed result is marked.

`VITE_API_MODE=mock` does not invent this screen. It says the Data map needs the API.

## Presenter view

"Presenter view" on the Data map, or the page URL `?present=1`, opens the same diagram with no sidebar. Previous, Next, and the arrow keys move through nine steps. The active step is drawn in full; the rest drops back. Step 9 is the data-quality count. The presenter sends the same catalogue through the same two endpoints and no other SQL.

## The statements

Each one is a single read-only statement. `check_read_only` accepts all of them. The replay file is `tests/fixtures/medtrace/<template_id>__<replay_key>.json`.

| id | file | SQL |
|---|---|---|
| emr | `MAP_COUNT__emr.json` | `SELECT COUNT(*) FROM medtrace.emr` |
| gp | `MAP_COUNT__gp.json` | `SELECT COUNT(*) FROM medtrace.gp` |
| pharmacy | `MAP_COUNT__pharmacy.json` | `SELECT COUNT(*) FROM medtrace.pharmacy` |
| patient | `MAP_COUNT__patient.json` | `SELECT COUNT(*) FROM medtrace.patient_report` |
| lexicon | `MAP_COUNT__lexicon.json` | `SELECT COUNT(*) FROM medtrace.med_lexicon` |
| apinchs | `MAP_COUNT__apinchs.json` | `SELECT COUNT(*) FROM medtrace.apinchs` |
| tga | `MAP_COUNT__tga.json` | `SELECT COUNT(*) FROM medtrace.tga_shortages` |
| all_sources | `MAP_COUNT__all_sources.json` | `SELECT COUNT(*) FROM medtrace.all_sources` |
| rows | `MAP_USL__rows.json` | `SELECT COUNT(*) FROM lightning.metastore.medtrace.medtrace_usl.medication_statement` |
| high_risk | `MAP_USL__high_risk.json` | `SELECT source_system, COUNT(*) FROM lightning.metastore.medtrace.medtrace_usl.medication_statement WHERE high_risk_class IS NOT NULL GROUP BY source_system` |
| dq | `MAP_USL__dq.json` | `SELECT COUNT(*) FROM lightning.metastore.medtrace.medtrace_usl.medication_statement WHERE NOT COALESCE(strength_listed, true)` |

## Latencies from the recording run

Pasted from `scripts/record_data_map.py` on this machine, 2026-11-03. `rows` here is the adapter's row count (how many rows came back), not a count typed beside it.

```
wrote MAP_COUNT__emr.json  rows=1  latency_ms=4263
wrote MAP_COUNT__gp.json  rows=1  latency_ms=2476
wrote MAP_COUNT__pharmacy.json  rows=1  latency_ms=1807
wrote MAP_COUNT__patient.json  rows=1  latency_ms=1537
wrote MAP_COUNT__lexicon.json  rows=1  latency_ms=968
wrote MAP_COUNT__apinchs.json  rows=1  latency_ms=704
wrote MAP_COUNT__tga.json  rows=1  latency_ms=954
wrote MAP_COUNT__all_sources.json  rows=1  latency_ms=4474
wrote MAP_USL__rows.json  rows=1  latency_ms=19805
wrote MAP_USL__high_risk.json  rows=3  latency_ms=13522
wrote MAP_USL__dq.json  rows=1  latency_ms=13304
```

## Re-record

Zetaris has to be up, and `SAMPLE_MODE` has to be off. The script refuses to run otherwise. It does not print settings.

```bash
python3 scripts/record_data_map.py
```

That overwrites `tests/fixtures/medtrace/MAP_*.json` with the envelopes it just received, without `timeUsed`. Commit those files. Do not edit them by hand.
