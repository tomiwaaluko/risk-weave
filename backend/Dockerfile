FROM ghcr.io/astral-sh/uv:0.11.20@sha256:eaa5f1a3305307aaf9e67fe2bbba1d85ebbb2d8a63bce23af21797bfafbe0f8b AS uv

FROM python:3.12-slim@sha256:423ed6ab25b1921a477529254bfeeabf5855151dc2c3141699a1bfc852199fbf AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

COPY --from=uv /uv /uvx /bin/
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

FROM python:3.12-slim@sha256:423ed6ab25b1921a477529254bfeeabf5855151dc2c3141699a1bfc852199fbf

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app/src:/app"

WORKDIR /app

COPY --from=builder /app/.venv ./.venv
COPY backend/src ./src
COPY backend/riskweave ./riskweave
COPY backend/alembic ./alembic
COPY backend/alembic.ini ./alembic.ini
COPY data/universe ./data/universe
# The committed CRE demo fixture backs /graph/seed; the loader resolves it at
# /app/data/fixtures/cre_graph.json, so it must ship in the image (RW-NFR-005).
COPY backend/data/fixtures ./data/fixtures

RUN useradd --create-home --uid 10001 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Apply migrations before serving so a fresh Postgres (e.g. docker compose's
# postgres service) has the scenario/run/snapshot tables RIS-30 needs before
# the app can use SCENARIO_STORE_BACKEND=postgres. Railway's railway.json
# start command does the same; this keeps docker compose in parity.
CMD ["sh", "-c", "alembic upgrade head && uvicorn riskweave_api.main:app --app-dir src --host 0.0.0.0 --port 8000"]
