# AI Act Assistant

**An AI chat assistant that helps small companies understand which AI rules apply to them, in which country, and from when.**

## The problem

Europe's AI Act is the first major law that regulates artificial intelligence. It affects any company that builds or uses AI, from a startup with a customer-service chatbot to a company screening job applications with software.

The law is long and technical, and it doesn't apply the same way everywhere:

- **It changes over time.** Some obligations already apply, some were postponed to 2027, and others are still being negotiated.
- **It changes by country.** Finland applies the law directly and started national enforcement in January 2026. Norway is outside the EU, so the law isn't binding there yet; Norway's own version is expected to reach Parliament in 2027. Norwegian companies that sell to EU customers still have to prepare.
- **Small companies can't afford lawyers for every question.** Large companies have compliance teams. A 10-person startup usually has a founder searching Google and reading law-firm blog posts that contradict each other.

Existing free tools mostly ask a short questionnaire and give a generic risk label. They rarely explain why, rarely cite the law, and don't account for country differences or dates.

## The solution

A chat assistant that answers in plain language. The user describes what their company does with AI, and the assistant explains:

1. **Which risk category** their AI system probably falls into, and why.
2. **What they have to do**: for example, tell users they're talking to a chatbot, or keep documentation.
3. **Where and when it applies**: today in Finland, from 2027 in Norway, or not at all.
4. **Where the answer comes from**: every answer points to the exact article or official guidance, so the user can check it or forward it to a lawyer.

### Example

> **User:** We're a startup with offices in Oslo and Helsinki. We use a chatbot on our website to answer customer questions. What do we need to do?
>
> **Assistant:** Your chatbot is most likely a *limited-risk* system. The main obligation is transparency: users must be told they're talking to an AI.
> - **Finland:** this has applied since August 2026 (AI Act, Article 50). Traficom is the authority to contact.
> - **Norway:** not legally binding yet. Norway's AI law is expected in 2027, but if you serve EU customers from Oslo, the EU rules already apply to that service.
>
> *Sources: AI Act Article 50; Traficom guidance (August 2026); Norwegian government consultation on the AI law.*
> *This is general information, not legal advice.*

## Who it's for

- **Founders and product managers** at small and medium-sized companies in the Nordics that build or use AI.
- **Consultants and small agencies** that advise clients on AI projects.
- **Students and journalists** who want to understand the law without reading 400 pages.

## What makes it different

- **It knows about countries and dates.** It doesn't give one answer for all of Europe; it says what applies in Finland, in Norway, and in the EU, today and later.
- **It always shows its sources.** No answer without a link to the article or official document it relies on.
- **It's measured.** Before launch, the assistant is tested on a set of real questions with known correct answers, and compared with the free chatbot published by Austria's AI regulator. The results are published openly.
- **It's honest about its limits.** When the law is unclear or still changing, it says so and suggests asking a professional.

## What it is not

- It isn't a lawyer, and it doesn't replace legal advice.
- It doesn't certify a company as compliant.
- The first version doesn't cover every European country, only the EU rules, Finland and Norway.

## Scope of the first version

- A public web page where anyone can ask questions, with no account needed.
- Coverage: the EU AI Act, Finland's national rules and Norway's draft law, all in English.
- A published report showing how often the assistant answers correctly, and where it fails.
- Built in about two weeks.

## How success will be measured

- **Quality:** the share of test questions answered correctly with the right source, compared with existing free tools.
- **Usage:** how many people try it, and how many come back.
- **Interest:** how many visitors join a waitlist for a future version.
- **Learning:** what at least five founders say in short interviews about how they deal with AI rules today.

## Possible future product

If the interviews show real demand, the next step would be **ongoing monitoring**. A company describes its AI systems once, and the assistant alerts it when a rule that affects them changes in one of its countries. Laws keep changing, so this is a recurring need, unlike a one-off questionnaire.

Other possible directions:

- Generating the basic documents a small company needs, such as a transparency notice for users.
- Adding more countries: Sweden and Denmark, then the rest of Europe.

The project is also an experiment in finding a product. I'll record each hypothesis, what users said, and the decision to continue, change direction or stop.

## Why I'm building it

I'm an AI engineering student at EPITA and co-founded a model-compression startup in EPITA's entrepreneurship program. I want to build something small, finish it properly, and test whether it solves a real problem. The AI Act is a good case: the rules are complex, they keep changing, and the companies most affected are the ones with the fewest resources to deal with them.
