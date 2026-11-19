"""v0 baseline: plain RAG chain, retrieve -> generate -> finalize. The agent is measured against it.

Same search, writer prompt, citation check and rendering as the agent, so the difference in the
eval comes from the graph (routing, company profile, tables, planned research), not from prompts.
"""

from __future__ import annotations

import time
from datetime import date

from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from aiact.agent import llm, prompts
from aiact.agent.evidence import chunk_sources, format_sources
from aiact.agent.render import render, verify
from aiact.agent.schemas import Answer, Source, Verification
from aiact.search import search

K = 8


class BaselineState(TypedDict, total=False):
    question: str
    today: str
    sources: list[Source]
    answer: Answer
    verification: Verification
    cited: list[Source]
    output: str


def retrieve(state: BaselineState) -> dict:
    return {"sources": chunk_sources(search(state["question"], k=K))}


def generate(state: BaselineState) -> dict:
    system = prompts.WRITER.format(today=state["today"], sources=format_sources(state["sources"]))
    answer = llm.structured(Answer, [("system", system), ("user", state["question"])],
                            model=llm.WRITER_MODEL)
    return {"answer": answer}


def finalize(state: BaselineState) -> dict:
    points, v = verify(state["answer"], state["sources"])
    output, cited = render(state["answer"], points, state["sources"], v)
    return {"verification": v, "output": output, "cited": cited}


def build():
    g = StateGraph(BaselineState)
    g.add_node(retrieve)
    g.add_node(generate)
    g.add_node(finalize)
    g.add_edge(START, "retrieve")
    g.add_edge("retrieve", "generate")
    g.add_edge("generate", "finalize")
    g.add_edge("finalize", END)
    return g.compile()


def run(question: str, today: date | None = None) -> dict:
    t = time.perf_counter()
    out = build().invoke({"question": question, "today": (today or date.today()).isoformat()})
    return {**out, "seconds": time.perf_counter() - t}
