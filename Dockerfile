# Multi-stage: build the UI, then a slim CPU-only runtime.
# Secrets are never baked in -- pass them at runtime with --env-file .env.

FROM node:20-slim AS web
WORKDIR /web
COPY web/package*.json ./
RUN if [ -f package.json ]; then npm ci --no-audit --no-fund; fi
COPY web/ ./
# The UI's mock mode imports the API examples through `@fixtures` -> ../tests/fixtures/api
# (web/tsconfig.json, web/vite.config.ts). From WORKDIR /web that is /tests/fixtures/api,
# so it has to exist here or tsc fails with "Cannot find module" (scan S3, 25 Oct).
COPY tests/fixtures/api/ /tests/fixtures/api/
# The image serves the UI from the API itself (app/main.py), so it calls the real API on
# the same origin; mock mode would replay hand-written examples (scan S18).
ENV VITE_API_MODE=live VITE_API_URL=
RUN if [ -f package.json ]; then npm run build; else mkdir -p dist; fi

FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DEFAULT_TIMEOUT=120 \
    HOST=0.0.0.0

WORKDIR /app

# Dependencies at build time, nothing installed at runtime.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY datasvc/ ./datasvc/
COPY data/ ./data/
COPY scripts/ ./scripts/
COPY input_examples/ ./input_examples/
# SAMPLE_MODE's replay set. It lives under tests/ because the contract tests read it
# too; data/reference/ and data/synthetic/ are gitignored, so a clean clone has nothing else.
COPY tests/fixtures/medtrace/ ./tests/fixtures/medtrace/
COPY run.py ./
COPY --from=web /web/dist ./web/dist

RUN mkdir -p logs .state && \
    adduser --disabled-password --gecos "" hakken && \
    chown -R hakken:hakken /app
USER hakken

EXPOSE 8000
CMD ["python", "run.py", "serve"]
