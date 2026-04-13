#!/usr/bin/env sh
set -e
# Fly.io / Docker: SQLite + Chroma need these directories on the mounted volume.
if [ -n "${INTELLIDIGEST_PERSIST_DIR:-}" ]; then
  mkdir -p "${INTELLIDIGEST_PERSIST_DIR}/data" "${INTELLIDIGEST_PERSIST_DIR}/chroma_db" || true
fi
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"
exec uvicorn server:app --host "$HOST" --port "$PORT"
