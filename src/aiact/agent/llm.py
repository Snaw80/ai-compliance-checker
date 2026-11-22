"""Local chat models (Ollama) and structured calls.

Why tool calling (qwen3.5 on Ollama 0.20, M4, 32 GB):
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
# Seconds per call. Writer calls take ~40-70 s; without a timeout a wedged Ollama runner
# blocks forever (seen in an eval run: one request hung for over an hour).
TIMEOUT = float(os.environ.get("AIACT_LLM_TIMEOUT", "300"))
MAX_TOKENS = 2048  # longest real answer is ~1k tokens; caps runaway (repeating) generations

T = TypeVar("T", bound=BaseModel)


class LLMError(RuntimeError):
    """The model did not return a valid structured output."""


@cache
def chat(model: str) -> ChatOllama:
    # temperature 0 overrides the Modelfile default (1.0) so eval runs are repeatable.
    return ChatOllama(model=model, base_url=OLLAMA_URL, reasoning=False, num_ctx=NUM_CTX,
                      temperature=0, num_predict=MAX_TOKENS, keep_alive="30m",
                      client_kwargs={"timeout": TIMEOUT})


def _destringify(x):
    """qwen sometimes sends a nested list/object as a JSON string ('[{"text": ...}]')."""
    if isinstance(x, dict):
        return {k: _destringify(v) for k, v in x.items()}
    if isinstance(x, list):
        # qwen sometimes nests one item one level too deep: ['a', ['b']] -> ['a', 'b']
        flat = [w for v in x for w in (v if isinstance(v, list) else [v])]
        return [_destringify(v) for v in flat]
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
    nudge = ("user", f"Reply only by calling the {schema.__name__} tool.")
    error: Exception | None = None
    for attempt in range(retries + 1):
        t = time.perf_counter()
        # at temperature 0 the same request gives the same output: nudge the retry
        msg = bound.invoke(list(messages) + ([nudge] if attempt else []))
        log.info("%s via %s: %.1fs (attempt %d)", schema.__name__, model,
                 time.perf_counter() - t, attempt + 1)
        calls = [c for c in msg.tool_calls if c["name"] == schema.__name__]
        if not calls:
            error = LLMError(f"no {schema.__name__} tool call; got: {str(msg.content)[:200]!r}")
            continue
        try:
            return _validate(schema, _destringify(calls[0]["args"]))
        except ValidationError as e:
            error = e
    raise LLMError(f"{schema.__name__}: no valid output from {model}: {str(error)[:300]}") from error


def _validate(schema: type[T], args: dict) -> T:
    """Validate; if some optional fields are invalid (a null list, a value outside a Literal),
    drop them so they take their default ('unknown', []) rather than losing the whole output."""
    try:
        return schema.model_validate(args)
    except ValidationError as e:
        bad = {err["loc"][0] for err in e.errors() if err["loc"]}
        required = {n for n, f in schema.model_fields.items() if f.is_required()}
        if not bad or bad & required or not isinstance(args, dict):
            raise
        log.warning("%s: dropped invalid fields %s", schema.__name__, sorted(bad))
        return schema.model_validate({k: v for k, v in args.items() if k not in bad})
