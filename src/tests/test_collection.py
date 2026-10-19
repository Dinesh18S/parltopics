from pathlib import Path
from types import SimpleNamespace

import openai
import pytest

from parltopics import batch, collection
from parltopics.config import Settings
from parltopics.llm import LLMClient
from parltopics.sources.api import Affair, Body, OPDError
from parltopics.store import Store

TEXT = "Le Conseil d'Etat est invité à créer une plateforme numérique pour les citoyens et les entreprises."
GOOD = '{"label": "match", "confidence": 0.95, "evidence": "créer une plateforme numérique pour les citoyens", "rationale": "r"}'


def _affair(i: int) -> Affair:
    return Affair(
        id=i, body=Body(key="GE", type="canton", languages=["fr"], primary="fr"), number=str(i), type="Motion",
        begin_date="2024-01-01", title={"fr": f"Titre {i}"}, url_external={}, url_api=f"u{i}", texts=[],
        docs=[{"id": i, "name": "d", "date": None, "language": "fr", "url": None, "text": TEXT}],
    )


class _Source:
    """Stands in for AffairSource: a listing and affairs by id; ids in `broken` fail to fetch."""

    def __init__(self, ids, broken=()):
        self.ids, self.broken, self.fetched = list(ids), set(broken), []
        self.api = SimpleNamespace(list_affairs_since=lambda body, since, fresh=False: [
            {"id": i, "begin_date": "2024-01-01", "type_en": "Consultation" if i == 99 else "Motion"}
            for i in self.ids])

    def get_affair(self, affair_id, body_key=None):
        self.fetched.append(affair_id)
        if affair_id in self.broken:
            raise OPDError("HTTP 503")
        return _affair(affair_id)


class _LLM:
    """Fake chat endpoint; answers GOOD, or raises for affairs listed in `down` (a transient llm_error)."""

    def __init__(self):
        self.calls, self.down = [], set()

    def create(self, **kw):
        affair = next(i for i in range(1, 100) if f"Titre {i}" in kw["messages"][-1]["content"])
        self.calls.append(affair)
        if affair in self.down:
            raise openai.OpenAIError("gateway down")
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=GOOD))],
                               usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5))


@pytest.fixture
def env(tmp_path, monkeypatch):
    settings = Settings(_env_file=None, llm_base_url="http://x/v1", llm_json_mode="none", data_dir=tmp_path,
                        db_path=tmp_path / "t.db", bulk_db_path=tmp_path / "none.db", llm_concurrency=2)
    fake = _LLM()

    def client(s):
        llm = LLMClient(s)
        llm.client = SimpleNamespace(chat=SimpleNamespace(completions=fake))
        return llm

    monkeypatch.setattr(batch, "LLMClient", client)
    topic = tmp_path / "x.yaml"
    topic.write_text("name: Topic X\ndefinition: Affairs about X.\n")
    return SimpleNamespace(settings=settings, store=Store(settings.db_path), llm=fake, topic=str(topic),
                           results=tmp_path / "results")


def _index(env, source, **kw):
    return collection.index(env.settings, env.store, env.results, "GE", env.topic, **kw)


def test_ingest_is_idempotent_and_excludes_consultations(env):
    source = _Source([1, 2, 3, 99])
    first = collection.ingest(env.settings, env.store, "GE", "2018-01-01", source)
    assert first["listed"] == 3 and first["new"] == 3 and sorted(source.fetched) == [1, 2, 3]
    second = collection.ingest(env.settings, env.store, "GE", "2018-01-01", source)
    assert second["new"] == 0 and second["fetched"] == 0 and len(source.fetched) == 3
    assert [i["status"] for i in env.store.items("GE")] == ["ok", "ok", "ok"]
    assert second["quality"]["status"] == {"ok": 3}


def test_ingest_retries_fetch_errors_next_time(env):
    source = _Source([1, 2], broken={2})
    assert collection.ingest(env.settings, env.store, "GE", "2018-01-01", source)["quality"]["status"] == {
        "ok": 1, "fetch_error": 1}
    source.broken.clear()
    again = collection.ingest(env.settings, env.store, "GE", "2018-01-01", source)
    assert again["fetched"] == 1 and again["new"] == 0 and again["quality"]["status"] == {"ok": 2}


def test_index_is_resumable_and_retries_transient_failures(env):
    source = _Source([1, 2, 3])
    collection.ingest(env.settings, env.store, "GE", "2018-01-01", source)
    env.llm.down = {3}
    out = _index(env, source, passes=1)
    assert out["done"] == 2 and out["not_done"] == 1
    assert _index(env, source, passes=1)["done"] == 2  # still down: retried, not duplicated for 1 and 2
    env.llm.down.clear()
    out = _index(env, source)
    assert out["done"] == 3 and out["not_done"] == 0
    assert sorted(env.llm.calls) == [1, 2, 3, 3, 3]
    assert _index(env, source)["runs"] == []  # nothing left: no new run, no model call
    assert len(env.llm.calls) == 5
    results = env.store.collection_results(collection.collection_ref("GE"), out["prompt_version"])
    assert sorted(r["affair_id"] for r in results) == [1, 2, 3] and {r["status"] for r in results} == {"ok"}


def test_update_classifies_only_new_affairs(env):
    source = _Source([1, 2])
    collection.ingest(env.settings, env.store, "GE", "2018-01-01", source)
    _index(env, source)
    assert sorted(env.llm.calls) == [1, 2]
    source.ids.append(3)
    out = collection.update(env.settings, env.store, env.results, "GE", source_of=source)
    assert out["new_ids"] == [3] and out["indexed"][0]["done"] == 3
    assert sorted(env.llm.calls) == [1, 2, 3]
    out = collection.update(env.settings, env.store, env.results, "GE", source_of=source)
    assert out["new_ids"] == [] and len(env.llm.calls) == 3


def test_update_skips_a_topic_changed_since_indexing(env, tmp_path):
    source = _Source([1])
    collection.ingest(env.settings, env.store, "GE", "2018-01-01", source)
    _index(env, source)
    (tmp_path / "x.yaml").write_text("name: Topic X\ndefinition: Affairs about Y.\n")
    source.ids.append(2)
    out = collection.update(env.settings, env.store, env.results, "GE", source_of=source)
    assert out["skipped_changed"] == [env.topic] and out["indexed"] == [] and env.llm.calls == [1]


def test_export_rows_flag_shown_matches(env):
    source = _Source([1])
    collection.ingest(env.settings, env.store, "GE", "2018-01-01", source)
    version = _index(env, source)["prompt_version"]
    [row] = collection.export_rows(env.store, "GE", version, 0.9)
    assert row["shown_as_match"] and row["evidence_verified"] and row["review"] == ""
    assert not collection.export_rows(env.store, "GE", version, 0.99)[0]["shown_as_match"]


def test_custom_ui_topic_maps_to_one_file_so_it_resumes(tmp_path, monkeypatch):
    from parltopics import api_collections
    from parltopics.topics import Topic, load_topic

    monkeypatch.setattr(api_collections, "CUSTOM_TOPICS_DIR", tmp_path)
    topic = Topic(name="Wolf", definition="Affairs about wolves.", include=["culling"])
    first = api_collections._custom_target(topic)
    assert api_collections._custom_target(Topic(**topic.model_dump())) == first
    assert api_collections._custom_target(topic.model_copy(update={"definition": "Wolves."})) != first
    assert load_topic(Path(first)) == topic


def test_offline_copy_round_trip_gives_the_same_results(env, tmp_path):
    from parltopics import demo

    source = _Source([1, 2, 3])
    collection.ingest(env.settings, env.store, "GE", "2018-01-01", source)
    out = _index(env, source)
    target = collection.latest_targets(env.store, "GE")[env.topic]
    demo.export_collection(env.store, "GE", target, tmp_path / "GE.json.gz")
    fresh = Store(tmp_path / "fresh.db")
    assert demo.import_collection(fresh, tmp_path / "GE.json.gz") == 3
    assert demo.import_collection(fresh, tmp_path / "GE.json.gz") == 0  # idempotent
    key = lambda rows: sorted((r["affair_id"], r["label"], r["confidence"], r["evidence"]) for r in rows)
    ref = collection.collection_ref("GE")
    assert key(fresh.collection_results(ref, out["prompt_version"])) == key(env.store.collection_results(ref, out["prompt_version"]))
    assert len(fresh.done_affairs(ref, out["prompt_version"])) == 3
