"""
Resolved paths for SQLite (`data/`) and Chroma (`chroma_db/`).

Set INTELLIDIGEST_PERSIST_DIR (e.g. /data on Fly.io) to put both under one volume.
"""

from __future__ import annotations

import os

_REPO_ROOT = os.path.dirname(os.path.abspath(__file__))


def persist_root() -> str | None:
    p = (os.getenv("INTELLIDIGEST_PERSIST_DIR") or "").strip().rstrip("/\\")
    return p or None


def data_dir() -> str:
    if persist_root():
        return os.path.join(persist_root(), "data")
    return os.path.join(_REPO_ROOT, "data")


def chroma_persist_dir() -> str:
    if persist_root():
        return os.path.join(persist_root(), "chroma_db")
    return os.path.join(_REPO_ROOT, "chroma_db")
