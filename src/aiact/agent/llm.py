"""Local chat models (Ollama) and structured calls.

Day-4 check of qwen3.5 on Ollama 0.20 (M4, 32 GB):
- JSON-schema `format` (LangChain's default `json_schema` method) is ignored when thinking is off:
  the model answers in prose.
- Thinking on: minutes per call even for a one-line routing question. Unusable here.
- Tool calling with thinking off: 7/7 routing cases right, ~5 s per call; profile extraction ~14 s.
So every structured call goes through tool calling (`method="function_calling"`), thinking off.
"""

from __future__ import annotations

import json
import logging
import os
import time
from functools import cache
from typing import TypeVar

from langchain_core.messages import AnyMessage
from langchain_ollama import ChatOllama
from pydantic import BaseModel, ValidationError

from aiact.embed import OLLAMA_URL

log = logging.getLogger("aiact.agent")

FAST_MODEL = os.environ.get("AIACT_FAST_MODEL", "qwen3.5:9b")      # router, profile
WRITER_MODEL = os.environ.get("AIACT_WRITER_MODEL", "qwen3.5:9b")  # final answer
NUM_CTX = int(os.environ.get("AIACT_NUM_CTX", "16384"))

T = TypeVar("T", bound=BaseModel)


class LLMError(RuntimeError):
    """The model did not return a valid structured output."""


@cache
def chat(model: str) -> ChatOllama:
    # temperature 0 overrides the Modelfile default (1.0) so eval runs are repeatable.
    return ChatOllama(model=model, base_url=OLLAMA_URL, reasoning=False, num_ctx=NUM_CTX,
                      temperature=0, keep_alive="30m")


def _destringify(x):
    """qwen sometimes sends a nested list/object as a JSON string ('[{"text": ...}]')."""
    if isinstance(x, dict):
        return {k: _destringify(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_destringify(v) for v in x]
    if isinstance(x, str) and x.strip()[:1] in ("[", "{"):
        try:
            return _destringify(json.loads(x))
        except json.JSONDecodeError:
            items = _salvage_list(x) if x.strip().startswith("[") else None
            return _destringify(items) if items else x
    return x


def _salvage_list(s: str) -> list | None:
    """Every top-level JSON value of a broken array string, e.g. '[{..}, {..}], {..}]' (seen
    from qwen: it closes the array, then adds one more element)."""
    dec, items, i = json.JSONDecoder(), [], 1
    while i < len(s):
        if s[i] in "{[\"":
            try:
                value, i = dec.raw_decode(s, i)
                items.append(value)
                continue
            except json.JSONDecodeError:
                return None
        i += 1
    return items or None


def structured(schema: type[T], messages: list[AnyMessage] | list[tuple[str, str]], *,
               model: str = FAST_MODEL, retries: int = 1) -> T:
    """Call `model` with `schema` as its only tool and validate the call; retry once on a bad output.

    Parses the tool call itself (rather than `with_structured_output`) to repair stringified
    nested fields before validation.
    """
    bound = chat(model).bind_tools([schema])
    error: Exception | None = None
    for attempt in range(retries + 1):
        t = time.perf_counter()
        msg = bound.invoke(messages)
        log.info("%s via %s: %.1fs (attempt %d)", schema.__name__, model,
                 time.perf_counter() - t, attempt + 1)
        calls = [c for c in msg.tool_calls if c["name"] == schema.__name__]
        if not calls:
            error = LLMError(f"no {schema.__name__} tool call; got: {str(msg.content)[:200]!r}")
            continue
        try:
            return schema.model_validate(_destringify(calls[0]["args"]))
        except ValidationError as e:
            error = e
    raise LLMError(f"{schema.__name__}: no valid output from {model}") from error
