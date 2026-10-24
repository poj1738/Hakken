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

_cache: dict[pathlib.Path, dict[str, Any]] = {}


def _load(path: pathlib.Path) -> dict[str, Any]:
    """Read and cache one file.

    Cached in-process because a Lightning REST table may re-call its source on
    every query (`REFERENCE_NOTES` 1.3). The files are generated and immutable
    between runs of `make synth`, so caching cannot serve stale data within a
    process -- and it stops a demo re-reading megabytes per query.
    """
    if path not in _cache:
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
        _cache[path] = payload
    return _cache[path]


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
