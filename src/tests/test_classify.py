from types import SimpleNamespace

from parltopics.classify import classify_adhoc
from parltopics.config import Settings
from parltopics.llm import LLMClient
from parltopics.prompts import load_prompt
from parltopics.sources.api import Affair, Body
from parltopics.sources.assemble import assemble
from parltopics.topics import Topic

TOPIC = Topic(name="Topic X", definition="Affairs about X.")
AFFAIR = Affair(
    id=1, body=Body(key="GE", type="canton", languages=["fr"], primary="fr"), number="1", type="Motion",
    begin_date="2024-01-01", title={"fr": "Un titre"}, url_external={}, url_api="u", texts=[],
    docs=[{"id": 1, "name": "d", "date": None, "language": "fr", "url": None,
           "text": "Le Conseil d'Etat est invité à créer une plateforme numérique pour les citoyens et les entreprises."}],
)
GOOD = '{"label": "match", "confidence": 0.9, "evidence": "créer une plateforme numérique pour les citoyens", "rationale": "r"}'
BAD = '{"label": "match", "confidence": 0.9, "evidence": "une plateforme digitale sera construite pour tous", "rationale": "r"}'


class _Fake:
    def __init__(self, replies):
        self.replies, self.calls = list(replies), []

    def create(self, **kw):
        self.calls.append(kw)
        usage = SimpleNamespace(prompt_tokens=10, completion_tokens=5)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=self.replies.pop(0)))],
                               usage=usage)


def _run(replies):
    llm = LLMClient(Settings(_env_file=None, llm_base_url="http://x/v1", llm_json_mode="none"))
    fake = _Fake(replies)
    llm.client = SimpleNamespace(chat=SimpleNamespace(completions=fake))
    source = assemble(Affair.model_validate(AFFAIR), 12000)
    return classify_adhoc(llm, load_prompt("adhoc_v4"), source, TOPIC, 0.6, "run"), fake


def test_failed_evidence_is_retried_once_and_recovers():
    p, fake = _run([BAD, GOOD])
    assert p.status == "ok" and p.evidence_retried and p.evidence_recovered
    assert len(fake.calls) == 2 and "not found verbatim" in fake.calls[1]["messages"][-1]["content"]
    assert p.tok_in == 20


def test_failed_retry_stays_evidence_failed():
    p, fake = _run([BAD, BAD])
    assert p.status == "evidence_failed" and p.evidence_retried and not p.evidence_recovered
    assert len(fake.calls) == 2


def test_verified_evidence_is_not_retried():
    p, fake = _run([GOOD])
    assert p.status == "ok" and not p.evidence_retried and len(fake.calls) == 1
