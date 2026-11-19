"""The agent: a fixed LangGraph workflow (research/04-agent-graph.md, day-4 cut).

    router ─┬─ off_topic ──────────────────────────────────────────────────────▶ finalize
            ├─ general ──────────────────────────▶ plan ─▶ research ─▶ generate ─▶ finalize
            └─ company_case ─▶ build_profile ⇄ ask_clarify (interrupt)
                                     └─────────────▶ plan

The model decides only in `router`, `build_profile` (facts the user stated) and `generate`.
Role, clarifying questions, which obligations and countries to cover, dates, the country
section and the citation check are code.

Not in the day-4 cut (see research/04): parallel per-country research (Send), the corrective
retrieval loop, a model check of citations and the revise loop.
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import date
from typing import Annotated, Any

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.types import Command, interrupt
from typing_extensions import TypedDict

from aiact.agent import llm, prompts, render, rules, schemas
from aiact.agent.evidence import (chunk_sources, country_sources, format_sources, is_date_chunk,
                                  table_sources)
from aiact.agent.render import OFF_TOPIC, country_section, verify, when_section
from aiact.agent.schemas import Answer, CompanyProfile, Intent, Route, Source, Verification
from aiact.search import LAW_DOC, get_chunks, query_refs, search
from aiact.tables import Applicability, lookup_applicability

log = logging.getLogger("aiact.agent")
CLARIFY = "clarify"  # name on the AIMessages that carry a clarifying question
K = 8           # search hits for the question
K_OBLIGATION = 3  # extra hits per selected obligation (company cases)
MAX_CHUNKS = 12   # corpus chunks shown to the writer


class State(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    today: str                     # ISO date the answer is given for (fixed in evals)
    # per turn (reset by the router)
    question: str                  # the user message that started this turn
    intent: Intent
    clarify_rounds: int
    clarify_asked: list[str]       # clarify topics asked this turn ('system', 'role')
    obligations: list[dict]        # [{id, reason}] rows of tables/applicability.yaml
    countries: list[str]           # ISO2, EU/EEA only
    plan_caveats: list[str]        # code-made caveats (assumptions, countries outside the EEA)
    sources: list[Source]
    answer: Answer | None
    verification: Verification | None
    cited: list[Source]
    output: str
    # per conversation
    profile: CompanyProfile | None


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------

def router(state: State) -> dict:
    question = str(state["messages"][-1].content)
    note = prompts.ROUTER_PROFILE_NOTE if state.get("profile") else ""
    recent = state["messages"][-5:]
    route = llm.structured(Route, [("system", prompts.ROUTER.format(profile_note=note)),
                                   *[(_role(m), _clip(m.content)) for m in recent]])
    log.info("intent: %s", route.intent)
    return {"question": question, "intent": route.intent, "clarify_rounds": 0, "clarify_asked": [], "obligations": [],
            "countries": [], "plan_caveats": [], "sources": [], "answer": None,
            "verification": None, "cited": [], "output": ""}


def build_profile(state: State) -> dict:
    # user messages + our clarifying questions (not our long answers)
    convo = [(_role(m), str(m.content)) for m in state["messages"]
             if isinstance(m, HumanMessage) or m.name == CLARIFY]
    profile = llm.structured(CompanyProfile, [("system", prompts.PROFILE), *convo])
    log.info("profile: %s", profile.model_dump(exclude_defaults=True))
    return {"profile": profile}


def ask_clarify(state: State) -> dict:
    asked = state.get("clarify_asked", [])
    topic = rules.clarify_topic(state["profile"], asked)
    question = rules.clarify_question(state["profile"], asked)
    reply = interrupt({"question": question})  # pauses the graph; resumed with the user's reply
    return {"messages": [AIMessage(question, name=CLARIFY), HumanMessage(str(reply))],
            "clarify_rounds": state.get("clarify_rounds", 0) + 1, "clarify_asked": [*asked, topic]}


def plan(state: State) -> dict:
    """Which obligations and countries to cover (code only)."""
    if state["intent"] == "company_case":
        p = state["profile"]
        obligations, caveats = rules.obligations_for_profile(p)
        names = [*p.countries_established, *p.countries_users, *rules.countries_in_text(state["question"])]
        if rules.role(p) == "unknown":
            caveats.insert(0, "You did not say whether you built the system or bought it, so this answer "
                              "covers both the provider's and the deployer's obligations.")
        if not names:
            caveats.append("You did not say where your company or its users are. The EU rules apply the "
                           "same way in every EU country; name your countries for national details.")
    else:
        obligations, caveats = [], []  # general questions: picked from the retrieved articles
        names = rules.countries_in_text(state["question"])
    countries, country_caveats = rules.resolve_countries(names)
    log.info("plan: obligations=%s countries=%s", [o["id"] for o in obligations], countries)
    return {"obligations": obligations, "countries": countries, "plan_caveats": caveats + country_caveats}


def research(state: State) -> dict:
    """Search + the obligations' own articles + table rows + country profiles -> tagged sources."""
    question, case = state["question"], state["intent"] == "company_case"
    query = question
    if case and state["profile"].system_description:
        query = f"{state['profile'].system_description}. {question}"
    hits = search(query, k=K)
    obligations = state["obligations"]
    if not case:
        retrieved = [h.article_ref for h in hits if h.doc_id == LAW_DOC][:3]
        obligations = rules.obligations_for_refs(query_refs(question), retrieved)
    rows = applicability(obligations, state["today"])
    # company case: the law of each selected obligation first, then the search hits;
    # general question: the hits first (the row's law must not crowd out e.g. the recital that answers it)
    ids = [c for a in rows for c in a.obligation.source_chunk_ids if not is_date_chunk(c)]
    if case:  # the core duties for the company's role (e.g. Art. 26 for a deployer of a high-risk system)
        ids = [c for o in obligations for c in rules.core_chunks(o["id"], state["profile"])] + ids
    law = get_chunks(ids)
    pool = law + hits if case else hits + law
    if case:
        for a in rows:
            pool += search(a.obligation.obligation, k=K_OBLIGATION)
    sources = (chunk_sources(pool)[:MAX_CHUNKS] + table_sources(rows)
               + country_sources(state["countries"]))
    log.info("research: %d sources (%s)", len(sources), " ".join(s.tag for s in sources))
    return {"sources": sources, "obligations": obligations}


def generate(state: State) -> dict:
    system = prompts.WRITER.format(today=state["today"], sources=format_sources(state["sources"]))
    user = state["question"]
    if state["intent"] == "company_case":
        tags = table_tags(state["obligations"])
        listed = "\n".join(f"- [{tags[o['id']]}] {o['id']}: {o['reason']}" for o in state["obligations"])
        tier = rules.risk_tier(state["profile"])
        user += "\n\n" + prompts.CASE.format(profile=rules.profile_summary(state["profile"]),
                                             risk_tier=render.RISK_LABEL[tier], obligations=listed or "- none")
    answer = llm.structured(Answer, [("system", system), ("user", user)], model=llm.WRITER_MODEL)
    if state["intent"] == "company_case":  # the category is code's call, not the model's
        answer = answer.model_copy(update={"risk_tier": rules.risk_tier(state["profile"])})
    else:
        answer = answer.model_copy(update={"risk_tier": None})
    return {"answer": answer}


def finalize(state: State) -> dict:
    if state["intent"] == "off_topic":
        return {"output": OFF_TOPIC, "messages": [AIMessage(OFF_TOPIC)]}
    case = state["intent"] == "company_case"
    points, v = verify(state["answer"], state["sources"])
    tags = table_tags(state["obligations"])
    rows = applicability(state["obligations"], state["today"])
    if not case:  # general question: only the rows the answer relies on (the rest were just retrieved)
        used = {t for p in points for t in p.sources}
        rows = [a for a in rows if tags[a.obligation.id] in used]
    reasons = {o["id"]: o["reason"] for o in state["obligations"]} if case else None
    sections = [when_section(rows, tags, reasons), country_section(state["countries"])]
    output, cited = render.render(state["answer"], points, state["sources"], v,
                           sections=sections, caveats=state.get("plan_caveats", []))
    return {"output": output, "verification": v, "cited": cited, "messages": [AIMessage(output)]}


def applicability(obligations: list[dict], today: str) -> list[Applicability]:
    on = date.fromisoformat(today)
    return [lookup_applicability(o["id"], on=on)[0] for o in obligations]


def table_tags(obligations: list[dict]) -> dict[str, str]:
    """Obligation id -> its T tag (same order as table_sources)."""
    return {o["id"]: f"T{i}" for i, o in enumerate(obligations, 1)}


# ---------------------------------------------------------------------------
# Edges
# ---------------------------------------------------------------------------

def after_router(state: State) -> str:
    return {"off_topic": "finalize", "general": "plan", "company_case": "build_profile"}[state["intent"]]


def after_profile(state: State) -> str:
    if (rules.clarify_topic(state["profile"], state.get("clarify_asked", []))
            and state.get("clarify_rounds", 0) < rules.MAX_CLARIFY):
        return "ask_clarify"
    return "plan"


def build(checkpointer=None):
    g = StateGraph(State)
    for node in (router, build_profile, ask_clarify, plan, research, generate, finalize):
        g.add_node(node)
    g.add_edge(START, "router")
    g.add_conditional_edges("router", after_router, ["finalize", "plan", "build_profile"])
    g.add_conditional_edges("build_profile", after_profile, ["ask_clarify", "plan"])
    g.add_edge("ask_clarify", "build_profile")
    g.add_edge("plan", "research")
    g.add_edge("research", "generate")
    g.add_edge("generate", "finalize")
    g.add_edge("finalize", END)
    return g.compile(checkpointer=checkpointer or InMemorySaver(serde=SERDE))


# Checkpoints store our pydantic models; allow exactly those types to be restored.
SERDE = JsonPlusSerializer(allowed_msgpack_modules=[
    (schemas.__name__, name) for name in ("Source", "Answer", "Verification", "CompanyProfile")])


# ---------------------------------------------------------------------------
# Running a conversation
# ---------------------------------------------------------------------------

class Conversation:
    """One chat thread. `send` returns either a clarifying question or the final answer.

        c = Conversation()
        r = c.send("We use a chatbot ...")   # r["question"] if the agent asks something
        r = c.send("We built it ourselves")  # resumes the paused graph
    """

    def __init__(self, today: date | None = None, graph=None):
        self.graph = graph or build()
        self.today = (today or date.today()).isoformat()
        self.config = {"configurable": {"thread_id": str(uuid.uuid4())}}
        self.waiting = False  # True while the graph is paused on a clarifying question

    def send(self, message: str) -> dict[str, Any]:
        t = time.perf_counter()
        if self.waiting:
            out = self.graph.invoke(Command(resume=message), self.config)
        else:
            out = self.graph.invoke({"messages": [HumanMessage(message)], "today": self.today}, self.config)
        seconds = time.perf_counter() - t
        if out.get("__interrupt__"):
            self.waiting = True
            return {"question": out["__interrupt__"][0].value["question"], "seconds": seconds, "state": out}
        self.waiting = False
        return {"output": out["output"], "seconds": seconds, "state": out}


def _role(m: AnyMessage) -> str:
    return "user" if isinstance(m, HumanMessage) else "assistant"


def _clip(content, n: int = 600) -> str:
    s = str(content)
    return s if len(s) <= n else s[:n] + " [...]"
