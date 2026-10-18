from types import SimpleNamespace

from parltopics.classify import AdhocOutput
from parltopics.config import Settings
from parltopics.llm import LLMClient, extract_json

VALID = '{"label": "no_match", "confidence": 0.8, "evidence": "", "rationale": "r"}'


class _FakeCompletions:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def create(self, **kw):
        self.calls.append(kw)
        content = self.replies.pop(0)
        usage = SimpleNamespace(prompt_tokens=10, completion_tokens=5)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))], usage=usage)


def _client(replies, mode="none"):
    llm = LLMClient(Settings(_env_file=None, llm_base_url="http://x/v1", llm_json_mode=mode))
    fake = _FakeCompletions(replies)
    llm.client = SimpleNamespace(chat=SimpleNamespace(completions=fake))
    return llm, fake


def test_extract_json_skips_prose_and_broken_braces():
    assert extract_json('Sure! {bad} then {"a": 1} trailing') == {"a": 1}
    assert extract_json("no json here") is None


def test_valid_first_reply():
    llm, fake = _client([VALID])
    call = llm.complete_json("s", "u", AdhocOutput)
    assert call.status == "ok" and not call.repaired and len(fake.calls) == 1
    assert (call.tok_in, call.tok_out) == (10, 5)


def test_one_repair_retry_then_ok():
    llm, fake = _client(['{"label": "yes"}', VALID])
    call = llm.complete_json("s", "u", AdhocOutput)
    assert call.status == "ok" and call.repaired and len(fake.calls) == 2
    assert call.tok_in == 20


def test_parse_error_after_failed_repair():
    llm, fake = _client(["nope", "still nope"])
    call = llm.complete_json("s", "u", AdhocOutput)
    assert call.status == "parse_error" and len(fake.calls) == 2


def test_json_schema_mode_sends_strict_schema():
    llm, fake = _client([VALID], mode="json_schema")
    llm.complete_json("s", "u", AdhocOutput)
    rf = fake.calls[0]["response_format"]
    assert rf["type"] == "json_schema" and rf["json_schema"]["strict"] is True
    assert rf["json_schema"]["schema"]["additionalProperties"] is False
