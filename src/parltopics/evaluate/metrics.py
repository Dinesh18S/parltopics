"""Metrics: pure functions over prediction records."""

import math
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
    called = [r for r in scored if r["status"] not in {"fetch_error"}]
    latencies = [r["latency_ms"] for r in called if r.get("latency_ms")]
    return {
        "n_rows": len(rows),
        "excluded_lang_missing": len(rows) - len(scored),
        "status_counts": dict(Counter(r["status"] for r in rows)),
        "positives": _rate(sum(is_predicted_match(r) for r in pos), len(pos)),
        "negatives": _rate(sum(r["status"] == "ok" and r["label"] != "match" for r in neg), len(neg)),
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
        },
        "latency_ms": {"p50": int(median(latencies)) if latencies else None, "p95": _pct(latencies, 0.95)},
        "tokens": {"in": sum(r.get("tok_in") or 0 for r in called), "out": sum(r.get("tok_out") or 0 for r in called)},
    }
