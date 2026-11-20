"""Agent graph + profile rules with a scripted fake model and fake search (no Ollama, no database)."""

import asyncio
from datetime import date

import pytest

from aiact.agent import evidence, llm, rules
from aiact.agent import graph as agent_graph
from aiact.agent.schemas import Answer, CompanyProfile, Route
from aiact.search import Hit

TODAY = date(2026, 11, 19)
CHATBOT = "chatbot answering customer questions"


class FakeModel:
    """Returns scripted outputs per schema, records the calls."""

    def __init__(self, intent="company_case", profiles=(), points=("Disclose the chatbot [S1]",)):
        self.intent, self.profiles, self.points, self.calls = intent, list(profiles), list(points), []

    def __call__(self, schema, messages, **kw):
        self.calls.append((schema.__name__, messages))
        if schema is Route:
            return Route(intent=self.intent)
        if schema is CompanyProfile:
            return self.profiles.pop(0) if len(self.profiles) > 1 else self.profiles[0]
        if schema is Answer:
            return Answer(summary="Tell users it is AI.", points=self.points)
        raise AssertionError(schema)


@pytest.fixture
def fake(monkeypatch):
    def install(**kw):
        model = FakeModel(**kw)
        monkeypatch.setattr(llm, "structured", model)
        hit = Hit("eu-ai-act-consolidated:art_50:1", "eu-ai-act-consolidated", "Art. 50(1)", "Transparency",
                  "", "Providers shall ensure ...", "https://x", None)
        monkeypatch.setattr(agent_graph, "search", lambda q, k: [hit])
        monkeypatch.setattr(agent_graph, "get_chunks", lambda ids: [])
        monkeypatch.setattr(evidence, "get_chunks", lambda ids: [])
        return model
    return install


def names(model):
    return [n for n, _ in model.calls]


def test_off_topic_skips_research(fake):
    model = fake(intent="off_topic")
    r = agent_graph.Conversation(TODAY).send("What is the corporate tax rate in Finland?")
    assert "only help with the EU AI Act" in r["output"]
    assert names(model) == ["Route"]


def test_general_question_goes_straight_to_research(fake):
    model = fake(intent="general", points=["Disclose the chatbot [S1]", "From 2 August 2026 [T1]"])
    r = agent_graph.Conversation(TODAY).send("What does Art. 50(1) say?")
    assert names(model) == ["Route", "Answer"]
    assert "Disclose the chatbot [1]" in r["output"] and "AI Act, Art. 50(1)" in r["output"]
    # the date comes from the applicability table, picked from the article named in the question
    assert "| Inform people that they are interacting with an AI system" in r["output"]
    assert "| 2 Aug 2026 | applies |" in r["output"]
    assert "Probable risk category" not in r["output"]


def test_general_question_shows_only_the_table_rows_the_answer_cites(fake):
    fake(intent="general")  # the answer cites no T source
    r = agent_graph.Conversation(TODAY).send("What does Art. 50(1) say?")
    assert "When it applies" not in r["output"]


def test_company_case_asks_build_or_buy_then_resumes(fake):
    model = fake(profiles=[CompanyProfile(system_description=CHATBOT, interacts_with_people=True),
                           CompanyProfile(system_description=CHATBOT, interacts_with_people=True,
                                          built_or_bought="built")])
    c = agent_graph.Conversation(TODAY)
    r = c.send("We use a chatbot on our website. What do we need to do?")
    assert "build this AI system (chatbot answering" in r["question"] and c.waiting
    r = c.send("We built it on top of an LLM API.")
    assert not c.waiting and "Disclose the chatbot" in r["output"]
    assert names(model) == ["Route", "CompanyProfile", "CompanyProfile", "Answer"]
    # the second profile extraction saw our question and the user's reply
    convo = model.calls[2][1]
    assert any("build this AI system" in text for role, text in convo if role == "assistant")
    assert convo[-1] == ("user", "We built it on top of an LLM API.")
    assert r["state"]["profile"].built_or_bought == "built"
    assert [o["id"] for o in r["state"]["obligations"]] == ["art50-chatbot-disclosure", "ai-literacy"]
    assert "**Probable risk category:** limited risk" in r["output"]
    assert "You did not say where your company" in r["output"]
    # the writer saw the selected obligations with their T tags
    writer_prompt = model.calls[3][1][1][1]
    assert "[T1] art50-chatbot-disclosure" in writer_prompt and "[T2] ai-literacy" in writer_prompt


def test_asend_reports_nodes_and_pauses_like_send(fake):
    """The UI path: same answers as `send`, plus node start/end events with each node's update."""
    fake(profiles=[CompanyProfile(system_description=CHATBOT, interacts_with_people=True),
                   CompanyProfile(system_description=CHATBOT, interacts_with_people=True, built_or_bought="built")])
    c, events = agent_graph.Conversation(TODAY), []

    async def on_node(name, update):
        events.append((name, update))

    r = asyncio.run(c.asend("We use a chatbot on our website. What do we need to do?", on_node))
    assert "build this AI system" in r["question"] and c.waiting
    assert [(n, u is not None) for n, u in events] == [
        ("router", False), ("router", True), ("build_profile", False), ("build_profile", True),
        ("ask_clarify", False), ("ask_clarify", True)]  # ended by the interrupt
    assert events[1][1]["intent"] == "company_case" and events[3][1]["profile"].system_description == CHATBOT
    events.clear()
    r = asyncio.run(c.asend("We built it on top of an LLM API.", on_node))
    assert not c.waiting and "Disclose the chatbot" in r["output"]
    assert [n for n, u in events if u is not None] == ["ask_clarify", "build_profile", "plan", "research",
                                                       "generate", "finalize"]
    assert r["state"]["profile"].built_or_bought == "built"


def test_clarify_never_repeats_a_question_and_says_so(fake):
    fake(profiles=[CompanyProfile(system_description=CHATBOT)])  # never learns the role
    c = agent_graph.Conversation(TODAY)
    r = c.send("We use a chatbot.")
    assert "build this AI system" in r["question"]
    r = c.send("Not sure.")  # the role question is not asked a second time
    assert "output" in r and "covers both the provider's and the deployer's" in r["output"]


def test_clarify_asks_each_missing_topic_once(fake):
    fake(profiles=[CompanyProfile(), CompanyProfile(system_description=CHATBOT)])
    c = agent_graph.Conversation(TODAY)
    assert "What does your AI system do" in c.send("What do we need to do?")["question"]
    assert "build this AI system" in c.send("A chatbot for customers.")["question"]
    assert "output" in c.send("No idea.")
    assert rules.MAX_CLARIFY == 2


def test_company_countries_get_profile_sources_and_section(fake):
    fake(profiles=[CompanyProfile(system_description=CHATBOT, built_or_bought="built", interacts_with_people=True,
                                  countries_established=["Norway", "Finland", "USA"])])
    r = agent_graph.Conversation(TODAY).send("We're in Oslo, Helsinki and New York. What applies?")
    assert r["state"]["countries"] == ["NO", "FI"]
    assert [s.tag for s in r["state"]["sources"] if s.kind == "country"] == ["NO", "FI"]
    out = r["output"]
    assert "- **Norway**: AI Act not binding yet (EEA)" in out and "- **Finland**: AI Act applies directly" in out
    assert "USA: outside the EU/EEA" in out and "Country profile: Finland" in out


def test_follow_up_keeps_profile(fake):
    model = fake(profiles=[CompanyProfile(system_description=CHATBOT, built_or_bought="bought")])
    c = agent_graph.Conversation(TODAY)
    c.send("We use a vendor chatbot on our website.")
    c.send("And does that apply in Finland?")
    router_calls = [m for n, m in model.calls if n == "Route"]
    assert "described their company" not in router_calls[0][0][1]
    assert "described their company" in router_calls[1][0][1]


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("built,role", [("built", "provider"), ("bought", "deployer"),
                                        ("both", "both"), ("unknown", "unknown")])
def test_role(built, role):
    assert rules.role(CompanyProfile(built_or_bought=built)) == role


def test_clarify_question_order():
    assert "What does your AI system do" in rules.clarify_question(CompanyProfile())
    # a known fact about the system is enough to skip "what does it do"
    assert "build this AI system itself" in rules.clarify_question(CompanyProfile(interacts_with_people=True))
    assert "build this AI system (chatbot) itself" in rules.clarify_question(CompanyProfile(system_description="Chatbot"))
    assert rules.clarify_question(CompanyProfile(system_description="Chatbot", built_or_bought="bought")) is None
    assert rules.clarify_question(CompanyProfile(system_description="Chatbot"), asked=["role"]) is None


def test_profile_summary():
    s = rules.profile_summary(CompanyProfile(system_description=CHATBOT, built_or_bought="built",
                                             interacts_with_people=True, countries_established=["Finland"]))
    assert "- Role: provider" in s and "- Talks directly with people: yes" in s
    assert "- Offices in: Finland" in s and "- Generates images/audio/video/text: not stated" in s


def test_obligations_for_profile_deployer_chatbot():
    obs, caveats = rules.obligations_for_profile(
        CompanyProfile(system_description=CHATBOT, built_or_bought="bought", interacts_with_people=True,
                       generates_content=True, high_risk_area="none"))
    assert [o["id"] for o in obs] == ["art50-chatbot-disclosure", "ai-literacy"]  # no 50(2): not the provider
    assert "your vendor" in obs[0]["reason"] and caveats == []


def test_obligations_for_profile_hiring_tool():
    obs, _ = rules.obligations_for_profile(CompanyProfile(system_description="CV ranking", built_or_bought="bought",
                                                          high_risk_area="employment"))
    assert [o["id"] for o in obs] == ["high-risk-annex-iii", "ai-literacy"]
    obs, _ = rules.obligations_for_profile(CompanyProfile(system_description="CV ranking", built_or_bought="built",
                                                          high_risk_area="employment"))
    assert [o["id"] for o in obs] == ["high-risk-annex-iii", "high-risk-conformity-procedures", "ai-literacy"]


def test_obligations_for_profile_unknown_role_covers_both_and_flags_area():
    obs, caveats = rules.obligations_for_profile(CompanyProfile(system_description="image generator",
                                                                generates_content=True, publishes_generated_content=True))
    assert [o["id"] for o in obs] == ["art50-content-marking", "art50-deepfake-disclosure", "ai-literacy"]
    assert "high-risk area" in caveats[0]


@pytest.mark.parametrize("profile,tier", [
    (CompanyProfile(emotion_or_biometric=True, high_risk_area="employment"), "prohibited"),
    (CompanyProfile(high_risk_area="employment"), "high_risk"),
    (CompanyProfile(safety_component=True, high_risk_area="none"), "high_risk"),
    (CompanyProfile(interacts_with_people=True, high_risk_area="none"), "transparency"),
    (CompanyProfile(high_risk_area="none"), "minimal"),
    (CompanyProfile(), "unclear"),
])
def test_risk_tier(profile, tier):
    assert rules.risk_tier(profile) == tier


def test_obligations_for_refs():
    obs = rules.obligations_for_refs(["Annex III"], ["Art. 3(4)", "Art. 71(1)"])
    assert [o["id"] for o in obs] == ["high-risk-annex-iii", "scope-and-definitions"]  # no catch-all for Art. 71
    assert [o["id"] for o in rules.obligations_for_refs(["Art. 71"], [])] == ["general-application"]
    assert rules.obligations_for_refs(["Recital 132"], []) == []


def test_resolve_countries():
    isos, caveats = rules.resolve_countries(["Norway", "finland", "FI", "USA", "United Kingdom"])
    assert isos == ["NO", "FI"]
    assert caveats[0].startswith("USA, United Kingdom: outside the EU/EEA")
    isos, caveats = rules.resolve_countries(["France", "Germany", "Italy", "Spain", "Austria", "Poland"])
    assert len(isos) == rules.MAX_COUNTRIES and "first 5" in caveats[0]


def test_countries_in_text():
    assert rules.countries_in_text("Who supervises AI in the Netherlands and Finland? Is it Traficom?") == [
        "Netherlands", "Finland"]
    assert rules.countries_in_text("No, it is not in scope") == []  # ISO codes are not matched


def test_core_law_follows_the_role():
    deployer = CompanyProfile(system_description="CV screening", built_or_bought="bought", high_risk_area="employment")
    ids = rules.core_chunks("high-risk-annex-iii", deployer)
    assert "eu-ai-act-consolidated:art_26:1" in ids and "eu-ai-act-consolidated:art_27:1" in ids
    assert "eu-ai-act-consolidated:art_16" not in ids
    provider = deployer.model_copy(update={"built_or_bought": "built"})
    assert rules.core_chunks("high-risk-annex-iii", provider) == ["eu-ai-act-consolidated:art_16"]
    unknown = deployer.model_copy(update={"built_or_bought": "unknown"})
    assert len(rules.core_chunks("high-risk-annex-iii", unknown)) == 5
    assert rules.core_chunks("art50-chatbot-disclosure", deployer) == []


def test_prohibited_practice_covers_only_the_ban():
    p = CompanyProfile(system_description="detects employees' emotions", built_or_bought="built",
                       emotion_or_biometric=True, high_risk_area="employment", interacts_with_people=True)
    obligations, _ = rules.obligations_for_profile(p)
    assert [o["id"] for o in obligations] == ["prohibited-practices", "ai-literacy"]
    assert rules.risk_tier(p) == "prohibited"
