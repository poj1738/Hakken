# 2c — Making the USL stronger: a product requirement

*Written as a product manager would write it for the Zetaris team, from friction we actually
hit building MedTrace. Each item cites where it was recorded.*

## The killer requirement

### Declarative code crosswalks in the USL ("same thing, different code")

**Problem.** In every multi-source domain the hardest part of a unified layer is not joining
tables — it is knowing that two *codes* mean the same thing. In MedTrace four sources describe
one medicine four ways: the hospital by AMT product, the GP by AMT **pack**, the pharmacy by PBS
item (or, for private scripts, only a brand name), the patient in their own words. Today the USL
has no concept for this, so the whole crosswalk lives inside one 43-line activation query
([`07_usl_activate_medication_statement.sql`](../../data/zetaris/usl/07_usl_activate_medication_statement.sql)):
a hand-built key map, a `CASE` per source, a brand fallback and a longest-prefix match. And
because Lightning SQL cannot reference the same exploded view twice
(`MISSING_ATTRIBUTES.RESOLVED_ATTRIBUTE_APPEAR_IN_OPERATION`), we had to build the lexicon into
a single key map with `LATERAL VIEW explode(array(named_struct(...)))` and a window function to
avoid a second reference. It works; it is not something a data steward could read or maintain.

**User.** The data engineer or clinical informaticist who owns a USL over sources that code the
same entity differently: health (AMT/PBS/SNOMED/ICD), finance (ISIN/CUSIP/ticker), retail
(GTIN/SKU), government (ABS/ANZSIC codes).

**Requirement.** A USL column can declare that it is *resolved through* a reference table, with
a rule per source, and Zetaris generates the join, the lineage and the data-quality rule:

- Declare a crosswalk once per USL: the reference table, and per source which reference column
  the source's code matches (exact, case-insensitive, or longest-prefix), with an ordered
  fallback (e.g. PBS code, then brand).
- The resolved column records *how* it was resolved (which rule matched) without hand-written
  `CASE` logic.
- An unresolved value automatically produces a DQ rule result, separating **NULL because the
  source had no code** from **a code that matched nothing** (see acceptance criterion 4).
- The crosswalk is visible in the USL ERD as an edge from each source to the reference table.

**Acceptance criteria.**

1. MedTrace's `medication_statement` can be activated with a crosswalk declaration and a plain
   `SELECT` from `medtrace.ALL_SOURCES`, producing results identical to today's
   43-line activation (all 15 rows of [`1c_usl_2`](results/1c_usl_2.json) match).
2. Changing one source's rule (e.g. GP moves from AMT packs to AMT products) is a one-line
   change to the declaration, with no query rewrite.
3. The same exploded view may be referenced by several crosswalk rules without triggering the
   self-join error.
4. `RUN DQ` on the resolved column reports *no code* and *code not found* as separate counts.
   (Today the generated foreign-key rule counts all 1,552 patient free-text lines as invalid,
   which hides any genuinely broken code among them — [`1c_dq_fk`](results/1c_dq_fk.json).)
5. `LOAD USL` returns the crosswalk in the model JSON, so it can be reviewed and versioned.

**Priority: P1.** It is the step every multi-source USL needs and the one most likely to be
silently wrong: had we keyed the GP on AMT *products*, every GP line would have dropped out of
the result with no error.

### Mock of the proposed improvement (bonus)

> **MOCK — this is not valid Zetaris SQL today.** It shows the shape of the proposal only.

```sql
-- MOCK: not valid Zetaris SQL today.
COMPILE USL medtrace_usl DEPLOY NAMESPACE lightning.metastore.medtrace DDL
CREATE TABLE medicine (generic varchar(120) NOT NULL PRIMARY KEY, atc_primary varchar(16));
CREATE TABLE medication_statement (
  row_id varchar(32) NOT NULL PRIMARY KEY,
  source_system varchar(16),
  med_code varchar(64),
  med_text varchar(500),
  generic varchar(120) RESOLVED THROUGH medicine USING CROSSWALK medicine_codes
)

-- MOCK: the crosswalk, declared once.
CREATE CROSSWALK medicine_codes ON lightning.metastore.medtrace.medtrace_usl.medicine
  FROM medtrace.MED_LEXICON (generic)
  WHEN source_system = 'emr'      MATCH med_code = amt_mp
  WHEN source_system = 'gp'       MATCH med_code = amt_mpp
  WHEN source_system = 'pharmacy' MATCH med_code = pbs_code
                                  ELSE MATCH lower(med_text) = lower(brand)
  WHEN source_system = 'patient'  NO CODE

-- MOCK: activation becomes a plain SELECT.
ACTIVATE USL TABLE lightning.metastore.medtrace.medtrace_usl.medication_statement AS
SELECT row_id, source AS source_system, med_code, med_text FROM medtrace.ALL_SOURCES
```

## Other friction worth fixing (shorter)

| Friction we hit | Where recorded | Ask |
|---|---|---|
| A column named `source` is rejected as "Invalid DDL statement", with no hint which word is wrong | live, 27 Oct (`COMPILE USL` without `DEPLOY` isolated it) | Name the offending token; document reserved words |
| One statement per REST call, but a multi-table `COMPILE USL` must be one statement with `;` inside | Zetaris command reference 13.1; our `register_sources.py` special-cases it | A batch endpoint, or a documented multi-statement form |
| `''` is not an escaped quote: it silently deletes the apostrophe (`'O''Brien'` → `OBrien`) | [`docs/DECISIONS.md`](../DECISIONS.md), 24 Oct | Treat `''` as standard SQL, or raise an error |
| A Lightning REST table binds one fixed URL with no paging, so we serve each source whole | DECISIONS, 23 Oct | Paging parameters on REST tables |
| Latency tracks bytes scanned (~1 s + 2–3 s/MB); the USL query takes ~19 s on our data | DECISIONS, 24 Oct; [04](04_time_saved.md) | Make `MATERIALIZE USL` work against local storage out of the box |
| Our sources are local JSON files. Filestore tables read object storage, and we found no documented way to register a local JSON file directly, so we wrote and run a REST service (`datasvc/`) just to serve them | DECISIONS, 23–24 Oct (incl. the two-network URL trap: a `CREATE` that succeeds against a hostname Zetaris cannot reach, then every query fails) | A first-class "upload a JSON/CSV file" source, and a reachability check at `CREATE` time |
