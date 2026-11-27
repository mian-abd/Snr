# The public demo: one container serves the built site and the API.
# Provider keys are never baked in; the host sets them as environment variables at run time.

# ---- Stage 1: build the frontend ----
FROM node:24-slim AS frontend
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---- Stage 2: the API, with the built site ----
FROM python:3.12-slim AS app
COPY --from=ghcr.io/astral-sh/uv:0.12.21 /uv /usr/local/bin/uv

ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app
# Dependencies first, so a code change does not reinstall them. A plain sync leaves out the
# optional "dev" extra (test and lint tools).
COPY backend/pyproject.toml backend/uv.lock backend/README.md backend/
RUN uv sync --project backend --frozen --no-dev --no-install-project

COPY backend/app backend/app
COPY data data
COPY --from=frontend /build/frontend/dist frontend/dist

RUN useradd --no-create-home --shell /usr/sbin/nologin --uid 10001 app \
    && mkdir -p data/local \
    && chown app data/local
USER app

# Public mode limits live provider calls and turns off the paid Lab tools. Set OPENROUTER_API_KEY
# (and any limit overrides) in the host's variables; see docs/deploy.md.
ENV PUBLIC_MODE=true
EXPOSE 8000
# One worker: the daily live-call allowances are counted in memory.
CMD uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'
