import pytest

from parltopics.evaluate.adjudication import after_review

CELLS = {"TP": 55, "FN": 46, "FP": 5, "TN": 385}


def test_reviewer_agreeing_with_politmonitor_reproduces_before_numbers():
    answers = {"TP": [1] * 4, "FN": [1] * 19, "FP": [0] * 4, "TN": [0] * 22}
    a = after_review(CELLS, answers, prevalence=0.05, n_boot=200, seed=1)
    p_before = 0.05 * 55 / 101 / (0.05 * 55 / 101 + 0.95 * 5 / 390)
    assert a["precision"] == pytest.approx(p_before)
    assert a["recall"] == pytest.approx(55 / 101)


def test_confirmed_false_positives_raise_precision_and_missed_digital_negatives_lower_recall():
    base = {"TP": [1] * 4, "FN": [1] * 19, "FP": [0] * 4, "TN": [0] * 22}
    better = after_review(CELLS, base | {"FP": [1] * 4}, prevalence=0.05, n_boot=50, seed=1)
    assert better["precision"] == pytest.approx(1.0)
    worse = after_review(CELLS, base | {"TN": [1] + [0] * 21}, prevalence=0.05, n_boot=50, seed=1)
    assert worse["recall"] < 55 / 101
    lo, hi = better["recall_ci95"]
    assert lo <= better["recall"] <= hi
