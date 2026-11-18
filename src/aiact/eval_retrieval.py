"""Retrieval eval: does search put the gold article in the top k?

    uv run python -m aiact.eval_retrieval            # prints tables, writes eval/results/retrieval.md

Metrics (questions with empty gold are skipped):
  hit@k     at least one gold ref in the top k
  recall@k  share of the question's gold refs found in the top k
  MRR       1 / rank of the first gold hit (0 if not in the top 10)
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import date
from pathlib import Path

import yaml

from aiact.db import connect
from aiact.embed import EMBED_MODEL
from aiact.search import Hit, ref_matches, search
from aiact.sources import CORPUS_VERSION

QUESTIONS = Path("eval/questions.yaml")
OUT = Path("eval/results/retrieval.md")
KS = (5, 10)
CONFIGS = {  # label -> search kwargs; each row adds one component
    "dense": dict(mode="dense", exact_refs=False, cite_expand=False),
    "keyword (BM25)": dict(mode="keyword", exact_refs=False, cite_expand=False),
    "hybrid": dict(mode="hybrid", exact_refs=False, cite_expand=False),
    "hybrid + cited law": dict(mode="hybrid", exact_refs=False, cite_expand=True),
    "hybrid + cited law + exact refs": dict(mode="hybrid", exact_refs=True, cite_expand=True),
    "dense + cited law + exact refs": dict(mode="dense", exact_refs=True, cite_expand=True),
}
DEFAULT = "hybrid + cited law + exact refs"


def load_questions(path: Path = QUESTIONS) -> list[dict]:
    return yaml.safe_load(path.read_text())


def gold_rank(hits: list[Hit], gold_item: str) -> int | None:
    """1-based rank of the first hit matching a gold item ("A | B" = either)."""
    alts = [g.strip() for g in gold_item.split("|")]
    for i, h in enumerate(hits, 1):
        if any(ref_matches(h.article_ref, g) for g in alts):
            return i
    return None


def score(hits: list[Hit], gold: list[str]) -> dict[str, float]:
    ranks = [gold_rank(hits, g) for g in gold]
    m: dict[str, float] = {}
    for k in KS:
        found = [r for r in ranks if r is not None and r <= k]
        m[f"hit@{k}"] = float(bool(found))
        m[f"recall@{k}"] = len(found) / len(gold)
    first = min((r for r in ranks if r is not None), default=None)
    m["MRR"] = 1.0 / first if first else 0.0
    return m


def mean(rows: list[dict[str, float]]) -> dict[str, float]:
    return {key: sum(r[key] for r in rows) / len(rows) for key in rows[0]}


def md_table(header: list[str], rows: list[list[str]]) -> str:
    out = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    out += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-write", action="store_true")
    a = ap.parse_args()

    qs = [q for q in load_questions() if q["gold"]]
    metric_names = [f"{m}@{k}" for m in ("hit", "recall") for k in KS] + ["MRR"]
    per: dict[str, dict[str, dict]] = defaultdict(dict)  # config -> qid -> {metrics, hits}

    with connect() as conn:
        for label, kw in CONFIGS.items():
            for q in qs:
                hits = search(q["question"], k=max(KS), conn=conn, **kw)
                per[label][q["id"]] = {"m": score(hits, q["gold"]), "hits": hits}

    summary = md_table(["config"] + metric_names,
                       [[label] + [f"{mean([r['m'] for r in per[label].values()])[m]:.2f}" for m in metric_names]
                        for label in CONFIGS])

    by_type: dict[str, list[dict]] = defaultdict(list)
    for q in qs:
        by_type[q["type"]].append(per[DEFAULT][q["id"]]["m"])
    types = md_table(["type", "n", "hit@5", "recall@10", "MRR"],
                     [[t, str(len(rs)), f"{mean(rs)['hit@5']:.2f}", f"{mean(rs)['recall@10']:.2f}",
                       f"{mean(rs)['MRR']:.2f}"] for t, rs in sorted(by_type.items())])

    misses = []
    for q in qs:
        r = per[DEFAULT][q["id"]]
        if r["m"]["recall@5"] < 1:
            ranks = {g: gold_rank(r["hits"], g) for g in q["gold"]}
            top = ", ".join(h.article_ref or h.chunk_id for h in r["hits"][:3])
            misses.append([q["id"], q["question"],
                           "; ".join(f"{g} → {ranks[g] or '>10'}" for g in q["gold"]), top])
    miss_table = md_table(["id", "question", "gold → rank", "top 3 returned"], misses) if misses else "None."

    report = f"""# Retrieval eval

- Date: {date.today()} · corpus {CORPUS_VERSION} · embeddings `{EMBED_MODEL}` · {len(qs)} questions with gold refs (`{QUESTIONS}`)
- Dense: pgvector cosine top-30 · keyword: BM25 over Postgres English tsvectors top-30 · fused with RRF (k=60)
- Cited law: AI Act chunks cited by the top-10 guideline/FAQ/recital hits join the fusion
- Exact refs: the best chunk of each article/annex/recital named in the question goes first

## Summary

{summary}

## By question type ({DEFAULT})

{types}

## Questions with a gold ref outside the top 5 ({DEFAULT})

{miss_table}
"""
    print(report)
    if not a.no_write:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(report)
        print(f"-> {OUT}")


if __name__ == "__main__":
    main()
