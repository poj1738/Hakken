#!/usr/bin/env python3
"""Register the MedTrace silos and reference tables in Zetaris.

**Dry-run by default.** Prints every statement and changes nothing. `--apply`
executes. `--skip-exists` tolerates a re-run, which is needed because
`CREATE SCHEMASTORE CONTAINER` has no `IF NOT EXISTS` and fails on a duplicate
(`docs/REFERENCE_NOTES.md` 1.3).

Uses its **own minimal REST call**, not `app/adapters/zetaris.py`, so that this
and Arnav's adapter never wait on each other (PLAN 4 step 6).

The shape, all of it measured on 24 Oct (`docs/DECISIONS.md`):

  per silo   CREATE LIGHTNING DATABASE -> CREATE LIGHTNING REST TABLE
             -> CREATE SCHEMASTORE VIEW (explode + harmonise) -> CACHE TABLE
  then       CREATE SCHEMASTORE VIEW medtrace.all_sources AS <UNION ALL>

Three things this gets right because they were learned the hard way:

* **The REST endpoint is `DATASVC_PUBLIC_URL`**, which must resolve from inside
  the Zetaris containers. A compose-only hostname registers fine and then fails
  every query; `app/config.py` rejects one.
* **The per-source views harmonise, and `all_sources` is a plain `UNION ALL`.**
  The `SELECT` lists come from the generator's `HARMONISED_MAP`, so the live
  view and the replayed fixtures cannot drift apart.
* **Counts are verified against `datasvc` and a mismatch is fatal.** A
  successful `CREATE` does not prove a usable table (`REFERENCE_NOTES` 1.4).

Usage:
    python3 scripts/register_sources.py                 # dry run
    python3 scripts/register_sources.py --apply
    python3 scripts/register_sources.py --apply --skip-exists
    python3 scripts/register_sources.py --verify-only
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import pathlib
import ssl
import sys
import time
import urllib.error
import urllib.request
import uuid

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from app.config import get_settings
from app.domain.packs.medtrace.queries import (
    ALL_SOURCES_VIEW,
    CONTAINER,
    HARMONISED_COLUMNS,
    REFERENCE_VIEWS,
    SOURCE_VIEWS,
    TGA_COLUMNS,
    TGA_VIEW,
    sql_literal,
)

# HARMONISED_MAP lives in the generator: one definition for the view SQL and the
# fixtures both. Loaded by path because scripts/ is not a package.
_spec = importlib.util.spec_from_file_location(
    "generate_synthetic", pathlib.Path(__file__).resolve().parent / "generate_synthetic.py"
)
assert _spec and _spec.loader
_gen = importlib.util.module_from_spec(_spec)
sys.modules["generate_synthetic"] = _gen
_spec.loader.exec_module(_gen)
HARMONISED_MAP = _gen.HARMONISED_MAP

#: PLAN 2.1. (lightning_db, raw_table, datasvc_path, view, array_field)
SILOS = [
    ("MT_EMR", "emr_raw", "/silos/emr", SOURCE_VIEWS["emr"], "emr"),
    ("MT_GP", "gp_raw", "/silos/gp", SOURCE_VIEWS["gp"], "gp"),
    ("MT_PHARMACY", "pharmacy_raw", "/silos/pharmacy", SOURCE_VIEWS["pharmacy"], "pharmacy"),
    ("MT_PATIENT", "patient_raw", "/silos/patient", SOURCE_VIEWS["patient"], "patient"),
]

#: Reference tables all share one Lightning database (PLAN 2.1).
REFERENCES = [
    ("MT_REF", "lexicon_raw", "/ref/lexicon", REFERENCE_VIEWS["lexicon"],
     ("pbs_code", "brand", "generic", "amt_mp", "amt_mpp", "amt_tpp", "atc_primary",
      "strength", "form", "release", "pack_qty", "repeats", "is_combination",
      "ingredients", "dos_weight")),
    ("MT_REF", "apinchs_raw", "/ref/apinchs", REFERENCE_VIEWS["apinchs"],
     ("atc_prefix", "apinchs_class", "label")),
    ("MT_REF", "nicknames_raw", "/ref/nicknames", REFERENCE_VIEWS["nicknames"],
     ("canonical", "variant", "sex")),
]

#: Q4's TGA shortage table (PLAN 2.1), registered only with `--with-tga`. Kept out
#: of REFERENCES so verify/refresh/drift never touch a table that is not there.
#: Off by default: the TGA licence is not yet recorded in docs/DATA_LICENCES.md,
#: and registering a view over unlicensed data is worse than shipping without it.
#: `datasvc` does not serve `/ref/tga` either (`test_tga_is_deliberately_not_served`).
#: Once the licence is recorded: add `"tga": "tga_shortages.json"` to datasvc's
#: REFERENCES, update that test, then `--apply --skip-exists --with-tga`.
TGA = ("MT_TGA", "tga_raw", "/ref/tga", TGA_VIEW, TGA_COLUMNS)


try:
    import certifi

    SSL_CTX: ssl.SSLContext | None = ssl.create_default_context(cafile=certifi.where())
except ImportError:  # pragma: no cover
    SSL_CTX = None


def log(msg: str = "") -> None:
    print(msg, flush=True)


# --------------------------------------------------------------------------- #
# Minimal Zetaris client
# --------------------------------------------------------------------------- #


class Zetaris:
    """One POST per statement. Deliberately tiny -- this is a build-time tool."""

    def __init__(self) -> None:
        settings = get_settings()
        self.url = settings.zetaris_rest_url.rstrip("/") + "/sql-editor/sqls/run"
        self.key = settings.zetaris_api_key.get_secret_value()
        self.org = settings.zetaris_org_id
        self.timeout = settings.zetaris_timeout_s
        if not settings.has_zetaris_key:
            sys.exit("ZETARIS_API_KEY is not set in .env. Nothing was sent.")

    def run(self, sql: str, limit: int = 1000) -> tuple[dict | None, float, str | None]:
        if ";" in sql:
            return None, 0.0, "refused locally: one statement per call, no semicolon"
        body = json.dumps({"queryId": str(uuid.uuid4()), "sql": sql,
                           "source": "SqlEditor", "limit": limit}).encode()
        req = urllib.request.Request(self.url, data=body, method="POST", headers={
            "Authorization": f"Bearer {self.key}", "X-Org-ID": self.org,
            "X-Request-ID": str(uuid.uuid4()), "Content-Type": "application/json"})
        start = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=self.timeout, context=SSL_CTX) as resp:
                return json.loads(resp.read()), time.monotonic() - start, None
        except urllib.error.HTTPError as exc:
            return None, time.monotonic() - start, f"HTTP {exc.code}: {exc.read().decode()[:300]}"
        except Exception as exc:  # noqa: BLE001
            return None, time.monotonic() - start, f"{type(exc).__name__}: {exc}"


def already_exists(error: str) -> bool:
    low = error.lower()
    return any(w in low for w in ("already exist", "alreadyexists", "duplicate"))


# --------------------------------------------------------------------------- #
# SQL
# --------------------------------------------------------------------------- #


def one_statement(sql: str) -> str:
    collapsed = " ".join(sql.split())
    assert ";" not in collapsed, collapsed
    return collapsed


def create_database(db: str, description: str) -> str:
    # DESCRIBE BY accepts letters, digits, spaces and _ . - , only
    # (REFERENCE_NOTES 1.2), so the description is kept plain deliberately.
    return one_statement(f'CREATE LIGHTNING DATABASE {db} DESCRIBE BY "{description}"')


def create_rest_table(db: str, table: str, url: str) -> str:
    return one_statement(
        f'CREATE LIGHTNING REST TABLE {table} FROM {db} REQUEST( '
        f'endpoint "{url}", method "get", response_type "json", '
        f'http_encoding "URLENCODED" ) HEADER ( ) BODY ()'
    )


def harmonised_select(source: str) -> str:
    """The `SELECT` list that turns one exploded silo row into PLAN 2.3's shape."""
    parts: list[str] = []
    for column in HARMONISED_COLUMNS:
        mapping = HARMONISED_MAP[column].get(source)
        if mapping is None:
            parts.append(f"CAST(NULL AS STRING) AS {column}")
        elif isinstance(mapping, tuple):
            parts.append(f"{sql_literal(mapping[1])} AS {column}")
        else:
            parts.append(f"r.{mapping} AS {column}")
    return ", ".join(parts)


def create_silo_view(db: str, table: str, view: str, source: str) -> str:
    return one_statement(
        f"CREATE SCHEMASTORE VIEW {view.split('.', 1)[1]} WITH CONTAINER {CONTAINER} AS "
        f"SELECT {harmonised_select(source)} "
        f"FROM {db}.{table} LATERAL VIEW explode(records) AS r"
    )


def create_reference_view(db: str, table: str, view: str, columns: tuple[str, ...]) -> str:
    select = ", ".join(f"r.{c} AS {c}" for c in columns)
    return one_statement(
        f"CREATE SCHEMASTORE VIEW {view.split('.', 1)[1]} WITH CONTAINER {CONTAINER} AS "
        f"SELECT {select} FROM {db}.{table} LATERAL VIEW explode(records) AS r"
    )


def create_all_sources() -> str:
    """A plain `UNION ALL` of the four already-harmonised views.

    Harmonising one level down is what makes PLAN 2.1's fallback ("if the union
    view fails, query the four views separately") a one-line change instead of a
    rewrite. Confirmed working on 24 Oct: 4200 rows in 2.3 s.
    """
    columns = ", ".join(HARMONISED_COLUMNS)
    union = " UNION ALL ".join(f"SELECT {columns} FROM {SOURCE_VIEWS[s]}"
                               for s in ("emr", "gp", "pharmacy", "patient"))
    return one_statement(
        f"CREATE SCHEMASTORE VIEW {ALL_SOURCES_VIEW.split('.', 1)[1]} "
        f"WITH CONTAINER {CONTAINER} AS {union}"
    )


def plan_statements(with_tga: bool = False) -> list[tuple[str, str]]:
    """Every statement, in order. `(label, sql)`. Q4's TGA table only if asked."""
    settings = get_settings()
    base = settings.datasvc_public_url.rstrip("/")
    out: list[tuple[str, str]] = [("container", f"CREATE SCHEMASTORE CONTAINER {CONTAINER}")]
    for db, table, path, view, source in SILOS:
        out.append((f"{db} database", create_database(db, f"MedTrace {source} silo, synthetic")))
        out.append((f"{db}.{table} REST table", create_rest_table(db, table, base + path)))
        out.append((f"{view} view", create_silo_view(db, table, view, source)))
        out.append((f"CACHE {db}.{table}", f"CACHE TABLE {db}.{table}"))
    out.append(("MT_REF database", create_database("MT_REF", "MedTrace reference tables")))
    for db, table, path, view, columns in REFERENCES:
        out.append((f"{db}.{table} REST table", create_rest_table(db, table, base + path)))
        out.append((f"{view} view", create_reference_view(db, table, view, columns)))
        out.append((f"CACHE {db}.{table}", f"CACHE TABLE {db}.{table}"))
    out.append((f"{ALL_SOURCES_VIEW} view", create_all_sources()))
    if with_tga:
        db, table, path, view, columns = TGA
        out.append((f"{db} database", create_database(db, "MedTrace TGA known shortages")))
        out.append((f"{db}.{table} REST table", create_rest_table(db, table, base + path)))
        out.append((f"{view} view", create_reference_view(db, table, view, columns)))
        out.append((f"CACHE {db}.{table}", f"CACHE TABLE {db}.{table}"))
    return out


def inferred_fields(client: Zetaris, db: str, table: str) -> list[str] | None:
    """The struct field names Spark inferred for a REST table, or None."""
    result, _secs, error = client.run(f"DESCRIBE {db}.{table}")
    if error or not result.get("data"):
        return None
    for row in result["data"]:
        text = str(row[1]) if len(row) > 1 else ""
        if "struct<" not in text:
            continue
        inner = text.split("struct<", 1)[1].rsplit(">", 1)[0]
        return [f.split(":", 1)[0].strip() for f in inner.split(",") if ":" in f]
    return None


def served_fields(path: str, is_silo: bool) -> list[str] | None:
    """The field names datasvc would serve for that endpoint.

    Read from the file rather than over HTTP, the same way `datasvc_counts`
    does: `datasvc_public_url` is `host.docker.internal`, which resolves from
    inside the Zetaris container but not from the shell running this script.
    """
    folder = "data/synthetic/silos" if is_silo else "data/reference"
    file = pathlib.Path(folder) / f"{path.rsplit('/', 1)[1]}.json"
    if not file.exists():
        return None
    records = json.loads(file.read_text())["records"]
    return sorted(records[0]) if records else None


def view_columns(client: Zetaris, view: str) -> list[str] | None:
    """The columns a SchemaStore view actually exposes, or None."""
    result, _secs, error = client.run(f"DESCRIBE {view}")
    if error or not result.get("data"):
        return None
    return [str(row[0]) for row in result["data"]]


def view_drift(client: Zetaris) -> list[tuple[str, str, str, list[str], list[str]]]:
    """Views whose SELECT list no longer matches the columns we expect.

    A view pins its SELECT list at creation exactly as a REST table pins its
    inferred schema, so rebuilding the table is not enough -- `medtrace.nicknames`
    still exposed only `canonical, variant` after `MT_REF.nicknames_raw` had been
    rebuilt with `sex`, and `Q_REF(nicknames)` went on failing with
    UNRESOLVED_COLUMN. `COUNT(*)` passed throughout, because counting rows never
    names a column.
    """
    drifted = []
    for db, table, _path, view, source in SILOS:
        have, want = view_columns(client, view), list(HARMONISED_COLUMNS)
        if have is not None and have != want:
            drifted.append((db, table, view, have, want))
    for db, table, _path, view, columns in REFERENCES:
        have, want = view_columns(client, view), list(columns)
        if have is not None and have != want:
            drifted.append((db, table, view, have, want))
    return drifted


def recreate_view(db: str, table: str, view: str) -> str:
    """The CREATE for one view, whichever kind it is."""
    for sdb, stable, _p, sview, source in SILOS:
        if sview == view:
            return create_silo_view(sdb, stable, sview, source)
    for rdb, rtable, _p, rview, columns in REFERENCES:
        if rview == view:
            return create_reference_view(rdb, rtable, rview, columns)
    raise KeyError(view)


def schema_drift(client: Zetaris) -> list[tuple[str, str, str, list[str], list[str]]]:
    """Raw tables whose inferred schema no longer matches what datasvc serves.

    A Lightning REST table infers its schema once, when it is created, and then
    keeps it. `REFRESH TABLE` does not re-infer it -- it returns ok and changes
    nothing. So adding a column to a generated file leaves the table reading
    rows wider than its schema, and Spark fails the read with
    ArrayIndexOutOfBoundsException -- but only once the cached copy is dropped,
    which can be days later.

    That is what happened to nicknames on 24 Oct: `sex` was added by the
    name/sex correlation fix, the table kept its two-column schema, and the
    view went on serving a stale cache until a re-cache exposed it. Nothing
    raised in between, and the row count stayed plausible.
    """
    base = get_settings().datasvc_public_url.rstrip("/")
    drifted = []
    for is_silo, group in ((True, SILOS), (False, REFERENCES)):
        for db, table, path, _view, _rest in group:
            have = inferred_fields(client, db, table)
            want = served_fields(path, is_silo)
            if have is None or want is None:
                continue
            if sorted(have) != want:
                drifted.append((db, table, base + path, sorted(have), want))
    return drifted


def refresh_statements() -> list[tuple[str, str]]:
    """UNCACHE then CACHE every raw table. Creates and drops nothing.

    `CACHE TABLE` on an already-cached table is a no-op, so re-running --apply
    after regenerating the silos leaves Zetaris serving the previous
    generation. That is not theoretical: it happened on 24 Oct, and the only
    symptom was that patient names in the live views no longer matched any
    committed fixture. The cached copy has to be dropped before it is rebuilt.

    Worst case if UNCACHE succeeds and CACHE fails: the table is simply
    uncached, queries still work by re-calling datasvc, and a re-run fixes it.
    """
    out: list[tuple[str, str]] = []
    for db, table, _path, _view, _source in SILOS:
        out.append((f"UNCACHE {db}.{table}", f"UNCACHE TABLE {db}.{table}"))
        out.append((f"CACHE {db}.{table}", f"CACHE TABLE {db}.{table}"))
    for db, table, _path, _view, _columns in REFERENCES:
        out.append((f"UNCACHE {db}.{table}", f"UNCACHE TABLE {db}.{table}"))
        out.append((f"CACHE {db}.{table}", f"CACHE TABLE {db}.{table}"))
    return out


# --------------------------------------------------------------------------- #
# Verification
# --------------------------------------------------------------------------- #


def datasvc_counts() -> dict[str, int]:
    """Row counts straight from the files datasvc serves."""
    counts: dict[str, int] = {}
    for _db, _t, path, view, _s in SILOS:
        file = pathlib.Path("data/synthetic/silos") / f"{path.rsplit('/', 1)[1]}.json"
        counts[view] = len(json.loads(file.read_text())["records"]) if file.exists() else -1
    for _db, _t, path, view, _c in REFERENCES:
        file = pathlib.Path("data/reference") / f"{path.rsplit('/', 1)[1]}.json"
        counts[view] = len(json.loads(file.read_text())["records"]) if file.exists() else -1
    counts[ALL_SOURCES_VIEW] = sum(counts[v] for _d, _t, _p, v, _s in SILOS)
    return counts


def verify(client: Zetaris) -> int:
    """`COUNT(*)` per view against the source files. A mismatch is fatal.

    REFERENCE_NOTES 1.4: a successful CREATE does not prove a usable table. The
    reference repo has sources that register fine and then fail every query.
    """
    expected = datasvc_counts()
    log("\n--- verification: COUNT(*) per view vs the files datasvc serves ---")
    failures = 0
    for view, want in expected.items():
        result, secs, error = client.run(f"SELECT COUNT(*) FROM {view}", limit=5)
        if error:
            log(f"  FAIL  {view:28} {secs:6.2f}s  {error[:120]}")
            failures += 1
            continue
        got = int(result["data"][0][0]) if result.get("data") else -1
        ok = got == want
        failures += 0 if ok else 1
        log(f"  {'ok  ' if ok else 'FAIL'}  {view:28} {secs:6.2f}s  "
            f"zetaris={got} datasvc={want}{'' if ok else '  <-- MISMATCH'}")
    return failures


def time_templates(client: Zetaris) -> int:
    """Time Q_REF and Q1 to Q3 for one patient, and return how many failed.

    This used to return None, so a template that errored was printed in the
    timing list and then ignored: the script still exited 0. `Q_REF(nicknames)`
    was broken for a day that way. `COUNT(*)` in `verify()` cannot catch it
    either, because it never names a column -- only running the real query
    does, which is the whole point of timing them here.
    """
    from app.domain.packs.medtrace import queries as q
    from app.domain.packs.medtrace.types import IdentityLink, SourceRow

    failures = 0
    log("\n--- template timings ---")
    for name in ("lexicon", "apinchs", "nicknames"):
        _r, secs, error = client.run(q.q_reference(name), limit=5000)
        log(f"  Q_REF {name:12} {secs:6.2f}s  {('FAIL ' + error[:80]) if error else 'ok'}")
        failures += bool(error)

    result, secs, error = client.run(q.q_admissions(), limit=5000)
    log(f"  Q0 admissions      {secs:6.2f}s  {('FAIL ' + error[:80]) if error else 'ok'}")
    failures += bool(error)
    if error or not result or not result.get("data"):
        log("  cannot time Q1-Q3 without an anchor from Q0")
        return failures

    headers = result["headers"]
    row = dict(zip(headers, result["data"][0]))
    anchor = SourceRow(source="emr", row_id=row.get("row_id", "EMR-000001"),
                       source_patient_id=row.get("source_patient_id", ""),
                       ihi_syn=row.get("ihi_syn") or None,
                       name_given=row.get("name_given") or None,
                       name_family=row.get("name_family") or None,
                       dob_raw=row.get("dob_text") or None)
    def outcome(result: dict | None, error: str | None) -> str:
        if error:
            return error[:90]
        total = result.get("total") if result else None
        return f"ok  rows={total}"

    r1, secs, error = client.run(q.q_identity_candidates(anchor), limit=5000)
    log(f"  Q1 identity        {secs:6.2f}s  {outcome(r1, error)}")
    failures += bool(error)

    link = IdentityLink(anchor_id=anchor.record_key, candidate_id=anchor.record_key,
                        match_weight=0.0, probability=1.0, band="auto-merge", tier="ihi_exact")
    r2, secs, error = client.run(q.q_meds_for([link]), limit=5000)
    log(f"  Q2 meds            {secs:6.2f}s  {outcome(r2, error)}")
    failures += bool(error)

    if not error and r2 and r2.get("data"):
        idx = r2["headers"].index("row_id")
        ids = [r[idx] for r in r2["data"][:20]]
        r3, secs, error = client.run(q.q_verify_rows(ids), limit=5000)
        log(f"  Q3 verify ({len(ids):2} rows) {secs:6.2f}s  {outcome(r3, error)}")
        failures += bool(error)
    return failures


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #


def diff_fixtures(client: Zetaris, limit: int = 12) -> int:
    """Run the real Q1 live and diff it against the committed fixture, per patient.

    PLAN 2.9: "Once registration works, Arpon re-records them from live Zetaris
    and diffs; **any difference is a view bug**." Kept as a command rather than a
    one-off because the fixtures and the views can drift apart later -- a change
    to `HARMONISED_MAP`, a regenerated silo, an edited template.

    This is how the NULL-vs-empty-string bug was found: every row count matched,
    so nothing failed, while 409 cells differed and `SAMPLE_MODE` was quietly
    replaying the wrong shape.
    """
    from app.domain.packs.medtrace import queries as q
    from app.domain.packs.medtrace.types import SourceRow

    gt_path = pathlib.Path("data/synthetic/ground_truth.json")
    emr_path = pathlib.Path("data/synthetic/silos/emr.json")
    if not (gt_path.exists() and emr_path.exists()):
        log("\nno generated data; run `make synth` first")
        return 1
    ground_truth = json.loads(gt_path.read_text())
    emr = {r["mrn"]: r for r in json.loads(emr_path.read_text())["records"]}

    log("\n--- live Q1 vs the committed fixtures ---")
    checked = failures = 0
    for patient in ground_truth["patients"][:limit]:
        key = patient["patient_key"]
        fixture = pathlib.Path(f"tests/fixtures/medtrace/Q1__{key}.json")
        mrn = (patient["true_links"].get("emr") or [None])[0]
        if not fixture.exists() or mrn not in emr:
            continue
        row = emr[mrn]
        anchor = SourceRow(source="emr", row_id=row["row_id"], source_patient_id=mrn,
                           ihi_syn=row["ihi_syn"] or None, name_given=row["given_name"],
                           name_family=row["family_name"], dob_raw=row["dob"])
        result, secs, error = client.run(q.q_identity_candidates(anchor), limit=5000)
        checked += 1
        if error:
            log(f"  FAIL  {key}  {secs:5.2f}s  {error[:120]}")
            failures += 1
            continue
        doc = json.loads(fixture.read_text())
        same = (result["headers"] == doc["headers"]
                and sorted(map(tuple, result["data"])) == sorted(map(tuple, doc["data"])))
        failures += 0 if same else 1
        log(f"  {'ok  ' if same else 'FAIL'}  {key}  {secs:5.2f}s  "
            f"live={result['total']:4} fixture={doc['total']:4}"
            f"{'' if same else '   <-- VIEW BUG or stale fixture'}")
        if not same:
            live = {tuple(r) for r in result["data"]}
            fx = {tuple(r) for r in doc["data"]}
            for cells in list(live - fx)[:2]:
                log(f"          live only:    {cells[:7]}")
            for cells in list(fx - live)[:2]:
                log(f"          fixture only: {cells[:7]}")
    log(f"  {checked} patient(s) checked, {failures} mismatch(es)")
    return failures


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="execute (default is dry run)")
    ap.add_argument("--diff-fixtures", action="store_true",
                    help="run the real Q1 live and diff against the committed fixtures")
    ap.add_argument("--skip-exists", action="store_true",
                    help="treat 'already exists' as success, for a re-run")
    ap.add_argument("--verify-only", action="store_true", help="only count and time")
    ap.add_argument("--recreate-drifted", action="store_true",
                    help="DROP and re-create only the REST tables whose inferred "
                         "schema no longer matches what datasvc serves. This "
                         "drops objects -- ask Arpon first")
    ap.add_argument("--refresh", action="store_true",
                    help="re-cache the raw tables after regenerating the data; "
                         "creates and drops nothing")
    ap.add_argument("--with-tga", action="store_true",
                    help="also register Q4's TGA shortage table. Only once its licence "
                         "is recorded in docs/DATA_LICENCES.md")
    args = ap.parse_args()

    settings = get_settings()
    statements = plan_statements(with_tga=args.with_tga)

    log(f"Zetaris     {settings.zetaris_rest_url}")
    log(f"datasvc     {settings.datasvc_public_url}   <- goes into the REST tables verbatim")
    log(f"container   {CONTAINER}")
    log(f"statements  {len(statements)}")

    if args.diff_fixtures:
        return 1 if diff_fixtures(Zetaris()) else 0

    if args.recreate_drifted:
        client = Zetaris()
        tables, views = schema_drift(client), view_drift(client)
        if not tables and not views:
            log("\n--- no drift: every REST table and view matches what datasvc serves ---")
            return 0
        failures = 0

        if tables:
            log(f"\n--- {len(tables)} table(s) drifted; dropping and re-creating ---")
        for db, table, url, have, want in tables:
            log(f"  {db}.{table}: inferred {have} but datasvc serves {want}")
            for label, sql in (("DROP", f"DROP LIGHTNING DATABASE TABLE {db}.{table}"),
                               ("CREATE", create_rest_table(db, table, url)),
                               ("CACHE", f"CACHE TABLE {db}.{table}")):
                _result, secs, error = client.run(sql)
                if error:
                    log(f"    FAIL  {label:7} {secs:6.2f}s  {error[:160]}")
                    failures += 1
                    break
                log(f"    ok    {label:7} {secs:6.2f}s")

        # Re-read: rebuilding a table can change what its view should expose,
        # and a view pins its SELECT list at creation just as a table pins its
        # inferred schema. Rebuilding the table alone left medtrace.nicknames
        # exposing two columns and Q_REF failing on the third.
        views = view_drift(client)
        if views:
            log(f"\n--- {len(views)} view(s) drifted; dropping and re-creating ---")
        for db, table, view, have, want in views:
            log(f"  {view}: exposes {have} but should expose {want}")
            for label, sql in (("DROP", f"DROP VIEW {view}"),
                               ("CREATE", recreate_view(db, table, view))):
                _result, secs, error = client.run(sql)
                if error:
                    log(f"    FAIL  {label:7} {secs:6.2f}s  {error[:160]}")
                    failures += 1
                    break
                log(f"    ok    {label:7} {secs:6.2f}s")

        # all_sources is a UNION ALL over the four silo views, so if any of
        # them was just replaced it has to be rebuilt on top of the new ones.
        if any(view in {v for _d, _t, _p, v, _s in SILOS} for _d, _t, view, _h, _w in views):
            log(f"\n--- rebuilding {ALL_SOURCES_VIEW} on the new silo views ---")
            for label, sql in (("DROP", f"DROP VIEW {ALL_SOURCES_VIEW}"),
                               ("CREATE", create_all_sources())):
                _result, secs, error = client.run(sql)
                if error:
                    log(f"    FAIL  {label:7} {secs:6.2f}s  {error[:160]}")
                    failures += 1
                    break
                log(f"    ok    {label:7} {secs:6.2f}s")

        failures += verify(client)
        failures += time_templates(client)
        return 1 if failures else 0

    if args.refresh:
        client = Zetaris()
        log("\n--- refreshing cached tables (no object is created or dropped) ---")
        failures = 0
        for label, sql in refresh_statements():
            _result, secs, error = client.run(sql)
            # UNCACHE on a table that was never cached is not a problem.
            if error and label.startswith("UNCACHE"):
                log(f"  skip  {label:34} {secs:6.2f}s  {error[:80]}")
                continue
            if error:
                log(f"  FAIL  {label:34} {secs:6.2f}s  {error[:200]}")
                failures += 1
                continue
            log(f"  ok    {label:34} {secs:6.2f}s")
        failures += verify(client)
        failures += diff_fixtures(client, limit=6)
        return 1 if failures else 0

    if args.verify_only:
        client = Zetaris()
        failures = verify(client)
        failures += time_templates(client)
        failures += diff_fixtures(client, limit=6)
        return 1 if failures else 0

    if not args.apply:
        log("\n=== DRY RUN -- nothing is sent. Re-run with --apply. ===\n")
        for label, sql in statements:
            log(f"-- {label}")
            log(f"{sql}\n")
        log("=== end of dry run. Review the endpoints above, then --apply. ===")
        return 0

    client = Zetaris()
    log("\n--- applying ---")
    failures = 0
    for label, sql in statements:
        result, secs, error = client.run(sql)
        if error and args.skip_exists and already_exists(error):
            log(f"  skip  {label:34} {secs:6.2f}s  already exists")
            continue
        if error:
            log(f"  FAIL  {label:34} {secs:6.2f}s  {error[:200]}")
            failures += 1
            # A failed CREATE makes everything downstream of it meaningless.
            log("\nStopping. Later statements depend on this one.")
            break
        log(f"  ok    {label:34} {secs:6.2f}s")

    if failures:
        return 1
    failures = verify(client)
    failures += time_templates(client)
    if failures:
        log(f"\n{failures} view(s) failed verification. A successful CREATE does not prove "
            f"a usable table -- do not rely on this registration.")
        return 1
    log("\nall views registered and verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
