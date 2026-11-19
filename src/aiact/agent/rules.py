"""Deterministic decisions (no model): role, clarifying questions, which obligation rows apply,
which countries to cover.

The model only records what the user said (profile facts); code decides what follows from them,
so these rules can be unit-tested and the answer's dates and countries never depend on the model.
"""

from __future__ import annotations

import re
from typing import Literal

from aiact.agent.schemas import CompanyProfile, RiskTier
from aiact.tables import TableError, get_country_profile, load_countries, lookup_applicability

Role = Literal["provider", "deployer", "both", "unknown"]
MAX_CLARIFY = 2  # clarifying rounds per turn (each topic at most once); after that, assume and say so


def role(p: CompanyProfile) -> Role:
    """AI Act role: building it / offering it under your own name makes you its provider
    (Art. 3(3)); using someone else's system makes you a deployer (Art. 3(4))."""
    return {"built": "provider", "bought": "deployer", "both": "both"}.get(p.built_or_bought, "unknown")


def clarify_topic(p: CompanyProfile, asked: list[str] = ()) -> str | None:
    """The missing fact that changes the answer most ('system', then 'role'), skipping topics already
    asked this turn: if the user could not answer, asking again only annoys them."""
    missing = []
    if not p.system_description and not _any_system_fact(p):
        missing.append("system")
    if role(p) == "unknown":
        missing.append("role")
    return next((t for t in missing if t not in asked), None)


def clarify_question(p: CompanyProfile, asked: list[str] = ()) -> str | None:
    """The clarifying question for `clarify_topic`; None if nothing (new) is missing."""
    topic = clarify_topic(p, asked)
    if topic == "system":
        return "What does your AI system do, and who uses it (your customers, your staff, the public)?"
    if topic == "role":
        what = f"AI system ({_short(p.system_description)})" if p.system_description else "AI system"
        return (f"Did your company build this {what} itself (including on top of "
                "another company's AI model or API, or sold under your own name), or do you use a "
                "ready-made product from another company as is? This decides whether you are its "
                "provider or its deployer, which changes your obligations.")
    return None


def profile_summary(p: CompanyProfile) -> str:
    """Plain-text profile for prompts."""
    facts = {
        "AI system": p.system_description or "not described",
        "Role": {"provider": "provider (built it / offers it under its own name)",
                 "deployer": "deployer (uses a ready-made system from another company)",
                 "both": "provider and deployer",
                 "unknown": "unknown"}[role(p)],
        "Talks directly with people": p.interacts_with_people,
        "Generates images/audio/video/text": p.generates_content,
        "Publishes AI-generated content": p.publishes_generated_content,
        "Emotion recognition / biometric categorisation": p.emotion_or_biometric,
        "Annex III area": p.high_risk_area,
        "Part of a regulated product": p.safety_component,
        "Trains its own general-purpose model": p.trains_general_purpose_model,
        "Offices in": ", ".join(p.countries_established) or None,
        "Users in": ", ".join(p.countries_users) or None,
    }
    show = {True: "yes", False: "no", None: "not stated"}
    return "\n".join(f"- {k}: {show.get(v, v) if not isinstance(v, str) else v}" for k, v in facts.items())


def _any_system_fact(p: CompanyProfile) -> bool:
    return any(v is not None for v in (
        p.interacts_with_people, p.generates_content, p.publishes_generated_content,
        p.emotion_or_biometric, p.safety_component, p.trains_general_purpose_model,
    )) or p.high_risk_area != "unknown"


def _short(description: str) -> str:
    d = description.strip().rstrip(".")
    d = d[0].lower() + d[1:] if d[:1].isupper() and not d[1:2].isupper() else d
    words = d.split()
    return " ".join(words[:8]) if words else "AI system"


# ---------------------------------------------------------------------------
# Which rows of tables/applicability.yaml apply (decision B: profile facts -> rows by code)
# ---------------------------------------------------------------------------

def obligations_for_profile(p: CompanyProfile) -> tuple[list[dict], list[str]]:
    """Obligation rows for a company -> ([{id, reason}], caveats)."""
    r = role(p)
    provider, deployer = r in ("provider", "both", "unknown"), r in ("deployer", "both", "unknown")
    out: list[dict] = []
    caveats: list[str] = []

    def add(oid: str, reason: str) -> None:
        if all(o["id"] != oid for o in out):
            out.append({"id": oid, "reason": reason})

    if risk_tier(p) == "prohibited":
        # a banned practice: the other obligations (high-risk, transparency) would only distract from
        # the answer, which is "you may not offer/use it" (the writer still sees the Art. 5 exceptions)
        add("prohibited-practices", "emotion recognition at work or in education is prohibited (Art. 5(1)(f))")
        add("ai-literacy", "applies to every provider and deployer of an AI system")
        return out, caveats
    if p.trains_general_purpose_model:
        add("gpai-model-obligations", "you train and release a general-purpose AI model")
    if p.emotion_or_biometric:
        add("prohibited-practices", "emotion recognition at work or in education, and some biometric "
                                    "categorisation, are prohibited")
    if p.high_risk_area not in ("none", "unknown"):
        area = p.high_risk_area.replace("_", " ")
        add("high-risk-annex-iii", f"the system is used in an Annex III area ({area})")
        if provider:
            add("high-risk-conformity-procedures", "providers of high-risk systems must pass conformity assessment")
    if p.safety_component:
        add("high-risk-annex-i", "the AI is part of a product covered by EU product-safety law")
    if p.interacts_with_people:
        if provider:
            add("art50-chatbot-disclosure", "your system talks directly with people and you are its provider")
        else:
            add("art50-chatbot-disclosure", "the duty is on the provider (your vendor); you become the "
                                            "provider if you offer the system under your own name")
    if p.generates_content and provider:
        add("art50-content-marking", "your system generates synthetic content and you are its provider")
    if p.emotion_or_biometric and deployer:
        add("art50-emotion-biometric-notice", "you use emotion recognition or biometric categorisation")
    if p.publishes_generated_content:
        add("art50-deepfake-disclosure", "you publish AI-generated or manipulated content")
    add("ai-literacy", "applies to every provider and deployer of an AI system")

    if p.high_risk_area == "unknown" and not p.safety_component:
        caveats.append("It is not clear from your description whether the system is used in a high-risk "
                       "area (Annex III: hiring, credit, education, ...). If it is, more obligations apply.")
    return out, caveats


def risk_tier(p: CompanyProfile) -> RiskTier:
    """Probable risk category from the profile facts (shown as 'probable', never as a verdict)."""
    if p.emotion_or_biometric and p.high_risk_area in ("employment", "education"):
        return "prohibited"  # Art. 5(1)(f): emotion recognition at work / in education
    if p.high_risk_area not in ("none", "unknown") or p.safety_component:
        return "high_risk"
    if p.interacts_with_people or p.generates_content or p.publishes_generated_content or p.emotion_or_biometric:
        return "transparency"
    return "unclear" if p.high_risk_area == "unknown" else "minimal"


_LAW = "eu-ai-act-consolidated:"
_PROVIDER_HR = [_LAW + "art_16"]  # obligations of providers of high-risk systems
_DEPLOYER_HR = [_LAW + f"art_26:{n}" for n in (1, 2, 4, 5, 6, 7)] + [_LAW + "art_27:1"]  # Art. 26 + FRIA
# The core duties to show the writer for a selected obligation, by role. The table rows only cite the
# date articles; without this the writer gets whatever search returns (e.g. a provider's quality
# management system, Art. 17, for a company that only uses a high-risk system).
CORE_LAW = {
    "high-risk-annex-iii": {"provider": _PROVIDER_HR, "deployer": _DEPLOYER_HR},
    "high-risk-annex-i": {"provider": _PROVIDER_HR, "deployer": _DEPLOYER_HR},
}


def core_chunks(obligation_id: str, p: CompanyProfile) -> list[str]:
    """Chunk ids of the core law for an obligation and the company's role (both roles if unclear)."""
    by_role = CORE_LAW.get(obligation_id, {})
    r = role(p)
    if r in ("provider", "deployer"):
        return list(by_role.get(r, []))
    # both / unknown: the provider's list and the first deployer duties, to keep room for search hits
    return by_role.get("provider", []) + by_role.get("deployer", [])[:4]


def obligations_for_refs(named: list[str], retrieved: list[str], limit: int = 4) -> list[dict]:
    """Obligation rows for a general question: rows of the articles `named` in the question, then of
    the top `retrieved` law chunks. The catch-all row (general date) only for named articles."""
    out: list[dict] = []
    for ref, is_named in [(r, True) for r in named] + [(r, False) for r in retrieved]:
        if not ref or not ref.startswith(("Art.", "Annex")):
            continue
        try:
            rows = lookup_applicability(article=ref)
        except TableError:
            continue
        for row in rows:
            o = row.obligation
            if (o.default and not is_named) or any(x["id"] == o.id for x in out):
                continue
            out.append({"id": o.id, "reason": f"covers {ref}"})
    return out[:limit]


# ---------------------------------------------------------------------------
# Jurisdictions (decision D)
# ---------------------------------------------------------------------------

MAX_COUNTRIES = 5


def resolve_countries(names: list[str]) -> tuple[list[str], list[str]]:
    """Country names -> (EU/EEA ISO2 codes, max MAX_COUNTRIES; caveats)."""
    isos: list[str] = []
    caveats: list[str] = []
    outside: list[str] = []
    for name in names:
        try:
            iso = get_country_profile(name)["iso2"]
        except TableError:
            if name.strip() and name.strip() not in outside:
                outside.append(name.strip())
            continue
        if iso not in isos:
            isos.append(iso)
    if outside:
        caveats.append(f"{', '.join(outside)}: outside the EU/EEA, so no national AI Act rules there. The AI "
                       "Act still applies to a system placed on the EU market or whose output is used in "
                       "the EU (Art. 2(1)).")
    if len(isos) > MAX_COUNTRIES:
        caveats.append(f"Country details are shown for the first {MAX_COUNTRIES} countries only.")
        isos = isos[:MAX_COUNTRIES]
    return isos, caveats


def countries_in_text(text: str) -> list[str]:
    """EU/EEA countries named in free text (names and aliases, not ISO codes: 'IT', 'NO' are words)."""
    found: list[tuple[int, str]] = []
    for row in load_countries():
        for name in (row["name"], *row.get("aliases", [])):
            if len(name) > 2 and (m := re.search(rf"\b{re.escape(name)}\b", text, re.I)):
                found.append((m.start(), row["name"]))
                break
    return [n for _, n in sorted(found)]
