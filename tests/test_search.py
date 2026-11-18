"""Search unit tests (no database needed) + test set sanity checks against the corpus."""

import pytest

from aiact.eval_retrieval import load_questions, score
from aiact.search import Hit, query_refs, ref_matches, rrf


@pytest.mark.parametrize("q,expected", [
    ("What does Article 50(1) require?", ["Art. 50(1)"]),
    ("what does art. 6 say", ["Art. 6"]),
    ("Which areas are listed in annex III?", ["Annex III"]),
    ("Explain recital 132", ["Recital 132"]),
    ("Article 9 of Regulation (EU) 2016/679", []),
    ("Do I need to label my chatbot?", []),
])
def test_query_refs(q, expected):
    assert query_refs(q) == expected


@pytest.mark.parametrize("ref,target,ok", [
    ("Art. 50(1)", "Art. 50", True),
    ("Art. 5(1)(f)", "Art. 5(1)", True),
    ("Art. 50(1)", "Art. 5", False),
    ("Art. 50 Guidelines, para. 3", "Art. 50", False),
    ("Art. 50 Guidelines, para. 42", "Art. 50 Guidelines, para. 4", False),
    ("Annex III point 4", "Annex III", True),
    ("Annex III point 4", "Annex III point 4", True),
    ("Annex IV point 1", "Annex I", False),
    ("Recital 44", "Recital 4", False),
    (None, "Art. 1", False),
])
def test_ref_matches(ref, target, ok):
    assert ref_matches(ref, target) is ok


def test_rrf_rewards_agreement():
    fused = rrf({"dense": ["a", "b", "c"], "keyword": ["c", "a"]})
    assert [cid for cid, _, _ in fused] == ["a", "c", "b"]
    assert fused[0][2] == ["dense", "keyword"]


def _hit(ref):
    return Hit(chunk_id=ref, doc_id="d", article_ref=ref, title=None, context="", text="", url="", amended_by=None)


def test_score():
    hits = [_hit(r) for r in ["Art. 1", "Art. 50(2)", "Art. 26(1)"] + ["Art. 99"] * 7]
    m = score(hits, ["Art. 50", "Art. 27 | Art. 26"])
    assert m["hit@5"] == 1 and m["recall@5"] == 1 and m["MRR"] == 0.5
    assert score(hits, ["Art. 113"])["MRR"] == 0


def test_questions_gold_refs_exist():
    from aiact.ingest import build
    from aiact.sources import RAW_DIR
    if not RAW_DIR.exists():
        pytest.skip("run `python -m aiact.sources` first")
    refs = [c.article_ref for c in build()]
    qs = load_questions()
    assert len(qs) == 30 and len({q["id"] for q in qs}) == 30
    for q in qs:
        for item in q["gold"]:
            for g in item.split("|"):
                assert any(ref_matches(r, g.strip()) for r in refs), f"{q['id']}: {g!r} not in corpus"
