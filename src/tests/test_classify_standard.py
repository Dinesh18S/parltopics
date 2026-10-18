import json
from types import SimpleNamespace

from parltopics.classify import classify_standard
from parltopics.config import Settings
from parltopics.llm import LLMClient
from parltopics.prompts import load_prompt
from parltopics.schemes import Category, Scheme
from parltopics.sources.api import Affair, Body
from parltopics.sources.assemble import assemble

SCHEME = Scheme(name="S", definition="d", kind="test", categories=[
    Category(code="CV01", source_id="15", labels={"fr": "Economie"}),
    Category(code="CV02", source_id="34", labels={"fr": "Médias"}),
])
AFFAIR = Affair(
    id=1, body=Body(key="GE", type="canton", languages=["fr"], primary="fr"), number="1", type="Motion",
    begin_date="2024-01-01", title={"fr": "Un titre"}, url_external={}, url_api="u", texts=[],
    docs=[{"id": 1, "name": "d", "date": None, "language": "fr", "url": None,
           "text": "Le Conseil d'Etat est invité à créer une plateforme numérique pour les médias régionaux."}],
)


def _run(reply: dict):
    llm = LLMClient(Settings(_env_file=None, llm_base_url="http://x/v1", llm_json_mode="none"))
    usage = SimpleNamespace(prompt_tokens=10, completion_tokens=5)
    content = json.dumps(reply)
    llm.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
        create=lambda **kw: SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))], usage=usage))))
    return classify_standard(llm, load_prompt("standard_v1"), assemble(AFFAIR, 12000), SCHEME, "", 0.6, "run")


def test_one_record_per_label_with_source_ids_and_per_label_verification():
    recs = _run({"labels": [
        {"code": "CV02", "confidence": 0.9, "evidence": "créer une plateforme numérique pour les médias régionaux"},
        {"code": "CV01", "confidence": 0.6, "evidence": "une phrase inventée qui ne figure pas dans le texte"}],
        "rationale": "r"})
    by = {r["label"]: r for r in recs}
    assert set(by) == {"34", "15"}
    assert by["34"]["status"] == "ok" and by["34"]["verify_ok"]
    assert by["15"]["status"] == "evidence_failed"
    assert by["34"]["scheme_code"] == "CV02" and by["34"]["rank"] == 1


def test_none_other_alone_needs_no_evidence():
    recs = _run({"labels": [{"code": "NONE_OTHER", "confidence": 0.8, "evidence": ""}], "rationale": "r"})
    assert [(r["label"], r["status"]) for r in recs] == [("NONE_OTHER", "ok")]


def test_none_other_mixed_with_codes_is_dropped_and_flagged():
    recs = _run({"labels": [
        {"code": "CV02", "confidence": 0.9, "evidence": "créer une plateforme numérique pour les médias régionaux"},
        {"code": "NONE_OTHER", "confidence": 0.2, "evidence": ""}], "rationale": "r"})
    assert [r["label"] for r in recs] == ["34"] and recs[0]["error"] == "NONE_OTHER mixed with codes: dropped"


def test_unknown_code_is_invalid_label():
    recs = _run({"labels": [{"code": "CV99", "confidence": 0.9, "evidence": "x"}], "rationale": "r"})
    assert recs[0]["status"] in {"invalid_label", "parse_error"}


def test_duplicate_codes_are_kept_once():
    ev = "créer une plateforme numérique pour les médias régionaux"
    recs = _run({"labels": [{"code": "CV02", "confidence": 0.9, "evidence": ev},
                            {"code": "CV02", "confidence": 0.8, "evidence": ev}], "rationale": "r"})
    assert [r["label"] for r in recs] == ["34"]
