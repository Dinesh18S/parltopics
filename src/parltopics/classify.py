"""One affair × one topic → verified Prediction."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, create_model

from parltopics.llm import LLMCall, LLMClient
from parltopics.prompts import Prompt, render_adhoc, render_standard
from parltopics.schemes import Scheme
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


NONE_OTHER = "NONE_OTHER"


def standard_output_model(codes: list[str]) -> type[BaseModel]:
    """JSON schema for standard mode with the scheme's codes as an enum (enforced server-side)."""
    code_type = Literal[tuple(codes + [NONE_OTHER])]  # type: ignore[valid-type]
    label = create_model("StandardLabel", __config__=ConfigDict(extra="forbid"),
                         code=(code_type, ...), confidence=(float, Field(ge=0, le=1)), evidence=(str, ...))
    return create_model("StandardOutput", __config__=ConfigDict(extra="forbid"),
                        labels=(list[label], Field(min_length=1, max_length=3)), rationale=(str, ...))


def classify_standard(
    llm: LLMClient, prompt: Prompt, source: SourceText, scheme: Scheme, fallback_lang: str, title_only_cap: float,
    run_id: str, max_tokens: int | None = None,
) -> list[dict]:
    """One affair × one scheme → one record per chosen category (label = source id). Each label's evidence is
    verified on its own; NONE_OTHER must stand alone (else dropped and flagged)."""
    system, user = render_standard(prompt, scheme, source.text, source.lang, fallback_lang)
    call = llm.complete_json(system, user, standard_output_model([c.code for c in scheme.categories]), max_tokens)
    base = {"run_id": run_id, "affair_id": source.affair_id, "lang": source.lang, "topic": scheme.name,
            "model": call.model, "source_sha256": source.sha256, "tokens_estimated": call.tokens_estimated,
            "repaired": call.repaired, "raw_json": call.raw, "inconsistent": False, "evidence_retried": False,
            "evidence_recovered": False, "latency_ms": call.latency_ms, "tok_in": call.tok_in, "tok_out": call.tok_out}
    if call.status != "ok":
        return [base | {"label": None, "status": call.status, "error": call.error, "confidence": None, "evidence": "",
                        "rationale": "", "verify_ok": False, "verify_method": "not_run", "verify_score": 0.0}]
    labels = list({lab["code"]: lab for lab in reversed(call.parsed["labels"])}.values())[::-1]  # first occurrence wins
    note = None
    if any(lab["code"] == NONE_OTHER for lab in labels) and len(labels) > 1:
        labels = [lab for lab in labels if lab["code"] != NONE_OTHER]
        note = "NONE_OTHER mixed with codes: dropped"
    by_code = scheme.by_code()
    records = []
    for rank, lab in enumerate(labels, start=1):
        if lab["code"] == NONE_OTHER:
            check_label, source_id = "NONE_OTHER", NONE_OTHER
        elif lab["code"] in by_code:
            check_label, source_id = "match", by_code[lab["code"]].source_id
        else:
            records.append(base | {"label": None, "scheme_code": lab["code"], "rank": rank, "status": "invalid_label",
                                   "confidence": lab["confidence"], "evidence": lab["evidence"], "rationale": "",
                                   "verify_ok": False, "verify_method": "not_run", "verify_score": 0.0,
                                   "error": f"unknown code {lab['code']}"})
            continue
        check = check_prediction(check_label, lab["confidence"], lab["evidence"], source.text, source.title,
                                 title_only=source.title_only, cap=title_only_cap)
        records.append(base | {
            "label": source_id, "scheme_code": lab["code"], "rank": rank, "confidence": check.confidence,
            "evidence": lab["evidence"], "rationale": call.parsed["rationale"], "status": check.status,
            "verify_ok": check.verify_ok, "verify_method": check.verify_method, "verify_score": check.score,
            "error": note,
        } | ({} if rank == 1 else {"latency_ms": 0, "tok_in": 0, "tok_out": 0}))
    return records
