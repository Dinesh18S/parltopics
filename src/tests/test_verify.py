import pytest

from parltopics.verify import check_prediction, is_inconsistent, normalize, verify_evidence

TITLE = "Die Rolle von Hosting- und Cloud-Anbietern bei Cyberbedrohungen stärken"
TEXT = (
    f"TITLE: {TITLE}\n\n"
    "TEXT: Der Bundesrat wird beauftragt, gesetzliche Grundlagen auszuarbeiten, welche Hosting- und "
    "Cloudanbietern die nötigen Rechte erteilt. Le Conseil fédéral parle de l’« identité numérique » "
    "et de la Digitali- sierung der Verwaltung – ein wichtiges Thema."
)


# --- normalisation ---------------------------------------------------------

def test_normalize_unifies_quotes_dashes_case_whitespace_soft_hyphen():
    assert normalize("L’État «Numérique»  –\n ok­!") == normalize("l'état \"numérique\" - ok!")


def test_normalize_joins_line_break_hyphenation():
    assert normalize("Digitali- sierung") == normalize("Digitalisierung")
    assert normalize("Digitali-\nsierung") == "digitalisierung"


# --- verify_evidence -------------------------------------------------------

def test_exact():
    r = verify_evidence("gesetzliche Grundlagen auszuarbeiten", TEXT, TITLE)
    assert r.ok and r.method == "exact"


def test_exact_with_quote_variants():
    r = verify_evidence("Le Conseil fédéral parle de l'\"identité numérique\"", TEXT, TITLE)
    assert r.ok and r.method == "exact"


def test_exact_across_hyphenation():
    r = verify_evidence("de la Digitalisierung der Verwaltung", TEXT, TITLE)
    assert r.ok and r.method == "exact"


def test_fuzzy_pass_on_small_typo():
    r = verify_evidence("Der Bundesrat wird beauftragt, gesetzliche Grundlagen auszuarbeiten", TEXT, TITLE)
    assert r.ok and r.method == "exact"
    r = verify_evidence("Der Bundesrat wird beauftragt, gesetzliche Grundlage auszuarbeiten", TEXT, TITLE)
    assert r.ok and r.method == "fuzzy"
    assert r.score >= 92


def test_fuzzy_fail_on_paraphrase():
    r = verify_evidence("Der Bundesrat soll neue Gesetze für Cloudfirmen schreiben", TEXT, TITLE)
    assert not r.ok and r.method == "not_found"


def test_fuzzy_needs_25_chars():
    near_miss = "gesetzlich Grundlagen"  # 21 chars, one letter dropped: close, but too short for fuzzy
    r = verify_evidence(near_miss, TEXT, TITLE)
    assert not r.ok and r.method == "not_found"


def test_too_short_fails_unless_it_is_the_title():
    r = verify_evidence("Bundesrat", TEXT, TITLE)
    assert not r.ok and r.method == "too_short"
    r = verify_evidence("IA et droit", "TITLE: IA et droit", "IA et droit")
    assert r.ok and r.method == "exact"


def test_empty_evidence():
    r = verify_evidence("", TEXT, TITLE)
    assert not r.ok and r.method == "empty"


# --- check_prediction (status + title-only cap) ----------------------------

def test_match_with_verified_evidence_is_ok():
    c = check_prediction("match", 0.9, "gesetzliche Grundlagen auszuarbeiten", TEXT, TITLE, title_only=False, cap=0.6)
    assert c.status == "ok" and c.verify_ok and c.confidence == 0.9


def test_match_with_unverified_evidence_fails():
    c = check_prediction("match", 0.9, "erfundener Satz der nicht im Text steht", TEXT, TITLE, title_only=False, cap=0.6)
    assert c.status == "evidence_failed" and not c.verify_ok


def test_match_with_empty_evidence_fails():
    c = check_prediction("match", 0.9, "", TEXT, TITLE, title_only=False, cap=0.6)
    assert c.status == "evidence_failed"


@pytest.mark.parametrize("label", ["no_match", "abstain", "NONE_OTHER"])
def test_non_match_may_have_empty_evidence(label):
    c = check_prediction(label, 0.2, "", TEXT, TITLE, title_only=False, cap=0.6)
    assert c.status == "ok" and c.verify_method == "not_required"


def test_title_only_caps_confidence_and_requires_title_evidence():
    title_text = f"TITLE: {TITLE}"
    c = check_prediction("match", 0.95, "Hosting- und Cloud-Anbietern", title_text, TITLE, title_only=True, cap=0.6)
    assert c.status == "ok" and c.confidence == 0.6
    c = check_prediction("match", 0.4, TITLE, title_text, TITLE, title_only=True, cap=0.6)
    assert c.status == "ok" and c.confidence == 0.4


def test_title_only_rejects_evidence_outside_title():
    c = check_prediction("match", 0.9, "gesetzliche Grundlagen auszuarbeiten", TEXT, TITLE, title_only=True, cap=0.6)
    assert c.status == "evidence_failed"


# --- confidence / label consistency -----------------------------------------

@pytest.mark.parametrize("label,conf,expected", [
    ("match", 0.4, True), ("match", 0.5, False), ("match", 0.9, False),
    ("no_match", 0.6, True), ("no_match", 0.5, False), ("no_match", 0.0, False),
    ("abstain", 0.9, False), ("abstain", 0.1, False),
])
def test_inconsistent_flag(label, conf, expected):
    assert is_inconsistent(label, conf) is expected


def test_check_prediction_flags_inconsistency_on_raw_confidence():
    title_text = f"TITLE: {TITLE}"
    c = check_prediction("no_match", 0.9, "", title_text, TITLE, title_only=True, cap=0.6)
    assert c.inconsistent and c.confidence == 0.6
    c = check_prediction("match", 0.9, "gesetzliche Grundlagen auszuarbeiten", TEXT, TITLE, title_only=False, cap=0.6)
    assert not c.inconsistent
