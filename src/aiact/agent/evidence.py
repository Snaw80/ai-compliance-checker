"""Turn search hits into tagged sources the writer can cite."""

from __future__ import annotations

from aiact.agent.schemas import Source
from aiact.search import Hit

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
