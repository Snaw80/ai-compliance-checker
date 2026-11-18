# AI Act Assistant

Chat assistant that tells small companies which EU AI Act rules apply to them, where and from when, with sources. Fully local, free stack (Ollama + Postgres/pgvector). Background: `ai-act-assistant-description.md` and `research/`.

## Setup

```bash
cp .env.example .env
docker compose up -d db              # Postgres 17 + pgvector on :5433, schema from db/schema.sql
uv sync
uv run python -m aiact.sources       # download sources into data/raw (cached)
uv run python -m aiact.ingest        # parse -> data/corpus/chunks.jsonl -> Postgres
uv run pytest
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
