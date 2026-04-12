"""Load markdown files from support/kb into the dedicated support Chroma collection."""

import os
import re

from support.config import SUPPORT_KB_DIR
from vectorstore.engine import VectorStoreEngine

_MAX_CHUNK = 1000


def _chunk_text(text: str) -> list[str]:
    text = text.strip()
    if not text:
        return []
    parts = re.split(r"\n{2,}", text)
    chunks: list[str] = []
    buf = ""
    for p in parts:
        p = p.strip()
        if not p:
            continue
        if len(buf) + len(p) + 2 <= _MAX_CHUNK:
            buf = f"{buf}\n\n{p}" if buf else p
        else:
            if buf:
                chunks.append(buf)
            if len(p) > _MAX_CHUNK:
                for i in range(0, len(p), _MAX_CHUNK):
                    chunks.append(p[i : i + _MAX_CHUNK])
                buf = ""
            else:
                buf = p
    if buf:
        chunks.append(buf)
    return chunks


def bootstrap_support_knowledge_base(engine: VectorStoreEngine) -> int:
    """Ingest support/kb/*.md if the support collection is empty."""
    if engine.get_support_collection_count() > 0:
        return 0
    if not os.path.isdir(SUPPORT_KB_DIR):
        return 0
    md_files = sorted(
        f for f in os.listdir(SUPPORT_KB_DIR) if f.lower().endswith(".md")
    )
    if not md_files:
        return 0
    total = 0
    for name in md_files:
        path = os.path.join(SUPPORT_KB_DIR, name)
        try:
            with open(path, encoding="utf-8") as f:
                raw = f.read()
        except OSError:
            continue
        for i, chunk in enumerate(_chunk_text(raw)):
            n = engine.add_support_texts(
                [chunk],
                source=f"support_kb/{name}",
                metadata_extras={"chunk_index": i, "kb": "support"},
            )
            total += n
    return total
