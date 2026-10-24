#!/usr/bin/env python3
"""Fetch the PBS reference tables from the public API v3. Read-only, resumable.

**Why the API and not the CSV bundle.** `docs/PLAN_2026-10-24.md` section 3 names
the monthly "PBS API CSV files" ZIP as the backbone. That bundle is published in
the embargo area and needs an HPP/myID login, and the legacy XML and text files
were discontinued on 1 May 2026. The **public API v3 is free and needs no
login** -- it needs a `subscription-key` header, and the published unregistered
key works. See `docs/DECISIONS.md`, 24 Oct.

**Rate limit: one request per 20 seconds, shared by every user of the public
key.** So this script pulls **whole tables with large pages** and never makes a
per-item call. PLAN section 3's "do not loop the public API" rule is about
per-drug lookups; a handful of whole-table pulls is the intended use. Pages are
cached on disk, so a re-run costs nothing and an interrupted run resumes.

Licence: this prints the `_meta` copyright block verbatim, which PLAN section 3
requires reading before any PBS-derived row is committed. The output goes to
`data/reference/raw/`, which is **gitignored** -- see `docs/DATA_LICENCES.md`.

Usage:
    python3 scripts/fetch_reference.py                # auto-detect the schedule
    python3 scripts/fetch_reference.py --schedule 4751
    python3 scripts/fetch_reference.py --tables items # just one table
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import pathlib
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

try:
    import certifi

    SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:  # pragma: no cover - certifi ships with httpx
    SSL_CTX = ssl.create_default_context()

DEFAULT_BASE = "https://data-api.health.gov.au/pbs/api/v3"
MIN_INTERVAL_S = 21.0
PAGE_SIZE = 5000
READ_TIMEOUT_S = 300
MAX_ATTEMPTS = 3
RETRY_WAIT_S = 30.0

#: Only the columns we use. Field selection is *selection*, not modification --
#: it keeps the payload small enough that a page completes inside the timeout.
TABLES: dict[str, str] = {
    # Exactly the nine fields measured to complete a 5000-row page in ~50 s.
    # Asking for thirteen timed out at 300 s, so this list is a measurement, not
    # a preference -- widen it only after re-measuring.
    "items": (
        "pbs_code,drug_name,brand_name,li_form,pack_size,"
        "maximum_quantity_units,number_of_repeats,manner_of_administration,li_item_id"
    ),
    "item-atc-relationships": "pbs_code,atc_code,atc_priority_pct",
    "amt-items": "li_item_id,amt_code,concept_type_code,preferred_term,pbs_preferred_term",
}

_last_call = 0.0


def log(msg: str) -> None:
    # flush: a block-buffered script looks exactly like a hung one.
    print(msg, flush=True)


def _key() -> str:
    key = os.environ.get("PBS_SUBSCRIPTION_KEY", "").strip()
    if not key:
        env = pathlib.Path(".env")
        if env.exists():
            for line in env.read_text().splitlines():
                if line.startswith("PBS_SUBSCRIPTION_KEY="):
                    key = line.split("=", 1)[1].strip()
                    break
    if not key:
        sys.exit(
            "PBS_SUBSCRIPTION_KEY is not set. Put the PBS public API key in .env\n"
            "(see .env.example). It is a public key, but it stays out of git so the\n"
            "secret scan keeps meaning something."
        )
    return key


def _request(base: str, path: str, params: dict[str, object], accept: str) -> bytes:
    """One rate-limited GET. Never logs the key."""
    global _last_call
    wait = MIN_INTERVAL_S - (time.monotonic() - _last_call)
    if wait > 0:
        log(f"      (rate limit: waiting {wait:.0f}s)")
        time.sleep(wait)
    url = f"{base}/{path}?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"subscription-key": _key(), "Accept": accept})
    # Bounded retry: a large page occasionally stalls rather than erroring, and a
    # single stall should not throw away the pages already on disk.
    last: Exception | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        _last_call = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=READ_TIMEOUT_S, context=SSL_CTX) as resp:
                return resp.read()
        except urllib.error.HTTPError:
            raise  # a status code is an answer; do not retry it blindly
        except Exception as exc:  # noqa: BLE001 - transport stall
            last = exc
            if attempt < MAX_ATTEMPTS:
                log(f"      attempt {attempt} failed ({type(exc).__name__}); retrying after {RETRY_WAIT_S}s")
                time.sleep(RETRY_WAIT_S)
    raise RuntimeError(f"{path}: {MAX_ATTEMPTS} attempts failed; last was {last}")


def latest_schedule(base: str, out: pathlib.Path) -> int:
    """The current `schedule_code`, plus the copyright read PLAN section 3 requires."""
    raw = _request(base, "schedules", {"limit": 5, "get_latest_schedule_only": "true"}, "application/json")
    doc = json.loads(raw)
    messages = doc["_meta"]["info"].get("messages", [])
    copyright_lines: list[str] = []
    for m in messages:
        if m.get("type") == "copyright":
            copyright_lines = list(m.get("content", []))
    log("\n--- PBS _meta copyright block, verbatim -------------------------------")
    for line in copyright_lines:
        log(f"  {line}")
    log("----------------------------------------------------------------------\n")
    (out / "pbs_copyright.txt").write_text("\n".join(copyright_lines) + "\n", encoding="utf-8")
    rows = doc.get("data", [])
    if not rows:
        sys.exit("/schedules returned no rows; cannot determine the current schedule.")
    code = max(int(r["schedule_code"]) for r in rows)
    log(f"current schedule_code = {code}")
    return code


def fetch_table(base: str, table: str, schedule: int, out: pathlib.Path) -> pathlib.Path:
    """Page a whole table to CSV on disk. Resumable: existing pages are kept."""
    fields = TABLES[table]
    page = 1
    total: int | None = None
    parts: list[pathlib.Path] = []
    while True:
        part = out / f"pbs_{table}_{schedule}_p{page:02d}.csv"
        if part.exists() and part.stat().st_size > 0:
            log(f"  {table} page {page}: cached ({part.stat().st_size // 1024} KB)")
        else:
            log(f"  {table} page {page}: fetching...")
            body = _request(
                base, table,
                {"schedule_code": schedule, "limit": PAGE_SIZE, "page": page, "fields": fields},
                "text/csv",
            )
            part.write_bytes(body)
            log(f"  {table} page {page}: {len(body) // 1024} KB")
        rows = sum(1 for _ in csv.reader(io.StringIO(part.read_text(encoding="utf-8-sig")))) - 1
        parts.append(part)
        if rows < PAGE_SIZE:
            total = (page - 1) * PAGE_SIZE + rows
            break
        page += 1
        if page > 40:  # bounded: every loop is bounded (CLAUDE.md)
            log(f"  {table}: stopping at 40 pages, which should not happen")
            break

    # Concatenate, dropping the per-row _meta/_links columns. The copyright is
    # kept once, in pbs_copyright.txt, rather than repeated on every row.
    combined = out / f"pbs_{table}_{schedule}.csv"
    wanted = fields.split(",")
    with combined.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=wanted, extrasaction="ignore")
        writer.writeheader()
        written = 0
        for part in parts:
            reader = csv.DictReader(io.StringIO(part.read_text(encoding="utf-8-sig")))
            for row in reader:
                writer.writerow({k: row.get(k, "") for k in wanted})
                written += 1
    log(f"  {table}: {written} rows -> {combined}  (reported total {total})")
    return combined


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base", default=os.environ.get("PBS_API_BASE", DEFAULT_BASE))
    ap.add_argument("--schedule", type=int, default=None)
    ap.add_argument("--out", default="data/reference/raw")
    ap.add_argument("--tables", nargs="*", default=list(TABLES))
    args = ap.parse_args()

    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    log(f"PBS public API v3 at {args.base}")
    log(f"output: {out}/  (gitignored -- see docs/DATA_LICENCES.md)")

    try:
        schedule = args.schedule or latest_schedule(args.base, out)
        for table in args.tables:
            if table not in TABLES:
                log(f"unknown table {table!r}; known: {sorted(TABLES)}")
                return 2
            log(f"\n{table} (total pages unknown until the last short page)")
            fetch_table(args.base, table, schedule, out)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")[:400]
        log(f"\nFAILED HTTP {exc.code}: {body}")
        if exc.code in (401, 403):
            log("\nThe public subscription key was rejected. Stopping -- do not retry in a\n"
                "loop. Either the published key has been revoked or it needs rotating; a\n"
                "free key can be registered at data-api-portal.health.gov.au.")
        return 1
    except Exception as exc:  # noqa: BLE001 - report honestly and stop
        log(f"\nFAILED {type(exc).__name__}: {exc}")
        return 1

    log(f"\ndone. schedule {schedule}. Next: python3 scripts/build_lexicon.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
