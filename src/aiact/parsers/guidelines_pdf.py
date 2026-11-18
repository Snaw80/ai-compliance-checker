"""Parser for Commission guideline PDFs with numbered paragraphs: '(1) ...', '(2) ...'.

Layout rules (checked on the Art. 50 guidelines, C(2026) 7702):
- body text: 12 pt; headings: 12-13 pt lines starting with '1.', '2.4.1.' ...
- footnotes: 10 pt at the bottom of the page -> dropped
- page numbers: 8 pt -> dropped; tables: 11 pt -> kept as text in the paragraph
- pages before the first numbered heading (cover, table of contents) are skipped
"""

from __future__ import annotations

import re
from pathlib import Path

import pymupdf

from aiact.models import Chunk, Document, clean_ws, extract_refs

HEADING = re.compile(r"^(\d+(?:\.\d+)*)\.\s+(\S.*)$")
PARA = re.compile(r"^\((\d+)\)\s+(.*)$")
FOOTNOTE_MAX_SIZE = 10.5
TOC_LINE = re.compile(r"\.{5,}\s*\d+\s*$")


def _lines(pdf: pymupdf.Document):
    """Yield (size, text) for body lines in reading order."""
    for page in pdf:
        for block in page.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                spans = line["spans"]
                visible = [s for s in spans if s["text"].strip()]
                if not visible:
                    continue
                size = max(s["size"] for s in visible)
                if size <= FOOTNOTE_MAX_SIZE:  # footnotes and page numbers
                    continue
                yield size, clean_ws("".join(s["text"] for s in spans))


def parse_numbered_pdf(path: Path, doc: Document, short_name: str) -> list[Chunk]:
    pdf = pymupdf.open(path)
    chunks: list[Chunk] = []
    headings: dict[int, str] = {}  # depth -> heading
    started = False
    cur_num: str | None = None
    cur_lines: list[str] = []
    cur_headings: list[str] = []

    def flush() -> None:
        if cur_num is None:
            return
        text = "\n".join(_join_lines(cur_lines))
        chunks.append(Chunk(
            chunk_id=f"{doc.doc_id}:para_{cur_num}", doc_id=doc.doc_id, seq=len(chunks),
            article_ref=f"{short_name}, para. {cur_num}",
            title=cur_headings[-1] if cur_headings else None,
            context=" › ".join([doc.title, *cur_headings, f"paragraph ({cur_num})"]),
            text=f"({cur_num}) {text}", url=doc.url, refs=extract_refs(text),
        ))

    for size, line in _lines(pdf):
        if TOC_LINE.search(line):
            continue
        h = HEADING.match(line)
        if h and size >= 11.5 and not line.endswith((";", ",")) and len(line) < 160:
            started = True
            depth = h.group(1).count(".") + 1
            headings = {d: t for d, t in headings.items() if d < depth}
            headings[depth] = f"{h.group(1)}. {clean_ws(h.group(2))}"
            continue
        if not started:
            continue
        p = PARA.match(line)
        expected = 1 if cur_num is None else int(cur_num) + 1
        if p and size >= 11.5 and int(p.group(1)) == expected:
            flush()
            cur_num, cur_lines = p.group(1), [p.group(2)]
            cur_headings = [headings[d] for d in sorted(headings)]
        elif cur_num is not None:
            cur_lines.append(line)
    flush()
    return chunks


def _join_lines(lines: list[str]) -> list[str]:
    """Re-flow PDF lines into paragraphs; keep bullet items ('- ...') on their own line."""
    out: list[str] = []
    for line in lines:
        if line.startswith(("- ", "• ", "– ")) or not out:
            out.append(line)
        elif out[-1].endswith("-") and not out[-1].endswith(" -"):
            out[-1] = out[-1][:-1] + line  # hyphenated word split across lines
        else:
            out[-1] = f"{out[-1]} {line}"
    return [clean_ws(o) for o in out]
