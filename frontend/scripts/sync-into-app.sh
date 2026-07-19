#!/usr/bin/env bash
# =============================================================================
# sync-into-app.sh — build the React frontend and install it into app/static/
#
# WHAT THIS DOES
#   1. `npm run build` in frontend/ (Vite -> frontend/dist).
#   2. On first run, moves the CURRENT app/static/* (the upstream vanilla SPA:
#      index.html, app.js, style.css) into app/static.pre-react-backup/ so it
#      is preserved and restorable.
#   3. rsync-copies frontend/dist/* into app/static/ so the in-repo Starlette
#      server (`uv run python -m app serve --fixtures`) serves the React app
#      same-origin at http://127.0.0.1:<port>/ — no CORS, no dev proxy.
#
# WHY IT EXISTS
#   app/api.py mounts app/static as the SPA root. Replacing its contents is
#   how the React bundle rides the real /v1 API in one process. This REPLACES
#   the upstream vanilla SPA *locally only*.
#
# SAFETY RULES
#   * NEVER run this automatically (no CI, no postinstall, no git hook).
#   * COORDINATE with the team before committing any app/static changes —
#     app/ is the upstream Python app's territory.
#   * The script refuses to run while the git working tree under app/ has
#     changes outside app/static/ and app/static.pre-react-backup/ (the two
#     paths this script manages), so it can never clobber in-progress app work.
#   * Idempotent: the backup is taken once; later runs only re-sync dist/.
#
# RESTORE
#   rm -rf app/static && mv app/static.pre-react-backup app/static
# =============================================================================
set -euo pipefail

FRONTEND_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_ROOT="$(cd "${FRONTEND_DIR}/.." && pwd)"
APP_STATIC="${REPO_ROOT}/app/static"
BACKUP_DIR="${REPO_ROOT}/app/static.pre-react-backup"
DIST_DIR="${FRONTEND_DIR}/dist"

if [[ ! -d "${APP_STATIC}" ]]; then
  echo "error: ${APP_STATIC} not found — run from a checkout containing app/" >&2
  exit 1
fi

# Refuse if app/ is dirty beyond the two paths this script owns.
dirty="$(git -C "${REPO_ROOT}" status --porcelain -- app/ \
  | grep -vE ' app/static(\.pre-react-backup)?/' || true)"
if [[ -n "${dirty}" ]]; then
  echo "error: app/ has uncommitted changes outside app/static — refusing to sync:" >&2
  echo "${dirty}" >&2
  exit 1
fi

echo "==> Building frontend (vite)"
(cd "${FRONTEND_DIR}" && npm run build)

if [[ ! -f "${DIST_DIR}/index.html" ]]; then
  echo "error: ${DIST_DIR}/index.html missing after build" >&2
  exit 1
fi

if [[ -d "${BACKUP_DIR}" ]]; then
  echo "==> Backup already exists at ${BACKUP_DIR} — leaving it untouched"
else
  echo "==> Backing up upstream SPA to ${BACKUP_DIR}"
  mkdir -p "${BACKUP_DIR}"
  # Move everything (including dotfiles) out of app/static.
  find "${APP_STATIC}" -mindepth 1 -maxdepth 1 -exec mv {} "${BACKUP_DIR}/" \;
fi

echo "==> Syncing ${DIST_DIR}/ -> ${APP_STATIC}/"
rsync -a --delete "${DIST_DIR}/" "${APP_STATIC}/"

echo "==> Done. Serve it with: uv run python -m app serve --fixtures"
echo "    Restore upstream SPA: rm -rf app/static && mv app/static.pre-react-backup app/static"
