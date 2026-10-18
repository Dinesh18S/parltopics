from pathlib import Path

from parltopics.prompts import load_prompt, render_adhoc
from parltopics.topics import Topic, load_topic

TOPICS_DIR = Path(__file__).resolve().parents[2] / "topics"


def _topic(**kw) -> Topic:
    base = {"name": "Topic X", "definition": "Affairs about X.", "include": "", "exclude": "", "keywords": {}}
    return Topic(**(base | kw))


def test_templates_contain_no_topic_words():
    prompt = load_prompt("adhoc_v1")
    for path in TOPICS_DIR.glob("*.yaml"):
        name = load_topic(path).name.lower()
        assert name not in prompt.system.lower()
        assert name not in prompt.user.lower()


def test_render_inserts_topic_affair_and_language():
    system, user = render_adhoc(load_prompt("adhoc_v1"), _topic(), "TITLE: Some affair {with braces}", "fr")
    assert "TOPIC: Topic X" in user
    assert "DEFINITION: Affairs about X." in user
    assert "AFFAIR (language: fr):" in user
    assert "TITLE: Some affair {with braces}" in user
    assert "never judge" in system


def test_include_exclude_lines_only_when_set():
    _, user = render_adhoc(load_prompt("adhoc_v1"), _topic(), "text", "de")
    assert "COUNTS AS THIS TOPIC" not in user and "DOES NOT COUNT" not in user
    _, user = render_adhoc(load_prompt("adhoc_v1"), _topic(include="A", exclude="B"), "text", "de")
    assert "COUNTS AS THIS TOPIC: A" in user and "DOES NOT COUNT: B" in user


def test_prompt_sha_is_stable_and_versioned():
    a, b = load_prompt("adhoc_v1"), load_prompt("adhoc_v1")
    assert a.sha == b.sha and len(a.sha) == 64
    assert a.version == "adhoc_v1"
