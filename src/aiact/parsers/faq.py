"""Parser for the AI Act Service Desk FAQ (paginated ECL accordion pages)."""

from __future__ import annotations

import re
from pathlib import Path

from bs4 import BeautifulSoup

from aiact.models import Chunk, Document, clean_ws, extract_refs

# Items in these categories describe the Nov 2025 Omnibus *proposal*, not the adopted
# Regulation (EU) 2026/1744 (different dates). Excluded so they can't produce wrong answers.
# Re-check on every corpus refresh: remove from this set once the FAQ is updated.
EXCLUDED_CATEGORIES = {"Digital Omnibus"}


def _slug(s: str, n: int = 60) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:n].rstrip("-")


def parse_faq(paths: list[Path], doc: Document) -> list[Chunk]:
    chunks: list[Chunk] = []
    for path in sorted(paths, key=lambda p: int(re.search(r"(\d+)", p.stem).group(1))):
        soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
        for item in soup.select(".ecl-accordion__item"):
            toggle = item.select_one(".ecl-accordion__toggle")
            content = item.select_one(".ecl-accordion__content")
            if not toggle or not content:
                continue
            cat_el = toggle.select_one(".ecl-content-block__primary-meta-item")
            q_el = toggle.select_one("strong")
            category = clean_ws(cat_el.get_text(" ")) if cat_el else None
            question = clean_ws((q_el or toggle).get_text(" "))
            if category and set(category.split(" | ")) & EXCLUDED_CATEGORIES:
                continue
            answer = "\n".join(
                clean_ws(el.get_text(" ")) for el in content.find_all(["p", "li", "h3", "h4"])
                if clean_ws(el.get_text(" "))
            ) or clean_ws(content.get_text(" "))
            chunks.append(Chunk(
                chunk_id=f"{doc.doc_id}:{_slug(question)}", doc_id=doc.doc_id, seq=len(chunks),
                article_ref=f"Service Desk FAQ: {question}", title=question,
                context=" › ".join(filter(None, [doc.title, category, question])),
                text=f"Q: {question}\nA: {answer}", url=doc.url, refs=extract_refs(answer),
            ))
    return chunks
