"""Code-only citation check and the final markdown (no model involved).

The citation check is the day-4 version of `verify_citations`: it checks that every tag the writer
cites was actually shown to it, and that every date it writes appears in a source. Whether a source
really *supports* its point (a model check) comes later.
"""

from __future__ import annotations

import calendar
import re

from aiact.agent.schemas import Answer, Point, Source, Verification

DISCLAIMER = "_General information about the EU AI Act, not legal advice._"
OFF_TOPIC = ("I can only help with the EU AI Act: which rules apply to an AI system, in which "
             "EU/EEA country, and from when. Try asking about your AI system or an article of the Act.")
RISK_LABEL = {
    "prohibited": "prohibited practice (Art. 5)",
    "high_risk": "high-risk",
    "transparency": "limited risk: transparency obligations (Art. 50)",
    "minimal": "minimal risk: no specific AI Act obligations beyond AI literacy",
    "unclear": "unclear from what you described",
}

# ---------------------------------------------------------------------------
# Dates
# ---------------------------------------------------------------------------

_MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_name) if m}
_MONTHS |= {m.lower(): i for i, m in enumerate(calendar.month_abbr) if m}
_MONTHS["sept"] = 9
_DAY_MONTH_YEAR = re.compile(r"\b(?:(\d{1,2})(?:st|nd|rd|th)?\s+)?(" + "|".join(sorted(_MONTHS, key=len, reverse=True))
                             + r")\.?,?\s+(\d{4})\b", re.I)
_MONTH_DAY_YEAR = re.compile(r"\b(" + "|".join(sorted(_MONTHS, key=len, reverse=True))
                             + r")\.?\s+(\d{1,2}),?\s+(\d{4})\b", re.I)
_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")

Date = tuple[int, int, int | None]  # (year, month, day or None for "August 2026")


def dates_in(text: str) -> dict[Date, str]:
    """Calendar dates written in `text` -> how they were written."""
    out: dict[Date, str] = {}
    for m in _MONTH_DAY_YEAR.finditer(text):
        out[(int(m[3]), _MONTHS[m[1].lower()], int(m[2]))] = m[0]
    for m in _DAY_MONTH_YEAR.finditer(text):
        out.setdefault((int(m[3]), _MONTHS[m[2].lower()], int(m[1]) if m[1] else None), m[0])
    for m in _ISO.finditer(text):
        out[(int(m[1]), int(m[2]), int(m[3]))] = m[0]
    return out


def _date_known(d: Date, known: set[Date]) -> bool:
    if d in known:
        return True
    year, month, day = d
    return day is None and any(k[:2] == (year, month) for k in known)


# ---------------------------------------------------------------------------
# Citation check
# ---------------------------------------------------------------------------

_TAGS = re.compile(r"\[\s*([A-Za-z]{1,2}\d{0,3}(?:\s*[,;]\s*[A-Za-z]{1,2}\d{0,3})*)\s*\]")


def split_tags(point: str) -> tuple[str, list[str]]:
    """'Text [S1][T2, FI].' -> ('Text.', ['S1', 'T2', 'FI'])."""
    tags = [t.strip() for m in _TAGS.finditer(point) for t in re.split(r"[,;]", m[1])]
    text = re.sub(r"\s+([.,;:])", r"\1", _TAGS.sub("", point)).strip()
    return text, tags


def verify(answer: Answer, sources: list[Source]) -> tuple[list[Point], Verification]:
    """Parse each point's inline tags, drop tags never shown to the model, count unsupported
    points and dates that appear in no source."""
    by_tag = {s.tag.upper(): s.tag for s in sources}
    known_dates = {d for s in sources for d in dates_in(s.text)}
    v = Verification(n_points=len(answer.points))
    points = []
    for raw in answer.points:
        text, found = split_tags(raw)
        tags = []
        for t in found:
            if t.upper() in by_tag:
                if by_tag[t.upper()] not in tags:
                    tags.append(by_tag[t.upper()])
            else:
                v.unknown_tags.append(t)
        v.unsupported += not tags
        points.append(Point(text=text, sources=tags))
    summary, _ = split_tags(answer.summary)
    all_text = " ".join([summary] + [p.text for p in points] + answer.caveats)
    v.unverified_dates = [raw for d, raw in dates_in(all_text).items() if not _date_known(d, known_dates)]
    return points, v


# ---------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------

def render(answer: Answer, points: list[Point], sources: list[Source],
           verification: Verification | None = None, *,
           sections: list[str] = (), caveats: list[str] = ()) -> tuple[str, list[Source]]:
    """Markdown answer + the sources it cites (in footnote order).

    `sections` are code-built blocks (dates table, country specifics) placed after the points;
    `caveats` are code-made caveats (assumptions) added before the model's own.
    """
    by_tag = {s.tag: s for s in sources}
    cited: list[Source] = []

    def ref(tag: str) -> str:
        s = by_tag[tag]
        if s not in cited:
            cited.append(s)
        return f"[{cited.index(s) + 1}]"

    out = [split_tags(answer.summary)[0]]
    if answer.risk_tier:
        out.append(f"**Probable risk category:** {RISK_LABEL[answer.risk_tier]}")
    if points:
        lines = []
        for p in points:
            refs = "".join(ref(t) for t in p.sources if t in by_tag)
            lines.append(f"- {p.text.strip()} {refs}".rstrip() + ("" if refs else " _(no source found)_"))
        out.append("\n".join(lines))
    out += [s for s in sections if s]
    all_caveats = [*caveats, *(split_tags(c)[0] for c in answer.caveats)]
    if verification and verification.unverified_dates:
        all_caveats.append("These dates in the answer are not in the sources, so check them: "
                           + ", ".join(verification.unverified_dates) + ".")
    if all_caveats:
        out.append("**Caveats**\n" + "\n".join(f"- {c.strip()}" for c in all_caveats))
    if cited:
        out.append("**Sources**\n" + "\n".join(
            f"{i}. [{s.label}]({s.url})" if s.url else f"{i}. {s.label}" for i, s in enumerate(cited, 1)))
    out.append(DISCLAIMER)
    return "\n\n".join(out), cited
