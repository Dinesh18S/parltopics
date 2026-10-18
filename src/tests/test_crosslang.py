import pytest

from parltopics.evaluate.crosslang import cohen_kappa, crosslang_binary, crosslang_sets


def test_cohen_kappa_perfect_chance_and_known_value():
    assert cohen_kappa([1, 0, 1, 0], [1, 0, 1, 0]) == 1.0
    assert cohen_kappa([1, 1, 0, 0], [1, 0, 1, 0]) == 0.0
    # observed 0.8; expected 0.6·0.4 + 0.4·0.6 = 0.48 → (0.8 - 0.48) / 0.52
    assert cohen_kappa([1, 1, 1, 0, 0] * 2, [1, 1, 0, 0, 0] * 2) == pytest.approx(0.32 / 0.52)


def test_binary_agreement_all_three_and_pairs():
    labels = {1: {"de": 1, "fr": 1, "it": 1}, 2: {"de": 1, "fr": 0, "it": 1}, 3: {"de": 0, "fr": 0, "it": 0},
              4: {"de": 1, "fr": 1}}  # incomplete → skipped
    s = crosslang_binary(labels, ["de", "fr", "it"])
    assert s["n"] == 3 and s["skipped_incomplete"] == 1
    assert s["all_agree"]["rate"] == pytest.approx(2 / 3)
    assert s["pairs"]["de-fr"]["agreement"] == pytest.approx(2 / 3)
    assert s["pairs"]["de-it"]["agreement"] == 1.0


def test_set_agreement_top_label_and_jaccard():
    sets = {1: {"de": ["34", "4"], "fr": ["34"], "it": ["34", "15"]}, 2: {"de": ["15"], "fr": ["4"], "it": ["15"]}}
    s = crosslang_sets(sets, ["de", "fr", "it"])
    assert s["top_all_agree"]["rate"] == 0.5
    assert s["pairs"]["de-fr"]["jaccard_mean"] == pytest.approx((0.5 + 0.0) / 2)
