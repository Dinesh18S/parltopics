import pytest
from fastapi import HTTPException

from parltopics.api import SearchIn, TopicIn, build_topic


def test_custom_topic_without_definition_gets_neutral_default_and_no_keywords():
    topic, ref = build_topic(SearchIn(topic=TopicIn(name="Tamil", definition="")))
    assert topic.definition == "Affairs whose main subject is Tamil."
    assert topic.include == [] and topic.exclude == [] and topic.keywords == {}
    assert ref == "ui:Tamil"


def test_custom_topic_keeps_only_what_the_user_gave():
    topic, _ = build_topic(SearchIn(topic=TopicIn(name="Beekeeping", definition="Bees and honey.", include=["Varroa"])))
    assert topic.definition == "Bees and honey." and topic.include == ["Varroa"] and topic.keywords == {}


def test_preset_is_loaded_from_yaml():
    topic, ref = build_topic(SearchIn(preset_id="covid19"))
    assert topic.name == "Covid-19" and ref == "topics/covid19.yaml"


def test_neither_preset_nor_topic_is_rejected():
    with pytest.raises(HTTPException):
        build_topic(SearchIn())
