#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_PID=""
FRONTEND_PID=""

cleanup() {
  if [[ -n "${BACKEND_PID}" ]]; then kill "${BACKEND_PID}" 2>/dev/null || true; fi
  if [[ -n "${FRONTEND_PID}" ]]; then kill "${FRONTEND_PID}" 2>/dev/null || true; fi
}

trap cleanup EXIT INT TERM

if [[ ! -x "${PROJECT_ROOT}/.venv/bin/uvicorn" ]]; then
  echo "Missing backend environment. Run: python -m venv .venv && .venv/bin/python -m pip install -r backend/requirements.txt" >&2
  exit 1
fi

if [[ ! -d "${PROJECT_ROOT}/frontend/node_modules" ]]; then
  echo "Missing frontend dependencies. Run: npm --prefix frontend install" >&2
  exit 1
fi

echo "Starting backend at http://localhost:8000"
(
  cd "${PROJECT_ROOT}"
  .venv/bin/uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
) &
BACKEND_PID=$!

echo "Starting dashboard at http://localhost:5173"
(
  cd "${PROJECT_ROOT}/frontend"
  npm run dev -- --host 127.0.0.1 --port 5173
) &
FRONTEND_PID=$!

echo "Open http://localhost:5173 in your browser. Press Ctrl+C to stop both services."
wait -n "${BACKEND_PID}" "${FRONTEND_PID}"
