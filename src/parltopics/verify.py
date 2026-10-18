"""Evidence verification: pure functions, no model calls."""

import re
import unicodedata

from pydantic import BaseModel
from rapidfuzz import fuzz

FUZZY_MIN_CHARS = 25
FUZZY_MIN_SCORE = 92.0
SHORT_MIN_CHARS = 15
NO_EVIDENCE_LABELS = {"no_match", "abstain", "NONE_OTHER"}
CONSISTENCY_THRESHOLD = 0.5

_QUOTES = re.compile(r"[\"'«»‹›“”„‟‘’‚‛′″`´]")
_DASHES = re.compile(r"[‐-―−]")
_HYPHENATION = re.compile(r"(\w)-\s+(\w)")
_SPACE_AROUND_QUOTE = re.compile(r'\s*"\s*')


class VerifyResult(BaseModel):
    ok: bool
    method: str  # exact | fuzzy | not_found | too_short | empty
    score: float
    span: tuple[int, int] | None  # offsets in the normalised text


class Check(BaseModel):
    status: str  # ok | evidence_failed
    verify_ok: bool
    verify_method: str
    score: float
    confidence: float
    inconsistent: bool


def is_inconsistent(label: str, confidence: float) -> bool:
    """Confidence is P(topic): a match below 0.5 or a no_match above 0.5 contradicts its label."""
    if label == "match":
        return confidence < CONSISTENCY_THRESHOLD
    if label == "no_match":
        return confidence > CONSISTENCY_THRESHOLD
    return False


def normalize(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).replace("­", "")
    s = _QUOTES.sub('"', s)
    s = _DASHES.sub("-", s)
    s = _HYPHENATION.sub(r"\1\2", s)
    s = re.sub(r"\s+", " ", s.lower())
    return _SPACE_AROUND_QUOTE.sub('"', s).strip()


def verify_evidence(evidence: str, text: str, title: str = "") -> VerifyResult:
    ev = normalize(evidence)
    if not ev:
        return VerifyResult(ok=False, method="empty", score=0, span=None)
    if len(ev) < SHORT_MIN_CHARS and ev != normalize(title):
        return VerifyResult(ok=False, method="too_short", score=0, span=None)
    norm_text = normalize(text)
    start = norm_text.find(ev)
    if start != -1:
        return VerifyResult(ok=True, method="exact", score=100, span=(start, start + len(ev)))
    if len(ev) >= FUZZY_MIN_CHARS:
        best = fuzz.partial_ratio_alignment(ev, norm_text)
        if best is not None and best.score >= FUZZY_MIN_SCORE:
            return VerifyResult(ok=True, method="fuzzy", score=best.score, span=(best.dest_start, best.dest_end))
        score = best.score if best is not None else 0
        return VerifyResult(ok=False, method="not_found", score=score, span=None)
    return VerifyResult(ok=False, method="not_found", score=0, span=None)


def check_prediction(
    label: str, confidence: float, evidence: str, text: str, title: str, *, title_only: bool, cap: float
) -> Check:
    """Turn a model label into a stored status. Title-only affairs must cite the title; confidence capped."""
    inconsistent = is_inconsistent(label, confidence)
    if title_only:
        confidence = min(confidence, cap)
    if label in NO_EVIDENCE_LABELS and not evidence.strip():
        return Check(
            status="ok", verify_ok=False, verify_method="not_required", score=0, confidence=confidence,
            inconsistent=inconsistent,
        )
    result = verify_evidence(evidence, title if title_only else text, title)
    if label in NO_EVIDENCE_LABELS or result.ok:
        status = "ok"
    else:
        status = "evidence_failed"
    return Check(
        status=status, verify_ok=result.ok, verify_method=result.method, score=result.score, confidence=confidence,
        inconsistent=inconsistent,
    )
