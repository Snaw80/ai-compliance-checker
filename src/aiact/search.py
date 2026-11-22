"""Hybrid search over the corpus: dense (pgvector) + keyword (BM25) + cited-law expansion +
exact-reference lookup, fused with Reciprocal Rank Fusion.

    uv run python -m aiact.search "Do I have to tell users they talk to a chatbot?"
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Literal

import psycopg

from aiact.db import connect, to_pgvector
from aiact.embed import embed_query
from aiact.models import extract_refs

Mode = Literal["dense", "keyword", "hybrid"]
RRF_K = 60
LAW_DOC = "eu-ai-act-consolidated"
# RRF weights (default 1). cited: the binding text should beat the guidance paragraphs that
# discuss it. exact: "What does Art. 6 say?" must beat every other "paragraph 6".
WEIGHTS = {"cited": 2.0, "exact": 2.0}

_COLS = "chunk_id, doc_id, article_ref, title, context, text, url, amended_by"


@dataclass
class Hit:
    chunk_id: str
    doc_id: str
    article_ref: str | None
    title: str | None
    context: str
    text: str
    url: str
    amended_by: str | None
    score: float = 0.0
    via: list[str] = field(default_factory=list)  # which retrievers found it: exact / dense / keyword


# ---------------------------------------------------------------------------
# References named in the query ("Article 50(1)", "Art. 6", "Annex III", "recital 132")
# ---------------------------------------------------------------------------

_ART_ABBR = re.compile(r"\bArts?\.\s*(?=\d)", re.I)
_RECITAL = re.compile(r"\brecitals?\s+\(?(\d{1,3})\)?", re.I)


def query_refs(query: str) -> list[str]:
    """AI Act references named in a user query, in corpus `article_ref` form."""
    q = _ART_ABBR.sub("Article ", query)
    q = re.sub(r"\barticle", "Article", q, flags=re.I)
    q = re.sub(r"\bannex\b", "Annex", q, flags=re.I)
    return extract_refs(q) + [f"Recital {n}" for n in _RECITAL.findall(query)]


def ref_matches(ref: str | None, target: str) -> bool:
    """True if chunk `ref` is `target` or a sub-part of it.

    'Art. 50(1)' matches 'Art. 50' and 'Art. 50(1)'; 'Annex III point 4' matches 'Annex III';
    'Art. 50 Guidelines, para. 3' does NOT match 'Art. 50', and 'Art. 5(1)' does not match 'Art. 50'.
    """
    if ref is None:
        return False
    if ref == target or ref.startswith(target + "("):
        return True
    return target.startswith("Annex") and ref.startswith((target + " point", target + " Section"))


def _like_patterns(refs: list[str]) -> list[str]:
    pats = []
    for r in refs:
        pats += [r, r + "(%"]
        if r.startswith("Annex"):
            pats += [r + " point%", r + " Section%"]
    return pats


# ---------------------------------------------------------------------------
# Retrievers: each returns chunk_ids, best first
# ---------------------------------------------------------------------------

def _exact(cur: psycopg.Cursor, refs: list[str]) -> list[str]:
    if not refs:
        return []
    cur.execute("select chunk_id from chunks where article_ref like any(%s) order by doc_id, seq",
                (_like_patterns(refs),))
    return [r[0] for r in cur.fetchall()]


def _dense(cur: psycopg.Cursor, query: str, n: int) -> list[str]:
    v = to_pgvector(embed_query(query))
    cur.execute("select chunk_id from chunks where embedding is not null "
                "order by embedding <=> %s::vector limit %s", (v, n))
    return [r[0] for r in cur.fetchall()]


class _BM25:
    """BM25 over the Postgres tsvectors (same English stemming as the `tsv` column).

    Postgres `ts_rank` has no IDF, so on this corpus "AI" outweighs "chatbot"; at ~1k chunks an
    in-memory BM25 is simpler than an extension. Terms in the ref/title (weight A) count double.
    """

    def __init__(self, cur: psycopg.Cursor, k1: float = 1.2, b: float = 0.75):
        cur.execute("select chunk_id, t.lexeme, cardinality(t.positions) + "
                    "cardinality(array_positions(t.weights, 'A')) "
                    "from chunks, unnest(tsv) as t")
        self.postings: dict[str, list[tuple[str, int]]] = {}
        self.dl: dict[str, int] = {}
        for cid, lex, tf in cur.fetchall():
            self.postings.setdefault(lex, []).append((cid, tf))
            self.dl[cid] = self.dl.get(cid, 0) + tf
        self.n = len(self.dl)
        self.avgdl = sum(self.dl.values()) / max(self.n, 1)
        self.k1, self.b = k1, b

    def top(self, terms: list[str], n: int) -> list[str]:
        scores: dict[str, float] = {}
        for t in set(terms):
            post = self.postings.get(t, [])
            idf = math.log(1 + (self.n - len(post) + 0.5) / (len(post) + 0.5))
            for cid, tf in post:
                norm = tf + self.k1 * (1 - self.b + self.b * self.dl[cid] / self.avgdl)
                scores[cid] = scores.get(cid, 0.0) + idf * tf * (self.k1 + 1) / norm
        return [cid for cid, _ in sorted(scores.items(), key=lambda x: -x[1])[:n]]


_bm25: _BM25 | None = None


def _keyword(cur: psycopg.Cursor, query: str, n: int) -> list[str]:
    global _bm25
    if _bm25 is None:
        _bm25 = _BM25(cur)
    cur.execute("select lexeme from unnest(to_tsvector('english', %s))", (query,))
    return _bm25.top([r[0] for r in cur.fetchall()], n)


def _cited(cur: psycopg.Cursor, fused: list[tuple[str, float, list[str]]], n_sources: int = 10) -> list[str]:
    """Law chunks cited by the top non-law results (guidelines, FAQ, recitals), most cited first.

    Guideline paragraphs about Art. 50(1) often outrank Art. 50(1) itself; this pulls the
    binding text back in. Each citing chunk votes with its fused score.
    """
    top = [cid for cid, _, _ in fused[:n_sources]]
    cur.execute("select chunk_id, refs from chunks where chunk_id = any(%s) and doc_id <> %s",
                (top, LAW_DOC))
    score = {cid: s for cid, s, _ in fused}
    votes: dict[str, float] = {}
    for cid, refs in cur.fetchall():
        for r in refs:
            votes[r] = votes.get(r, 0.0) + score[cid]
    if not votes:
        return []
    # each cited ref -> its first chunk ('Art. 50' -> 'Art. 50(1)', 'Art. 5(1)' -> 'Art. 5(1)(a)')
    cur.execute("""select distinct on (r) r, chunk_id from unnest(%s::text[]) as r
                   join chunks on doc_id = %s and (article_ref = r or article_ref like r || '(%%')
                   order by r, seq""", (list(votes), LAW_DOC))
    ranked = [cid for r, cid in sorted(cur.fetchall(), key=lambda x: -votes[x[0]])]
    return list(dict.fromkeys(ranked))  # 'Art. 50' and 'Art. 50(1)' both map to Art. 50(1)


def rrf(rankings: dict[str, list[str]], k: int = RRF_K,
        weights: dict[str, float] | None = None) -> list[tuple[str, float, list[str]]]:
    """Reciprocal Rank Fusion. Returns (chunk_id, score, retrievers) best first."""
    scores: dict[str, float] = {}
    via: dict[str, list[str]] = {}
    for name, ids in rankings.items():
        w = (weights or {}).get(name, 1.0)
        for rank, cid in enumerate(ids):
            scores[cid] = scores.get(cid, 0.0) + w / (k + rank + 1)
            via.setdefault(cid, []).append(name)
    return [(cid, s, via[cid]) for cid, s in sorted(scores.items(), key=lambda x: -x[1])]


# ---------------------------------------------------------------------------

def search(query: str, k: int = 8, mode: Mode = "hybrid", exact_refs: bool = True,
           cite_expand: bool = True, n_candidates: int = 30,
           conn: psycopg.Connection | None = None) -> list[Hit]:
    """Top-k chunks for `query`.

    1. dense and/or keyword rankings, fused with RRF
    2. cite_expand: law chunks cited by the top guideline/FAQ/recital hits join as a third ranking
    3. exact_refs: for each article/annex/recital named in the query, its best chunk goes first;
       its other chunks join the fusion as one more ranking (so "Annex III" can't fill the top k)
    """
    own = conn is None
    conn = conn or connect()
    try:
        with conn.cursor() as cur:
            rankings: dict[str, list[str]] = {}
            if mode in ("dense", "hybrid"):
                rankings["dense"] = _dense(cur, query, n_candidates)
            if mode in ("keyword", "hybrid"):
                rankings["keyword"] = _keyword(cur, query, n_candidates)
            if cite_expand:
                rankings["cited"] = _cited(cur, rrf(rankings))

            pinned: list[str] = []
            if exact_refs and (refs := query_refs(query)):
                exact = _exact(cur, refs)
                base = {cid: i for i, (cid, _, _) in enumerate(rrf(rankings))}
                exact.sort(key=lambda c: base.get(c, len(base)))  # most relevant part first
                cur.execute("select chunk_id, article_ref from chunks where chunk_id = any(%s)", (exact,))
                ref_of = dict(cur.fetchall())
                for r in refs:  # best chunk of each named ref
                    best = next((c for c in exact if ref_matches(ref_of[c], r) and c not in pinned), None)
                    if best:
                        pinned.append(best)
                pinned = pinned[: max(3, k // 2)]
                rankings["exact"] = exact

            fused = rrf(rankings, weights=WEIGHTS)
            fused_by_id = {cid: (s, v) for cid, s, v in fused}
            ranked = [(cid, 1.0 + fused_by_id[cid][0], fused_by_id[cid][1]) for cid in pinned]
            ranked += [x for x in fused if x[0] not in set(pinned)]
            ranked = ranked[:k]

            cur.execute(f"select {_COLS} from chunks where chunk_id = any(%s)", ([c for c, _, _ in ranked],))
            rows = {r[0]: r for r in cur.fetchall()}
        return [Hit(*rows[cid], score=s, via=v) for cid, s, v in ranked]
    finally:
        if own:
            conn.close()


def get_chunks(chunk_ids: list[str], conn: psycopg.Connection | None = None) -> list[Hit]:
    """Chunks by id, in the given order (unknown ids are skipped)."""
    if not chunk_ids:
        return []
    own = conn is None
    conn = conn or connect()
    try:
        with conn.cursor() as cur:
            cur.execute(f"select {_COLS} from chunks where chunk_id = any(%s)", (list(chunk_ids),))
            rows = {r[0]: r for r in cur.fetchall()}
        return [Hit(*rows[c], via=["id"]) for c in chunk_ids if c in rows]
    finally:
        if own:
            conn.close()


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("query")
    ap.add_argument("-k", type=int, default=8)
    ap.add_argument("--mode", default="hybrid", choices=["dense", "keyword", "hybrid"])
    ap.add_argument("--no-exact", action="store_true")
    ap.add_argument("--no-cite", action="store_true")
    a = ap.parse_args()
    for i, h in enumerate(search(a.query, a.k, a.mode, not a.no_exact, not a.no_cite), 1):
        print(f"{i:2}. {h.score:.4f} [{','.join(h.via)}] {h.article_ref}  — {h.text[:110]!r}")
