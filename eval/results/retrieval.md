# Retrieval eval

- Date: 2026-11-19 · corpus 2026-11-18 · embeddings `bge-m3` · 29 questions with gold refs (`eval/questions.yaml`)
- Dense: pgvector cosine top-30 · keyword: BM25 over Postgres English tsvectors top-30 · fused with RRF (k=60)
- Cited law: AI Act chunks cited by the top-10 guideline/FAQ/recital hits join the fusion
- Exact refs: the best chunk of each article/annex/recital named in the question goes first

## Summary

| config | hit@5 | hit@10 | recall@5 | recall@10 | MRR |
|---|---|---|---|---|---|
| dense | 0.62 | 0.76 | 0.59 | 0.72 | 0.45 |
| keyword (BM25) | 0.48 | 0.59 | 0.45 | 0.55 | 0.33 |
| hybrid | 0.55 | 0.69 | 0.52 | 0.66 | 0.37 |
| hybrid + cited law | 0.72 | 0.79 | 0.71 | 0.78 | 0.54 |
| hybrid + cited law + exact refs | 0.76 | 0.83 | 0.74 | 0.81 | 0.55 |
| dense + cited law + exact refs | 0.62 | 0.90 | 0.60 | 0.88 | 0.52 |

## By question type (hybrid + cited law + exact refs)

| type | n | hit@5 | recall@10 | MRR |
|---|---|---|---|---|
| date | 2 | 0.50 | 0.50 | 0.17 |
| definition | 3 | 0.67 | 0.67 | 0.67 |
| faq | 1 | 1.00 | 1.00 | 0.50 |
| gpai | 1 | 1.00 | 1.00 | 0.33 |
| high_risk | 4 | 0.75 | 0.88 | 0.50 |
| named_ref | 3 | 1.00 | 1.00 | 1.00 |
| obligations | 4 | 0.75 | 1.00 | 0.27 |
| penalties | 2 | 1.00 | 1.00 | 0.75 |
| prohibited | 3 | 0.33 | 0.33 | 0.08 |
| scope | 1 | 0.00 | 0.00 | 0.00 |
| transparency | 5 | 1.00 | 1.00 | 1.00 |

## Questions with a gold ref outside the top 5 (hybrid + cited law + exact refs)

| id | question | gold → rank | top 3 returned |
|---|---|---|---|
| q04 | Who counts as a deployer under the AI Act? | Art. 3(4) → >10 | Art. 2(10), Art. 50(4), Art. 50 Guidelines, para. 14 |
| q12 | Can we use software that detects our employees' emotions during video meetings? | Art. 5(1)(f) → >10 | Art. 50(3), Art. 3(39), Service Desk FAQ: Is emotion recognition prohibited in workplace/education settings or for these purposes (e.g. employee monitoring)? |
| q14 | Why does the AI Act ban emotion recognition at work and in schools? | Recital 44 → >10 | Art. 50(3), Art. 3(39), Art. 5(1)(a) |
| q15 | We are building a tool that screens CVs and ranks job applicants. Is it high-risk? | Annex III point 4 → 1; Art. 6(2) → >10 | Annex III point 4, Recital 90, Art. 14(1) |
| q16 | Is an AI system that decides who gets a consumer loan based on creditworthiness high-risk? | Annex III point 5 → 6 | Art. 6(1), Art. 5(1)(a), Recital 58 |
| q20 | What must the provider of a high-risk AI system do before and after placing it on the market? | Art. 16 → 8 | Art. 25(3), Art. 25(1), Art. 6(4) |
| q23 | When do the rules for high-risk AI systems listed in Annex III start to apply? | Art. 113 → >10 | Annex III point 2, Annex III point 8, Annex III point 1 |
| q27 | We are a US company with no EU office, but the output of our AI system is used in the EU. Does the AI Act apply to us? | Art. 2(1) → >10 | Art. 50(1), Art. 50(2), Art. 2(6) |
