# Answer eval: baseline vs agent

- Date: 2026-11-19 · answers as of 2026-11-19 · 35 questions (`eval/questions.yaml`)
- Writer `qwen3.5:9b`, fast model `qwen3.5:9b`, judge `qwen3.5:9b` (Ollama, thinking off)
- **baseline** (v0): hybrid search top-8 → writer → code citation check. Same prompt and rendering as the agent.
- **agent** (day 4): router → company profile ⇄ clarifying question → plan (code: obligations, countries)
  → research (law of the selected obligations + search + applicability table + country profiles) → writer → code check
- Raw answers: `eval/results/answers.jsonl`. Score: judge vs expected gist (correct 1, partial 0.5, wrong 0).
  The judge is a 9B local model of the same family: indicative, spot-check the raw answers.

## Summary

| system | score | cites gold | unsupported points | answers with bad dates | errors | median s |
|---|---|---|---|---|---|---|
| baseline | 0.79 | 0.82 | 0.02 | 1 | 0 | 37 |
| agent | 0.86 | 0.85 | 0.00 | 0 | 0 | 62 |

## By question group

| questions | n | baseline score | agent score |
|---|---|---|---|
| general | 29 | 0.81 | 0.84 |
| out of scope | 1 | 1.00 | 1.00 |
| company case | 5 | 0.60 | 0.90 |

## Per question

| id | type | baseline | agent | agent asked / role | judge note (agent, if not correct) |
|---|---|---|---|---|---|
| q01 | named_ref | correct | partial |  | The assistant's answer correctly identifies the core obligation of Article 50(1) regarding informing natural persons about AI interaction. However, it misses the specific exception mentioned in the expected answer ("unle |
| q02 | named_ref | correct | correct |  |  |
| q03 | named_ref | correct | correct |  |  |
| q04 | definition | correct | correct |  |  |
| q05 | definition | correct | correct |  |  |
| q06 | definition | correct | correct |  |  |
| q07 | transparency | partial | correct | asked 1, unknown |  |
| q08 | transparency | partial | correct | asked 1, unknown |  |
| q09 | transparency | correct | correct | asked 1, unknown |  |
| q10 | transparency | partial | partial |  | The assistant's answer correctly identifies the standard ("reasonably well-informed, observant and circumspect person") and the requirement for the provider to assess and demonstrate this. However, it misses the key poin |
| q11 | transparency | correct | partial | asked 1, unknown | The assistant's answer correctly identifies the core exception: disclosure is not required if human review/editorial control exists AND a person holds editorial responsibility. It also correctly adds the nuance that subs |
| q12 | prohibited | correct | correct | asked 1, unknown |  |
| q13 | prohibited | correct | correct |  |  |
| q14 | prohibited | partial | partial |  | The assistant's answer misses the key reasons specified in the expected answer: concerns about the scientific basis (limited reliability, specificity, generalisability) and the power imbalance in work and education conte |
| q15 | high_risk | partial | partial | built | The assistant correctly identifies the system as high-risk under Annex III point 4(a) and cites the correct application dates (2 Dec 2027 for high-risk/deployer duties, 2 Aug 2026 for conformity assessment/registration,  |
| q16 | high_risk | correct | partial |  | The assistant correctly identifies the system as high-risk and cites the correct exception for fraud detection. However, it contradicts the expected answer by stating the application date is 2 December 2027, whereas the  |
| q17 | high_risk | correct | correct |  |  |
| q18 | high_risk | correct | correct |  |  |
| q19 | obligations | partial | partial |  | The assistant's answer correctly identifies the core deployer duties (use per instructions, monitoring, incident reporting) and cites the relevant articles. However, it misses key obligations explicitly listed in the exp |
| q20 | obligations | correct | correct |  |  |
| q21 | obligations | partial | correct |  |  |
| q22 | obligations | correct | partial | asked 2, unknown | The assistant correctly identifies the user as a provider under Art. 25(1)(a) but contradicts the expected answer by adding "without prejudice to contractual arrangements," which the expected answer explicitly includes.  |
| q23 | date | wrong | correct |  |  |
| q24 | date | correct | correct | asked 1, unknown |  |
| q25 | penalties | correct | correct |  |  |
| q26 | penalties | partial | correct |  |  |
| q27 | scope | partial | correct | asked 2, unknown |  |
| q28 | gpai | correct | partial |  | The assistant's answer correctly identifies the key obligations (technical documentation, info for downstream providers, copyright policy, training summary) and the open-source exemptions as per the expected answer. Howe |
| q29 | faq | correct | correct |  |  |
| q30 | out_of_scope | correct | correct |  |  |
| q31 | company_case | partial | correct | asked 1, built |  |
| q32 | company_case | partial | correct | bought |  |
| q33 | company_case | partial | correct | built |  |
| q34 | company_case | correct | correct | asked 1, built |  |
| q35 | company_case | partial | partial | asked 1, bought | The assistant's answer correctly identifies the user as a deployer, the AI literacy obligation (Art. 4) applicable since 2 February 2025, and the transparency obligation (Art. 50(1)) applicable since 2 August 2026. It al |
