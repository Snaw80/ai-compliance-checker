"""Parsers for EUR-Lex / Cellar XHTML.

- parse_consolidated(): consolidated AI Act -> one chunk per article paragraph, per
  definition (Art. 3), per long-list point, and per annex point.
- parse_recitals(): recitals of an Official Journal act (original AI Act, Omnibus).

Consolidated texts mark the origin of each passage: '▼B' = original act, '▼M1' = first
amending act (here Regulation (EU) 2026/1744). A marker applies until the next one.
'►M1 ... ◄' marks an inline amendment.
"""

from __future__ import annotations

import re
import warnings
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString, Tag, XMLParsedAsHTMLWarning

from aiact.models import Chunk, Document, clean_ws, extract_refs

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

MARKER = re.compile(r"[▼►]\s?(?:B|[MACR]\d+)|◄")
AMENDING_ACTS = {"M1": "Regulation (EU) 2026/1744"}
SPLIT_THRESHOLD = 3000  # chars; longer paragraphs are split into their list points
MAX_LEAD = 400  # chars of lead-in text repeated in front of every split point
ARTICLE_ID = re.compile(r"^art_(\d+[a-z]*)$")


def load(path: Path) -> BeautifulSoup:
    return BeautifulSoup(path.read_text(encoding="utf-8"), "lxml")


# ---------------------------------------------------------------------------
# Rendering: element -> readable text that keeps list structure
# ---------------------------------------------------------------------------

def _classes(tag: Tag) -> list[str]:
    return tag.get("class") or []


def render_lines(el: Tag) -> list[str]:
    lines: list[str] = []
    buf: list[str] = []

    def flush() -> None:
        t = clean_ws(" ".join(buf))
        buf.clear()
        if t:
            lines.append(t)

    for ch in el.children:
        if isinstance(ch, NavigableString):
            buf.append(str(ch))
            continue
        if not isinstance(ch, Tag):
            continue
        cls = _classes(ch)
        if "grid-container" in cls:
            flush()
            label_el = ch.find(class_="grid-list-column-1")
            body_el = ch.find(class_="grid-list-column-2")
            label = clean_ws(label_el.get_text(" ")) if label_el else ""
            body = render_lines(body_el) if body_el else []
            if body:
                lines.append(f"{label} {body[0]}".strip())
                lines.extend("    " + b for b in body[1:])
            elif label:
                lines.append(label)
        elif ch.name == "tr":
            flush()
            cells = [" ".join(render_lines(td)) for td in ch.find_all(["td", "th"], recursive=False)]
            row = " | ".join(c for c in cells if c)
            if row:
                lines.append(row)
        elif ch.name in ("p", "div", "table", "tbody", "thead", "li", "ul", "ol", "td", "th"):
            flush()
            lines.extend(render_lines(ch))
        elif ch.name == "br":
            flush()
        else:  # inline: span, a, em, strong, sup...
            buf.append(ch.get_text(" "))
    flush()
    return lines


LABEL_ONLY = re.compile(r"^\s*(?:\(?[0-9]{1,3}[a-z]?\)|\([a-z]{1,4}\)|[0-9]{1,3}[a-z]?\.|[a-z]\)|[ivx]{1,5}\))\s*$")


def to_text(lines: list[str]) -> str:
    out: list[str] = []
    pending = ""
    for line in lines:
        line = MARKER.sub("", line).rstrip()
        if not line.strip():
            continue
        line = re.sub(r"(?<=\S) {2,}", " ", line)
        if LABEL_ONLY.match(line):
            pending = (pending + " " + line.strip()) if pending else line
            continue
        if pending:
            indent = pending[: len(pending) - len(pending.lstrip())]
            line = f"{indent}{pending.strip()} {line.strip()}"
            pending = ""
        out.append(line)
    if pending:
        out.append(pending)
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Amendment tracking
# ---------------------------------------------------------------------------

def _marker_code(s: str) -> str:
    return re.sub(r"[▼►\s]", "", s)


def amended_by(first_el: Tag, els: list[Tag]) -> str | None:
    """Which amending act the text of `els` comes from (None = original text)."""
    codes = []
    prev = first_el.find_previous(string=MARKER)
    if prev is not None:
        last = MARKER.findall(str(prev))
        if last and last[-1].startswith("▼"):
            codes.append(_marker_code(last[-1]))
    for el in els:
        codes += [_marker_code(m) for m in MARKER.findall(el.get_text(" ")) if m != "◄"]
    acts = sorted({AMENDING_ACTS.get(c, c) for c in codes if c.startswith(("M", "A"))})
    return "; ".join(acts) or None


# ---------------------------------------------------------------------------
# Consolidated act
# ---------------------------------------------------------------------------

def _nice_heading(h: str) -> str:
    m = re.match(r"^(CHAPTER|SECTION)\s+([IVXLC\d]+)$", h)
    if m:
        return f"{m.group(1).capitalize()} {m.group(2)}"
    if h.isupper():
        h = h.capitalize()
        h = re.sub(r"\b(ai|eu|gpai|ce)\b", lambda x: x.group(1).upper(), h)
    return h


def _division_titles(el: Tag) -> list[str]:
    """Chapter / section headings enclosing an article, outermost first."""
    titles = []
    for anc in el.parents:
        if not isinstance(anc, Tag) or not anc.get("id", "").startswith("cpt_"):
            continue
        heads = [clean_ws(p.get_text(" ")) for p in anc.find_all("p", recursive=False)
                 if {"title-division-1", "title-division-2"} & set(_classes(p))]
        if heads:
            titles.append(" ".join(_nice_heading(h) for h in heads[:2]))
    return list(reversed(titles))


def _top_level_points(container: Tag) -> list[Tag]:
    """grid-list items directly inside container (not nested in another list)."""
    out = []
    for g in container.find_all("div", class_="grid-container"):
        a, nested = g.parent, False
        while a is not None and a is not container:
            if "grid-container" in _classes(a):
                nested = True
                break
            a = a.parent
        if not nested:
            out.append(g)
    return out


def _point_label(g: Tag) -> str:
    lab = g.find(class_="grid-list-column-1")
    return clean_ws(lab.get_text(" ")).strip(" .") if lab else ""


def _split_by_points(els: list[Tag]) -> list[tuple[str | None, list[Tag], str]] | None:
    """Split a long block into (point_label, elements, lead_in_text) pieces.

    `els` is either one element whose inner list is split, or a list of sibling
    elements (lead-in paragraph(s) followed by list items). Returns None if there is
    nothing to split on.
    """
    direct = [c for c in els if "grid-container" in _classes(c)]
    if len(direct) < 2:
        # Points nested inside the first element (e.g. Art. 5(1)); later elements trail.
        points = _top_level_points(els[0])
        if len(points) < 2 or any(p.parent is not points[0].parent for p in points):
            return None
        siblings = [c for c in points[0].parent.children if isinstance(c, Tag)] + list(els[1:])
    else:
        siblings = els
        points = [c for c in els if "grid-container" in _classes(c)]
        if len(points) < 2:
            return None
    lead_lines: list[str] = []
    pieces: list[tuple[str | None, list[Tag]]] = []
    for ch in siblings:
        if "modref" in _classes(ch):
            continue
        if ch in points:
            pieces.append((_point_label(ch), [ch]))
        elif not pieces:
            lead_lines += render_lines(ch)
        elif pieces[-1][0] is None:
            pieces[-1][1].append(ch)
        else:
            pieces.append((None, [ch]))
    lead = to_text(lead_lines)
    if len(lead) > MAX_LEAD:
        lead = lead[:MAX_LEAD].rsplit(" ", 1)[0] + " […]"
    return [(lab, p_els, lead) for lab, p_els in pieces]


def parse_consolidated(path: Path, doc: Document) -> list[Chunk]:
    soup = load(path)
    chunks: list[Chunk] = []
    short_title = f"EU AI Act (Reg. 2024/1689, consolidated {doc.version_date})"
    seen_ids: set[str] = set()

    def add(anchor: str, ref: str, title: str | None, context_parts: list[str], text: str,
            first_el: Tag, els: list[Tag], suffix: str) -> None:
        if not text.strip():
            return
        cid = f"{doc.doc_id}:{anchor}:{suffix}" if suffix else f"{doc.doc_id}:{anchor}"
        n = 2
        while cid in seen_ids:  # e.g. Annex VII has several "(a)" lists
            cid = f"{doc.doc_id}:{anchor}:{suffix}~{n}"
            n += 1
        seen_ids.add(cid)
        chunks.append(Chunk(
            chunk_id=cid,
            doc_id=doc.doc_id, seq=len(chunks), article_ref=ref, title=title,
            context=" › ".join([short_title, *context_parts]),
            text=text, url=f"{doc.url}#{anchor}",
            refs=[r for r in extract_refs(text) if r != ref],
            amended_by=amended_by(first_el, els),
        ))

    # --- Articles ----------------------------------------------------------
    for art in soup.find_all("div", class_="eli-subdivision", id=ARTICLE_ID):
        num = ARTICLE_ID.match(art["id"]).group(1)
        anchor = art["id"]
        title_el = art.find(class_="stitle-article-norm")
        # strip("'"): the consolidated text has a stray quote in Art. 1 ("Subject matter'")
        title = clean_ws(title_el.get_text(" ")).strip("'") if title_el else None
        art_label = f"Article {num}" + (f" {title}" if title else "")
        ctx_base = [*_division_titles(art), art_label]

        # Group children into numbered paragraphs.
        segments: list[tuple[str | None, list[Tag]]] = []
        pending_markers: list[Tag] = []
        for ch in art.find_all(recursive=False):
            cls = _classes(ch)
            if "title-article-norm" in cls or "eli-title" in cls:
                continue
            if "modref" in cls:
                pending_markers.append(ch)
                continue
            no = ch.find("span", class_="no-parag", recursive=False)
            if no is not None:
                segments.append((no.get_text(strip=True).rstrip(".").strip(), [ch]))
            elif segments:
                segments[-1][1].extend([*pending_markers, ch])
            else:
                segments.append((None, [ch]))
            pending_markers = []

        for para, els in segments:
            ref = f"Art. {num}" + (f"({para})" if para else "")
            ctx = ctx_base + ([f"paragraph {para}"] if para else [])
            full = to_text([l for e in els for l in render_lines(e)])
            # Long paragraph / long unnumbered article (Art. 3 definitions, Art. 5(1)...)
            pieces = _split_by_points(els) if len(full) > SPLIT_THRESHOLD else None
            if not pieces:
                add(anchor, ref, title, ctx, full, els[0], els, para or "")
                continue
            for label, p_els, lead in pieces:
                body = to_text([l for e in p_els for l in render_lines(e)])
                if label:
                    lab = label.strip("()")
                    text = f"{lead}\n{body}" if lead else body
                    # Definitions: name the defined term in the context.
                    term = re.match(r"^\(?\w+\)?\s*[‘'](.+?)[’']", body)
                    p_ctx = ctx + [f"point ({lab})" + (f" ‘{term.group(1)}’" if term else "")]
                    add(anchor, f"{ref}({lab})", title, p_ctx, text, p_els[0], p_els,
                        f"{para + '.' if para else ''}{lab}")
                else:  # subparagraphs after the list of points
                    add(anchor, ref, title, ctx + ["(continued)"], body, p_els[0], p_els,
                        f"{para or ''}rest")

    # --- Annexes ----------------------------------------------------------
    for anx in soup.find_all("div", id=re.compile(r"^anx_[IVX]+$")):
        roman = anx["id"].split("_")[1]
        anchor = anx["id"]
        t2 = anx.find(class_="title-annex-2")
        title = clean_ws(t2.get_text(" ")) if t2 else None
        ctx = [f"Annex {roman}" + (f" {title}" if title else "")]
        content = [c for c in anx.find_all(recursive=False)
                   if not ({"title-annex-1", "title-annex-2", "separator-annex", "modref"} & set(_classes(c)))
                   and c.name != "hr"]
        full = to_text([l for c in content for l in render_lines(c)])
        ref = f"Annex {roman}"
        if len(full) <= SPLIT_THRESHOLD:
            add(anchor, ref, title, ctx, full, anx, content, "")
            continue
        # 1) split on section headings ("Section A. ...") when present
        sections: list[tuple[str | None, list[Tag]]] = [(None, [])]
        for c in content:
            if "title-gr-seq-level-1" in _classes(c):
                sections.append((clean_ws(c.get_text(" ")), [c]))
            else:
                sections[-1][1].append(c)
        sections = [(h, els) for h, els in sections if els]
        for si, (heading, sec_els) in enumerate(sections):
            m = re.match(r"(Section\s+[A-Z0-9]+|\d+)", heading or "")
            sec_label = (f"point {m.group(1)}" if m.group(1).isdigit() else m.group(1)) if m else None
            sec_ref = f"{ref} {sec_label}" if sec_label else ref
            sec_ctx = ctx + ([heading] if heading else [])
            sec_text = to_text([l for e in sec_els for l in render_lines(e)])
            pieces = _split_by_points(sec_els) if len(sec_text) > SPLIT_THRESHOLD else None
            if not pieces:
                add(anchor, sec_ref, title, sec_ctx, sec_text, sec_els[0], sec_els,
                    sec_label.replace(" ", "_") if sec_label else f"part{si}")
                continue
            # 2) split on top-level list items
            for i, (lab, els, lead) in enumerate(pieces):
                body = to_text([l for e in els for l in render_lines(e)])
                text = f"{lead}\n{body}" if lead else body
                p_ref = f"{sec_ref} point {lab}" if lab else sec_ref
                add(anchor, p_ref, title, sec_ctx + ([f"point {lab}"] if lab else ["(continued)"]),
                    text, els[0], els, f"{sec_label + '.' if sec_label else ''}{lab or f'rest{i}'}")
    return chunks


# ---------------------------------------------------------------------------
# Official Journal acts (recitals, Omnibus articles)
# ---------------------------------------------------------------------------

def parse_recitals(path: Path, doc: Document, act_label: str) -> list[Chunk]:
    soup = load(path)
    chunks = []
    for r in soup.find_all("div", id=re.compile(r"^rct_\d+$")):
        n = r["id"].split("_")[1]
        tds = r.find_all("td")
        text = to_text(render_lines(tds[-1] if tds else r))
        chunks.append(Chunk(
            chunk_id=f"{doc.doc_id}:rct_{n}", doc_id=doc.doc_id, seq=len(chunks),
            article_ref=f"Recital {n}" if doc.doc_id == "eu-ai-act-recitals" else f"Omnibus recital {n}",
            title=None, context=f"{act_label} › Recital ({n})", text=text,
            url=f"{doc.url}#{r['id']}", refs=extract_refs(text),
        ))
    return chunks
