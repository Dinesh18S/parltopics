"""Multi-label metrics for standard mode (docs/06 §3): at-least-one-correct, micro/macro F1, per label."""

import random

from parltopics.evaluate.metrics import f1, wilson

NONE_OTHER = "NONE_OTHER"


def _prf(tp: int, fp: int, fn: int) -> dict:
    p = tp / (tp + fp) if tp + fp else None
    r = tp / (tp + fn) if tp + fn else None
    score = f1(p, r) if p is not None and r is not None else None
    return {"tp": tp, "fp": fp, "fn": fn, "precision": p, "recall": r, "f1": score or 0.0}


def _micro(pairs: list[tuple[set, set]]) -> dict:
    tp = sum(len(g & p) for g, p in pairs)
    fp = sum(len(p - g) for g, p in pairs)
    fn = sum(len(g - p) for g, p in pairs)
    return _prf(tp, fp, fn)


def multilabel_summary(gold: dict[int, set[str]], pred: dict[int, set[str]], labels: list[str],
                       n_boot: int = 1000, seed: int = 0) -> dict:
    """gold/pred: affair → label set. NONE_OTHER and missing predictions count as 'no labels'."""
    ids = sorted(a for a in gold if gold[a])
    pairs = [(set(gold[a]), set(pred.get(a, set())) - {NONE_OTHER}) for a in ids]
    hits = sum(bool(g & p) for g, p in pairs)
    micro = _micro(pairs)
    rng = random.Random(seed)
    boots = sorted(_micro([pairs[rng.randrange(len(pairs))] for _ in pairs])["f1"] for _ in range(n_boot)) if pairs else []
    per_label = {lab: _prf(sum(lab in g and lab in p for g, p in pairs), sum(lab not in g and lab in p for g, p in pairs),
                           sum(lab in g and lab not in p for g, p in pairs)) for lab in labels}
    present = [lab for lab in labels if per_label[lab]["tp"] + per_label[lab]["fn"] > 0]
    return {
        "n": len(ids),
        "skipped_no_gold": len(gold) - len(ids),
        "at_least_one_correct": {"correct": hits, "rate": hits / len(ids) if ids else None,
                                 "ci95": list(wilson(hits, len(ids)))},
        "micro": micro | {"f1_ci95": [boots[int(0.025 * (len(boots) - 1))], boots[int(0.975 * (len(boots) - 1))]]
                          if boots else None},
        "macro_f1": sum(per_label[lab]["f1"] for lab in present) / len(present) if present else None,
        "per_label": per_label,
        "cardinality": {"gold_mean": sum(len(g) for g, _ in pairs) / len(pairs) if pairs else 0,
                        "pred_mean": sum(len(p) for _, p in pairs) / len(pairs) if pairs else 0},
        "none_other_rate": sum(NONE_OTHER in pred.get(a, set()) for a in ids) / len(ids) if ids else None,
    }
