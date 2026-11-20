# AI Act Assistant

Describe what your company does with AI, or ask a question about the EU AI Act. The assistant tells you which obligations probably apply, in which EU/EEA countries and from when, and cites the article, guideline or table row behind each point.

- Runs fully locally: qwen3.5 9B through Ollama, BGE-M3 embeddings, Postgres + pgvector.
- Dates and country facts come from hand-checked tables (`tables/`), not from the model.
- One answer takes about a minute on an M4 laptop. The steps above each answer show what the agent decided.
- Corpus as of 18 November 2026. General information, not legal advice.
