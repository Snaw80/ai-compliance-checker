# RAG stack: technology choices

The aim is to retrieve the *right article, guideline paragraph or national provision*, with its **jurisdiction**, **date** and **status**, and to make every answer cite it.

What makes this RAG different from a generic "chat with PDFs" project:

- **The corpus is small but highly structured.** The AI Act has 113 articles, 180 recitals and 13 annexes. Add a few guidelines and national texts and you have roughly 3–8k chunks. Scale doesn't matter here. **Precision and structure do.**
- **Exact identifiers matter.** "Article 50(1)", "Annex III point 4(a)" and "1377/2025" are cases where pure vector search fails and keyword search succeeds.
- **The law changes over time.** The same article has an original version and an Omnibus-amended version. Retrieval has to return the version in force, or say clearly that it isn't.
- **Cross-references are everywhere.** "Systems referred to in Article 6(2)" means you need Art. 6(2) *and* Annex III to answer.

---

## 1. Corpus and ingestion

| Source | Format | How to get it | Notes |
|---|---|---|---|
| AI Act, consolidated (post-Omnibus) | HTML on EUR-Lex | Download the HTML, which has stable anchors per article | Prefer HTML to PDF: the structure (articles, paragraphs, points) is in the markup |
| Omnibus 2026/1744 | HTML on EUR-Lex | Same | Keep it **in addition to** the consolidated text, to answer "what changed" questions |
| Commission guidelines (Art. 50, definition, prohibited, draft Art. 6) | PDF | digital-strategy.ec.europa.eu | Long PDFs with numbered paragraphs. Chunk by paragraph number |
| AI Act Service Desk FAQ | HTML | ai-act-service-desk.ec.europa.eu | Q&A format makes good chunks |
| **Country profile table** (all 27 EU + 3 EEA) | Structured table, **not** chunks | Seeded from trackers and verified against official sources (see `05`) | Read by a tool; not embedded |
| National law + authority guidance, **deep-tier countries only** (e.g. FR, IT, DE, FI, NO) | HTML/PDF, original language | Official gazettes (Légifrance, Gazzetta Ufficiale, Finlex…), authority sites | Store `language`, `status`; see `05` § 4 for multilingual retrieval |

**Parsing.** Write small dedicated parsers rather than a generic loader: one for EUR-Lex HTML and one for numbered-paragraph PDFs. A generic PDF loader such as LangChain's `PyPDFLoader` loses the article boundaries. For PDFs, a layout-aware parser such as **Docling** or **Unstructured** is a good fallback. This parsing work is a real engineering task and a good resume talking point.

**Version the corpus.** Store a `corpus_version` and the download date. When the law changes, you re-ingest and re-run the evaluation.

## 2. Chunking: structural, not by token count

- **One chunk per article paragraph** (for example Art. 50(1)). Merge short paragraphs and split only very long ones.
- Add a **contextual header** to every chunk before embedding, as in Anthropic's Contextual Retrieval approach:
  `"EU AI Act (Reg. 2024/1689, consolidated 2026-07-27) › Chapter IV Transparency › Article 50 Transparency obligations for providers and deployers › paragraph 1"`
  Optionally add a one-sentence LLM-generated summary of how the chunk relates to the whole document. Anthropic reports a large drop in retrieval failures from this. Because the corpus is small, the one-off cost is a few dollars at most.
- **Recitals** become separate chunks with a `explains_articles: [50]` link. Recitals often hold the plain-language intent.
- **Definitions** (Art. 3) become one chunk per defined term. Many questions depend on a definition.

## 3. Metadata schema (the most important design decision)

Every chunk carries these fields:

| Field | Example | Why |
|---|---|---|
| `doc_id`, `doc_title` | `eu-ai-act-consolidated` | Citation |
| `jurisdiction` | `EU` or an ISO country code (`FR`, `IT`, `FI`, `NO`, …) | Filter by country |
| `doc_type` | `regulation` / `guideline` / `code_of_practice` / `national_law` / `authority_guidance` / `consultation` / `faq` | Ranks how binding the source is |
| `status` | `in_force` / `adopted_not_applicable_yet` / `draft` / `superseded` | Honest answers about drafts |
| `binding` | `true` / `false` | The answer should say "guidance, not law" |
| `article_ref` | `Art. 50(1)` | Exact-match retrieval and display |
| `references` | `["Art. 6(2)", "Annex III"]` | Cross-reference expansion |
| `published`, `applies_from`, `applies_until` | dates | Time-aware answers |
| `language` | `en` / `fi` / `no` | |
| `url` (with anchor) | EUR-Lex URL with `#art_50` | Clickable source |

## 4. Dates and countries: put them in a table, not in the vector store

Don't make the model *infer* "from when does X apply in Norway" from retrieved paragraphs. Keep a small, hand-checked **applicability table**, about 30–60 rows, as a database table or a YAML file:

```
obligation          | articles   | jurisdiction | applies_from | status        | source_chunk_ids
chatbot disclosure  | Art. 50(1) | EU, FI       | 2026-08-02   | in_force      | ...
Annex III high-risk | Art. 6-27  | EU, FI       | 2027-12-02   | adopted       | ...
all                 | —          | NO           | (unknown)    | not_in_force  | NO consultation 2026
```

With the "any EU country" scope, the per-country facts (authorities, national law status, penalties, sandbox) live in a second table, the **country profile table**, described in `05-country-coverage.md`. The applicability table stays EU-level, because the AI Act's dates are the same in every member state. Only EEA countries differ.

The agent queries both tables through **tools** (see `04`). This makes the date logic deterministic, testable and easy to update. You can also present it in interviews as "structured knowledge + RAG": the deterministic parts are separated from what the LLM does.

## 5. Embeddings

| Option | Type | Pros | Cons |
|---|---|---|---|
| **Voyage 4** (`voyage-4-large` for documents, a smaller model for queries; shared embedding space) | Hosted API | Top retrieval quality in 2026 reviews, about $0.12/M tokens, so the whole corpus costs cents | API dependency; data goes to a US provider |
| **voyage-law-2** | Hosted API | Built for legal text | Older generation; no independent benchmark on EU law |
| **Qwen3-Embedding** (0.6B / 4B / 8B) | Open weights, self-hosted | Top of the open-model multilingual leaderboards; handles FI and NO text | You host it; 8B needs a GPU (0.6B runs on CPU) |
| **BGE-M3** | Open weights | Multilingual, outputs **dense and sparse** vectors, so you get hybrid search from one model | A little weaker than Qwen3 |
| Cohere embed v4 / OpenAI text-embedding-3 | Hosted | Easy | No clear advantage here |

**Recommendation:** start with **Voyage 4** to move fast, and compare it with **BGE-M3 or Qwen3-Embedding-0.6B** in your evaluation. The comparison table is good material for your published report, and the self-hosted option supports a "data stays in Europe" pitch, which is how RTR describes its own chatbot.

Leaderboard numbers conflict between sources (Qwen3 vs Gemini vs Voyage), and I found no benchmark on EU legal text. **Your own retrieval evaluation is the deciding factor.**

## 6. Vector store

| Option | Hybrid search | Fit for this project |
|---|---|---|
| **Postgres + pgvector** (+ built-in full-text search) | Two queries fused yourself with Reciprocal Rank Fusion (RRF); Postgres `ts_rank` isn't true BM25 | ✅ **Recommended.** One database for vectors, metadata filters (plain SQL `WHERE jurisdiction = 'FI'`), **LangGraph checkpoints** (`langgraph-checkpoint-postgres`), conversation logs and the waitlist. Free tier on Supabase or Neon. "Postgres + pgvector" is also the most transferable skill for a resume. |
| **Qdrant** | Native dense + sparse with RRF, strong payload filtering | ✅ Good alternative if you want built-in hybrid search and a dedicated vector database on the resume. Free cloud tier. |
| Chroma / FAISS | Weak or none | Fine for a notebook prototype. No metadata-heavy hybrid search. |
| Pinecone / Weaviate | Yes | Works, but adds a vendor for a corpus this small. |

At 3–8k chunks, **performance is the same everywhere**. Choose for simplicity and for what you want to show.

## 7. Retrieval pipeline

```
query → (optional) query rewrite / decomposition per jurisdiction
      → metadata pre-filter (jurisdiction ∈ {EU, FI}, status ≠ superseded)
      → dense top-30  +  keyword top-30   (exact article refs are boosted)
      → RRF fusion → top-40
      → reranker → top-6 to 8
      → cross-reference expansion (add Art. 3 definitions and referenced articles, capped)
      → context for generation
```

- **Reranker:** **Cohere Rerank** (hosted) or **BGE-reranker-v2-m3** (open, multilingual). Reranking is the single cheapest quality gain. Measure with and without it.
- **Exact-reference shortcut:** if the user writes "Article 50", run a regex detection and do a direct lookup. Don't rely on similarity search for that.
- **Cross-language keyword search (deep countries):** keyword search doesn't match across languages, so translate the query into each deep country's language before the keyword search. Vector search handles cross-language matching if the embedding model is multilingual, which all three recommended options are.
- **Parent-document retrieval:** retrieve paragraphs, but show the model the whole article when it's short.

## 8. Generation with citations

Two approaches; pick one per answer node:

1. **The provider's native citations.** For example, the Anthropic Messages API accepts retrieved chunks as `document` blocks with citations enabled and returns the exact quoted span for each claim. This is very good for "every claim is sourced". Limitation: it can't be combined with strict structured (JSON) output in the same call.
2. **Prompted citations plus a structured answer:** the model returns JSON along the lines of `{claims: [{text, chunk_ids}], risk_category, ...}`. The next graph node then checks that every `chunk_id` exists and that it supports its claim.

Option 2 fits a LangGraph design better, because the verifier node gets machine-readable claims. Option 1 is a good stretch goal.

## 9. Evaluation (the differentiator)

Build a **gold set** of 60–100 questions. Each item has:

- the question, plus a company profile if needed
- expected risk category, role (provider or deployer), obligations
- expected **jurisdiction × date** facts
- **gold source chunks** (article refs)
- question type: `factual` / `classification` / `date` / `cross-jurisdiction` / `out_of_scope` / `law_unclear`

Metrics:

| Layer | Metric | Tool |
|---|---|---|
| Retrieval | Recall@k and MRR against the gold article refs | A plain Python script (the simplest and most convincing option) |
| Answer | Correctness (LLM judge with a rubric, then a **manual check of a sample**) | LangSmith datasets + evaluators, or DeepEval |
| Citations | Citation precision (does each cited chunk support its claim?) and recall (is the gold article cited?) | Custom judge |
| Faithfulness | Claims supported by the context | RAGAS or DeepEval faithfulness metrics |
| Honesty | On `law_unclear` and `out_of_scope` questions, does it decline or hedge? | Rubric |

Tooling recommendation: **LangSmith** for tracing and running experiments (it integrates directly with LangGraph and has a free tier), plus **DeepEval or RAGAS** for standard metrics in CI. Report retrieval and answer metrics separately, so you know which layer fails.

Run the same question set against the RTR chatbot (with German translations if needed) and the Commission's compliance checker, and publish the comparison.

## 10. Observability and operations (light)

- LangSmith traces for every request, so you can debug wrong answers.
- Log the question, the retrieved chunk ids, the answer and user feedback (thumbs up or down) in Postgres.
- Rate limiting on the public page, since there's no login (cost protection).
- Cache answers for identical normalised questions.

## Summary of picks

| Layer | Pick | Alternative to benchmark |
|---|---|---|
| Parsing | Custom EUR-Lex HTML parser + Docling for PDFs | Unstructured |
| Chunking | Structural (article paragraph) + contextual header | Fixed-size (as an evaluation baseline) |
| Embeddings | Voyage 4 | BGE-M3 / Qwen3-Embedding (self-hosted) |
| Store | Postgres + pgvector + FTS (RRF) | Qdrant hybrid |
| Reranker | Cohere Rerank | BGE-reranker-v2-m3 |
| Dates and countries | Applicability table as a tool | — |
| Evaluation | Gold set + LangSmith + DeepEval/RAGAS | — |
