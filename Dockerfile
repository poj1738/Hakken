# Multi-stage: build the UI, then a slim CPU-only runtime.
# Secrets are never baked in -- pass them at runtime with --env-file .env.

FROM node:20-slim AS web
WORKDIR /web
COPY web/package*.json ./
RUN if [ -f package.json ]; then npm ci --no-audit --no-fund; fi
COPY web/ ./
RUN if [ -f package.json ]; then npm run build; else mkdir -p dist; fi

FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependencies at build time, nothing installed at runtime.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY datasvc/ ./datasvc/
COPY data/ ./data/
COPY scripts/ ./scripts/
COPY input_examples/ ./input_examples/
COPY run.py ./
COPY --from=web /web/dist ./web/dist

RUN mkdir -p logs .state && \
    adduser --disabled-password --gecos "" hakken && \
    chown -R hakken:hakken /app
USER hakken

EXPOSE 8000
CMD ["python", "run.py", "serve"]
