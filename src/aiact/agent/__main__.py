"""Ask the assistant from the terminal.

    uv run python -m aiact.agent --baseline "Do I have to tell users they talk to a chatbot?"
"""

from __future__ import annotations

import argparse
import logging
from datetime import date

from aiact.agent import baseline


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("question")
    ap.add_argument("--baseline", action="store_true", help="plain RAG chain (v0)")
    ap.add_argument("--today", type=date.fromisoformat, help="answer as of this date (YYYY-MM-DD)")
    ap.add_argument("-v", "--verbose", action="store_true", help="log node timings")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO if a.verbose else logging.WARNING, format="%(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    out = baseline.run(a.question, a.today)
    print(out["output"])
    print(f"\n({out['seconds']:.0f}s, {out['verification'].model_dump()})")


if __name__ == "__main__":
    main()
