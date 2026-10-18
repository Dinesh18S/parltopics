from pathlib import Path

from parltopics.prompts import load_prompt, render_adhoc
from parltopics.topics import Topic, load_topic

TOPICS_DIR = Path(__file__).resolve().parents[2] / "topics"


def _topic(**kw) -> Topic:
    base = {"name": "Topic X", "definition": "Affairs about X.", "include": [], "exclude": [], "keywords": {}}
    return Topic(**(base | kw))


def test_templates_contain_no_topic_words():
    prompt = load_prompt("adhoc_v4")
    for path in TOPICS_DIR.glob("*.yaml"):
        name = load_topic(path).name.lower()
        assert name not in prompt.system.lower()
        assert name not in prompt.user.lower()


def test_render_inserts_topic_affair_and_language():
    system, user = render_adhoc(load_prompt("adhoc_v4"), _topic(), "TITLE: Some affair {with braces}", "fr")
    assert "TOPIC: Topic X" in user
    assert "DEFINITION: Affairs about X." in user
    assert "AFFAIR (language: fr):" in user
    assert "TITLE: Some affair {with braces}" in user
    assert "never judge" in system


def test_include_exclude_lines_only_when_set():
    _, user = render_adhoc(load_prompt("adhoc_v4"), _topic(), "text", "de")
    assert "COUNTS AS THIS TOPIC" not in user and "DOES NOT COUNT" not in user
    _, user = render_adhoc(load_prompt("adhoc_v4"), _topic(include=["A", "B"], exclude=["C"]), "text", "de")
    assert "COUNTS AS THIS TOPIC:\n- A\n- B\nDOES NOT COUNT:\n- C\n" in user


def test_topic_accepts_string_or_empty_rules():
    assert _topic(include="A", exclude="").include == ["A"] and _topic(exclude="").exclude == []


def test_prompt_sha_is_stable_and_versioned():
    a, b = load_prompt("adhoc_v4"), load_prompt("adhoc_v4")
    assert a.sha == b.sha and len(a.sha) == 64
    assert a.version == "adhoc_v4"
