"""Build the corpus: parse every source, write data/corpus/chunks.jsonl, load Postgres.

    uv run python -m aiact.sources        # download (cached)
    uv run python -m aiact.ingest            # parse + load + embed (needs `ollama pull bge-m3`)
    uv run python -m aiact.ingest --no-embed # parse + load
    uv run python -m aiact.ingest --no-db    # parse only
"""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from aiact.models import Chunk
from aiact.parsers.eurlex import parse_consolidated, parse_recitals
from aiact.parsers.faq import parse_faq
from aiact.parsers.guidelines_pdf import parse_numbered_pdf
from aiact.sources import CORPUS_VERSION, RAW_DIR, SOURCES

OUT = Path("data/corpus/chunks.jsonl")


def build() -> list[Chunk]:
    def path(doc_id: str) -> Path:
        return RAW_DIR / SOURCES[doc_id].filename

    def doc(doc_id: str):
        return SOURCES[doc_id].doc

    chunks: list[Chunk] = []
    chunks += parse_consolidated(path("eu-ai-act-consolidated"), doc("eu-ai-act-consolidated"))
    chunks += parse_recitals(path("eu-ai-act-recitals"), doc("eu-ai-act-recitals"),
                             "EU AI Act (Reg. 2024/1689), recitals")
    chunks += parse_recitals(path("eu-digital-omnibus-ai"), doc("eu-digital-omnibus-ai"),
                             "Digital Omnibus on AI (Reg. 2026/1744), recitals")
    # Omnibus articles are not indexed: Art. 1 is a list of edit instructions whose result is
    # already in the consolidated text (chunks carry amended_by), Arts. 2-3 amend other acts.
    chunks += parse_numbered_pdf(path("eu-guidelines-art50"), doc("eu-guidelines-art50"),
                                 "Art. 50 Guidelines")
    chunks += parse_faq(sorted(RAW_DIR.glob("faq-page-*.html")), doc("eu-service-desk-faq"))

    ids = Counter(c.chunk_id for c in chunks)
    dups = [k for k, v in ids.items() if v > 1]
    if dups:
        raise ValueError(f"duplicate chunk ids: {dups[:5]}")
    return chunks


def write_jsonl(chunks: list[Chunk]) -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps({"corpus_version": CORPUS_VERSION, **c.to_dict()}, ensure_ascii=False) + "\n")


def load_db(chunks: list[Chunk]) -> None:
    import psycopg

    url = os.environ.get("DATABASE_URL", "postgresql://aiact:aiact@localhost:5433/aiact")
    used_docs = {c.doc_id for c in chunks}
    with psycopg.connect(url) as conn, conn.cursor() as cur:
        # Full refresh of the corpus in one transaction; embeddings are re-filled from the cache.
        cur.execute("delete from documents")
        for doc_id in used_docs:
            d = asdict(SOURCES[doc_id].doc)
            cur.execute(
                """insert into documents (doc_id, title, jurisdiction, doc_type, status, binding,
                       language, published, version_date, url, corpus_version)
                   values (%(doc_id)s, %(title)s, %(jurisdiction)s, %(doc_type)s, %(status)s, %(binding)s,
                       %(language)s, %(published)s, %(version_date)s, %(url)s, %(corpus_version)s)""",
                {**d, "corpus_version": CORPUS_VERSION},
            )
        with cur.copy(
            "copy chunks (chunk_id, doc_id, seq, article_ref, title, context, text, refs, amended_by, url) from stdin"
        ) as copy:
            for c in chunks:
                copy.write_row((c.chunk_id, c.doc_id, c.seq, c.article_ref, c.title, c.context,
                                c.text, c.refs, c.amended_by, c.url))
        conn.commit()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-db", action="store_true")
    ap.add_argument("--no-embed", action="store_true")
    a = ap.parse_args()
    chunks = build()
    write_jsonl(chunks)
    print(f"{len(chunks)} chunks -> {OUT}")
    for doc_id, n in Counter(c.doc_id for c in chunks).items():
        print(f"  {doc_id:28} {n:5}")
    if not a.no_db:
        load_db(chunks)
        print("loaded into Postgres")
        if not a.no_embed:
            from aiact.embed import fill
            print(f"{fill()} chunk embeddings written")


if __name__ == "__main__":
    main()
