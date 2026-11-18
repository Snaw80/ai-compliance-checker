# Agent execution graph (LangGraph)

## Which graph shape?

LangGraph supports three broad shapes. Here is how each fits this project:

| Shape | What it is | Verdict |
|---|---|---|
| **A. Simple RAG chain** | retrieve → generate | Too weak: no clarifying questions, no per-country reasoning, no checks. Keep it as the **evaluation baseline**. |
| **B. ReAct agent** (`create_agent` / prebuilt agent with tools) | The LLM decides in a loop which tool to call | Flexible, but hard to evaluate and debug. Cost and latency are unpredictable. It can skip retrieval and answer from memory, which is dangerous for legal facts. |
| **C. Custom `StateGraph` workflow with bounded agentic loops** | You define the nodes and edges; the LLM makes decisions only at specific points (routing, grading) | ✅ **Recommended.** Predictable, testable node by node, and it shows the most LangGraph skill (state, conditional edges, parallel fan-out, checkpoints, interrupts). |

This follows Anthropic's "Building effective agents" advice: use a **workflow** when the steps are known, and add agentic loops only where they help. Here, the corrective-retrieval loop is the agentic part.

Interview pitch: *"I benchmarked a plain RAG chain against a corrective-RAG LangGraph workflow, and here's the measured difference."* Shape A is your baseline and shape C is the product.

---

## The recommended graph

```
                         ┌──────────────┐
            user msg ──▶ │   router     │  (fast model, structured output)
                         └──────┬───────┘
         ┌──────────────┬───────┼─────────────────┬────────────────┐
         ▼              ▼       ▼                 ▼                ▼
   off_topic /     general_law  company_case   follow_up      exact_article
   unsafe          question     ("we use AI    (uses saved    ("what does
     │               │          for X")         profile)       Art. 50 say")
     │               │              │               │                │
     │               │              ▼               │                │
     │               │      ┌───────────────┐       │                │
     │               │      │ build_profile │◀──────┘                │
     │               │      │ role, system, │                        │
     │               │      │ sector, users,│                        │
     │               │      │ countries     │                        │
     │               │      └──────┬────────┘                        │
     │               │     missing │ info?                           │
     │               │      ┌──────┴──────┐                          │
     │               │      ▼             ▼                          │
     │               │  ask_clarify    complete                      │
     │               │  (interrupt →      │                          │
     │               │   wait for user)   │                          │
     │               │                    ▼                          │
     │               │          ┌──────────────────┐                 │
     │               │          │ classify_risk    │ prohibited?     │
     │               │          │ (prelim. tier +  │ high-risk?      │
     │               │          │  candidate       │ Art.50? minimal │
     │               │          │  obligations)    │                 │
     │               │          └────────┬─────────┘                 │
     │               ▼                   ▼                           ▼
     │        ┌─────────────────────────────────────────────────────────┐
     │        │ resolve_jurisdictions: where established / where users  │
     │        │   / EU market? → [EU] + countries (cap 5 in detail)     │
     │        └────────────────────────┬────────────────────────────────┘
     │                                 ▼
     │        ┌─────────────────────────────────────────────────────────┐
     │        │ plan_research: EU sub-tasks per topic + one sub-task    │
     │        │   per country, e.g. [EU: Art.50 chatbot],               │
     │        │   [FR: authority+national law], [IT: Law 132/2025],     │
     │        │   [NO: EEA status + extraterritoriality]                │
     │        └────────────────────────┬────────────────────────────────┘
     │                                 │  fan-out with Send()  (parallel)
     │                ┌────────────────┼────────────────┐
     │                ▼                ▼                ▼
     │        ┌─────────────────────────────────────────────┐
     │        │  research_subgraph (one per sub-task)       │
     │        │                                             │
     │        │   retrieve (hybrid + filter + rerank)       │
     │        │        │                                    │
     │        │        ▼                                    │
     │        │   grade_docs (fast model)                   │
     │        │     ├─ relevant ─────────────▶ done         │
     │        │     └─ weak ─▶ rewrite_query ─▶ retrieve    │
     │        │                (max 2 loops, then           │
     │        │                 done + "low_confidence")    │
     │        │                                             │
     │        │   lookup_applicability (deterministic table)│
     │        │   get_country_profile (country tasks)       │
     │        │   country tier = deep → also national RAG   │
     │        │     (query translated to national language) │
     │        │   tier = profile_only → profile + caveat    │
     │        └──────────────────────┬──────────────────────┘
     │                               │  fan-in (reducer merges evidence)
     │                               ▼
     │                     ┌───────────────────┐
     │                     │ generate_answer   │ (reasoning model)
     │                     │ structured claims │
     │                     │ + citations       │
     │                     └─────────┬─────────┘
     │                               ▼
     │                     ┌───────────────────┐
     │                     │ verify_citations  │ (fast model + code checks)
     │                     └─────────┬─────────┘
     │                    ok │               │ unsupported claims
     │                       │               ▼
     │                       │       revise_answer (once) ──▶ verify again
     │                       │               │ still failing
     │                       ▼               ▼
     │                ┌──────────────────────────────┐
     └──────────────▶ │ finalize                     │
                      │ - format per jurisdiction    │
                      │ - sources list + links       │
                      │ - "not legal advice" notice  │
                      │ - hedge if low_confidence or │
                      │   draft / contested sources  │
                      └──────────────────────────────┘
```

## Nodes in detail

| Node | Type | Model | Input → output | Why it exists |
|---|---|---|---|---|
| `router` | LLM, structured | Fast | message + history → `intent` | Off-topic questions skip the pipeline. "What does Art. 50 say" goes straight to retrieval. |
| `build_profile` | LLM, structured | Reasoner | conversation → `CompanyProfile` (role: provider/deployer/both/unknown, system description, purpose, sector, end users, countries, EU customers?) | **The core of correctness.** Obligations depend on role and use case. |
| `ask_clarify` | `interrupt` | Fast | missing fields → one targeted question | Asks only what changes the answer, for example "Did you build the chatbot or buy a ready-made one?" Limit it to one or two rounds. |
| `classify_risk` | LLM + retrieval of Art. 5, Art. 6 and Annex III | Reasoner | profile → preliminary tier + candidate obligations + uncertainty | The tier is *preliminary*. The research step confirms it. |
| `resolve_jurisdictions` | LLM, structured + code | Fast | profile → `[EU] + [countries]` with reason (established / users / market) | Placing a system on the EU market brings in the EU layer for any company. Countries are added for national specifics. Above 5 countries, the rest get a compact authority table only. See `05` § 6. |
| `plan_research` | Code + LLM | Fast | profile + tier + jurisdictions → list of sub-tasks | Mostly code: EU sub-tasks per obligation, plus one sub-task per country. Deterministic is better here. |
| `get_country_profile` | Tool, deterministic | — | country → authorities, national law status, penalties, sandbox, coverage tier, last_verified, sources | Makes "any EU country" possible without 27 corpora. Answers show `last_verified`. |
| `research_subgraph` | **Subgraph**, run in parallel via `Send` | Fast for grading | sub-task → `Evidence` (chunks, applicability rows, confidence) | The corrective RAG (CRAG) pattern, with a loop cap. |
| `lookup_applicability` | Tool, deterministic | — | (obligation, jurisdiction, today) → status and date | Dates and countries never come from the LLM's memory. |
| `generate_answer` | LLM, structured | Reasoner | profile + evidence → `Answer{risk_tier, obligations[], per_jurisdiction[], claims[{text, chunk_ids}], caveats}` | Machine-readable, so it can be verified. |
| `verify_citations` | Code + LLM | Fast | answer + chunks → pass / fail list | Code checks that every chunk id exists. The LLM checks that each chunk supports its claim. This is the Self-RAG idea, applied to citations. |
| `revise_answer` | LLM | Reasoner | answer + failures → fixed answer | **One** retry, then hedge instead of looping. |
| `finalize` | Code (template) | — | answer → markdown | Formatting and the disclaimer are deterministic. Layout: "EU rules (apply in every member state)" first, then "Country specifics" per country with `last_verified`. |

## State (conceptual; no code yet)

The shared state of the graph holds:

- `messages`: the conversation (with LangGraph's message-appending reducer)
- `intent`
- `profile`: CompanyProfile, kept across turns so follow-ups reuse it
- `risk_assessment`
- `research_tasks`
- `evidence`: a list with an **append reducer**, so parallel branches merge their results instead of overwriting each other
- `draft_answer`, `verification`, `revision_count`
- `flags`: low_confidence, uses_draft_source, law_contested

## LangGraph features this uses (good for the resume)

| Feature | Where |
|---|---|
| `StateGraph` + typed state + reducers | Whole graph; `evidence` merging |
| Conditional edges | router, grade loop, verify loop |
| **`Send` API (map-reduce fan-out)** | Parallel per-jurisdiction research |
| **Subgraphs** | `research_subgraph`, testable in isolation |
| **Checkpointer** (Postgres) | Multi-turn memory per `thread_id`, so follow-ups keep the profile |
| **`interrupt`** (human-in-the-loop) | `ask_clarify` pauses the graph until the user answers |
| Streaming | Stream node progress ("Checking Finnish rules…") and answer tokens to the UI |
| Recursion limit / loop counters | Hard caps on rewrite and revise loops |
| LangSmith tracing | Debugging and evaluation experiments |

The exact API names (`Send`, `interrupt`, `Command`, the checkpointer package names) should be checked against the LangGraph 1.2 docs when you start coding. Tutorials from 2024 often use older signatures.

## Latency and cost per question

- Typical path (no clarification, first retrieval good): about 2 reasoner calls + 4–6 fast calls. The parallel research branches keep wall-clock time down.
- Worst case: with 2 rewrites per branch and 1 revision, about 3 reasoner calls + 12 fast calls.
- Stream progress to the UI so a 10–20 s answer feels responsive.

## Build order (incremental, always evaluable)

1. **v0, baseline:** `retrieve → generate_answer → finalize`. Run the evaluation and record the numbers.
2. **v1:** add `router` + `build_profile` + `ask_clarify` (with the checkpointer). Evaluate on company-case questions.
3. **v2:** add `resolve_jurisdictions` + `plan_research` + parallel `research_subgraph` + `lookup_applicability` + `get_country_profile` (all countries at the profile tier). Evaluate on cross-jurisdiction and date questions.
3b. **v2.5:** add national RAG for the first deep-tier country. Evaluate deep-tier vs profile-only questions separately.
4. **v3:** add the CRAG grade/rewrite loop. Evaluate retrieval recall.
5. **v4:** add `verify_citations` + `revise_answer`. Evaluate citation precision.

Each step gets one row in your published results table. That table shows the value of each graph component and is the strongest artefact for your resume.

## Things to avoid

- Letting the LLM answer "from when" questions from its own knowledge. Training data predates the Omnibus.
- Open-ended loops. Cap every loop and fall back to an honest "I'm not sure".
- Over-agentifying. If a step can be code (planning per jurisdiction, formatting, disclaimers), make it code.
- Hiding draft status. When evidence comes from a draft (the Art. 6 guidelines, Norway's KI-lov), say so in the answer.
