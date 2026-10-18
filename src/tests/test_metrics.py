from parltopics.evaluate.metrics import first_loop_summary, is_correct, wilson
from parltopics.topics import Topic, keyword_absent, tech_vocab_absent

CORE = {"de": ["Digitalisierung", "digital*"], "fr": ["numérique"]}
BROAD = {"de": ["Daten", "Cyber"]}
TOPIC = Topic(name="T", definition="d", keywords=CORE, keywords_broad=BROAD)


def test_keyword_absent_core_words_word_start_prefix_case_insensitive():
    assert not keyword_absent("die DIGITALEN Dienste", TOPIC)  # digital* prefix
    assert not keyword_absent("Digitalisierungsstrategie 2025", TOPIC)  # compound starting with the word
    assert not keyword_absent("les services numériques", TOPIC)  # plural, any language counts
    assert keyword_absent("Schutz von Datenbanken gegen Cyberangriffe", TOPIC)  # broad words don't count here
    assert keyword_absent("Breitband für alle", TOPIC)


def test_tech_vocab_absent_uses_core_and_broad():
    assert not tech_vocab_absent("Schutz von DATENbanken", TOPIC)
    assert not tech_vocab_absent("gegen Cyberangriffe", TOPIC)
    assert not tech_vocab_absent("digitale Verwaltung", TOPIC)
    assert tech_vocab_absent("Kandidaten und Mandate", TOPIC)  # 'daten' inside a word is not a hit
    assert tech_vocab_absent("Breitband für alle", TOPIC)


def _row(gold, label, status="ok", verify_ok=True, kw_absent=False, lang="de", ms=1000, inconsistent=False):
    return {"gold": gold, "label": label, "status": status, "verify_ok": verify_ok, "inconsistent": inconsistent,
            "keyword_absent": kw_absent, "lang": lang, "latency_ms": ms, "tok_in": 100, "tok_out": 10}


def test_summary_counts_failures_as_wrong_and_excludes_lang_missing():
    rows = [
        _row(1, "match"), _row(1, "match", status="evidence_failed", verify_ok=False),
        _row(1, "no_match"), _row(1, None, status="parse_error"),
        _row(0, "no_match", inconsistent=True), _row(0, "abstain"), _row(0, "match", kw_absent=True),
        _row(0, None, status="lang_missing"),
    ]
    s = first_loop_summary(rows)
    assert s["positives"]["n"] == 4 and s["positives"]["correct"] == 1
    assert s["negatives"]["n"] == 3 and s["negatives"]["correct"] == 2
    assert s["excluded_lang_missing"] == 1
    assert s["evidence"]["model_matches"] == 3 and s["evidence"]["verified"] == 2
    assert s["keyword_absent_matches"] == {
        "total": 1, "gold_positive": 0, "gold_negative": 1, "also_tech_vocab_absent": 0,
    }
    assert s["status_counts"]["parse_error"] == 1
    assert s["abstain"] == 1 and s["inconsistent"] == 1


def test_wilson_interval():
    lo, hi = wilson(18, 20)
    assert 0.68 < lo < 0.70 and 0.97 < hi < 0.98
    assert wilson(0, 0) == (0.0, 0.0)


def test_is_correct_counts_failures_as_wrong():
    assert is_correct(_row(1, "match")) and not is_correct(_row(1, "abstain"))
    assert is_correct(_row(0, "abstain")) and is_correct(_row(0, "no_match"))
    assert not is_correct(_row(0, "match", status="evidence_failed"))
    assert not is_correct(_row(0, None, status="llm_error"))
