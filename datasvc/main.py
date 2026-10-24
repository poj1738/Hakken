"""Synthetic silo service -- what Zetaris registers as REST tables.

Serves each silo and each reference table **whole, at one fixed URL**, as
`{"records": [...]}`. Not paged, and that is forced rather than chosen: a
Lightning REST table binds **one fixed endpoint URL** with no paging parameter
(`docs/REFERENCE_NOTES.md` 1.3), so a paged endpoint cannot be registered at all.

**Two URLs reach this service, from two different networks** (`docs/DECISIONS.md`,
24 Oct):

  DATASVC_PUBLIC_URL    what ZETARIS uses. Goes verbatim into the registration
                        SQL, so it must resolve from inside the Zetaris
                        containers -- `http://host.docker.internal:8100`,
                        verified reachable (HTTP 200 in ~20 ms) on 24 Oct.
  DATASVC_INTERNAL_URL  what our own app uses. `localhost` on the host,
                        `http://datasvc:8100` under our compose file.

Getting them the wrong way round makes `CREATE LIGHTNING REST TABLE` succeed and
then every query against it fail, which is why `app/config.py` rejects a
compose-only hostname for the public one.

Read-only. This serves generated synthetic data and nothing else; it has no
database, no writes and no auth, because it holds nothing worth protecting.
"""

from __future__ import annotations

import json
import pathlib
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from app.config import get_settings

SILO_DIR = pathlib.Path("data/synthetic/silos")
REF_DIR = pathlib.Path("data/reference")

#: `GET /silos/<name>` -> the file it serves. One table per silo (PLAN 2.1).
SILOS = {"emr": "emr.json", "gp": "gp.json", "pharmacy": "pharmacy.json",
         "patient": "patient.json"}

#: `GET /ref/<name>`. `tga` is deliberately absent: Q4 is Monday and optional,
#: and registering a view over data we have not licensed would be worse than
#: shipping without it.
REFERENCES = {"lexicon": "lexicon.json", "apinchs": "apinchs.json",
              "nicknames": "nicknames.json"}

app = FastAPI(
    title="MedTrace datasvc",
    description="Serves synthetic silos and reference tables for Zetaris REST tables.",
    version="1.0.0",
)

# (path, mtime_ns, size) -> payload. See _load() for why the mtime is in the key.
_cache: dict[tuple[pathlib.Path, int, int], dict[str, Any]] = {}


def _load(path: pathlib.Path) -> dict[str, Any]:
    """Read and cache one file.

    Cached in-process because a Lightning REST table may re-call its source on
    every query (`REFERENCE_NOTES` 1.3) -- it stops a demo re-reading megabytes
    per query.

    Keyed on the file's mtime and size, not just its path. The original version
    cached on path alone, reasoning that the files are immutable between runs of
    `make synth`. They are not immutable across one: regenerating the silos
    while this process stayed up left it serving the previous generation, and
    Zetaris cached THAT, so the live views disagreed with every committed
    fixture until someone noticed the names had changed. A stale read here is
    invisible -- the row count is plausible and nothing raises.
    """
    try:
        stat = path.stat()
        key = (path, stat.st_mtime_ns, stat.st_size)
    except OSError:
        key = (path, 0, 0)
    if key not in _cache:
        if not path.exists():
            raise HTTPException(
                status_code=503,
                detail=(f"{path} does not exist. Run `make synth` (silos) or "
                        f"`make lexicon` (reference) first."),
            )
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=500, detail=f"{path} is not valid JSON: {exc}") from exc
        if not isinstance(payload, dict) or "records" not in payload:
            raise HTTPException(
                status_code=500,
                detail=f"{path} must be an object with a 'records' array; a REST table "
                       f"needs one array field to explode.",
            )
        # Drop any older generation of the same file rather than growing
        # the cache once per regeneration.
        for stale in [k for k in _cache if k[0] == path]:
            del _cache[stale]
        _cache[key] = payload
    return _cache[key]


@app.get("/healthz")
def healthz() -> dict[str, Any]:
    """Liveness, plus which files are actually present.

    Reports both URLs so a mismatched registration is visible here rather than
    as a Zetaris query that returns nothing.
    """
    settings = get_settings()
    return {
        "status": "ok",
        "public_url": settings.datasvc_public_url,
        "internal_url": settings.datasvc_internal_url,
        "silos": {name: (SILO_DIR / file).exists() for name, file in SILOS.items()},
        "references": {name: (REF_DIR / file).exists() for name, file in REFERENCES.items()},
    }


@app.get("/silos/{name}")
def silo(name: str) -> JSONResponse:
    if name not in SILOS:
        raise HTTPException(status_code=404,
                            detail=f"unknown silo {name!r}; known: {sorted(SILOS)}")
    return JSONResponse(_load(SILO_DIR / SILOS[name]))


@app.get("/ref/{name}")
def reference(name: str) -> JSONResponse:
    if name not in REFERENCES:
        raise HTTPException(status_code=404,
                            detail=f"unknown reference table {name!r}; known: {sorted(REFERENCES)}")
    return JSONResponse(_load(REF_DIR / REFERENCES[name]))


@app.get("/")
def index() -> dict[str, Any]:
    """What a human sees, and what `register_sources.py` registers."""
    return {
        "service": "MedTrace datasvc",
        "endpoints": (["/healthz"] + [f"/silos/{n}" for n in sorted(SILOS)]
                      + [f"/ref/{n}" for n in sorted(REFERENCES)]),
        "note": "Each endpoint returns the whole table as {\"records\": [...]}. "
                "Not paged: a Lightning REST table binds one fixed URL.",
    }
