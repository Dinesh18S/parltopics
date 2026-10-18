from parltopics.config import Settings
from parltopics.prompts import load_prompt
from parltopics.runlog import fingerprint
from parltopics.topics import Topic

TOPIC = Topic(name="Topic X", definition="Affairs about X.", keywords={"de": ["x"]})


def _settings(**kw) -> Settings:
    return Settings(_env_file=None, **({"llm_name": "m"} | kw))


def test_same_inputs_same_version():
    a = fingerprint(load_prompt("adhoc_v3"), TOPIC, _settings())
    b = fingerprint(load_prompt("adhoc_v3"), TOPIC, _settings())
    assert a.prompt_version == b.prompt_version and len(a.prompt_version) == 64


def test_changed_definition_changes_version_and_only_topic_part():
    a = fingerprint(load_prompt("adhoc_v3"), TOPIC, _settings())
    b = fingerprint(load_prompt("adhoc_v3"), TOPIC.model_copy(update={"definition": "Affairs about Y."}), _settings())
    assert a.prompt_version != b.prompt_version
    changed = {k for k in a.parts if a.parts[k] != b.parts[k]}
    assert changed == {"topic"}


def test_model_params_change_version():
    base = fingerprint(load_prompt("adhoc_v3"), TOPIC, _settings())
    for kw in ({"llm_name": "other"}, {"llm_temperature": 0.2}, {"llm_max_tokens": 50},
               {"llm_json_mode": "none"}, {"max_input_chars": 40000}):
        other = fingerprint(load_prompt("adhoc_v3"), TOPIC, _settings(**kw))
        assert other.prompt_version != base.prompt_version, kw
        assert {k for k in base.parts if base.parts[k] != other.parts[k]} == {"params"}


def test_fewshot_changes_version():
    a = fingerprint(load_prompt("adhoc_v3"), TOPIC, _settings())
    b = fingerprint(load_prompt("adhoc_v3"), TOPIC, _settings(), fewshot=[{"affair_id": 1, "label": "match"}])
    assert a.parts["fewshot"] != b.parts["fewshot"] and a.prompt_version != b.prompt_version
