"""Cached demo results: export a finished demo-pool run to results/demo/*.json (committed) and seed a fresh
store from it, so a clean checkout can demo without a model endpoint (docs/02 §3)."""

import json
from pathlib import Path

from parltopics.runlog import RunManifest
from parltopics.schemes import Scheme
from parltopics.sources.api import Affair, Body
from parltopics.sources.assemble import SourceText
from parltopics.store import Store
from parltopics.topics import Topic

CACHE_VERSION = 1


def export_run(store: Store, run_id: str, path: Path) -> int:
    run = store.run(run_id)
    topic = json.loads(store.db.execute("SELECT topic_json FROM topics WHERE id = ?", (run["topic_sha"],))
                       .fetchone()["topic_json"])
    preds = [dict(r) for r in store.db.execute("SELECT * FROM predictions WHERE run_id = ? ORDER BY id", (run_id,))]
    shas = sorted({p["source_sha256"] for p in preds if p["source_sha256"]})
    sources = [dict(r) for r in store.db.execute(
        f"SELECT * FROM sources WHERE text_sha256 IN ({','.join('?' * len(shas))})", shas)] if shas else []
    ids = sorted({p["affair_id"] for p in preds})
    affairs = [dict(r) for r in store.db.execute(
        f"SELECT * FROM affairs WHERE id IN ({','.join('?' * len(ids))})", ids)] if ids else []
    for p in preds:
        p.pop("id")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"cache_version": CACHE_VERSION, "manifest": run["manifest"], "topic": topic,
                                "affairs": affairs, "sources": sources, "predictions": preds},
                               ensure_ascii=False, indent=1))
    return len(preds)


def import_cache(store: Store, path: Path) -> str | None:
    """Load a cache file into the store unless its run is already there. Returns the run id if imported."""
    data = json.loads(path.read_text())
    manifest = RunManifest.model_validate(data["manifest"])
    if store.db.execute("SELECT 1 FROM runs WHERE id = ?", (manifest.run_id,)).fetchone():
        return None
    topic_cls = Scheme if "categories" in data["topic"] else Topic
    store.add_run(manifest, topic_cls.model_validate(data["topic"]))
    affairs = {a["id"]: a for a in data["affairs"]}
    for s in data["sources"]:
        a = affairs[s["affair_id"]]
        affair = Affair(
            id=a["id"], body=Body(key=a["body_key"], type=a["body_type"], languages=[], primary=None),
            number=a["number"], type=a["type"], begin_date=a["begin_date"], title=json.loads(a["title_json"]),
            url_external=json.loads(a["url_external_json"]), url_api=a["url_api"], texts=[], docs=[],
        )
        source = SourceText(
            affair_id=s["affair_id"], lang=s["lang"], lang_source=s["lang_source"], detected_lang=s["detected_lang"],
            lang_mismatch=bool(s["lang_mismatch"]), title=s["title"], text=s["text"], sha256=s["text_sha256"],
            sections=[], title_only=bool(s["title_only"]), truncated=bool(s["truncated"]),
            cut_section=s["cut_section"], chars_lost=s["chars_lost"], n_chars_full=s["n_chars_full"], url=s["url"],
        )
        store.add_source(affair, source)
    for p in data["predictions"]:
        store.add_prediction(p)
    store.finish_run(manifest.run_id, len(data["predictions"]))
    return manifest.run_id
