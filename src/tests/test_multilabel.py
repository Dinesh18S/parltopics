import pytest

from parltopics.evaluate.multilabel import multilabel_summary


def test_at_least_one_micro_macro_and_cardinality():
    gold = {1: {"A", "B"}, 2: {"C"}, 3: {"A"}, 4: {"B"}}
    pred = {1: {"A"}, 2: {"B", "C"}, 3: set(), 4: {"NONE_OTHER"}}
    s = multilabel_summary(gold, pred, labels=["A", "B", "C"], n_boot=200, seed=1)
    assert s["n"] == 4
    assert s["at_least_one_correct"]["correct"] == 2  # affairs 1 and 2
    # micro: TP = A(1) + C(2) = 2; FP = B(2) = 1; FN = B(1) + A(3) + B(4) = 3
    assert s["micro"]["precision"] == pytest.approx(2 / 3)
    assert s["micro"]["recall"] == pytest.approx(2 / 5)
    assert s["micro"]["f1"] == pytest.approx(2 * (2 / 3) * (2 / 5) / (2 / 3 + 2 / 5))
    assert s["per_label"]["C"]["f1"] == pytest.approx(1.0)
    assert s["per_label"]["B"]["f1"] == 0.0
    assert s["macro_f1"] == pytest.approx((s["per_label"]["A"]["f1"] + 0.0 + 1.0) / 3)
    assert s["cardinality"] == {"gold_mean": 1.25, "pred_mean": 0.75}  # NONE_OTHER and empty count as 0 labels
    assert s["none_other_rate"] == 0.25
    lo, hi = s["micro"]["f1_ci95"]
    assert 0 <= lo <= s["micro"]["f1"] <= hi <= 1


def test_affairs_without_gold_labels_are_skipped_and_counted():
    s = multilabel_summary({1: {"A"}, 2: set()}, {1: {"A"}, 2: {"A"}}, labels=["A"], n_boot=50, seed=1)
    assert s["n"] == 1 and s["skipped_no_gold"] == 1
