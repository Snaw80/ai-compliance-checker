# Research overview: AI Act Assistant

Research date: **18 November 2026**. Everything below was checked against web sources on that date. The law is still moving, so re-check the dates before you build the corpus.

## Files in this folder

| File | What it answers |
|---|---|
| `00-overview.md` | Summary, fact-check of the project description, decisions to make |
| `01-ai-act-reading-list.md` | What to read to understand the problem, in order |
| `02-rag-stack.md` | Retrieval technology: corpus, chunking, embeddings, vector store, reranking, evaluation |
| `03-llm-model-choice.md` | Which LLM to use for each part of the agent, and what it costs |
| `04-agent-graph.md` | The LangGraph execution graph for the agent workflow |
| `05-country-coverage.md` | **Scope change: any EU/EEA country.** Three-layer design, country table, tiers, multilingual retrieval, freshness |

> **Scope update:** the target is now *any EU country* (+ EEA), not only Finland and Norway. See `05`. Short version: the AI Act is the same everywhere, so we keep one deep EU corpus, add a **structured profile table for all 27 + 3 EEA countries**, and add national documents only for 2–5 "deep" countries.

## Recommendation in five lines

1. **Corpus:** consolidated AI Act (with the 2026 Omnibus changes), Commission guidelines and the Service Desk FAQ (EU layer), plus national law and guidance for a few deep-coverage countries only. That's a small corpus of a few thousand chunks, all with dates and jurisdictions attached.
2. **Retrieval:** chunk by article and paragraph, use hybrid search (keyword plus vectors), add a reranker, and expand cross-references. Use Postgres with pgvector, so one database also holds the LangGraph checkpoints and the waitlist.
3. **Dates and countries go in tables, not in retrieval.** A hand-checked applicability table ("which obligation applies from when") and a **country profile table** (authorities, national law status, penalties, sandbox, last verified, for every EU/EEA country) are read through tools. The model never infers dates or authorities from retrieved text or from memory.
4. **Graph:** a mostly fixed LangGraph `StateGraph`: route → build a company profile → ask a clarifying question if needed → research in parallel per jurisdiction (with one bounded corrective-retrieval loop) → write the answer → check the citations → respond. Avoid a free-form ReAct agent: it's harder to evaluate, and evaluation is a selling point of this project.
5. **Models:** one strong model writes the answer, and a cheap fast model routes, grades and checks citations. Details and costs are in `03`.

## Fact-check of `ai-act-assistant-description.md`

The description mostly holds up against current sources. Four points need attention:

| Claim in the description | Status (Nov 2026) | Note |
|---|---|---|
| "Some obligations were postponed to 2027" | ✅ Correct | Digital Omnibus on AI, Regulation (EU) 2026/1744, in force 27 July 2026. Annex III high-risk moved from 2 Aug 2026 to **2 Dec 2027**. AI in Annex I regulated products moved to **2 Aug 2028**. |
| "Finland started national enforcement in January 2026" | ✅ Correct | Act on the Supervision of Certain AI Systems (1377/2025), in force 1 Jan 2026. A second-phase amendment is still pending, and sources disagree on its timing. |
| "Traficom is the authority to contact" (chatbot example) | ⚠️ Mostly correct | Traficom supervises **transparency** (Art. 50) and is the national single point of contact. High-risk supervision is **split across sectoral authorities**. The assistant must not name Traficom for every question. |
| "Norway's own version is expected to reach Parliament in 2027" | ✅ Correct | New consultation in autumn 2026. A consultation on the Omnibus changes runs until 11 Dec 2026. The bill is targeted for spring 2027. The AI Act is **not yet incorporated into the EEA Agreement**. |
| Chatbot transparency "applied since August 2026" | ⚠️ Needs nuance | Art. 50 applies EU-wide from 2 Aug 2026; it isn't specific to Finland. The Omnibus grace period to **2 Dec 2026** applies to *marking generated content* (Art. 50(2)) for systems already on the market, not to the chatbot disclosure in Art. 50(1). Confirm this against the consolidated text. |
| Compare with "the free chatbot published by Austria's AI regulator" | ⚠️ Watch out | RTR's KI-Servicestelle chatbot is **German-language**. Your test set is in English. Decide whether to translate the questions or compare on a German subset. |

## Hidden difficulty: who is the "provider"?

Most obligations depend on the company's **role**: provider, deployer, importer or distributor (Art. 3, Art. 25). A startup that puts its own branded chatbot on top of an LLM API may be a *provider* of that system, not only a deployer. The agent's intake step has to work out the role, or the answers will be wrong. This is the most important thing to get right in the graph (see `04`).

## Scope risk

Two weeks is tight. A realistic split:

- **Days 1–3:** EU corpus collection and cleaning (this always takes longer than expected for legal text) + **country profile table seeded for all 30 countries** (about one day).
- **Days 4–6:** retrieval plus a 30-question test set, measuring retrieval only.
- **Days 7–10:** LangGraph workflow, citation check, minimal web UI.
- **Days 11–14:** add 2–3 deep countries, expand the test set to 60–100 questions, run the comparison, write the report.

If you run late, cut the number of deep countries (keep the profile table for all of them) before cutting evaluation. The published evaluation is what makes this project stand out on a resume.

## Decisions for you

1. **Language:** Python (the main LangGraph ecosystem) or TypeScript (LangGraph.js)? Python is assumed in these notes.
2. **Model provider:** see `03`. The trade-off is answer quality against cost per question on a public page with no login.
3. **Hosted or self-hosted embeddings:** see `02`. Hosted is quicker. Self-hosted gives a "data stays in Europe" story, as RTR does.
4. **Test-set comparison with RTR:** translate to German or not.
5. **Which countries get deep coverage?** Suggested: France (you can check French sources yourself), Italy (the most substantial national AI law), Germany (largest market), and optionally Finland and Norway as the EEA case. See `05` § 2.
6. **Update the project description?** It still says "Nordics" and "only EU, Finland and Norway".
