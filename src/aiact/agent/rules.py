"""Deterministic decisions on the company profile (no model): role and clarifying questions.

The model only records what the user said (profile facts); code decides what follows from them,
so these rules can be unit-tested and the clarifying question doesn't depend on model mood.
"""

from __future__ import annotations

from typing import Literal

from aiact.agent.schemas import CompanyProfile

Role = Literal["provider", "deployer", "both", "unknown"]
MAX_CLARIFY = 2  # clarifying rounds per turn; after that, assume and say so


def role(p: CompanyProfile) -> Role:
    """AI Act role: building it / offering it under your own name makes you its provider
    (Art. 3(3)); using someone else's system makes you a deployer (Art. 3(4))."""
    return {"built": "provider", "bought": "deployer", "both": "both"}.get(p.built_or_bought, "unknown")


def clarify_question(p: CompanyProfile) -> str | None:
    """The one missing fact that changes the answer most, as a question; None if nothing is missing."""
    if not p.system_description and not _any_system_fact(p):
        return "What does your AI system do, and who uses it (your customers, your staff, the public)?"
    if role(p) == "unknown":
        what = _short(p.system_description) if p.system_description else "AI system"
        return (f"Did your company build the {what} itself (including on top of "
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
