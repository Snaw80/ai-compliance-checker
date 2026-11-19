"""Answer eval: v0 baseline (plain RAG chain) vs the agent graph, on eval/questions.yaml.

    uv run python -m aiact.eval_answers                  # both systems; resumes from eval/results/answers.jsonl
    uv run python -m aiact.eval_answers --only q31 q35   # a subset
    uv run python -m aiact.eval_answers --fresh          # recompute everything
    uv run python -m aiact.eval_answers --report         # rewrite the report from the cached answers

Every answer is given "as of" TODAY so dates and statuses are reproducible. When the agent asks a
clarifying question, it gets the question's scripted `clarify` reply (else "I don't know.").

Metrics:
  score       judge verdict vs the expected answer gist: correct = 1, partial = 0.5, wrong = 0
  cites gold  at least one cited source stands for a gold article (questions with gold refs)
  unsupported share of answer points with no valid source tag (code check)
  bad dates   answers containing a date that appears in none of their sources
  asked       the agent asked at least one clarifying question
  seconds     wall-clock per question, clarifying turns included (one M4, models already loaded)

The judge is a local model (default: the fast model). It only compares against the expected gist,
but it is the same model family as the systems it grades: treat scores as indicative.
"""

from __future__ import annotations

import argparse
import json
import logging
import statistics
import time
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from aiact.agent import baseline, llm
from aiact.agent.graph import Conversation
from aiact.eval_retrieval import load_questions, md_table
from aiact.search import ref_matches

TODAY = date(2026, 11, 19)
RAW = Path("eval/results/answers.jsonl")
OUT = Path("eval/results/answers.md")
SYSTEMS = ("baseline", "agent")
SCORE = {"correct": 1.0, "partial": 0.5, "wrong": 0.0}

log = logging.getLogger("aiact.eval")

JUDGE = """You grade answers of an assistant that explains the EU AI Act to companies.

Compare the assistant's answer with the expected answer, written by a reviewer. The expected answer is the reference: do not use your own knowledge of the AI Act, it is outdated. Dates, roles (provider/deployer), obligations and whether something applies must match the expected answer.

Extra details the expected answer does not mention (dates, other obligations, caveats) are fine: do not mark them down unless they contradict the expected answer or the facts below.

Current dates of application (AI Act as amended by the Digital Omnibus, Regulation (EU) 2026/1744, which exists and is in force):
- 2 February 2025: definitions, AI literacy (Art. 4), prohibited practices (Art. 5)
- 2 August 2025: general-purpose AI model obligations, penalties
- 2 August 2026: general date, incl. transparency obligations (Art. 50); systems placed on the market before then have until 2 December 2026 for Art. 50(2) marking
- 2 December 2027: high-risk systems of Annex III (incl. deployer duties, Art. 26-27), postponed from 2 August 2026
- 2 August 2028: high-risk AI in Annex I products, postponed from 2 August 2027

If the expected answer says the question is out of scope, the answer is correct only if the assistant declines or says it only covers the AI Act."""


class Verdict(BaseModel):
    """Your grade for the assistant's answer."""
    reasoning: str = Field(description="1-2 sentences: which key facts of the expected answer are present, missing or contradicted.")
    verdict: Literal["correct", "partial", "wrong"] = Field(description=(
        "correct: has the key facts of the expected answer and nothing contradicting it. "
        "partial: some key facts missing, nothing badly wrong. "
        "wrong: misses the main point or contradicts the expected answer (wrong date, obligation or role)."))


# ---------------------------------------------------------------------------
# Running the systems
# ---------------------------------------------------------------------------

def run_baseline(q: dict) -> dict:
    out = baseline.run(q["question"], TODAY)
    return {"output": out["output"], "seconds": out["seconds"], "asked": 0,
            "cited_refs": [r for s in out["cited"] for r in s.refs],
            "verification": out["verification"].model_dump()}


def run_agent(q: dict) -> dict:
    convo = Conversation(today=TODAY)
    replies = list(q.get("clarify") or [])
    t = time.perf_counter()
    r = convo.send(q["question"])
    questions = []
    while "question" in r:
        questions.append(r["question"])
        r = convo.send(replies.pop(0) if replies else "I don't know.")
    state = r["state"]
    profile = state.get("profile")
    return {"output": r["output"], "seconds": time.perf_counter() - t, "asked": len(questions),
            "clarifying_questions": questions, "intent": state.get("intent"),
            "obligations": [o["id"] for o in state.get("obligations") or []],
            "countries": state.get("countries") or [],
            "role": profile.built_or_bought if profile and state.get("intent") == "company_case" else None,
            "cited_refs": [r for s in state.get("cited") or [] for r in s.refs],
            "verification": state["verification"].model_dump() if state.get("verification") else None}


def judge(q: dict, output: str, model: str) -> dict:
    v = llm.structured(Verdict, [
        ("system", JUDGE),
        ("user", f"Question: {q['question']}\n\nExpected answer: {q['answer']}\n\nAssistant's answer:\n{output}"),
    ], model=model)
    return v.model_dump()


def cites_gold(cited_refs: list[str], gold: list[str]) -> bool:
    return any(ref_matches(r, g.strip()) for item in gold for g in item.split("|") for r in cited_refs)


# ---------------------------------------------------------------------------
# Cache (one JSON line per system + question)
# ---------------------------------------------------------------------------

def load_cache() -> dict[tuple[str, str], dict]:
    if not RAW.exists():
        return {}
    rows = [json.loads(line) for line in RAW.read_text().splitlines() if line.strip()]
    return {(r["system"], r["id"]): r for r in rows}


def save_cache(cache: dict[tuple[str, str], dict]) -> None:
    RAW.parent.mkdir(parents=True, exist_ok=True)
    rows = sorted(cache.values(), key=lambda r: (r["id"], SYSTEMS.index(r["system"])))
    RAW.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def _mean(xs: list[float]) -> str:
    return f"{statistics.mean(xs):.2f}" if xs else "-"


def summarize(rows: list[dict], qs: dict[str, dict]) -> list[str]:
    scores = [SCORE[r["judge"]["verdict"]] for r in rows if r.get("judge")]
    gold = [r for r in rows if qs[r["id"]]["gold"]]
    ver = [r["verification"] for r in rows if r.get("verification")]
    unsupported = sum(v["unsupported"] for v in ver) / max(1, sum(v["n_points"] for v in ver))
    return [_mean(scores),
            _mean([float(cites_gold(r["cited_refs"], qs[r["id"]]["gold"])) for r in gold]),
            f"{unsupported:.2f}",
            str(sum(bool(v["unverified_dates"]) for v in ver)),
            str(sum(bool(r.get("error")) for r in rows)),
            f"{statistics.median(r['seconds'] for r in rows):.0f}" if rows else "-"]


def report(cache: dict[tuple[str, str], dict], questions: list[dict], judge_model: str) -> str:
    qs = {q["id"]: q for q in questions}
    by_sys = {s: [cache[(s, q["id"])] for q in questions if (s, q["id"]) in cache] for s in SYSTEMS}
    summary = md_table(["system", "score", "cites gold", "unsupported points", "answers with bad dates",
                        "errors", "median s"], [[s] + summarize(by_sys[s], qs) for s in SYSTEMS])

    groups: dict[str, list[str]] = defaultdict(list)
    for q in questions:
        groups["company case" if q["type"] == "company_case" else
               "out of scope" if q["type"] == "out_of_scope" else "general"].append(q["id"])
    group_rows = []
    for g, ids in groups.items():
        row = [g, str(len(ids))]
        for s in SYSTEMS:
            sc = [SCORE[cache[(s, i)]["judge"]["verdict"]] for i in ids if cache.get((s, i), {}).get("judge")]
            row.append(_mean(sc))
        group_rows.append(row)
    by_group = md_table(["questions", "n", *[f"{s} score" for s in SYSTEMS]], group_rows)

    per_q = []
    for q in questions:
        b, a = cache.get(("baseline", q["id"]), {}), cache.get(("agent", q["id"]), {})
        verdict = lambda r: (r.get("judge") or {}).get("verdict", "error" if r.get("error") else "-")
        note = (a.get("judge") or {}).get("reasoning", a.get("error", "")) if verdict(a) != "correct" else ""
        agent_extra = []
        if a.get("asked"):
            agent_extra.append(f"asked {a['asked']}")
        if a.get("role"):
            agent_extra.append(a["role"])
        per_q.append([q["id"], q["type"], verdict(b), verdict(a), ", ".join(agent_extra),
                      note.replace("|", "/").replace("\n", " ")[:220]])
    per_table = md_table(["id", "type", "baseline", "agent", "agent asked / role", "judge note (agent, if not correct)"],
                         per_q)
    return f"""# Answer eval: baseline vs agent

- Date: {date.today()} · answers as of {TODAY} · {len(questions)} questions (`eval/questions.yaml`)
- Writer `{llm.WRITER_MODEL}`, fast model `{llm.FAST_MODEL}`, judge `{judge_model}` (Ollama, thinking off)
- **baseline** (v0): hybrid search top-8 → writer → code citation check. Same prompt and rendering as the agent.
- **agent** (day 4): router → company profile ⇄ clarifying question → plan (code: obligations, countries)
  → research (law of the selected obligations + search + applicability table + country profiles) → writer → code check
- Raw answers: `eval/results/answers.jsonl`. Score: judge vs expected gist (correct 1, partial 0.5, wrong 0).
  The judge is a 9B local model of the same family: indicative, spot-check the raw answers.

## Summary

{summary}

## By question group

{by_group}

## Per question

{per_table}
"""


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", nargs="*", help="question ids")
    ap.add_argument("--systems", nargs="*", default=list(SYSTEMS), choices=SYSTEMS)
    ap.add_argument("--fresh", action="store_true", help="recompute the selected answers")
    ap.add_argument("--rejudge", action="store_true", help="keep answers, judge again")
    ap.add_argument("--report", action="store_true", help="only rewrite the report")
    ap.add_argument("--judge-model", default=llm.FAST_MODEL)
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    for name in ("httpx", "aiact.agent"):
        logging.getLogger(name).setLevel(logging.WARNING)

    questions = load_questions()
    todo = [q for q in questions if not a.only or q["id"] in a.only]
    cache = load_cache()
    if a.fresh:  # drop only the selected answers, keep the rest of the cache
        cache = {k: v for k, v in cache.items() if not (k[0] in a.systems and k[1] in {q["id"] for q in todo})}
    runners = {"baseline": run_baseline, "agent": run_agent}

    if not a.report:
        for q in todo:
            for s in a.systems:
                key = (s, q["id"])
                row = cache.get(key)
                if row is None or row.get("error"):
                    try:
                        row = {"system": s, "id": q["id"], **runners[s](q)}
                    except Exception as e:  # a failed answer is a result too
                        row = {"system": s, "id": q["id"], "error": f"{type(e).__name__}: {e}"[:300],
                               "output": "", "seconds": 0.0, "asked": 0, "cited_refs": [], "verification": None}
                    row.pop("judge", None)
                if row.get("output") and (a.rejudge or not row.get("judge")):
                    row["judge"] = judge(q, row["output"], a.judge_model)
                cache[key] = row
                save_cache(cache)  # after every answer: a crash or ^C loses nothing
                verdict = (row.get("judge") or {}).get("verdict", "error")
                log.info("%s %-8s %-7s %5.0fs %s", q["id"], s, verdict, row["seconds"],
                         f"asked {row['asked']}" if row.get("asked") else "")

    text = report(cache, questions, a.judge_model)
    OUT.write_text(text)
    print(text)
    print(f"-> {OUT}")


if __name__ == "__main__":
    main()
