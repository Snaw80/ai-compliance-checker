"""Local web UI for the AI Act assistant (Chainlit).

    uv run --directory ui chainlit run app.py      # then open http://localhost:8000

One `Conversation` (agent thread) per browser chat. While the agent works, each graph node is
shown as a step with what it decided: the route, the company profile, the obligations and
countries to cover, the sources found. The answer is the agent's rendered markdown, unchanged.
"""

from __future__ import annotations

import logging
from collections import Counter

import chainlit as cl
from chainlit.utils import utc_now

from aiact.agent import rules
from aiact.agent.graph import Conversation

log = logging.getLogger("aiact.ui")

STEPS = {  # graph node -> step label (ask_clarify shows up as the question, finalize is instant)
    "router": "Reading the question",
    "build_profile": "Describing your AI system",
    "plan": "Choosing obligations and countries",
    "research": "Searching the AI Act and the tables",
    "generate": "Writing the answer",
}
ROUTES = {"off_topic": "Not about the AI Act.",
          "general": "General question about the AI Act.",
          "company_case": "Question about your company's AI system."}
SOURCE_KINDS = {"chunk": "passages of law and guidance", "table": "date rows", "country": "country profiles"}

STARTERS = {
    "Chatbot in Oslo and Helsinki": "We're a startup with offices in Oslo and Helsinki. We use a chatbot on "
                                    "our website to answer customer questions. What do we need to do?",
    "CV screening tool": "We built a tool that ranks job applicants' CVs for recruiting agencies in France. "
                         "Which rules apply to us?",
    "High-risk deadlines": "When do the obligations for high-risk AI systems apply?",
    "Provider or deployer?": "What is the difference between a provider and a deployer?",
}

SETUP_HINT = ("Check that Ollama is running with `qwen3.5:9b` and `bge-m3` pulled, and that Postgres is up "
              "(`docker compose up -d db`). The full error is in the terminal.")


@cl.set_starters
async def starters(user=None, language=None) -> list[cl.Starter]:
    return [cl.Starter(label=label, message=message) for label, message in STARTERS.items()]


@cl.on_chat_start
async def start() -> None:
    cl.user_session.set("convo", Conversation())


@cl.on_message
async def on_message(message: cl.Message) -> None:
    convo: Conversation = cl.user_session.get("convo")
    steps: dict[str, cl.Step] = {}

    async def on_node(name: str, update: dict | None) -> None:
        if name not in STEPS:
            return
        if update is None:  # node started
            step = steps[name] = cl.Step(name=STEPS[name], type="tool", show_input=False)
            step.start = utc_now()
            await step.send()
            return
        step = steps.pop(name, None)
        if step:
            step.output, step.end = summary(name, update), utc_now()
            await step.update()

    try:
        r = await convo.asend(message.content, on_node)
    except Exception:
        log.exception("agent failed")
        for step in steps.values():
            step.is_error, step.end = True, utc_now()
            await step.update()
        cl.user_session.set("convo", Conversation())  # the failed turn may have left the thread half-written
        await cl.ErrorMessage(f"Sorry, the assistant failed. {SETUP_HINT}").send()
        return
    await cl.Message(content=r.get("question") or r["output"]).send()


def summary(node: str, update: dict) -> str:
    """What a node decided, in a few lines of markdown."""
    if node == "router":
        return ROUTES[update["intent"]]
    if node == "build_profile":  # only the facts the user gave
        lines = rules.profile_summary(update["profile"]).splitlines()
        return "\n".join(line for line in lines if not line.endswith(": not stated"))
    if node == "plan":
        obligations = ", ".join(f"`{o['id']}`" for o in update["obligations"]) or "picked from the search results"
        countries = ", ".join(update["countries"]) or "none named"
        return f"- Obligations: {obligations}\n- Countries: {countries}"
    if node == "research":
        counts = Counter(s.kind for s in update["sources"])
        return "\n".join(f"- {n} {SOURCE_KINDS[kind]}" for kind, n in counts.items())
    return ""
