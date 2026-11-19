"""Agent graph + profile rules with a scripted fake model and fake search (no Ollama, no database)."""

from datetime import date

import pytest

from aiact.agent import graph as agent_graph
from aiact.agent import llm, rules
from aiact.agent.schemas import Answer, CompanyProfile, Route
from aiact.search import Hit

TODAY = date(2026, 11, 19)
CHATBOT = "chatbot answering customer questions"


class FakeModel:
    """Returns scripted outputs per schema, records the calls."""

    def __init__(self, intent="company_case", profiles=()):
        self.intent, self.profiles, self.calls = intent, list(profiles), []

    def __call__(self, schema, messages, **kw):
        self.calls.append((schema.__name__, messages))
        if schema is Route:
            return Route(intent=self.intent)
        if schema is CompanyProfile:
            return self.profiles.pop(0) if len(self.profiles) > 1 else self.profiles[0]
        if schema is Answer:
            return Answer(summary="Tell users it is AI.", points=["Disclose the chatbot [S1]"])
        raise AssertionError(schema)


@pytest.fixture
def fake(monkeypatch):
    def install(**kw):
        model = FakeModel(**kw)
        monkeypatch.setattr(llm, "structured", model)
        hit = Hit("eu-ai-act-consolidated:art_50:1", "eu-ai-act-consolidated", "Art. 50(1)", "Transparency",
                  "", "Providers shall ensure ...", "https://x", None)
        monkeypatch.setattr(agent_graph, "search", lambda q, k: [hit])
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
    model = fake(intent="general")
    r = agent_graph.Conversation(TODAY).send("What does Art. 50(1) say?")
    assert names(model) == ["Route", "Answer"]
    assert "Disclose the chatbot [1]" in r["output"] and "AI Act, Art. 50(1)" in r["output"]


def test_company_case_asks_build_or_buy_then_resumes(fake):
    model = fake(profiles=[CompanyProfile(system_description=CHATBOT, interacts_with_people=True),
                           CompanyProfile(system_description=CHATBOT, interacts_with_people=True,
                                          built_or_bought="built")])
    c = agent_graph.Conversation(TODAY)
    r = c.send("We use a chatbot on our website. What do we need to do?")
    assert "build the chatbot" in r["question"] and c.waiting
    r = c.send("We built it on top of an LLM API.")
    assert not c.waiting and "Disclose the chatbot" in r["output"]
    assert names(model) == ["Route", "CompanyProfile", "CompanyProfile", "Answer"]
    # the second profile extraction saw our question and the user's reply
    convo = model.calls[2][1]
    assert any("build the chatbot" in text for role, text in convo if role == "assistant")
    assert convo[-1] == ("user", "We built it on top of an LLM API.")
    assert r["state"]["profile"].built_or_bought == "built"


def test_clarify_stops_after_max_rounds_and_says_so(fake):
    fake(profiles=[CompanyProfile(system_description=CHATBOT)])  # never learns the role
    c = agent_graph.Conversation(TODAY)
    r = c.send("We use a chatbot.")
    for _ in range(rules.MAX_CLARIFY - 1):
        r = c.send("Not sure.")
        assert "question" in r
    r = c.send("Still not sure.")
    assert "output" in r and "covers both the provider's and the deployer's" in r["output"]


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
    assert "build the AI system" in rules.clarify_question(CompanyProfile(interacts_with_people=True))
    assert "build the chatbot" in rules.clarify_question(CompanyProfile(system_description="Chatbot"))
    assert rules.clarify_question(CompanyProfile(system_description="Chatbot", built_or_bought="bought")) is None


def test_profile_summary():
    s = rules.profile_summary(CompanyProfile(system_description=CHATBOT, built_or_bought="built",
                                             interacts_with_people=True, countries_established=["Finland"]))
    assert "- Role: provider" in s and "- Talks directly with people: yes" in s
    assert "- Offices in: Finland" in s and "- Generates images/audio/video/text: not stated" in s
