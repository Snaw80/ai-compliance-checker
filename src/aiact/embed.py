"""Dense embeddings with BGE-M3 through Ollama, cached on disk.

    ollama pull bge-m3
    uv run python -m aiact.embed          # embed chunks that have no embedding yet

`aiact.ingest` calls `fill()` after every load, so a full corpus refresh only re-embeds
chunks whose text changed (the cache is keyed by model + input text).
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import httpx

from aiact.db import connect, to_pgvector

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "bge-m3")
DIM = 1024  # must match chunks.embedding vector(1024)
CACHE = Path(f"data/corpus/embeddings-{EMBED_MODEL.replace(':', '_')}.jsonl")


def embed(texts: list[str], batch: int = 16) -> list[list[float]]:
    out: list[list[float]] = []
    with httpx.Client(timeout=300) as client:
        for i in range(0, len(texts), batch):
            r = client.post(f"{OLLAMA_URL}/api/embed",
                            json={"model": EMBED_MODEL, "input": texts[i:i + batch]})
            r.raise_for_status()
            out += r.json()["embeddings"]
    if out and len(out[0]) != DIM:
        raise ValueError(f"{EMBED_MODEL} returns {len(out[0])} dims, schema expects {DIM}")
    return out


def embed_query(q: str) -> list[float]:
    return embed([q])[0]


def chunk_input(context: str, text: str) -> str:
    """What gets embedded: the contextual header, then the chunk text."""
    return f"{context}\n\n{text}"


def _key(s: str) -> str:
    return hashlib.sha256(f"{EMBED_MODEL}\n{s}".encode()).hexdigest()


def _load_cache() -> dict[str, list[float]]:
    if not CACHE.exists():
        return {}
    with CACHE.open() as f:
        return {row["k"]: row["v"] for row in map(json.loads, f)}


def fill(only_missing: bool = True) -> int:
    """Embed chunks in Postgres (using the cache where possible). Returns the number updated."""
    cache = _load_cache()
    with connect() as conn, conn.cursor() as cur:
        cur.execute("select chunk_id, context, text from chunks"
                    + (" where embedding is null" if only_missing else ""))
        rows = [(cid, chunk_input(ctx, txt)) for cid, ctx, txt in cur.fetchall()]
        todo = [(cid, s) for cid, s in rows if _key(s) not in cache]
        if todo:
            print(f"embedding {len(todo)} chunks with {EMBED_MODEL} ({len(rows) - len(todo)} cached)")
            vecs = embed([s for _, s in todo])
            CACHE.parent.mkdir(parents=True, exist_ok=True)
            with CACHE.open("a") as f:
                for (_, s), v in zip(todo, vecs):
                    cache[_key(s)] = v
                    f.write(json.dumps({"k": _key(s), "v": v}) + "\n")
        cur.executemany("update chunks set embedding = %s::vector where chunk_id = %s",
                        [(to_pgvector(cache[_key(s)]), cid) for cid, s in rows])
        conn.commit()
    return len(rows)


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="re-write every embedding, not only missing ones")
    n = fill(only_missing=not ap.parse_args().all)
    print(f"{n} chunk embeddings written")
