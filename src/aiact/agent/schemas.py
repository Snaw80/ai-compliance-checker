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
