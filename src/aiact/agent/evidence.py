"""Turn search hits, applicability rows and country profiles into tagged sources the writer cites.

    S1, S2, ...  corpus chunks (law, recitals, guidelines, FAQ)
    T1, T2, ...  applicability table rows (dates: never from the model)
    FI, NO, ...  country profile rows
"""

from __future__ import annotations

import re
from datetime import date

from aiact.agent.schemas import Source
from aiact.search import Hit, get_chunks
from aiact.tables import Applicability, get_country_profile

MAX_CHARS = 1500  # per chunk shown to the model; the longest annex chunks are ~4k chars

DOC_SHORT = {
    "eu-ai-act-consolidated": "AI Act",
    "eu-ai-act-recitals": "AI Act",
    "eu-digital-omnibus-ai": "Digital Omnibus (Reg. 2026/1744)",
    "eu-guidelines-art50": "Commission Art. 50 guidelines",
    "eu-service-desk-faq": "AI Act Service Desk FAQ",
}


def hit_label(h: Hit) -> str:
    doc = DOC_SHORT.get(h.doc_id, h.doc_id)
    ref = h.article_ref or h.title or h.chunk_id
    if h.doc_id == "eu-guidelines-art50":
        return f"{doc}, para. {ref.rsplit('para. ', 1)[-1]}" if "para. " in ref else doc
    if h.doc_id == "eu-service-desk-faq":
        return f"{doc}: {h.title}" if h.title else doc
    return f"{doc}, {ref}"


def chunk_sources(hits: list[Hit], start: int = 1) -> list[Source]:
    """S1, S2, ... one per distinct chunk."""
    out: list[Source] = []
    seen: set[str] = set()
    for h in hits:
        if h.chunk_id in seen:
            continue
        seen.add(h.chunk_id)
        text = h.text if len(h.text) <= MAX_CHARS else h.text[:MAX_CHARS] + " [...]"
        amended = f" (amended by {h.amended_by})" if h.amended_by else ""
        out.append(Source(
            tag=f"S{start + len(out)}", kind="chunk", label=hit_label(h) + amended,
            # title, not the long breadcrumb `context`: same signal, fewer tokens
            text=f"({h.title})\n{text}" if h.title else text, url=h.url,
            refs=[h.article_ref] if h.article_ref else [], chunk_ids=[h.chunk_id]))
    return out


def format_sources(sources: list[Source]) -> str:
    """The evidence block of the writer prompt."""
    return "\n\n".join(f"[{s.tag}] {s.label}\n{s.text}" for s in sources)


def compact_articles(articles: tuple[str, ...] | list[str]) -> str:
    """('Art. 6', 'Art. 7', ..., 'Art. 27', 'Annex III') -> 'Art. 6-27, Annex III'."""
    out: list[str] = []
    run: list[int] = []

    def flush() -> None:
        if run:
            out.append(f"Art. {run[0]}" if len(run) == 1 else f"Art. {run[0]}-{run[-1]}")
            run.clear()

    for a in articles:
        m = re.fullmatch(r"Art\. (\d+)", a)
        if m and (not run or int(m[1]) == run[-1] + 1):
            run.append(int(m[1]))
            continue
        flush()
        if m:
            run.append(int(m[1]))
        else:
            out.append(a)
    flush()
    return ", ".join(out)


def fmt_date(d: date | str) -> str:
    d = date.fromisoformat(d) if isinstance(d, str) else d
    return f"{d.day} {d:%B %Y}"


# Chunks that only carry dates: cited through T sources, not shown as S sources.
DATE_ARTICLES = ("eu-ai-act-consolidated:art_113", "eu-ai-act-consolidated:art_111")


def is_date_chunk(chunk_id: str) -> bool:
    return chunk_id.startswith(DATE_ARTICLES)


def table_source(tag: str, a: Applicability, ref_of: dict[str, Hit]) -> Source:
    o = a.obligation
    status = {"applicable": f"applies (since {fmt_date(a.applies_from)})",
              "not_yet_applicable": f"does not apply yet (applies from {fmt_date(a.applies_from)}, "
                                    f"in {a.days_until} days)",
              "not_binding": "not binding"}[a.status]
    lines = [f"{o.obligation} ({', '.join(o.articles) or 'all other articles'}).",
             f"Addressed to: {', '.join(o.roles)}.",
             f"Applies from {fmt_date(o.applies_from)} ({o.basis}).",
             f"Status on {fmt_date(a.on)}: {status}."]
    for t in a.transitions:
        deadline = f" Deadline {fmt_date(t['deadline'])} ({t['status']})." if t.get("deadline") else ""
        lines.append(f"Transition ({', '.join(t.get('articles', []))}): {t['applies_to']}: {t['effect']}{deadline}")
    if o.notes:
        lines.append(f"Note: {o.notes}")
    hits = [ref_of[c] for c in o.source_chunk_ids if c in ref_of]
    what = compact_articles(o.articles) or "other articles"
    return Source(tag=tag, kind="table", label=f"AI Act, {o.basis}: date of application of {what}",
                  text="\n".join(lines),
                  url=hits[0].url if hits else None,
                  refs=[h.article_ref for h in hits if h.article_ref], chunk_ids=list(o.source_chunk_ids))


def table_sources(rows: list[Applicability], start: int = 1) -> list[Source]:
    ref_of = {h.chunk_id: h for h in get_chunks(sorted({c for a in rows for c in a.obligation.source_chunk_ids}))}
    return [table_source(f"T{start + i}", a, ref_of) for i, a in enumerate(rows)]


def _authority(a: dict | None) -> str:
    if not a:
        return "none designated"
    scope = f" ({a['scope']})" if a.get("scope") else ""
    status = "" if a["status"] == "designated" else f" [{a['status']}]"
    return f"{a['name']}{scope}{status}"


def _end(s: str) -> str:
    s = s.rstrip()
    return s if s.endswith((".", "!", "?")) else s + "."


def country_text(c: dict) -> str:
    law = c["national_law"]
    law_s = law["status"].replace("_", " ")
    if law.get("name"):
        law_s += f": {law['name']}" + (f" ({law['ref']})" if law.get("ref") else "")
    if law.get("in_force_from"):
        law_s += f", in force from {fmt_date(law['in_force_from'])}"
    if law.get("notes"):
        law_s = f"{_end(law_s)} {law['notes']}"
    binding = ("the AI Act applies directly (EU regulation)" if c["ai_act_binding"] else
               "EEA country: the AI Act is not binding here until it is incorporated into the EEA "
               "Agreement. It still applies to the company's AI systems placed on the market or used in the EU")
    lines = [f"{c['name']} ({c['membership']}): {binding}.",
             _end(f"National AI law: {law_s}"),
             f"Single point of contact: {_authority(c.get('single_point_of_contact'))}.",
             "Market surveillance authorities: "
             + ("; ".join(_authority(a) for a in c["market_surveillance_authorities"]) or "none designated") + "."]
    if c.get("penalties"):
        lines.append(_end(f"National penalty rules: {c['penalties']['status'].replace('_', ' ')}. "
                          + (c["penalties"].get("notes") or "")))
    if c.get("sandbox"):
        lines.append(_end(f"Regulatory sandbox: {c['sandbox']['status']}. " + (c["sandbox"].get("notes") or "")))
    if c.get("national_extras"):
        lines.append(_end(c["national_extras"]))
    lines.append(f"Last verified {fmt_date(c['last_verified'])}, {c['confidence']} confidence.")
    return "\n".join(lines)


def country_sources(isos: list[str]) -> list[Source]:
    out = []
    for iso in isos:
        c = get_country_profile(iso)
        web = [x["url"] for x in c["sources"] if x["url"].startswith("http")]
        url = c["national_law"].get("url") or (web[0] if web else None)
        out.append(Source(tag=iso, kind="country", url=url, text=country_text(c),
                          label=f"Country profile: {c['name']} (last verified {c['last_verified']}, "
                                f"{c['confidence']} confidence)"))
    return out
