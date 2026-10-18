"""OpenAI-compatible client: JSON output, one repair retry, timing and token counts."""

import json
import time
from typing import Literal

import openai
from pydantic import BaseModel, ValidationError

from parltopics.config import Settings

Status = Literal["ok", "parse_error", "llm_error"]
CHARS_PER_TOKEN = 4


class LLMCall(BaseModel):
    status: Status
    parsed: dict | None
    raw: str | None
    model: str
    latency_ms: int
    tok_in: int
    tok_out: int
    tokens_estimated: bool
    repaired: bool
    error: str | None = None
    messages: list[dict] = []


def extract_json(raw: str) -> dict | None:
    """First JSON object in the text, or None."""
    decoder = json.JSONDecoder()
    start = raw.find("{")
    while start != -1:
        try:
            obj, _ = decoder.raw_decode(raw, start)
        except json.JSONDecodeError:
            start = raw.find("{", start + 1)
            continue
        return obj if isinstance(obj, dict) else None
    return None


class LLMClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = openai.OpenAI(
            base_url=settings.llm_base_url, api_key=settings.llm_api_key or "none", timeout=120, max_retries=2
        )

    def _response_format(self, schema: type[BaseModel]) -> dict | None:
        mode = self.settings.llm_json_mode
        if mode == "json_schema":
            return {
                "type": "json_schema",
                "json_schema": {"name": schema.__name__, "schema": schema.model_json_schema(), "strict": True},
            }
        if mode == "json_object":
            return {"type": "json_object"}
        return None

    def _validate(self, raw: str, schema: type[BaseModel]) -> dict | None:
        obj = extract_json(raw)
        if obj is None:
            return None
        try:
            return schema.model_validate(obj).model_dump()
        except ValidationError:
            return None

    def complete_json(self, system: str, user: str, schema: type[BaseModel]) -> LLMCall:
        return self.complete_messages([{"role": "system", "content": system}, {"role": "user", "content": user}], schema)

    def complete_messages(self, messages: list[dict], schema: type[BaseModel]) -> LLMCall:
        """One JSON answer for a conversation; one repair retry if the JSON is invalid."""
        messages = list(messages)
        n_given = len(messages)
        response_format = self._response_format(schema)
        extra = {"response_format": response_format} if response_format else {}
        started = time.perf_counter()
        usage = {"tok_in": 0, "tok_out": 0, "tokens_estimated": False}
        raw: str | None = None

        def result(status: Status, parsed: dict | None = None, error: str | None = None) -> LLMCall:
            return LLMCall(
                status=status, parsed=parsed, raw=raw, model=self.settings.llm_name,
                latency_ms=int((time.perf_counter() - started) * 1000), repaired=len(messages) > n_given,
                error=error, messages=messages + ([{"role": "assistant", "content": raw}] if raw is not None else []),
                **usage,
            )

        for attempt in range(2):
            try:
                r = self.client.chat.completions.create(
                    model=self.settings.llm_name,
                    messages=messages,
                    temperature=self.settings.llm_temperature,
                    max_tokens=self.settings.llm_max_tokens,
                    **extra,
                )
            except openai.OpenAIError as e:
                return result("llm_error", error=f"{type(e).__name__}: {str(e)[:200]}")
            raw = r.choices[0].message.content or ""
            if r.usage:
                usage["tok_in"] += r.usage.prompt_tokens
                usage["tok_out"] += r.usage.completion_tokens
            else:
                usage["tokens_estimated"] = True
                usage["tok_in"] += sum(len(m["content"]) for m in messages) // CHARS_PER_TOKEN
                usage["tok_out"] += len(raw) // CHARS_PER_TOKEN
            parsed = self._validate(raw, schema)
            if parsed is not None:
                return result("ok", parsed)
            if attempt == 0:
                messages += [
                    {"role": "assistant", "content": raw},
                    {
                        "role": "user",
                        "content": "Return only valid JSON for this schema, nothing else: "
                        + json.dumps(schema.model_json_schema()),
                    },
                ]
        return result("parse_error", error="invalid JSON after one repair retry")
