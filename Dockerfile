# =============================================================================
# One container: the Starlette app serves /v1 AND the built React SPA.
#
# WHY ONE CONTAINER
#   app/api.py mounts app/static at "/" and has no CORS middleware, so serving
#   the bundle same-origin is both the simplest and the only CORS-free option.
#   Sessions (app/auth.py SessionRegistry) are in-memory, so this must run as a
#   single long-lived process — never serverless, never more than one instance.
#
# The SPA is copied into app/static at BUILD time. We deliberately do not run
# frontend/scripts/sync-into-app.sh and commit its output; that script's header
# forbids automating it, and the git tree stays clean this way.
# =============================================================================

# --- stage 1: build the SPA (reads frontend/.env.production -> live mode) ---
FROM node:22-slim AS web
WORKDIR /w
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# --- stage 2: the Python app ---
FROM python:3.13-slim
COPY --from=ghcr.io/astral-sh/uv:0.9.5 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

WORKDIR /srv

# Dependencies first, as their own cache layer: --no-install-project means this
# layer survives every source edit and only rebuilds when the lock changes.
COPY pyproject.toml uv.lock README.md LICENSE ./
RUN uv sync --locked --no-group dev --no-install-project

# The wheel packages from [tool.hatch.build.targets.wheel]. fixtures/ is needed
# even in live mode: app/deps.py imports from it at module load.
COPY contracts/ contracts/
COPY fixtures/ fixtures/
COPY tools/ tools/
COPY scrapers/ scrapers/
COPY er/ er/
COPY scoring/ scoring/
COPY sources/ sources/
COPY app/ app/
RUN uv sync --locked --no-group dev

# Replace the upstream vanilla SPA with the React build.
RUN rm -rf app/static/*
COPY --from=web /w/dist/ app/static/

EXPOSE 8080
# No --fixtures: app/__main__.py then takes the build_live_deps path (real
# Databricks). Requires DATABRICKS_* and APP_PASSWORD in the environment.
CMD ["uv", "run", "--no-sync", "python", "-m", "app", "serve", "--host", "0.0.0.0", "--port", "8080"]
