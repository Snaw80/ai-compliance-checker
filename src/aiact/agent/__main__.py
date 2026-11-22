"""Ask the assistant from the terminal.

    uv run python -m aiact.agent "We use a chatbot on our website. What do we need to do?"
    uv run python -m aiact.agent                      # chat (several turns, same thread)
    uv run python -m aiact.agent --baseline "Do I have to tell users they talk to a chatbot?"
"""

from __future__ import annotations

import argparse
import logging
from datetime import date

from aiact.agent import baseline
from aiact.agent.graph import Conversation


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("question", nargs="?", help="omit to chat")
    ap.add_argument("--baseline", action="store_true", help="plain RAG chain baseline")
    ap.add_argument("--today", type=date.fromisoformat, help="answer as of this date (YYYY-MM-DD)")
    ap.add_argument("-v", "--verbose", action="store_true", help="log decisions and timings")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO if a.verbose else logging.WARNING, format="  · %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    if a.baseline:
        if not a.question:
            ap.error("--baseline needs a question")
        out = baseline.run(a.question, a.today)
        print(out["output"])
        print(f"\n({out['seconds']:.0f}s, {out['verification'].model_dump()})")
        return

    convo = Conversation(today=a.today)
    message = a.question
    while True:
        if message is None:
            try:
                message = input("\nyou> ").strip()
            except (EOFError, KeyboardInterrupt):
                return
            if not message:
                return
        r = convo.send(message)
        print(f"\nassistant> {r.get('question') or r['output']}\n  ({r['seconds']:.0f}s)")
        if a.question and not convo.waiting:
            return  # one-shot mode: stop after the answer
        message = None


if __name__ == "__main__":
    main()
