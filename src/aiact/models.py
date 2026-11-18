"""Core data types for the corpus."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import date


@dataclass(frozen=True)
class Document:
    doc_id: str
    title: str
    jurisdiction: str
    doc_type: str
    status: str
    binding: bool
    language: str
    url: str
    published: date | None = None
    version_date: date | None = None


@dataclass
class Chunk:
    chunk_id: str
    doc_id: str
    seq: int
    article_ref: str | None
    title: str | None
    context: str
    text: str
    url: str
    refs: list[str] = field(default_factory=list)
    amended_by: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Cross-reference extraction ("Article 6(2)", "Articles 8 to 15", "Annex III")
# ---------------------------------------------------------------------------

_ART = re.compile(
    r"\bArticles?\s+(\d+[a-z]?)((?:\(\d+[a-z]?\))*)"
    r"((?:\s*(?:,|and|or|to)\s*(?:\d+[a-z]?(?:\(\d+[a-z]?\))*|\(\d+[a-z]?\)))*)"
)
_ANNEX = re.compile(r"\bAnnex(?:es)?\s+([IVX]+)\b((?:\s*(?:,|and|or|to)\s*[IVX]+\b)*)")
# A reference followed by one of these points to another legal act, not to the AI Act.
_OTHER_ACT = re.compile(
    r"^\s*(?:,\s*)?(?:first|second|third|\w+\s+subparagraph|point\s+\S+\s*,?\s*)*\s*"
    r"(?:of|to)\s+(?:Regulation|Directive|Decision|the\s+Treaty|the\s+Charter|that\s+Regulation|that\s+Directive|Implementing|Delegated)"
    r"|^\s*TFEU|^\s*TEU|^\s*GDPR"
)


def extract_refs(text: str) -> list[str]:
    """Return AI Act cross-references found in text, normalised ('Art. 6(2)', 'Annex III')."""
    refs: list[str] = []

    def add(r: str) -> None:
        if r not in refs:
            refs.append(r)

    for m in _ART.finditer(text):
        if _OTHER_ACT.match(text[m.end():m.end() + 60]):
            continue
        num, paras, tail = m.group(1), m.group(2), m.group(3)
        add(f"Art. {num}{paras.split(')')[0] + ')' if paras else ''}")
        # "Articles 8 to 15" / "Articles 16, 17 and 18"
        if tail:
            # tokens: "17", "17(2)" (another article) or "(4)" (another paragraph of `num`)
            toks = re.findall(r"(\d+[a-z]?)(?:\((\d+[a-z]?)\))?|\((\d+[a-z]?)\)", tail)
            arts = [(n, p) for n, p, _ in toks if n]
            if " to " in tail and arts and num.isdigit() and arts[-1][0].isdigit():
                for n in range(int(num) + 1, int(arts[-1][0]) + 1):
                    add(f"Art. {n}")
            else:
                for n, p, bare in toks:
                    add(f"Art. {num}({bare})" if bare else f"Art. {n}({p})" if p else f"Art. {n}")
    for m in _ANNEX.finditer(text):
        if _OTHER_ACT.match(text[m.end():m.end() + 60]):
            continue
        add(f"Annex {m.group(1)}")
        for extra in re.findall(r"[IVX]+", m.group(2) or ""):
            add(f"Annex {extra}")
    return refs


def clean_ws(s: str) -> str:
    return " ".join(s.split())
