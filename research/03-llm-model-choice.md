# Model choice for the agent

> Disclosure: this was written by Claude, an Anthropic model. Prices and model IDs below come from Anthropic's current model table (cached 3 Nov 2026). I did **not** price-check other providers, so verify them yourself. LangChain makes the model swappable (`langchain-anthropic`, `langchain-openai`, `langchain-mistralai`, …), so you can benchmark more than one provider in your evaluation. That comparison is itself good report content.

## Different nodes, different needs

The graph in `04` has two kinds of LLM calls:

| Role | Nodes | Needs | Volume |
|---|---|---|---|
| **Reasoner / writer** | profile extraction (role, risk), final answer | Careful legal reasoning, follows long instructions, accurate citations, honest hedging | 1–2 calls per question |
| **Fast helper** | router, retrieval grader, query rewriter, citation checker | Speed, low cost, reliable structured output | 3–8 calls per question |

Using two model tiers is the standard pattern. It's also a good interview talking point about cost and latency engineering.

## Anthropic options (current generation, Nov 2026)

| Model | ID | Context | Input / output per 1M tokens | Use here |
|---|---|---|---|---|
| Claude Opus 5.5 | `claude-opus-5-5` | 1M | $4 / $20 | **Reasoner (recommended default)**: best quality for legal reasoning and citation discipline |
| Claude Sonnet 5.5 | `claude-sonnet-5-5` | 1M | $2 / $10 | Reasoner at half the price: benchmark it against Opus |
| Claude Haiku 5.5 | `claude-haiku-5-5` | 1M | $0.10 / $0.50 | **Fast helper**: router, graders, citation checker |
| Claude Fable 5.2 | `claude-fable-5-2` | 1M | $8 / $40 | More than you need here |

### Rough cost per question

Assumptions: about 12k input tokens of retrieved context plus prompt, about 1.5k visible output, plus thinking tokens (billed as output) at moderate effort.

| Setup | Approx. cost per question | 1,000 questions |
|---|---|---|
| Opus 5.5 writer + Haiku 5.5 helpers | ~$0.08–0.15 | ~$80–150 |
| Sonnet 5.5 writer + Haiku 5.5 helpers | ~$0.04–0.08 | ~$40–80 |
| Haiku 5.5 everywhere | ~$0.005 | ~$5 |

These are estimates, not measurements. Measure real token use from LangSmith traces during evaluation. **Prompt caching** on the fixed system prompt and the applicability table cuts input cost noticeably on repeated requests.

**My recommendation:** build with **Opus 5.5 as the writer and Haiku 5.5 as the helper**. Then run your evaluation set on **Sonnet 5.5 as the writer** too, and publish the quality-versus-cost table. Whether Opus is worth the extra cost for a free public page is your call once you have the numbers.

### API details that will affect a LangGraph build (check them in the docs when you code)

These are specific to the current Claude models and affect how you use them through LangChain:

1. **Forced tool choice is rejected** on Opus 5.5 and Sonnet 5.5 (`tool_choice` set to `any` or a specific tool returns a 400 error). Some LangChain helpers, such as `with_structured_output` in certain modes, get structured output by forcing a tool call. Use the provider's **native structured-output (JSON schema) mode** instead, and check which method `langchain-anthropic` uses for these models.
2. **Thinking can't be turned off on Opus 5.5.** You control it with the `effort` setting (`low` → `max`, default `medium`). Use `low` effort for quick nodes if you put Opus there, and `medium` or `high` for the final answer.
3. **No assistant prefill** (you can't pre-write the start of the reply). Use structured output or system-prompt instructions instead.
4. **The `temperature` parameter is no longer accepted.** Don't copy old tutorials that set `temperature=0` "for determinism". Use effort and structured output instead.
5. **Native citations** (document blocks with citations enabled) can't be combined with structured JSON output in the same call. See `02` § 8.
6. **Refusals**: always check the stop reason. A legal-information assistant is low-risk, but handle the case anyway.

Many 2024–2025 LangGraph tutorials use older APIs. Check every snippet you borrow against the current docs.

## Non-Anthropic alternatives (not verified here)

| Option | Why consider it |
|---|---|
| **Mistral** (EU company, EU hosting) | Good story for an EU-compliance product ("EU data, EU model"); strong in French and other European languages |
| **OpenAI GPT models** | Widely used in LangChain tutorials, so many examples exist |
| **Open-weight models served locally** (e.g. the Qwen or Llama families via vLLM or Ollama) | Same approach as RTR (fully local). Zero data leaves your machine. Weaker reasoning and more hosting work |

If you include one non-Anthropic writer in the benchmark, the evaluation report gets more interesting and you show model-agnostic LangChain skills.

## Embeddings and reranker models

Covered in `02-rag-stack.md` (Voyage 4 / BGE-M3 / Qwen3-Embedding; Cohere Rerank / BGE-reranker). Anthropic doesn't provide embedding models.

## Decision checklist

- [ ] Monthly budget for the public page: this sets the writer model and the rate limit.
- [ ] Is "data stays in the EU" part of the pitch? If so, consider an EU-hosted provider or a self-hosted model, at least as a benchmarked option.
- [ ] Writer models to benchmark: Opus 5.5 vs Sonnet 5.5 (+ optionally one non-Anthropic model).
