"""Deterministic knowledge tables: applicability dates and country profiles.

Dates and countries are NOT retrieved by search and NOT inferred by the LLM. The agent reads
them from two hand-checked YAML files through these two functions:

    lookup_applicability(obligation_id | article=..., country="EU", on=date)
    get_country_profile("Finland" | "FI")

    uv run python -m aiact.tables "Art. 50(2)" --country FI
    uv run python -m aiact.tables --country Germany
"""

from __future__ import annotations

import argparse
import copy
import json
import re
from dataclasses import dataclass, field
from datetime import date
from functools import cache
from pathlib import Path

import yaml

from aiact.search import ref_matches

TABLES_DIR = Path(__file__).resolve().parents[2] / "tables"
APPLICABILITY_YAML = TABLES_DIR / "applicability.yaml"
COUNTRIES_YAML = TABLES_DIR / "countries.yaml"

ROLES = {"provider", "deployer", "importer", "distributor", "authorised_representative",
         "gpai_provider", "notified_body", "member_state", "commission", "any"}
LAW_STATUS = {"in_force", "adopted", "bill", "draft", "lapsed", "none", "unknown"}
AUTHORITY_STATUS = {"designated", "proposed", "unclear"}
PENALTY_STATUS = {"national_rules", "none", "unknown"}
SANDBOX_STATUS = {"operational", "pilot", "planned", "none", "unknown"}
CONFIDENCE = {"high", "medium", "low"}


class TableError(ValueError):
    """Bad table data, or a lookup the tables can't answer."""


# ---------------------------------------------------------------------------
# Applicability table
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Obligation:
    id: str
    obligation: str
    articles: tuple[str, ...]   # ranges already expanded: "Art. 6-8" -> Art. 6, Art. 7, Art. 8
    roles: tuple[str, ...]
    applies_from: date
    basis: str
    source_chunk_ids: tuple[str, ...]
    transitions: tuple[dict, ...] = ()
    notes: str | None = None
    default: bool = False


@dataclass
class Applicability:
    """Answer to "does X apply in <country> on <date>?"."""
    obligation: Obligation
    country: str                # "EU" or ISO2
    on: date
    status: str                 # applicable | not_yet_applicable | not_binding
    applies_from: date
    days_until: int | None      # days until applies_from when not yet applicable
    transitions: list[dict] = field(default_factory=list)  # + status: running | ended | None
    note: str | None = None

    def to_dict(self) -> dict:
        """JSON-ready dict (for the agent's tool output)."""
        o = self.obligation
        return _jsonable({
            "obligation_id": o.id, "obligation": o.obligation, "articles": list(o.articles),
            "roles": list(o.roles), "country": self.country, "on": self.on,
            "status": self.status, "applies_from": self.applies_from,
            "days_until": self.days_until, "basis": o.basis,
            "source_chunk_ids": list(o.source_chunk_ids), "transitions": self.transitions,
            "notes": o.notes, "note": self.note,
        })


_RANGE = re.compile(r"^Art\. (\d+)-(\d+)$")


def _expand(article: str) -> list[str]:
    m = _RANGE.match(article)
    if not m:
        return [article]
    lo, hi = int(m.group(1)), int(m.group(2))
    if lo >= hi:
        raise TableError(f"bad article range {article!r}")
    return [f"Art. {n}" for n in range(lo, hi + 1)]


def _require(row: dict, keys: tuple[str, ...], where: str) -> None:
    missing = [k for k in keys if k not in row]
    if missing:
        raise TableError(f"{where}: missing {', '.join(missing)}")


def _no_extra(row: dict, allowed: set[str], where: str) -> None:
    extra = set(row) - allowed
    if extra:
        raise TableError(f"{where}: unexpected field(s) {sorted(extra)}")


def _date(value, where: str) -> date:
    if not isinstance(value, date):
        raise TableError(f"{where}: expected a YYYY-MM-DD date, got {value!r}")
    return value


def _parse_obligation(row: dict) -> Obligation:
    where = f"obligation {row.get('id', '?')}"
    _require(row, ("id", "obligation", "articles", "roles", "applies_from", "basis",
                   "source_chunk_ids"), where)
    _no_extra(row, {"id", "obligation", "articles", "roles", "applies_from", "basis",
                    "source_chunk_ids", "transitions", "notes", "default"}, where)
    bad_roles = set(row["roles"]) - ROLES
    if bad_roles:
        raise TableError(f"{where}: unknown role(s) {sorted(bad_roles)}")
    articles = [a for art in row["articles"] for a in _expand(art)]
    for a in articles:
        if not a.startswith(("Art. ", "Annex ")):
            raise TableError(f"{where}: {a!r} is not an AI Act article or annex")
    transitions = []
    for t in row.get("transitions") or []:
        _require(t, ("applies_to", "effect"), f"{where} transition")
        _no_extra(t, {"applies_to", "effect", "deadline", "articles"}, f"{where} transition")
        if t.get("deadline") is not None:
            _date(t["deadline"], f"{where} transition deadline")
        transitions.append(dict(t))
    return Obligation(
        id=row["id"], obligation=" ".join(row["obligation"].split()),
        articles=tuple(articles), roles=tuple(row["roles"]),
        applies_from=_date(row["applies_from"], f"{where} applies_from"),
        basis=row["basis"], source_chunk_ids=tuple(row["source_chunk_ids"]),
        transitions=tuple(transitions), notes=row.get("notes"),
        default=bool(row.get("default", False)),
    )


@cache
def load_obligations(path: Path = APPLICABILITY_YAML) -> list[Obligation]:
    rows = [_parse_obligation(r) for r in yaml.safe_load(path.read_text())["obligations"]]
    seen: set[str] = set()
    for o in rows:
        if o.id in seen:
            raise TableError(f"duplicate obligation id {o.id!r}")
        seen.add(o.id)
    if sum(o.default for o in rows) > 1:
        raise TableError("more than one `default: true` obligation")
    return rows


def _match_article(rows: list[Obligation], article: str) -> list[Obligation]:
    """Rows covering `article`.

    - rows *inside* the query ('Art. 5' -> the 'Art. 5(1)(ba)' row) all match;
    - rows *containing* the query ('Art. 5(1)(f)' -> the 'Art. 5' row): only the most specific
      ones, so 'Art. 5(1)(ba)' gets the Omnibus row and not the general Art. 5 row;
    - nothing matches -> the default row (Art. 113 general date).
    """
    if not article.startswith(("Art. ", "Annex ")):
        raise TableError(f"{article!r} is not an AI Act article or annex (use 'Art. 50(1)', 'Annex III')")
    inside = [o for o in rows if any(ref_matches(a, article) for a in o.articles)]
    containing: dict[str, tuple[int, Obligation]] = {}
    for o in rows:
        lengths = [len(a) for a in o.articles if ref_matches(article, a)]
        if lengths:
            containing[o.id] = (max(lengths), o)
    best = max((n for n, _ in containing.values()), default=0)
    hits = inside + [o for n, o in containing.values() if n == best and o not in inside]
    if not hits:
        hits = [o for o in rows if o.default]
    return hits


def lookup_applicability(obligation: str | None = None, *, article: str | None = None,
                         country: str = "EU", on: date | None = None) -> list[Applicability]:
    """Applicability of AI Act obligations on date `on` (default today) in `country`.

    Select by `obligation` id, by `article` ('Art. 50(1)', 'Annex III'), or neither (all rows).
    `country` is "EU" (default) or an EU/EEA country name/ISO2. EU member states always get the
    EU dates; EEA countries get status "not_binding" until the Act is part of the EEA Agreement.
    """
    on = on or date.today()
    rows = load_obligations()
    if obligation is not None:
        rows = [o for o in rows if o.id == obligation]
        if not rows:
            raise TableError(f"unknown obligation {obligation!r}; known: "
                             + ", ".join(o.id for o in load_obligations()))
    if article is not None:
        rows = _match_article(rows, article)

    profile = None if country.strip().upper() == "EU" else get_country_profile(country)
    iso = profile["iso2"] if profile else "EU"
    results = []
    for o in rows:
        if profile and not profile["ai_act_binding"]:
            status, days, note = "not_binding", None, (
                f"{profile['name']} is an EEA country: the AI Act is not binding there until it is "
                "incorporated into the EEA Agreement. It still applies to the company's AI systems "
                f"placed on the market or used in the EU (from {o.applies_from.isoformat()}).")
        elif on >= o.applies_from:
            status, days, note = "applicable", None, None
        else:
            status, days, note = "not_yet_applicable", (o.applies_from - on).days, None
        transitions = [
            {**t, "status": None if t.get("deadline") is None
             else ("running" if on < t["deadline"] else "ended")}
            for t in o.transitions
        ]
        results.append(Applicability(o, iso, on, status, o.applies_from, days, transitions, note))
    return results


# ---------------------------------------------------------------------------
# Country profile table
# ---------------------------------------------------------------------------

_COUNTRY_KEYS = {"iso2", "name", "aliases", "membership", "ai_act_binding", "coverage_tier",
                 "national_law", "single_point_of_contact", "market_surveillance_authorities",
                 "notifying_authorities", "penalties", "sandbox", "national_extras", "sources",
                 "last_verified", "confidence", "open_questions"}
_AUTHORITY_KEYS = {"name", "scope", "status", "url"}


def _check_authority(a: dict, where: str) -> None:
    if not isinstance(a, dict):
        raise TableError(f"{where}: expected a mapping, got {a!r}")
    _require(a, ("name", "status"), where)
    _no_extra(a, _AUTHORITY_KEYS, where)  # catches unquoted commas in YAML flow mappings
    if a["status"] not in AUTHORITY_STATUS:
        raise TableError(f"{where}: status {a['status']!r} not in {sorted(AUTHORITY_STATUS)}")


def _check_enum(value, allowed: set[str], where: str) -> None:
    if value not in allowed:
        raise TableError(f"{where}: {value!r} not in {sorted(allowed)}")


def _check_country(row: dict, source_keys: set[str]) -> None:
    where = f"country {row.get('iso2', '?')}"
    _require(row, ("iso2", "name", "membership", "ai_act_binding", "coverage_tier",
                   "national_law", "market_surveillance_authorities", "sources",
                   "last_verified", "confidence"), where)
    _no_extra(row, _COUNTRY_KEYS, where)
    if not (isinstance(row["iso2"], str) and re.fullmatch(r"[A-Z]{2}", row["iso2"])):
        # YAML 1.1 reads an unquoted NO (Norway) as false: quote it
        raise TableError(f"{where}: iso2 must be a quoted 2-letter code, got {row['iso2']!r}")
    _check_enum(row["membership"], {"EU", "EEA"}, f"{where} membership")
    _check_enum(row["coverage_tier"], {"deep", "profile_only"}, f"{where} coverage_tier")
    _check_enum(row["confidence"], CONFIDENCE, f"{where} confidence")
    _check_enum(row["national_law"].get("status"), LAW_STATUS, f"{where} national_law.status")
    _no_extra(row["national_law"], {"status", "name", "ref", "in_force_from", "url", "notes"},
              f"{where} national_law")
    if row["national_law"].get("in_force_from") is not None:
        _date(row["national_law"]["in_force_from"], f"{where} national_law.in_force_from")
    _date(row["last_verified"], f"{where} last_verified")
    if not isinstance(row["ai_act_binding"], bool):
        raise TableError(f"{where}: ai_act_binding must be true/false")
    if row.get("single_point_of_contact") is not None:
        _check_authority(row["single_point_of_contact"], f"{where} single_point_of_contact")
    for key in ("market_surveillance_authorities", "notifying_authorities"):
        for a in row.get(key) or []:
            _check_authority(a, f"{where} {key}")
    if "penalties" in row:
        _check_enum(row["penalties"].get("status"), PENALTY_STATUS, f"{where} penalties.status")
    if "sandbox" in row:
        _check_enum(row["sandbox"].get("status"), SANDBOX_STATUS, f"{where} sandbox.status")
    for s in row["sources"]:
        if isinstance(s, str) and s not in source_keys:
            raise TableError(f"{where}: unknown source key {s!r}")
        if isinstance(s, dict):
            _require(s, ("title", "url"), f"{where} source")


@cache
def load_countries(path: Path = COUNTRIES_YAML) -> list[dict]:
    data = yaml.safe_load(path.read_text())
    shared = data.get("sources") or {}
    rows = data["countries"]
    for row in rows:
        _check_country(row, set(shared))
        # inline the shared sources so a profile is self-contained for the agent
        row["sources"] = [shared[s] if isinstance(s, str) else s for s in row["sources"]]
    isos = [r["iso2"] for r in rows]
    if len(isos) != len(set(isos)):
        raise TableError("duplicate iso2 in country table")
    return rows


def _key(s: str) -> str:
    s = s.strip().lower()
    return s[4:] if s.startswith("the ") else s


@cache
def _country_index() -> dict[str, dict]:
    index = {}
    for row in load_countries():
        for k in (row["iso2"], row["name"], *row.get("aliases", [])):
            index[_key(k)] = row
    return index


def get_country_profile(country: str) -> dict:
    """Profile of one EU/EEA country, by ISO2 code, English name or alias (case-insensitive)."""
    row = _country_index().get(_key(country))
    if row is None:
        raise TableError(f"{country!r} is not an EU/EEA country in the profile table")
    return copy.deepcopy(row)


# ---------------------------------------------------------------------------
# Helpers + CLI
# ---------------------------------------------------------------------------

def _jsonable(x):
    if isinstance(x, date):
        return x.isoformat()
    if isinstance(x, dict):
        return {k: _jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_jsonable(v) for v in x]
    return x


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("article", nargs="?", help="AI Act ref, e.g. 'Art. 50(2)' or 'Annex III'")
    p.add_argument("--obligation", help="obligation id from tables/applicability.yaml")
    p.add_argument("--country", default="EU")
    p.add_argument("--on", type=date.fromisoformat, help="date (YYYY-MM-DD), default today")
    args = p.parse_args()
    if args.article or args.obligation:
        out = [r.to_dict() for r in lookup_applicability(
            args.obligation, article=args.article, country=args.country, on=args.on)]
    else:
        out = _jsonable(get_country_profile(args.country))
    print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
