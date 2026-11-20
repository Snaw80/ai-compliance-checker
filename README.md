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
ollama pull qwen3.5:9b                  # the agent's model (6.6 GB)
uv run --directory ui chainlit run app.py   # web UI -> http://localhost:8000
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

## Agent (day 4)

```bash
ollama pull qwen3.5:9b
uv run python -m aiact.agent                 # chat in the terminal (multi-turn, asks clarifying questions)
uv run python -m aiact.agent -v "We use a chatbot on our website. What do we need to do?"
uv run python -m aiact.agent --baseline "..."   # v0 plain RAG chain, for comparison
uv run python -m aiact.eval_answers             # baseline vs agent -> eval/results/answers.md
```

A fixed LangGraph workflow (`aiact.agent.graph`), the day-4 cut of `research/04-agent-graph.md`:

```
router ─┬─ off_topic ──────────────────────────────────────────────────────▶ finalize
        ├─ general ──────────────────────────▶ plan ─▶ research ─▶ generate ─▶ finalize
        └─ company_case ─▶ build_profile ⇄ ask_clarify (interrupt)
                                 └─────────────▶ plan
```

The model decides only three things: the route, the **facts the user stated** (`CompanyProfile`, including whether they *built* or *bought* the system), and the wording of the answer. Everything else is code (`aiact.agent.rules`) and unit-tested:

| Decision | How |
|---|---|
| Provider or deployer | `built` → provider, `bought` → deployer; unknown → ask once, then cover both and say so |
| Clarifying question | the missing fact that changes the answer most (what the system does, then built/bought); each asked at most once per turn |
| Which obligations | profile facts → rows of `tables/applicability.yaml` (company cases; a prohibited practice → only the ban); articles named or retrieved → rows (general questions) |
| Which law the writer sees | the core duties for the role (e.g. Art. 26-27 for a deployer of a high-risk system, Art. 16 for its provider), then search hits |
| Risk category | from the profile facts, shown as *probable* |
| Countries | where the company and its users are (or countries named in the question), EU/EEA only, max 5 |
| Dates, country details | rendered from the tables, never written by the model (general questions: only the rows the answer cites) |
| Citations | the writer cites tags (`[S1]` chunk, `[T1]` table row, `[FI]` country); code drops tags it never saw, counts unsourced points and flags dates that appear in no source |

Models: qwen3.5 9B through Ollama, thinking **off** (on, a one-line routing call takes minutes). Structured output goes through **tool calling**: Ollama 0.20 ignores the JSON-schema `format` for qwen3.5 when thinking is off. qwen sometimes sends nested JSON as a (broken) string, nests a list item too deep, sends `null` for a list or a value outside an enum, so answers are kept flat and `llm.structured` repairs what it can (invalid optional fields fall back to their default). Each call has a 300 s timeout and a 2,048-token cap: without them, one stuck Ollama request froze an eval run for over an hour. Set `AIACT_WRITER_MODEL=qwen3.5:27b-mlx` to try the larger writer.

Not in the day-4 cut: parallel per-country research (`Send`), the corrective retrieval loop, a model check of citations, the revise loop, a Postgres checkpointer (in-memory for now).

### Answer eval (`eval/results/answers.md`)

35 questions (30 general/scope + 5 company cases with scripted replies to the clarifying questions), answers as of 19 Nov 2026, graded by a local qwen3.5 9B judge against the expected gist (correct 1, partial 0.5, wrong 0):

| | score | general (29) | company cases (5) | cites a gold source | unsupported points | answers with unsourced dates | median s |
|---|---|---|---|---|---|---|---|
| baseline (v0 RAG chain) | 0.79 | 0.81 | 0.60 | 0.82 | 0.02 | 1 | 37 |
| agent (day 4) | 0.86 | 0.84 | 0.90 | 0.85 | 0.00 | 0 | 62 |

Read with care: the judge is a 9B model of the same family as the systems. Even when given the current dates, it still sometimes marks the correct post-Omnibus dates (2 Dec 2027 for Annex III) as wrong. Five company cases are too few to generalise from, and several agent fixes were made after looking at failures on this same set, so these scores are optimistic. Spot-check `answers.jsonl`. Known agent weaknesses: the writer sometimes states the Art. 111(2) grace period with its condition reversed; misses details the expected answer lists (q19 deployer duties, q14 reasons from Recital 44); ~1.7x slower than the baseline (a clarifying round costs ~15 s, the writer 40-70 s).


## Web UI (day 5)

```bash
docker compose up -d db                       # Postgres must be up and ingested (see Setup)
uv run --directory ui chainlit run app.py     # -> http://localhost:8000
```

A local [Chainlit](https://docs.chainlit.io) chat (`ui/app.py`) over the same agent. Each browser chat is one agent thread, so a clarifying question and its answer stay in the conversation. While the agent works, each graph node shows as a step with what it decided: the route, the company profile (only the facts the user gave), the obligations and countries to cover, and the sources found. The answer is the agent's rendered markdown, with its sources as links. The UI calls `Conversation.asend`, which streams LangGraph's `tasks` events. Answers take about 1-2 minutes on an M4 (the writer is most of it). Local only: no accounts, no persistence across restarts.
