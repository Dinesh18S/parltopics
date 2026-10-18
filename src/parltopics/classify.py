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
    run_id: str
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
    inconsistent: bool
    evidence_retried: bool
    evidence_recovered: bool
    model: str
    source_sha256: str
    latency_ms: int
    tok_in: int
    tok_out: int
    tokens_estimated: bool
    repaired: bool
    error: str | None
    raw_json: str | None


def _check(out: dict, source: SourceText, cap: float):
    return check_prediction(out["label"], out["confidence"], out["evidence"], source.text, source.title,
                            title_only=source.title_only, cap=cap)


def classify_adhoc(
    llm: LLMClient, prompt: Prompt, source: SourceText, topic: Topic, title_only_cap: float, run_id: str
) -> Prediction:
    system, user = render_adhoc(prompt, topic, source.text, source.lang)
    call: LLMCall = llm.complete_json(system, user, AdhocOutput)
    out = call.parsed or {}
    latency, tok_in, tok_out = call.latency_ms, call.tok_in, call.tok_out
    check = _check(out, source, title_only_cap) if call.status == "ok" else None
    retried = recovered = False
    if check is not None and check.status == "evidence_failed" and prompt.retry:
        retried = True
        retry = llm.complete_messages(call.messages + [{"role": "user", "content": prompt.retry.strip()}], AdhocOutput)
        latency, tok_in, tok_out = latency + retry.latency_ms, tok_in + retry.tok_in, tok_out + retry.tok_out
        if retry.status == "ok":
            retry_check = _check(retry.parsed, source, title_only_cap)
            if retry_check.status == "ok":
                call, out, check, recovered = retry, retry.parsed, retry_check, True
    return Prediction(
        run_id=run_id,
        affair_id=source.affair_id,
        lang=source.lang,
        topic=topic.name,
        label=out.get("label"),
        confidence=check.confidence if check else out.get("confidence"),
        evidence=out.get("evidence", ""),
        rationale=out.get("rationale", ""),
        status=check.status if check else call.status,
        verify_ok=check.verify_ok if check else False,
        verify_method=check.verify_method if check else "not_run",
        verify_score=check.score if check else 0.0,
        inconsistent=check.inconsistent if check else False,
        evidence_retried=retried,
        evidence_recovered=recovered,
        model=call.model,
        source_sha256=source.sha256,
        latency_ms=latency,
        tok_in=tok_in,
        tok_out=tok_out,
        tokens_estimated=call.tokens_estimated,
        repaired=call.repaired,
        error=call.error,
        raw_json=call.raw,
    )
