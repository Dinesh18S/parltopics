from parltopics.evaluate.metrics import first_loop_summary, wilson
from parltopics.topics import keyword_absent

KW = {"de": ["Digitalisierung", "Daten", "Cyber"], "fr": ["numérique"]}


def test_keyword_absent_uses_word_start_prefix_case_insensitive():
    assert not keyword_absent("Schutz von DATENbanken", KW)  # prefix of a word
    assert not keyword_absent("gegen Cyberangriffe", KW)
    assert not keyword_absent("l'identité numérique", KW)  # any language counts
    assert keyword_absent("Kandidaten und Mandate", KW)  # 'daten' inside a word is not a match
    assert keyword_absent("Breitband für alle", KW)


def _row(gold, label, status="ok", verify_ok=True, kw_absent=False, lang="de", ms=1000):
    return {"gold": gold, "label": label, "status": status, "verify_ok": verify_ok,
            "keyword_absent": kw_absent, "lang": lang, "latency_ms": ms, "tok_in": 100, "tok_out": 10}


def test_summary_counts_failures_as_wrong_and_excludes_lang_missing():
    rows = [
        _row(1, "match"), _row(1, "match", status="evidence_failed", verify_ok=False),
        _row(1, "no_match"), _row(1, None, status="parse_error"),
        _row(0, "no_match"), _row(0, "abstain"), _row(0, "match", kw_absent=True),
        _row(0, None, status="lang_missing"),
    ]
    s = first_loop_summary(rows)
    assert s["positives"]["n"] == 4 and s["positives"]["correct"] == 1
    assert s["negatives"]["n"] == 3 and s["negatives"]["correct"] == 2
    assert s["excluded_lang_missing"] == 1
    assert s["evidence"]["model_matches"] == 3 and s["evidence"]["verified"] == 2
    assert s["keyword_absent_matches"] == {"total": 1, "gold_positive": 0, "gold_negative": 1}
    assert s["status_counts"]["parse_error"] == 1


def test_wilson_interval():
    lo, hi = wilson(18, 20)
    assert 0.68 < lo < 0.70 and 0.97 < hi < 0.98
    assert wilson(0, 0) == (0.0, 0.0)
