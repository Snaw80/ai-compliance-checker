# Reading list: understanding the AI Act problem

Ordered for the project. Read **section A** before anything else (about half a day). Sections B–E are what you'll need for the corpus and the test set. Section F covers the technology.

Legend: 🟢 primary or official source (goes in the RAG corpus), 🔵 secondary analysis (read to understand; don't use as a citation source), ⚠️ check the date or status before relying on it.

---

## A. Get the big picture (start here)

1. 🔵 **EU AI Act high-level summary** (Future of Life Institute): https://artificialintelligenceact.eu/high-level-summary/
   About ten minutes of reading on risk tiers, provider and deployer roles, and the GPAI rules. It's the best entry point. It was written before the 2026 Omnibus, so the dates are out of date.
2. 🟢 **AI Act Explorer** (same site, article by article): https://artificialintelligenceact.eu/ai-act-explorer/
   Read these articles in this order. They are the core of almost every SME question:
   - **Art. 2:** scope, including who is covered outside the EU. This matters for Norway.
   - **Art. 3:** definitions ("AI system", "provider", "deployer", "placing on the market").
   - **Art. 4:** AI literacy, softened by the Omnibus (see B).
   - **Art. 5:** prohibited practices.
   - **Art. 6 + Annex III:** when a system is high-risk. Art. 6(3) covers the "not actually high-risk" exception.
   - **Art. 25:** when a deployer *becomes* a provider, for example by putting its own name on a system or changing its purpose.
   - **Art. 26:** deployer obligations for high-risk systems.
   - **Art. 50:** transparency (chatbots, deepfakes, generated content). This is the main obligation for most of your users.
   - **Art. 99:** penalties.
   - **Art. 113:** application dates. The Omnibus amended them, so read the amended version.
3. 🟢 **Official text, Regulation (EU) 2024/1689** on EUR-Lex: https://eur-lex.europa.eu/eli/reg/2024/1689/oj
   Use the **consolidated version** that includes the Omnibus amendments when you build the corpus. EUR-Lex publishes consolidated texts under "Current consolidated version". Check that it is dated after 27 July 2026.

## B. What changed in 2026: the Digital Omnibus on AI

The single most important update. Most blog posts written before mid-2026 are now out of date.

4. 🟢⚠️ **Regulation (EU) 2026/1744** (Digital Omnibus on AI), published in the Official Journal on 24 July 2026, in force on 27 July 2026. Search EUR-Lex for "2026/1744". The number comes from secondary sources and I didn't open the official text.
5. 🔵 **Orrick: "Digital Omnibus Finalizes 8 Compliance Changes"** (July 2026): https://www.orrick.com/en/Insights/2026/07/EU-AI-Act-Update-Digital-Omnibus-Finalizes-8-Compliance-Changes
   A clear list of the new dates: Annex III high-risk moves to 2 Dec 2027, Annex I products to 2 Aug 2028, public authorities to 2 Aug 2030.
6. 🔵 **Lewis Silkin: "The Digital Omnibus on AI enters into force today"**: https://www.lewissilkin.com/insights/2026/07/27/the-digital-omnibus-on-ai-enters-into-force-today-102nedo
7. 🔵 **Stibbe: "AI Act reloaded? What the latest changes mean in practice"**: https://www.stibbe.com/publications-and-insights/ai-act-reloaded-what-the-latest-ai-act-changes-mean-in-practice
   Practical angle, covering the AI literacy change (Art. 4 became an "obligation of effort") and the SME and small mid-cap relief.
8. 🔵 **CDT: "Final AI Omnibus Text Dilutes Fundamental Rights Protections"**: https://cdt.org/?p=11417
   The critical view. It's useful for understanding where the law is genuinely contested, which is where your assistant should say "ask a professional".

## C. Commission guidance (goes in the corpus)

Index page for all official guidance: https://digital-strategy.ec.europa.eu/en/policies/regulatory-framework-ai

9. 🟢 **Guidelines on Article 50 transparency obligations**, final version adopted 20 July 2026.
   Summary: Stephenson Harwood, https://www.stephensonharwood.com/post/102nfqh/eu-ai-act-update-european-commission-adopts-guidelines-on-article-50-transparency-obligations/
   This is the most relevant document for the "we have a chatbot" use case.
10. 🟢 **Code of Practice on Transparency of AI-Generated Content** (10 June 2026, voluntary). Covers Art. 50(2), (4) and (5), **not** the chatbot disclosure in 50(1).
    FAQ: https://digital-strategy.ec.europa.eu/en/faqs/code-practice-transparency-ai-generated-content
11. 🟢⚠️ **Draft guidelines on high-risk classification (Art. 6)**, published 19 May 2026. **Still a draft**; the final version is promised by end of 2026.
    https://digital-strategy.ec.europa.eu/en/library/draft-commission-guidelines-classification-high-risk-ai-systems
    Summary: Jones Day, https://jonesday.com/en/insights/2026/06/draft-eu-guidelines-clarify-when-ai-systems-are-highrisk-under-the-ai-act
    → Your corpus metadata needs a `status: draft | final` field because of this document.
12. 🟢 **Guidelines on the definition of an AI system** and **Guidelines on prohibited AI practices** (both February 2025). They're on the index page above. They answer "is my software even an AI system?", which is a common SME question.
13. 🟢⚠️ **AI Act Service Desk / Single Information Platform** (European Commission): https://ai-act-service-desk.ec.europa.eu/
    It includes an official FAQ and a compliance checker. This is a **competitor** and also a **source**. Check that it's still live.

## D. National implementation

### All member states (start here for the "any EU country" scope; see `05`)
- 🟢 **AI Act Service Desk, Article 70** (national authorities; points to the Commission's continuously updated list): https://ai-act-service-desk.ec.europa.eu/en/ai-act/article-70
- 🔵 **FLI: national implementation plans** (one table, EU-27 + EEA; last update 17 June 2026): https://artificialintelligenceact.eu/national-implementation-plans/
- 🔵 **Cullen International: "Status of national AI laws across Europe"** (June 2026): https://www.cullen-international.com/news/2026/06/Status-of-national-AI-laws-across-Europe.html
- 🔵 **Cullen International: snapshot of AI laws, regulatory bodies and penalties** (April 2026): https://www.cullen-international.com/news/2026/04/National-implementation-of-the-EU-AI-Act--a-snapshot-of-AI-laws--regulatory-bodies-and-penalties.html
- 🔵 **regulatoryai.eu: all 27 national regulators** (Sept 2026): https://www.regulatoryai.eu/ai-act-authorities/
- 🔵 **IAPP: EU AI Act Regulatory Directory**: https://iapp.org/resources/article/eu-ai-act-regulatory-directory
- 🔵 **Italy, Law 132/2025** (the first comprehensive national AI law): Linklaters summary, https://www.linklaters.com/insights/blogs/digilinks/2025/september/italy--a-pioneering-national-framework-to-complement-the-eu-ai-act ; the debate over whether it goes beyond the AI Act: https://verfassungsblog.de/italys-constitutional-gamble/

### Finland
14. 🟢 **Traficom: guidance on the new transparency obligations** (August 2026): https://traficom.fi/en/news/more-transparency-now-required-when-ai-used-traficom-published-guidance-new-obligations
15. 🔵 **Hannes Snellman: "EU AI Act: latest regulatory developments in Finland"**: https://www.hannessnellman.com/news-and-views/blog/eu-ai-act-latest-regulatory-developments-in-finland
    Explains Act 1377/2025, the sectoral authorities and the phase-two amendments.
16. 🔵 **Bird & Bird AI Regulatory Horizon Tracker, Finland**: https://www.twobirds.com/en/capabilities/artificial-intelligence/ai-legal-services/ai-regulatory-horizon-tracker/finland
17. 🟢 **Finlex** (official Finnish legislation database), entry for Act 1377/2025. Use the English or Swedish translation if one exists. Otherwise note in the corpus metadata that the source is Finnish only.

### Norway
18. 🟢 **Regjeringen: original KI-lov consultation** (30 June 2025): https://www.regjeringen.no/no/aktuelt/lov-om-kunstig-intelligens-i-norge-sendes-na-pa-horing/id3113732/
19. 🟢 **Regjeringen: "Tung vil sende KI-loven med endringer på høring"** (4 Aug 2026, new consultation and 2027 target): https://www.regjeringen.no/no/aktuelt/tung-vil-sende-ki-loven-med-endringer-pa-horing/id3169693/
20. 🟢 **Regjeringen: consultation on the EU Omnibus changes** (30 Oct 2026, deadline 11 Dec 2026): https://www.regjeringen.no/no/aktuelt/regjeringen-sender-forenklinger-i-ki-forordningen-pa-horing/id3187283/
21. 🔵 **BAHR: "The EU AI Act: a call and guide to implementation for Norwegian asset managers"**: https://bahr.no/newsletter/asset-management-the-eu-ai-act-a-call-and-guide-to-implementation-for-norwegian-asset-managers
    Written for asset managers, but it explains clearly why Norwegian companies are affected *before* the EEA incorporation.
22. 🔵 **Computer Weekly: "EU regulation sharpens fear of Norwegian AI exodus"**: https://www.computerweekly.com/news/366632823/EU-regulation-sharpens-fear-of-Norwegian-AI-exodus
    Context for your user interviews.

> Most Norwegian primary sources are in Norwegian. Decide whether the corpus keeps the original language, which the LLM can read, and answers in English. Keeping the original is recommended, so the citation points to the real document.

## E. Competitors and the comparison target

23. **RTR KI-Servicestelle chatbot** (Austria): https://www.rtr.at/rtr/service/ki-servicestelle/
    Read the **technical documentation**: https://www.rtr.at/rtr/service/ki-servicestelle/chat/technical-documentation.en.html
    It's an open-source RAG over the AI Act plus RTR publications, with locally hosted models. It's German-language. This is your comparison baseline, and its documentation is a useful architecture reference.
24. **FLI EU AI Act Compliance Checker** (questionnaire): on artificialintelligenceact.eu. A good example of the "short questionnaire, generic label" tools your description criticises.

## F. Technology reading (for files 02–04)

25. **Anthropic: "Building effective agents"** (Dec 2024): https://www.anthropic.com/research/building-effective-agents
    The clearest explanation of *workflows* compared with *agents*. It supports the graph design in `04`.
26. **Anthropic: "Introducing Contextual Retrieval"** (Sep 2024): https://www.anthropic.com/news/contextual-retrieval
    Covers contextual chunk headers, hybrid BM25 plus embeddings, and reranking, with measured gains. Directly applicable to legal text.
27. **Magesh et al., "Hallucination-Free? Assessing the Reliability of Leading AI Legal Research Tools"** (Stanford, 2024), arXiv:2405.20362.
    Found that commercial legal RAG tools still hallucinate in roughly 17–33% of answers. Read it before you design your evaluation. It also gives you a strong opening paragraph for your report.
28. **The three agentic RAG papers** that LangGraph's tutorials implement:
    - Self-RAG (Asai et al., 2023), arXiv:2310.11511
    - Corrective RAG / CRAG (Yan et al., 2024), arXiv:2401.15884
    - Adaptive-RAG (Jeong et al., 2024), arXiv:2403.14403
29. **LangGraph documentation**: https://docs.langchain.com/oss/python/langgraph/overview
    At the time of writing, the current version is langgraph 1.2.x (v1.0 stable since Oct 2025, v1.2 since May 2026).

---

## Suggested reading order (about two days)

| Day | Read | Outcome |
|---|---|---|
| Day 1 morning | A1, A2 (articles listed), B5 | You can explain risk tiers, roles and the new dates |
| Day 1 afternoon | C9, C11 summary, D14, D15, D19 | You know the chatbot case end to end for EU, Finland and Norway |
| Day 2 morning | E23 (try the RTR chatbot with 10 questions), F25, F27 | You know the baseline and the failure modes |
| Day 2 afternoon | F26, F28, F29 | Ready to review `02`–`04` |

## Turn the reading into your test set

While reading, write down every question an SME founder might ask, with the answer and the exact article. Aim for 30 by the end of day 2. That becomes the first version of the evaluation set described in `02-rag-stack.md` § Evaluation.
