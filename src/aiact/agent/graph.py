"""The agent: a fixed LangGraph workflow (research/04-agent-graph.md, day-4 cut).

    router ─┬─ off_topic ─────────────────────────────────────────────▶ finalize
            ├─ general ───────────────────────────────▶ research ─▶ generate ─▶ finalize
            └─ company_case ─▶ build_profile ⇄ ask_clarify (interrupt)
                                     └──────────────────▶ research

The model decides only in `router`, `build_profile` (facts the user stated) and `generate`.
Role, clarifying questions and everything after them are code.
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

from aiact.agent import llm, prompts, rules
from aiact.agent.evidence import chunk_sources, format_sources
from aiact.agent.render import OFF_TOPIC, render, verify
from aiact.agent import schemas
from aiact.agent.schemas import Answer, CompanyProfile, Intent, Route, Source, Verification
from aiact.search import search

log = logging.getLogger("aiact.agent")
CLARIFY = "clarify"  # name on the AIMessages that carry a clarifying question
K = 8


class State(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    today: str                     # ISO date the answer is given for (fixed in evals)
    # per turn (reset by the router)
    question: str                  # the user message that started this turn
    intent: Intent
    clarify_rounds: int
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
    return {"question": question, "intent": route.intent, "clarify_rounds": 0, "sources": [],
            "answer": None, "verification": None, "cited": [], "output": ""}


def build_profile(state: State) -> dict:
    # user messages + our clarifying questions (not our long answers)
    convo = [(_role(m), str(m.content)) for m in state["messages"]
             if isinstance(m, HumanMessage) or m.name == CLARIFY]
    profile = llm.structured(CompanyProfile, [("system", prompts.PROFILE), *convo])
    log.info("profile: %s", profile.model_dump(exclude_defaults=True))
    return {"profile": profile}


def ask_clarify(state: State) -> dict:
    question = rules.clarify_question(state["profile"])
    reply = interrupt({"question": question})  # pauses the graph; resumed with the user's reply
    return {"messages": [AIMessage(question, name=CLARIFY), HumanMessage(str(reply))],
            "clarify_rounds": state.get("clarify_rounds", 0) + 1}


def research(state: State) -> dict:
    query = state["question"]
    if state["intent"] == "company_case" and state["profile"].system_description:
        query = f"{state['profile'].system_description}. {query}"
    return {"sources": chunk_sources(search(query, k=K))}


def generate(state: State) -> dict:
    system = prompts.WRITER.format(today=state["today"], sources=format_sources(state["sources"]))
    user = state["question"]
    if state["intent"] == "company_case":
        user += "\n\n" + prompts.CASE.format(profile=rules.profile_summary(state["profile"]))
    answer = llm.structured(Answer, [("system", system), ("user", user)], model=llm.WRITER_MODEL)
    return {"answer": answer}


def finalize(state: State) -> dict:
    if state["intent"] == "off_topic":
        return {"output": OFF_TOPIC, "messages": [AIMessage(OFF_TOPIC)]}
    caveats = []
    if state["intent"] == "company_case" and rules.role(state["profile"]) == "unknown":
        caveats.append("You did not say whether you built the system or bought it, so this answer "
                       "covers both the provider's and the deployer's obligations.")
    points, v = verify(state["answer"], state["sources"])
    output, cited = render(state["answer"], points, state["sources"], v, caveats=caveats)
    return {"output": output, "verification": v, "cited": cited, "messages": [AIMessage(output)]}


# ---------------------------------------------------------------------------
# Edges
# ---------------------------------------------------------------------------

def after_router(state: State) -> str:
    return {"off_topic": "finalize", "general": "research", "company_case": "build_profile"}[state["intent"]]


def after_profile(state: State) -> str:
    if rules.clarify_question(state["profile"]) and state.get("clarify_rounds", 0) < rules.MAX_CLARIFY:
        return "ask_clarify"
    return "research"


def build(checkpointer=None):
    g = StateGraph(State)
    for node in (router, build_profile, ask_clarify, research, generate, finalize):
        g.add_node(node)
    g.add_edge(START, "router")
    g.add_conditional_edges("router", after_router, ["finalize", "research", "build_profile"])
    g.add_conditional_edges("build_profile", after_profile, ["ask_clarify", "research"])
    g.add_edge("ask_clarify", "build_profile")
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
