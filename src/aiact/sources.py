"""Source registry and downloader.

EUR-Lex itself blocks scripted downloads (it answers HTTP 202 with an empty body: a bot
challenge), so EU law is fetched from the Publications Office "Cellar" endpoint, which
serves the same XHTML by CELEX number. To find newer consolidated versions:

    uv run python -m aiact.sources --check-consolidated
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import httpx

from aiact.models import Document

RAW_DIR = Path("data/raw")
CORPUS_VERSION = "2026-11-18"

CELLAR = "https://publications.europa.eu/resource/celex/{celex}"
EURLEX = "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:{celex}"
FAQ_URL = "https://ai-act-service-desk.ec.europa.eu/en/faq"
UA = {"User-Agent": "Mozilla/5.0 (compatible; aiact-corpus/0.1)"}


@dataclass(frozen=True)
class Source:
    doc: Document
    fetch_url: str
    filename: str
    headers: dict[str, str]


AI_ACT_CONSOLIDATED_CELEX = "02024R1689-20260727"

SOURCES: dict[str, Source] = {
    s.doc.doc_id: s
    for s in [
        Source(
            Document(
                doc_id="eu-ai-act-consolidated",
                title="AI Act, Regulation (EU) 2024/1689 (consolidated text, 27 July 2026)",
                jurisdiction="EU", doc_type="regulation", status="in_force", binding=True,
                language="en", url=EURLEX.format(celex=AI_ACT_CONSOLIDATED_CELEX),
                published=date(2024, 7, 12), version_date=date(2026, 7, 27),
            ),
            CELLAR.format(celex=AI_ACT_CONSOLIDATED_CELEX),
            "ai-act-consolidated-20260727.xhtml",
            {"Accept": "application/xhtml+xml", "Accept-Language": "eng"},
        ),
        Source(
            Document(
                doc_id="eu-ai-act-recitals",
                title="AI Act, Regulation (EU) 2024/1689 (recitals, original Official Journal text)",
                jurisdiction="EU", doc_type="regulation", status="in_force", binding=True,
                language="en", url=EURLEX.format(celex="32024R1689"),
                published=date(2024, 7, 12),
            ),
            CELLAR.format(celex="32024R1689"),
            "ai-act-original-2024-1689.xhtml",
            {"Accept": "application/xhtml+xml", "Accept-Language": "eng"},
        ),
        Source(
            Document(
                doc_id="eu-digital-omnibus-ai",
                title="Digital Omnibus on AI, Regulation (EU) 2026/1744",
                jurisdiction="EU", doc_type="amending_regulation", status="in_force", binding=True,
                language="en", url=EURLEX.format(celex="32026R1744"),
                published=date(2026, 7, 24),
            ),
            CELLAR.format(celex="32026R1744"),
            "omnibus-2026-1744.xhtml",
            {"Accept": "application/xhtml+xml", "Accept-Language": "eng"},
        ),
        Source(
            Document(
                doc_id="eu-guidelines-art50",
                title="Commission Guidelines on the transparency obligations under Article 50 AI Act, C(2026) 7702",
                jurisdiction="EU", doc_type="guideline", status="final", binding=False,
                language="en",
                url="https://digital-strategy.ec.europa.eu/en/library/guidelines-transparency-obligations-providers-and-deployers-ai-systems",
                published=date(2026, 11, 5),
            ),
            "https://ec.europa.eu/newsroom/dae/redirection/document/131215",
            "guidelines-art50-en.pdf",
            UA,
        ),
        Source(
            Document(
                doc_id="eu-service-desk-faq",
                title="AI Act Service Desk: Frequently Asked Questions",
                jurisdiction="EU", doc_type="faq", status="final", binding=False,
                language="en", url=FAQ_URL,
            ),
            FAQ_URL,
            "faq-page-{page}.html",  # paginated, see download_faq()
            UA,
        ),
    ]
}


def _get(client: httpx.Client, url: str, headers: dict[str, str]) -> bytes:
    r = client.get(url, headers=headers, follow_redirects=True, timeout=60)
    r.raise_for_status()
    if not r.content:
        raise RuntimeError(f"Empty response from {url} (bot challenge?)")
    return r.content


def download_faq(client: httpx.Client, src: Source, max_pages: int = 20) -> list[Path]:
    paths = []
    for page in range(max_pages):
        body = _get(client, f"{src.fetch_url}?page={page}", src.headers)
        if b"ecl-accordion__item" not in body:
            break
        p = RAW_DIR / src.filename.format(page=page)
        p.write_bytes(body)
        paths.append(p)
    return paths


def download_all(force: bool = False) -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    with httpx.Client() as client:
        for doc_id, src in SOURCES.items():
            if doc_id == "eu-service-desk-faq":
                if force or not list(RAW_DIR.glob("faq-page-*.html")):
                    paths = download_faq(client, src)
                    print(f"  {doc_id}: {len(paths)} pages")
                continue
            path = RAW_DIR / src.filename
            if path.exists() and not force:
                print(f"  {doc_id}: cached ({path})")
                continue
            path.write_bytes(_get(client, src.fetch_url, src.headers))
            print(f"  {doc_id}: {path.stat().st_size // 1024} KB")


def check_consolidated() -> list[str]:
    """List all consolidated versions of the AI Act known to the Publications Office."""
    query = """PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
SELECT DISTINCT ?celex WHERE { ?w cdm:resource_legal_id_celex ?celex .
FILTER(STRSTARTS(STR(?celex), "02024R1689")) } ORDER BY ?celex"""
    r = httpx.get("https://publications.europa.eu/webapi/rdf/sparql",
                  params={"query": query}, headers={"Accept": "text/csv"}, timeout=60)
    r.raise_for_status()
    return [line.strip('"') for line in r.text.splitlines()[1:] if line]


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="re-download cached files")
    ap.add_argument("--check-consolidated", action="store_true")
    a = ap.parse_args()
    if a.check_consolidated:
        versions = check_consolidated()
        print("\n".join(versions))
        latest = versions[-1] if versions else None
        if latest and latest != AI_ACT_CONSOLIDATED_CELEX:
            print(f"NEWER VERSION AVAILABLE: {latest} (corpus uses {AI_ACT_CONSOLIDATED_CELEX})")
            sys.exit(1)
    else:
        download_all(force=a.force)
