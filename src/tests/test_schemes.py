from pathlib import Path

import pytest

from parltopics.prompts import load_prompt, render_standard
from parltopics.schemes import load_aps_chapters, load_aps_topics, load_curia_vista

RAW = Path(__file__).resolve().parents[2] / "data" / "raw"
pytestmark = pytest.mark.skipif(not (RAW / "che_topics_vocabulary.csv").exists(), reason="needs make data")


def test_schemes_load_from_data_files():
    cv, ch = load_curia_vista(RAW), load_aps_chapters(RAW)
    assert len(cv.categories) == 28 and len(ch.categories) == 22 and len(load_aps_topics(RAW).categories) == 165
    assert all(set(c.labels) <= {"de", "fr", "it"} for c in cv.categories)
    assert all(t.source_id.startswith(("6.1.", "4.4.")) for t in load_aps_topics(RAW, ["6.1", "4.4"]).categories)


def test_aps_has_no_italian_labels_so_fallback_is_used():
    ch = load_aps_chapters(RAW)
    assert ch.label(ch.categories[0], "it", "de") == ch.categories[0].labels["de"]


def test_standard_prompt_lists_codes_in_affair_language_and_repeats_task_after_text():
    _, user = render_standard(load_prompt("standard_v1"), load_curia_vista(RAW), "TEXT: x", "fr", "")
    assert "CV11: Médias et communication" in user
    assert user.index("Task: choose 1 to 3 codes") > user.index(">>>")
