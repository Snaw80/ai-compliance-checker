# Covering every EU country (27 member states + EEA)

Research date: 18 November 2026. This file changes the scope from "EU + Finland + Norway" to **"any EU or EEA country"**. Its decisions update files `00`, `02` and `04`.

## 1. The key legal fact: most of the answer is the same everywhere

The AI Act is a **regulation**, not a directive. It applies directly and identically in all 27 member states. Nothing has to be transposed into national law. For a typical SME question, **80–90% of the answer is EU-level**: the risk category, the obligations, the Article 50 transparency rule and the dates.

What actually differs by country is a short, structured list:

| What differs | AI Act basis | Example |
|---|---|---|
| **Who supervises**: market surveillance authority, notifying authority, single point of contact | Art. 70 | Finland: Traficom (single point of contact) + sectoral authorities. Germany: Bundesnetzagentur as default. Italy: ACN notified as market surveillance authority. Ireland: 15 sectoral authorities. |
| **Fundamental-rights authorities** with extra powers | Art. 77 | A list per country, published by the Commission |
| **Penalties and procedure**: national rules on fines, appeals, sanction boards | Art. 99 (member states set penalty rules within the EU caps) | Finland: separate sanctions board for fines above €300k |
| **National implementing law status** | — | In force: Italy (Law 132/2025), Finland (1377/2025), Denmark, Ireland (S.I. 366/2025), Slovenia, Hungary (Decree 344/2025)… Many others: bill or nothing yet |
| **Extra national rules** where the AI Act allows them | e.g. Art. 2(11) (more protective worker rules), Art. 5(5) (national authorisation of real-time remote biometric identification) | Italy's law adds its own provisions (minors' consent, workplace information, criminal offences for deepfakes). How far it goes beyond the AI Act is debated. |
| **Regulatory sandbox** | Art. 57 (deadline moved to 2 Aug 2027 by the Omnibus) | Status varies by country |
| **National guidance**, in the national language | — | Traficom guidance (FI), CNIL publications (FR), … |
| **EEA countries** (Norway, Iceland, Liechtenstein) | EEA Agreement | Not binding until incorporated into the EEA Agreement. The EU rules still apply to their companies' services used in the EU. |

**Design consequence:** don't build "27 RAG corpora". Build **one deep EU corpus** plus a **structured country table**, and add national documents **only where they change the answer**.

## 2. Architecture: three layers

```
┌──────────────────────────────────────────────────────────────────┐
│ Layer 1: EU corpus (RAG, deep)                                   │
│   consolidated AI Act, Omnibus, Commission guidelines, Service   │
│   Desk FAQ. English. Same for every country.                     │
├──────────────────────────────────────────────────────────────────┤
│ Layer 2: Country profile table (structured, all 27 + 3 EEA)      │
│   one row per country → read by a tool, not retrieved by search  │
├──────────────────────────────────────────────────────────────────┤
│ Layer 3: National documents (RAG, only for "deep" countries)     │
│   national law text + authority guidance, original language      │
└──────────────────────────────────────────────────────────────────┘
```

### Layer 2: country profile table (the core of "any country")

One row per country, about 30 rows. Fields:

| Field | Example (Finland) |
|---|---|
| `country`, `iso2`, `membership` | Finland, FI, EU |
| `ai_act_binding` | true (EEA: false until incorporated) |
| `national_law` | {name, number, status: in_force/bill/consultation/none, in_force_from, url} |
| `single_point_of_contact` | Traficom + url |
| `market_surveillance_authorities` | [{name, scope: "default" / "transparency" / "employment" / …, url}] |
| `notifying_authority` | … |
| `fundamental_rights_authorities` | [...] |
| `penalty_regime` | {status, notes, url} |
| `sandbox` | {status, operator, url} |
| `national_extras` | free text + sources (e.g. Italy Law 132/2025 provisions) |
| `coverage_tier` | `deep` / `profile_only` |
| `sources` | list of URLs |
| `last_verified` | 2026-11-18 |
| `confidence` | high (official gazette or government page) / medium (law-firm tracker) / low (single secondary source) |

The agent calls a **`get_country_profile(country)`** tool. Every country answer shows **"Last verified: <date>"** and the source. With that, the assistant can answer for all 27 countries without claiming more than it knows.

### Layer 3: deep countries (tiered coverage)

| Tier | Countries | What the assistant does |
|---|---|---|
| **Deep** | 3–5 chosen countries | EU corpus + country profile + national law and guidance retrieved and cited |
| **Profile only** | all other EU/EEA countries | EU corpus + country profile, with an explicit caveat: "National guidance for <country> isn't indexed yet; check <authority link>" |

**Which countries go deep?** Pick countries where:
1. you can **read the language yourself** to check the answers (French is an obvious one for you, plus English sources),
2. **national law actually adds something**: Italy has the most substantial national AI law,
3. you have **interview access** to founders,
4. the market is large: Germany, France.

A sensible first set: **France, Italy, Finland, Germany** (+ Norway as the EEA case). Leave Finland and Norway out if you want to keep it small.

## 3. Data sources to seed the country table

No single source is authoritative or complete, and the trackers disagree. In my research, counts of "authorities designated" ranged from 9 to 14 of 27, depending on the tracker and on what counts as "designated" (proposed, notified or enacted).

| Source | What it gives | Use |
|---|---|---|
| **AI Act Service Desk**: Article 70 page + the Commission's list of authorities: https://ai-act-service-desk.ec.europa.eu/en/ai-act/article-70 | Official, but the list is maintained separately and updated continuously | 🟢 Primary for authorities |
| **FLI national implementation plans**: https://artificialintelligenceact.eu/national-implementation-plans/ | One HTML table, EU-27 + EEA, authority status (Clear / Partial / Unclear), notes per country. Last update 17 June 2026. No download or API. | 🔵 Best free starting point for the seed |
| **regulatoryai.eu authorities page**: https://www.regulatoryai.eu/ai-act-authorities/ | Updated Sept 2026 | 🔵 Cross-check |
| **aiactguide.net authorities**: https://aiactguide.net/authorities/ | Updated Oct 2026; marks rows verified against a gazette | 🔵 Cross-check |
| **IAPP EU AI Act Regulatory Directory**: https://iapp.org/resources/article/eu-ai-act-regulatory-directory | Directory of authorities | 🔵 Cross-check |
| **Cullen International**: "Status of national AI laws across Europe" (June 2026): https://www.cullen-international.com/news/2026/06/Status-of-national-AI-laws-across-Europe.html and the April 2026 snapshot on authorities and penalties: https://www.cullen-international.com/news/2026/04/National-implementation-of-the-EU-AI-Act--a-snapshot-of-AI-laws--regulatory-bodies-and-penalties.html | National law status per country | 🔵 Cross-check |
| **National official gazettes and government pages** | The real source | 🟢 Required for deep-tier countries; at least spot-check the others |

**Seeding process (about one day for 30 rows):**
1. Collect the tracker rows into a draft table.
2. Mark the disagreements between trackers.
3. Resolve the disagreements, or the whole row for deep countries, against official sources.
4. Set `confidence` and `last_verified` per row.

You can use an LLM to help *extract* rows from tracker pages, but **you** verify them. This table is the part of the product users trust most.

## 4. Multilingual retrieval (deep tier)

National documents come in 24 languages. Consequences:

- **Embeddings must be multilingual** so an English query finds Italian or French text: Voyage 4, BGE-M3 or Qwen3-Embedding are all multilingual (see `02`).
- **Keyword search doesn't cross languages.** "Transparency obligation" won't match "obbligo di trasparenza". Add a **query-translation step**: for each deep country, translate the query into that country's language before the keyword search. That's one cheap fast-model call.
- **Store the original text** and cite the original. Optionally store an English translation per chunk for display. Generate it once at ingestion and label it "unofficial translation".
- The answer stays in English, which the description already assumes. The writer model reads the original-language chunks directly.

## 5. Freshness: the real cost of covering 30 countries

With 30 rows, something changes almost every month: new laws, authorities designated, penalty laws passed. You need:

- `last_verified` on every row, shown in answers;
- an **update routine**: a monthly scripted check of the tracker pages and the Commission list, with a diff against your table and a manual review of the changes;
- a public changelog ("2026-12-02: Spain designated AESIA as …").

This is also your **"future product: ongoing monitoring"** idea from the description. The update routine is a first version of it, and that's worth saying in the pitch.

## 6. Effect on the agent graph (details in `04`)

- New node **`resolve_jurisdictions`**: turns the user's description ("offices in Lyon, customers in Germany and Spain, system sold EU-wide") into a list of relevant countries. **Placing a system on the EU market brings in the EU layer, whichever country the company is in.** Country-specific facts are needed for the countries where the company is established or where its users are.
- The **per-country fan-out** (the `Send` step in LangGraph) now has a variable number of branches. **Cap it** (e.g. 5 countries in detail). Above that, give the EU answer plus a compact table of authorities per country.
- The per-country branch **depends on the tier**: deep → national RAG + profile; profile-only → profile tool + caveat.
- `finalize` always shows "EU rules (all countries)" first, then "Country specifics", so it's clear that most of the answer doesn't depend on the country.

## 7. Effect on evaluation

- Add **country-profile accuracy**: for every row, are the authority, law status and source correct? Check this by hand against official sources. It's a table, so you measure it directly instead of with an LLM judge.
- Split the test questions by **tier**. Report deep-country and profile-only results separately.
- Add **"honest about coverage" questions**: ask about a profile-only country's niche national rule. The correct answer is "not indexed; here's the authority to ask", not an invented answer.

## 8. Effect on scope and positioning

- **Two-week MVP that's still realistic:** EU layer (deep) + **country table for all 30 countries** + **2–3 deep countries**. The country table is about one day of work and gives you an honest "any EU country" claim.
- **Positioning:** several free trackers already list authorities per country (FLI, IAPP, regulatoryai.eu…). Your difference isn't the list. It's **applying the EU rules to the user's specific case and attaching the right national authority and status**, with sources and dates.
- **Description update:** the "Nordics" target audience and the "only EU, Finland and Norway" line in `ai-act-assistant-description.md` no longer match. I haven't edited your description.
