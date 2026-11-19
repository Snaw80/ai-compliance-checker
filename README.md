# AI Act Assistant

Chat assistant that tells small companies which EU AI Act rules apply to them, where and from when, with sources. Fully local, free stack (Ollama + Postgres/pgvector). Background: `ai-act-assistant-description.md` and `research/`.

## Setup

```bash
cp .env.example .env
docker compose up -d db              # Postgres 17 + pgvector on :5433, schema from db/schema.sql
ollama pull bge-m3                   # embedding model (1.2 GB)
uv sync
uv run python -m aiact.sources       # download sources into data/raw (cached)
uv run python -m aiact.ingest        # parse -> data/corpus/chunks.jsonl -> Postgres -> BGE-M3 embeddings (cached)
uv run pytest
uv run python -m aiact.search "Do I have to tell users they talk to a chatbot?"
uv run python -m aiact.eval_retrieval   # -> eval/results/retrieval.md
```

Check for a newer consolidated AI Act: `uv run python -m aiact.sources --check-consolidated`

## Corpus (version 2026-11-18)

| doc_id | Source | Chunking |
|---|---|---|
| `eu-ai-act-consolidated` | AI Act consolidated 27 Jul 2026 (CELEX 02024R1689-20260727) | article paragraph; Art. 3 one per definition; long paragraphs per point; annexes per section/point. `amended_by` set for text from the Omnibus |
| `eu-ai-act-recitals` | AI Act original recitals (1–180) | one per recital |
| `eu-digital-omnibus-ai` | Omnibus Reg. 2026/1744 recitals (1–47) | one per recital |
| `eu-guidelines-art50` | Commission Art. 50 guidelines, C(2026) 7702, 5 Nov 2026 | one per numbered paragraph |
| `eu-service-desk-faq` | AI Act Service Desk FAQ | one per Q&A (outdated "Digital Omnibus" proposal items excluded) |

EUR-Lex blocks scripts, so EU law comes from the Publications Office Cellar API (same text).

## Search (day 2)

`aiact.search.search(query, k)` fuses four rankings with Reciprocal Rank Fusion:

1. **dense**: BGE-M3 (Ollama) over `context + text`, pgvector cosine
2. **keyword**: BM25 over the Postgres English tsvectors (`ts_rank` has no IDF, so "AI" swamped every query)
3. **cited law** (weight 2): AI Act chunks cited by the top guideline/FAQ/recital hits. Without it, Art. 50 guideline paragraphs push Art. 50 itself out of the top 10
4. **exact refs** (weight 2): articles/annexes/recitals named in the query; the best chunk of each is pinned first

Test set: `eval/questions.yaml` (30 questions, gold `article_ref`s, expected answer gist). Results in `eval/results/retrieval.md`: hit@5 0.62 (dense only) → 0.76, hit@10 0.76 → 0.83. No reranker yet.

## Dates and countries (day 3)

Dates and per-country facts are **not** retrieved and **not** left to the LLM. They live in two hand-checked YAML tables, read through `aiact.tables` (the agent's future tools):

| File | Function | Content |
|---|---|---|
| `tables/applicability.yaml` | `lookup_applicability(obligation_id \| article=, country=, on=)` | 20 rows covering every AI Act article, dates from Art. 113 + transitional rules from Art. 111 (consolidated 27 Jul 2026, Omnibus included). Each row cites its corpus `source_chunk_ids` (tested) |
| `tables/countries.yaml` | `get_country_profile("Finland" \| "FI")` | 27 EU + 3 EEA countries: national law status, single point of contact, market surveillance and notifying authorities, penalties, sandbox, sources, `last_verified`, `confidence`, `open_questions` |

```bash
uv run python -m aiact.tables "Art. 50(2)" --country FI     # applicability, JSON
uv run python -m aiact.tables --country Germany              # country profile, JSON
```

The loader validates strictly (enums, dates, unknown keys), so a YAML typo fails at load time instead of reaching an answer. Country rows were seeded on 2026-11-19 from aiactguide.net (Oct/Nov 2026) and FLI (Jun 2026). No row is `confidence: high` until someone checks it against the official gazette.
