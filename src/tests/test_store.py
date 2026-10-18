import sqlite3

import pytest

from parltopics.config import Settings
from parltopics.prompts import load_prompt
from parltopics.runlog import RunManifest, fingerprint
from parltopics.sources.api import Affair, Body
from parltopics.sources.assemble import assemble
from parltopics.store import Store
from parltopics.topics import Topic

TOPIC = Topic(name="Topic X", definition="Affairs about X.")
AFFAIR = Affair(
    id=7, body=Body(key="GE", type="canton", languages=["fr"], primary="fr"), number="M 1", type="Motion",
    begin_date="2024-01-01", title={"fr": "Un titre assez long"}, url_external={"fr": "https://ge.ch/x"},
    url_api="https://api/x", texts=[], docs=[],
)


def _manifest(run_id: str) -> RunManifest:
    return RunManifest(
        run_id=run_id, started_at="2026-10-18T00:00:00", prompt_template="adhoc_v4",
        fingerprint=fingerprint(load_prompt("adhoc_v4"), TOPIC, Settings(_env_file=None, llm_name="m")),
        topic_name=TOPIC.name, topic_path="topics/x.yaml", base_url_host="h", git_commit="abc",
        sample_file="s.csv", notes="",
    )


def _record(run_id: str, source_sha: str | None, status: str = "ok", label: str | None = "match") -> dict:
    return {
        "run_id": run_id, "affair_id": 7, "lang": "fr", "gold": 1, "body_key": "GE", "title": "Un titre",
        "label": label, "confidence": 0.9, "evidence": "Un titre assez long", "rationale": "r",
        "verify_ok": True, "verify_method": "exact", "verify_score": 100.0, "inconsistent": False,
        "keyword_absent": True, "tech_vocab_absent": True, "status": status, "model": "m",
        "source_sha256": source_sha, "latency_ms": 10, "tok_in": 5, "tok_out": 2, "tokens_estimated": False,
        "repaired": False, "error": None, "raw_json": "{}",
    }


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "t.db")
    source = assemble(AFFAIR, 12000)
    s.add_run(_manifest("run1"), TOPIC)
    s.add_source(AFFAIR, source)
    s.add_prediction(_record("run1", source.sha256))
    return s, source


def test_runs_are_kept_side_by_side(store):
    s, source = store
    s.add_run(_manifest("run2"), TOPIC)
    s.add_prediction(_record("run2", source.sha256, label="no_match"))
    assert [r["id"] for r in s.runs()] == ["run2", "run1"]
    assert s.predictions("run1")[0]["label"] == "match"
    assert s.predictions("run2")[0]["label"] == "no_match"
    assert s.predictions("run1")[0]["title_only"] is True  # joined from sources


def test_predictions_are_append_only(store):
    s, _ = store
    with pytest.raises(sqlite3.DatabaseError):
        s.db.execute("UPDATE predictions SET label = 'no_match'")
    with pytest.raises(sqlite3.DatabaseError):
        s.db.execute("DELETE FROM predictions")


def test_prediction_must_point_at_a_run(store):
    s, source = store
    with pytest.raises(sqlite3.IntegrityError):
        s.add_prediction(_record("missing-run", source.sha256))


def test_lang_missing_prediction_without_source(store):
    s, _ = store
    s.add_prediction(_record("run1", None, status="lang_missing", label=None))
    statuses = sorted(p["status"] for p in s.predictions("run1"))
    assert statuses == ["lang_missing", "ok"]


def test_reviews_never_change_predictions(store):
    s, _ = store
    pid = s.predictions("run1")[0]["id"]
    s.add_review(pid, "correct", corrected_label="no_match", reviewer="A", note="media only")
    s.add_review(pid, "confirm", reviewer="B")
    assert s.predictions("run1")[0]["label"] == "match"
    assert [r["decision"] for r in s.reviews(pid)] == ["correct", "confirm"]
    with pytest.raises(sqlite3.IntegrityError):
        s.add_review(pid, "maybe")
    with pytest.raises(sqlite3.IntegrityError):
        s.add_review(pid, "correct")  # correct needs a corrected_label


def test_run_manifest_round_trip(store):
    s, _ = store
    run = s.run("run1")
    assert run["prompt_template"] == "adhoc_v4"
    assert run["manifest"]["fingerprint"]["parts"]["topic"] == run["topic_sha"]
