from parltopics.evaluate.full_population import exact, is_shown


def test_exact_counts_every_affair_of_the_population():
    pred = {1: True, 2: True, 3: False, 4: False, 5: False}
    gold = {1, 3, 9}  # 9 is tagged but outside the population: not counted
    m = exact(pred, gold)
    assert (m["tp"], m["fp"], m["fn"], m["tn"], m["n"]) == (1, 1, 1, 2, 5)
    assert m["precision"] == 0.5 and m["recall"] == 0.5 and m["f1"] == 0.5
    assert m["recall_ci95"][0] < 0.5 < m["recall_ci95"][1]


def test_exact_without_predictions_has_no_precision():
    m = exact({1: False}, {1})
    assert m["precision"] is None and m["recall"] == 0.0


def test_shown_needs_ok_match_and_threshold():
    assert is_shown({"status": "ok", "label": "match", "confidence": 0.9}, 0.9)
    assert not is_shown({"status": "ok", "label": "match", "confidence": 0.85}, 0.9)
    assert not is_shown({"status": "evidence_failed", "label": "match", "confidence": 1.0}, 0.9)
    assert not is_shown(None, 0.9)
