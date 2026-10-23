# Pre-existing components

Anything created before the build window opened (**2026-10-22 00:00 UTC**) must be
declared here. Open-source libraries do not need declaring.

| Component | Origin | Date | How it is used |
|---|---|---|---|
| H-MEM specification + conformance vectors | `github.com/Meterless/Meterless` (Apache-2.0) | pre-existing | Read-only reference in gitignored `.refs/`. Our Python implementation is written during the window; the official `vectors.json` is copied into `tests/engines/vectors/` with an Apache-2.0 attribution header. |
| World Model specification + conformance runner | `github.com/Meterless/Meterless` (Apache-2.0) | pre-existing | Same: read-only reference; the 8 inline checks are translated to pytest during the window. |
| Zetaris getting-started repo | `github.com/zetaris/getting-started` | pre-existing | Read-only reference for the REST call shape and the REST-table registration recipe. Not shipped. |
| `zetaris-platform` Docker install | Sponsor-provided | installed 2026-10-12 | The local Zetaris instance. Infrastructure, not part of our submission. |

**Everything in `app/`, `datasvc/`, `scripts/`, `tests/`, `data/`, `web/` and `docs/`
was written inside the build window.**

As of this commit no pre-existing code of our own is included.
