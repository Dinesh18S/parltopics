import pytest

from parltopics.evaluate.metrics import (
    bootstrap_corrected, corrected_precision, f1, grouped_split, threshold_curve,
)


def test_corrected_precision_formula():
    # recall 0.8, FPR 0.05, prevalence 0.05 → 0.04 / (0.04 + 0.0475)
    assert corrected_precision(0.8, 0.05, 0.05) == pytest.approx(0.04 / 0.0875)
    assert corrected_precision(0.0, 0.0, 0.05) is None
    assert corrected_precision(1.0, 0.0, 0.05) == 1.0


def test_f1():
    assert f1(0.5, 0.5) == 0.5
    assert f1(None, 0.5) is None and f1(0.0, 0.0) is None


def test_bootstrap_is_seeded_and_brackets_point_estimate():
    pos = [True] * 80 + [False] * 20
    neg = [True] * 10 + [False] * 190
    a = bootstrap_corrected(pos, neg, prevalence=0.05, n_boot=500, seed=1)
    b = bootstrap_corrected(pos, neg, prevalence=0.05, n_boot=500, seed=1)
    assert a == b
    point = corrected_precision(0.8, 0.05, 0.05)
    assert a["precision"][0] < point < a["precision"][1]
    assert a["recall"][0] < 0.8 < a["recall"][1]


def test_grouped_split_keeps_identical_titles_together_and_is_stable():
    titles = [f"Titel {i}" for i in range(300)] + ["Gleicher Titel"] * 6
    splits = grouped_split(titles, dev_share=0.3, seed=42)
    same = {s for t, s in zip(titles, splits) if t == "Gleicher Titel"}
    assert len(same) == 1
    assert splits == grouped_split(titles, dev_share=0.3, seed=42)
    share = splits.count("dev") / len(splits)
    assert 0.22 < share < 0.38
    assert grouped_split([" Gleicher  titel "], 0.3, 42) == grouped_split(["gleicher titel"], 0.3, 42)


def test_threshold_curve():
    rows = [
        {"gold": 1, "status": "ok", "label": "match", "confidence": 0.9},
        {"gold": 1, "status": "ok", "label": "match", "confidence": 0.6},
        {"gold": 0, "status": "ok", "label": "match", "confidence": 0.7},
        {"gold": 0, "status": "ok", "label": "no_match", "confidence": 0.1},
    ]
    curve = {p["threshold"]: p for p in threshold_curve(rows, [0.5, 0.65, 0.8], prevalence=0.5)}
    assert curve[0.5]["recall"] == 1.0 and curve[0.5]["fpr"] == 0.5
    assert curve[0.65]["recall"] == 0.5 and curve[0.65]["fpr"] == 0.5
    assert curve[0.8]["recall"] == 0.5 and curve[0.8]["fpr"] == 0.0
