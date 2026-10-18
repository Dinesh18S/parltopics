"""Metrics: pure functions over prediction records."""

import hashlib
import math
import random
from collections import Counter
from statistics import median

Z95 = 1.959964


def wilson(k: int, n: int, z: float = Z95) -> tuple[float, float]:
    """Wilson score interval for a proportion k/n."""
    if n == 0:
        return 0.0, 0.0
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - margin), min(1.0, centre + margin)


def is_predicted_match(row: dict) -> bool:
    return row["status"] == "ok" and row["label"] == "match"


def is_correct(row: dict) -> bool:
    """Gold yes: shown as match. Gold no: a valid non-match answer. Any failure status is wrong."""
    if row["gold"] == 1:
        return is_predicted_match(row)
    return row["status"] == "ok" and row["label"] != "match"


def _rate(k: int, n: int) -> dict:
    lo, hi = wilson(k, n)
    return {"n": n, "correct": k, "rate": k / n if n else None, "ci95": [lo, hi]}


def _pct(values: list[int], q: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, math.ceil(q * len(ordered)) - 1)]


def first_loop_summary(rows: list[dict]) -> dict:
    """Failures count as wrong; lang_missing rows are excluded and counted."""
    scored = [r for r in rows if r["status"] != "lang_missing"]
    pos = [r for r in scored if r["gold"] == 1]
    neg = [r for r in scored if r["gold"] == 0]
    model_matches = [r for r in scored if r["label"] == "match"]
    kw_matches = [r for r in scored if is_predicted_match(r) and r["keyword_absent"]]
    tech_matches = [r for r in kw_matches if r.get("tech_vocab_absent")]
    called = [r for r in scored if r["status"] not in {"fetch_error"}]
    latencies = [r["latency_ms"] for r in called if r.get("latency_ms")]
    return {
        "n_rows": len(rows),
        "excluded_lang_missing": len(rows) - len(scored),
        "status_counts": dict(Counter(r["status"] for r in rows)),
        "abstain": sum(r["label"] == "abstain" for r in scored),
        "inconsistent": sum(bool(r.get("inconsistent")) for r in scored),
        "positives": _rate(sum(is_correct(r) for r in pos), len(pos)),
        "negatives": _rate(sum(is_correct(r) for r in neg), len(neg)),
        "evidence": {
            "model_matches": len(model_matches),
            "verified": sum(bool(r["verify_ok"]) for r in model_matches),
            **{k: v for k, v in _rate(sum(bool(r["verify_ok"]) for r in model_matches), len(model_matches)).items()
               if k in ("rate", "ci95")},
        },
        "keyword_absent_matches": {
            "total": len(kw_matches),
            "gold_positive": sum(r["gold"] == 1 for r in kw_matches),
            "gold_negative": sum(r["gold"] == 0 for r in kw_matches),
            "also_tech_vocab_absent": len(tech_matches),
        },
        "latency_ms": {"p50": int(median(latencies)) if latencies else None, "p95": _pct(latencies, 0.95)},
        "tokens": {"in": sum(r.get("tok_in") or 0 for r in called), "out": sum(r.get("tok_out") or 0 for r in called)},
    }


def corrected_precision(recall: float, fpr: float, prevalence: float) -> float | None:
    """Precision on the population, from sample recall and FPR (docs/06 §2.3)."""
    tp = recall * prevalence
    fp = fpr * (1 - prevalence)
    return tp / (tp + fp) if tp + fp > 0 else None


def f1(precision: float | None, recall: float | None) -> float | None:
    if precision is None or recall is None or precision + recall == 0:
        return None
    return 2 * precision * recall / (precision + recall)


def _percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, int(round(q * (len(ordered) - 1)))))]


def bootstrap_corrected(
    pos_hits: list[bool], neg_hits: list[bool], prevalence: float, n_boot: int = 1000, seed: int = 0
) -> dict[str, list[float]]:
    """Stratified bootstrap (positives and negatives resampled separately): 95% percentile intervals."""
    rng = random.Random(seed)
    draws: dict[str, list[float]] = {"recall": [], "fpr": [], "precision": [], "f1": []}
    for _ in range(n_boot):
        r = sum(rng.choices(pos_hits, k=len(pos_hits))) / len(pos_hits)
        fp = sum(rng.choices(neg_hits, k=len(neg_hits))) / len(neg_hits)
        p = corrected_precision(r, fp, prevalence)
        draws["recall"].append(r)
        draws["fpr"].append(fp)
        if p is not None:
            draws["precision"].append(p)
            draws["f1"].append(f1(p, r) or 0.0)
    return {k: [_percentile(v, 0.025), _percentile(v, 0.975)] if v else [0.0, 0.0] for k, v in draws.items()}


def _group_key(title: str) -> str:
    return " ".join(title.lower().split())


def grouped_split(keys: list[str], dev_share: float, seed: int) -> list[str]:
    """'dev' or 'test' per row; rows with the same (normalised) key always share a split."""
    def bucket(key: str) -> float:
        digest = hashlib.sha256(f"{seed}:{_group_key(key)}".encode()).hexdigest()
        return int(digest[:8], 16) / 0xFFFFFFFF
    return ["dev" if bucket(k) < dev_share else "test" for k in keys]


def threshold_curve(rows: list[dict], thresholds: list[float], prevalence: float) -> list[dict]:
    """Recall, FPR and prevalence-corrected precision if 'shown as match' also needs confidence >= t."""
    pos = [r for r in rows if r["gold"] == 1]
    neg = [r for r in rows if r["gold"] == 0]
    curve = []
    for t in thresholds:
        def hit(r: dict) -> bool:
            return is_predicted_match(r) and (r.get("confidence") or 0) >= t
        recall = sum(map(hit, pos)) / len(pos) if pos else None
        fpr = sum(map(hit, neg)) / len(neg) if neg else None
        precision = corrected_precision(recall, fpr, prevalence) if pos and neg else None
        curve.append({"threshold": t, "recall": recall, "fpr": fpr, "precision_corrected": precision,
                      "f1_corrected": f1(precision, recall), "n_pos": len(pos), "n_neg": len(neg)})
    return curve
