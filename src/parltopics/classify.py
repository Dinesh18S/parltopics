"""One affair × one topic → verified Prediction."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from parltopics.llm import LLMCall, LLMClient
from parltopics.prompts import Prompt, render_adhoc
from parltopics.sources.assemble import SourceText
from parltopics.topics import Topic
from parltopics.verify import check_prediction


class AdhocOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: Literal["match", "no_match", "abstain"]
    confidence: float = Field(ge=0, le=1)
    evidence: str
    rationale: str


class Prediction(BaseModel):
    affair_id: int
    lang: str
    topic: str
    label: str | None
    confidence: float | None
    evidence: str
    rationale: str
    status: str
    verify_ok: bool
    verify_method: str
    verify_score: float
    model: str
    prompt_version: str
    prompt_sha: str
    source_sha256: str
    latency_ms: int
    tok_in: int
    tok_out: int
    tokens_estimated: bool
    repaired: bool
    error: str | None
    raw_json: str | None


def classify_adhoc(
    llm: LLMClient, prompt: Prompt, source: SourceText, topic: Topic, title_only_cap: float
) -> Prediction:
    system, user = render_adhoc(prompt, topic, source.text, source.lang)
    call: LLMCall = llm.complete_json(system, user, AdhocOutput)
    out = call.parsed or {}
    status, confidence = call.status, out.get("confidence")
    verify_ok, verify_method, verify_score = False, "not_run", 0.0
    if call.status == "ok":
        check = check_prediction(
            out["label"], out["confidence"], out["evidence"], source.text, source.title,
            title_only=source.title_only, cap=title_only_cap,
        )
        status, confidence = check.status, check.confidence
        verify_ok, verify_method, verify_score = check.verify_ok, check.verify_method, check.score
    return Prediction(
        affair_id=source.affair_id,
        lang=source.lang,
        topic=topic.name,
        label=out.get("label"),
        confidence=confidence,
        evidence=out.get("evidence", ""),
        rationale=out.get("rationale", ""),
        status=status,
        verify_ok=verify_ok,
        verify_method=verify_method,
        verify_score=verify_score,
        model=call.model,
        prompt_version=prompt.version,
        prompt_sha=prompt.sha,
        source_sha256=source.sha256,
        latency_ms=call.latency_ms,
        tok_in=call.tok_in,
        tok_out=call.tok_out,
        tokens_estimated=call.tokens_estimated,
        repaired=call.repaired,
        error=call.error,
        raw_json=call.raw,
    )
