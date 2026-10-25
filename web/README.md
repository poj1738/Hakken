# MedTrace web UI

One screen, Vite + React + TypeScript (PLAN §6). It displays what the API returns
and never computes a clinical fact.

```bash
cd web
npm install
cp .env.example .env.local   # VITE_API_MODE=mock|live, VITE_API_URL
npm run dev                  # http://localhost:5173
npm run build                # typecheck + production build
```

**Mock mode** (the default) replays the hand-written examples in
`tests/fixtures/api/` with fake delays, so the timeline animates and no backend is
needed. They are not real runs, and the screen says so.

| Patient | Mock replay |
|---|---|
| MRN0000001 | `run_P0001_done.json` |
| MRN0000001 with `?mock=gp_not_found` | `run_P0001_gp_not_found.json` |
| MRN0000015 | `run_P0002_needs_review.json` (the file kept its old name) |

Other patients have no example, so mock mode says so instead of inventing a
result. For MRN0000015, deciding every identity candidate returns
`src/placeholders/resumed_run.PLACEHOLDER.json`: a **placeholder**, not an
API example, because no resumed-run example exists yet. It says so on screen and
shows no grid or flags. Replace it once Arnav records a real resumed run. Feedback returns `feedback_response.json` only for
the recorded verdict (reject F-006 as "Source outdated", GP daily dose); any other verdict is
acknowledged with no trust change.

**Live mode** calls `GET /status`, `GET /patients`, `POST /run`, `GET /run/{id}`
(polled), `POST /run/{id}/identity` and `POST /feedback` on `VITE_API_URL`. Every
request has a 30 s timeout and polling stops after 15 minutes.

`src/types.ts` is hand-copied from `app/schemas.py` and
`app/domain/packs/medtrace/types.py`. Update it when a schema change is announced
in `docs/HANDOFF.md`.
