"""Corpus tests. They run against the downloaded raw files (data/raw); run
`uv run python -m aiact.sources` first. They pin facts the agent relies on."""

from collections import Counter

import pytest

from aiact.ingest import build
from aiact.models import extract_refs
from aiact.sources import RAW_DIR

pytestmark = pytest.mark.skipif(not RAW_DIR.exists(), reason="run `python -m aiact.sources` first")


@pytest.fixture(scope="module")
def chunks():
    return build()


@pytest.fixture(scope="module")
def by_ref(chunks):
    return {c.article_ref: c for c in chunks}


def test_ids_unique_and_text_present(chunks):
    assert len({c.chunk_id for c in chunks}) == len(chunks)
    assert all(c.text.strip() for c in chunks)
    assert not any("▼" in c.text or "►" in c.text for c in chunks), "amendment markers leaked"


def test_every_article_and_annex_present(chunks):
    arts = {c.chunk_id.split(":")[1] for c in chunks if c.doc_id == "eu-ai-act-consolidated"}
    assert sum(a.startswith("art_") for a in arts) == 119  # 113 + inserted (4a, ...)
    assert {f"anx_{r}" for r in "I II III IV V VI VII VIII IX X XI XII XIII XIV".split()} <= arts


def test_chatbot_transparency(by_ref):
    c = by_ref["Art. 50(1)"]
    assert "informed that they are interacting with an AI system" in c.text
    assert c.text.startswith("1. Providers shall ensure")  # label merged with text
    assert "Chapter IV" in c.context


def test_definitions_split_one_per_term(by_ref):
    assert "‘deployer’ means" in by_ref["Art. 3(4)"].text
    assert "‘provider’ means" in by_ref["Art. 3(3)"].text
    assert "‘deployer’" in by_ref["Art. 3(4)"].context


def test_omnibus_changes_flagged(by_ref):
    # Omnibus dates: Annex III high-risk from 2 Dec 2027, Annex I from 2 Aug 2028
    art113 = by_ref["Art. 113"]
    assert "2 December 2027" in art113.text and "2 August 2028" in art113.text
    assert art113.amended_by == "Regulation (EU) 2026/1744"
    assert by_ref["Art. 5(1)(ba)"].amended_by == "Regulation (EU) 2026/1744"
    assert by_ref["Art. 50(1)"].amended_by is None


def test_prohibited_practices_split(by_ref):
    assert by_ref["Art. 5(1)(a)"].text.startswith("The following AI practices shall be prohibited:")
    assert "subliminal" in by_ref["Art. 5(1)(a)"].text


def test_annex_iii_areas(by_ref):
    assert "Employment" in by_ref["Annex III point 4"].text
    assert all(f"Annex III point {i}" in by_ref for i in range(1, 9))


def test_recitals(chunks):
    n = Counter(c.doc_id for c in chunks)
    assert n["eu-ai-act-recitals"] == 180
    assert n["eu-digital-omnibus-ai"] == 47


def test_guidelines_paragraphs_sequential(chunks):
    g = [c for c in chunks if c.doc_id == "eu-guidelines-art50"]
    nums = [int(c.chunk_id.rsplit("_", 1)[1]) for c in g]
    assert nums == list(range(1, len(g) + 1)) and len(g) >= 150
    assert not any("OJ L" in c.text[:40] for c in g)  # footnotes not taken as paragraphs


def test_faq_excludes_outdated_omnibus_items(chunks):
    faq = [c for c in chunks if c.doc_id == "eu-service-desk-faq"]
    assert len(faq) >= 40
    assert not any("Digital Omnibus" in c.context for c in faq)


@pytest.mark.parametrize("text,expected", [
    ("referred to in Article 6(2) and Annex III", ["Art. 6(2)", "Annex III"]),
    ("Articles 102 to 104 shall apply", ["Art. 102", "Art. 103", "Art. 104"]),
    ("Article 9 of Regulation (EU) 2016/679", []),
    ("Article 50(3) and (4) AI Act", ["Art. 50(3)", "Art. 50(4)"]),
])
def test_extract_refs(text, expected):
    assert extract_refs(text) == expected
