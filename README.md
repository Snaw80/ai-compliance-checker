# AI Act Assistant

A chat assistant that tells small companies **which EU AI Act rules apply to their AI system, in which EU/EEA country, and from when**, citing the article or guideline behind every point. It runs fully locally on a laptop, with free models.

> "We're a startup in Oslo and Helsinki with a chatbot on our website. What do we need to do?"
> → asks whether they built or bought the chatbot, then answers: probable risk category, the obligations that apply (Art. 50(1) disclosure, AI literacy), the date each one applies, what differs in Finland vs Norway (an EEA country, not bound yet), and numbered sources.

## Why it is built this way

The AI Act is long, recently amended (the 2026 Digital Omnibus moved several deadlines), and its effect depends on the company's **role** (provider or deployer), the **date** and the **country**. A plain RAG chatbot gets exactly those things wrong: it mixes up old and new dates and invents authorities. So the design rule is: **the model writes, code decides.**

- **Dates and countries are tables, not retrieval.** Every article's date of application (Art. 113, plus Art. 111 grace periods) and a profile of all 27 EU + 3 EEA countries (national law, authorities, penalties) live in two hand-checked YAML files, validated strictly at load time. The answer's "when" and "where" sections are rendered from them; the model never writes a date on its own.
- **A fixed graph, not a free-form agent.** A LangGraph workflow in which the model only (1) routes the message, (2) extracts the facts the user stated, and (3) words the answer. The role, the clarifying question, the obligations, the risk category and the countries are deterministic rules, so they are unit-tested.
- **Every claim is checked.** The writer cites tagged sources (`[S1]` law passage, `[T1]` table row, `[FI]` country). Code drops tags it never showed the model, flags points without a source, and flags any date that appears in no source.
- **Measured against a baseline.** Retrieval and answers are evaluated on a 35-question test set, and the agent is compared with a plain RAG chain using the same search and prompt.

## How it works

```
router ─┬─ off_topic ────────────────────────────────────────────────────▶ finalize
        ├─ general ─────────────────────────▶ plan ─▶ research ─▶ generate ─▶ finalize
        └─ company_case ─▶ build_profile ⇄ ask_clarify (pauses for the user)
                                 └────────────▶ plan
```

| Step | What happens | Model or code |
|---|---|---|
| router | off-topic, general question about the law, or the user's own case | model |
| build_profile | facts the user stated: what the system does, built or bought, Annex III area, countries... | model |
| ask_clarify | asks the one missing fact that changes the answer most (each at most once) | code |
| plan | role, obligations (rows of the applicability table), countries | code |
| research | hybrid search + the core articles for the role + table rows + country profiles | code |
| generate | writes the answer from the tagged sources only | model |
| finalize | citation and date check, renders the dates table, country section and source links | code |

**Search** fuses four rankings with Reciprocal Rank Fusion: dense vectors (BGE-M3, pgvector), BM25 keyword search, the AI Act articles cited by the top guideline/FAQ hits (so the binding text beats commentary about it), and exact matches for articles named in the question.

**Corpus** (as of 18 Nov 2026): the consolidated AI Act including the Omnibus amendments, the original and Omnibus recitals, the Commission's Art. 50 guidelines, and the AI Act Service Desk FAQ. Each is chunked along its legal structure (article paragraph, definition, recital, numbered guideline paragraph, FAQ item).

## Tech choices

| Need | Choice | Why |
|---|---|---|
| LLM | qwen3.5 9B via Ollama, thinking off | free and local on a 32 GB laptop; thinking mode took minutes per call |
| Structured output | tool calling + a small repair layer | Ollama ignored JSON-schema mode for this model; outputs are kept flat because the 9B model garbles nested JSON |
| Embeddings | BGE-M3 via Ollama | multilingual, runs locally, 1024-dim dense vectors |
| Store | Postgres 17 + pgvector (Docker) | one database for vectors, full-text search and metadata |
| Orchestration | LangGraph | explicit graph, interrupts for clarifying questions, per-node streaming for the UI |
| Knowledge tables | YAML + strict validator | hand-reviewable in a diff, typos fail at load time |
| UI | Chainlit | chat UI with live steps showing what each node decided |

## Results

Retrieval (29 questions with gold articles, `eval/results/retrieval.md`): hit@5 goes from 0.62 (dense only) to **0.76** with the full hybrid search, hit@10 from 0.76 to **0.83**.

Answers (35 questions incl. 5 company cases with scripted replies, `eval/results/answers.md`), graded by a local judge against the expected answer:

| | score | company cases | cites a gold source | unsupported points | answers with unsourced dates | median time |
|---|---|---|---|---|---|---|
| plain RAG baseline | 0.79 | 0.60 | 0.82 | 2% | 1 | 37 s |
| agent | **0.86** | **0.90** | 0.85 | 0% | 0 | 62 s |

Take these as indicative: the judge is a 9B model from the same family, five company cases is a small sample, and some fixes were made after reading failures on this set.

## Run it

Needs Docker, [Ollama](https://ollama.com) and [uv](https://docs.astral.sh/uv/).

```bash
cp .env.example .env
docker compose up -d db                  # Postgres + pgvector on :5433
ollama pull bge-m3 && ollama pull qwen3.5:9b
uv sync
uv run python -m aiact.sources           # download the sources (cached in data/raw)
uv run python -m aiact.ingest            # parse, load Postgres, embed
uv run pytest

uv run --directory ui chainlit run app.py            # web UI on http://localhost:8000
uv run python -m aiact.agent                         # or chat in the terminal (-v shows decisions)
uv run python -m aiact.eval_retrieval                # retrieval eval
uv run python -m aiact.eval_answers                  # baseline vs agent (slow: ~1 min per answer)
```

An answer takes about 1 minute on an Apple M4. Set `AIACT_WRITER_MODEL` to try a larger writer model.

## Layout

```
src/aiact/
  sources.py, parsers/, ingest.py   download and chunk the corpus
  embed.py, search.py               embeddings and hybrid search
  tables.py                         applicability + country tables (tables/*.yaml)
  agent/                            graph, rules, evidence, prompts, citation check, rendering
  eval_retrieval.py, eval_answers.py
eval/        test questions and results
ui/          Chainlit app
tests/       unit tests (agent tests use a scripted fake model, no Ollama needed)
```

## Limits

- General information, not legal advice. English only.
- Country profiles were seeded from public trackers (Nov 2026) and are marked medium/low confidence until checked against official gazettes. No national law texts are indexed.
- The citation check verifies that sources exist and dates match, not that each source fully supports its point.
