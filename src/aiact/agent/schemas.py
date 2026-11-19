"""Structured model outputs (filled through tool calling, see llm.py) and the evidence format."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

RiskTier = Literal["prohibited", "high_risk", "transparency", "minimal", "unclear"]


class Source(BaseModel):
    """One piece of evidence shown to the writer under a short tag it cites."""
    tag: str                       # S1.. (corpus chunk), T1.. (applicability row), FI.. (country)
    kind: Literal["chunk", "table", "country"]
    label: str                     # shown in the answer's source list
    text: str                      # shown to the model
    url: str | None = None
    refs: list[str] = []           # AI Act refs it stands for (eval: was the gold article cited?)
    chunk_ids: list[str] = []


class Answer(BaseModel):
    """Answer to the user, built only from the numbered sources.

    Flat on purpose: qwen 9B garbles nested objects in tool calls (stringified, broken JSON), so
    each point is a string with its source tags inline, parsed by render.verify.
    """
    summary: str = Field(description="Direct answer in 1-3 plain-English sentences.")
    risk_tier: RiskTier | None = Field(
        default=None,
        description="Only for a described AI system: its probable AI Act risk category. null for general questions.")
    points: list[str] = Field(description=(
        "The key facts, obligations or steps, one per item, each ending with the tags of the sources "
        "that support it, e.g. 'Providers must tell people they are talking to an AI system [S1][T2]'."))
    caveats: list[str] = Field(
        default=[], description="Uncertainty, missing information, or things the sources do not cover.")


class Point(BaseModel):
    """A point after its inline tags were parsed and checked."""
    text: str
    sources: list[str] = []


class Verification(BaseModel):
    """Code check of an Answer against its sources (no model involved)."""
    n_points: int = 0
    unsupported: int = 0          # points left with no valid source tag
    unknown_tags: list[str] = []  # tags the model invented
    unverified_dates: list[str] = []  # dates in the answer that appear in no source


# ---------------------------------------------------------------------------
# Router + company profile
# ---------------------------------------------------------------------------

Intent = Literal["off_topic", "general", "company_case"]


class Route(BaseModel):
    """Route the user's latest message."""
    intent: Intent = Field(description=(
        "off_topic: not about the EU AI Act or AI regulation. "
        "general: a question about the law itself (articles, definitions, dates, obligations, "
        "authorities in general). "
        "company_case: the user describes their own company or AI system, or follows up on it, "
        "and asks what applies to them."))


HighRiskArea = Literal["biometrics", "critical_infrastructure", "education", "employment",
                       "essential_services", "law_enforcement", "migration_border",
                       "justice_democracy", "none", "unknown"]


class CompanyProfile(BaseModel):
    """What the user said about their company and its AI system. Only facts the user stated:
    use null / "unknown" / [] for anything they did not say. Do not guess."""
    system_description: str | None = Field(
        default=None, description=(
            "What the AI system does and for whom, in a few words, e.g. 'chatbot answering customer "
            "questions on the website' or 'tool ranking job applicants'. null only if the user did not "
            "mention any AI system."))
    built_or_bought: Literal["built", "bought", "both", "unknown"] = Field(
        default="unknown", description=(
            "built = the company developed the AI system, or offers it under its own name or brand "
            "(including a product built on top of another company's AI model or API); "
            "bought = it uses a ready-made AI product from another company as is; "
            "unknown = the user did not say which. Using a chatbot on your website does NOT say "
            "which: answer unknown unless the user says who made it."))
    interacts_with_people: bool | None = Field(
        default=None, description="The system talks or chats directly with people (chatbot, voice agent).")
    generates_content: bool | None = Field(
        default=None, description="The system generates synthetic images, audio, video or text.")
    publishes_generated_content: bool | None = Field(
        default=None, description=(
            "The company publishes AI-generated or manipulated images, audio or video (deepfakes), "
            "or AI-written text informing the public."))
    emotion_or_biometric: bool | None = Field(
        default=None, description="The system recognises emotions or categorises people from biometric data (face, voice, ...).")
    high_risk_area: HighRiskArea = Field(
        default="unknown", description=(
            "AI Act Annex III area the system is used in. employment = recruiting, screening CVs, "
            "evaluating, promoting or monitoring workers; essential_services = credit scoring, life or "
            "health insurance pricing, public benefits, emergency calls; education = admissions, "
            "grading, exam proctoring; biometrics = remote identification of people. "
            "none = clearly none of the Annex III areas (e.g. customer support, marketing content); "
            "unknown = cannot tell."))
    safety_component: bool | None = Field(
        default=None, description=(
            "The AI is part of a product covered by EU product-safety law (machinery, toys, medical "
            "devices, vehicles, lifts, ...)."))
    trains_general_purpose_model: bool | None = Field(
        default=None, description=(
            "The company trains and releases its own general-purpose AI model (not just using one through an API)."))
    countries_established: list[str] = Field(
        default=[], description="Countries where the company has offices, as English country names.")
    countries_users: list[str] = Field(
        default=[], description="Countries where the system's users or customers are, as English country names.")
