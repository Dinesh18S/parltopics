"""Cached demo results: export a finished demo-pool run to results/demo/*.json (committed) and seed a fresh
store from it, so a clean checkout can demo without a model endpoint (docs/02 §3)."""

import gzip
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


# ---------- whole collections (docs/08 phase 3: offline mode) ----------
COMPACT_DROP = ("raw_json",)  # never shipped
TEXT_LABELS = ("match",)  # texts are shipped only for rows the app can open (model matches + evidence failures)


def export_collection(store: Store, body_key: str, target: dict, path: Path) -> dict:
    """The result that counts per affair (see Store.collection_results) of one ad-hoc target, compact: every
    affair and prediction, but texts, rationales and evidence only for model matches / evidence failures."""
    from parltopics import collection

    ref = collection.collection_ref(body_key)
    rows = store.collection_results(ref, target["prompt_version"])
    ids = [r["prediction_id"] for r in rows]
    preds = []
    for i in range(0, len(ids), 900):
        chunk = ids[i:i + 900]
        preds += [dict(r) for r in store.db.execute(
            f"SELECT * FROM predictions WHERE id IN ({','.join('?' * len(chunk))})", chunk)]
    openable = {p["affair_id"] for p in preds if p["label"] in TEXT_LABELS or p["status"] == "evidence_failed"}
    for p in preds:
        for k in COMPACT_DROP:
            p.pop(k, None)
        if p["affair_id"] not in openable:  # its text is not shipped: no reference to it
            p.update(rationale="", evidence="", title="", source_sha256=None)
    items = [{k: i[k] for k in ("affair_id", "begin_date", "type", "title", "text_sha256", "status", "error",
                                "first_seen_at")} | ({} if i["affair_id"] in openable else {"title": "", "text_sha256": None})
             for i in store.items(body_key)]
    shas = sorted({p["source_sha256"] for p in preds if p["affair_id"] in openable and p["source_sha256"]})
    sources = []
    for i in range(0, len(shas), 900):
        chunk = shas[i:i + 900]
        sources += [dict(r) for r in store.db.execute(
            f"SELECT * FROM sources WHERE text_sha256 IN ({','.join('?' * len(chunk))})", chunk)]
    affair_ids = sorted(openable | {s["affair_id"] for s in sources})  # shared texts name another affair (D69)
    affairs = []
    for i in range(0, len(affair_ids), 900):
        chunk = affair_ids[i:i + 900]
        affairs += [dict(r) for r in store.db.execute(
            f"SELECT * FROM affairs WHERE id IN ({','.join('?' * len(chunk))})", chunk)]
    runs = sorted({p["run_id"] for p in preds})
    topic_sha = store.run(runs[0])["topic_sha"]
    topic = json.loads(store.db.execute("SELECT topic_json FROM topics WHERE id = ?", (topic_sha,)).fetchone()[0])
    last = store.last_ingest(body_key)
    data = {"cache_version": CACHE_VERSION, "body_key": body_key, "since": last["since"], "topic": topic,
            "manifests": [store.run(r)["manifest"] for r in runs], "items": items, "affairs": affairs,
            "sources": sources, "predictions": preds}
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    return {"path": str(path), "bytes": path.stat().st_size, "affairs": len(items), "predictions": len(preds),
            "texts": len(sources), "runs": runs}


def import_collection(store: Store, path: Path) -> int:
    """Seed a store from an exported collection file; runs already present are skipped. Returns rows imported."""
    with gzip.open(path, "rt", encoding="utf-8") as f:
        data = json.load(f)
    manifests = [RunManifest.model_validate(m) for m in data["manifests"]]
    new_runs = {m.run_id for m in manifests
                if not store.db.execute("SELECT 1 FROM runs WHERE id = ?", (m.run_id,)).fetchone()}
    if not new_runs:
        return 0
    topic = Topic.model_validate(data["topic"])
    for m in manifests:
        if m.run_id in new_runs:
            store.add_run(m, topic)
    with store.lock:
        db = store.db
        db.execute("BEGIN")
        try:
            _insert_collection(db, data, new_runs, manifests, path)
        except Exception:  # undo everything, including the runs added above, so a later start can retry
            db.execute("ROLLBACK")
            db.executemany("DELETE FROM runs WHERE id = ?", [(r,) for r in new_runs])
            raise
        db.execute("COMMIT")
    return sum(p["run_id"] in new_runs for p in data["predictions"])


def _insert_collection(db, data: dict, new_runs: set[str], manifests: list, path: Path) -> None:
    db.executemany("INSERT OR IGNORE INTO affairs VALUES (:id,:body_key,:body_type,:number,:type,:begin_date,"
                   ":title_json,:url_external_json,:url_api)", data["affairs"])
    db.executemany("INSERT OR IGNORE INTO sources VALUES (:text_sha256,:affair_id,:lang,:lang_source,"
                   ":detected_lang,:lang_mismatch,:title,:title_only,:truncated,:cut_section,:chars_lost,"
                   ":n_chars_full,:url,:text,:assembled_at)", data["sources"])
    if not db.execute("SELECT 1 FROM ingests WHERE body_key = ?", (data["body_key"],)).fetchone():
        db.execute("INSERT INTO ingests (body_key, since, started_at, finished_at, n_listed, n_new, report_json) "
                   "VALUES (?, ?, ?, ?, ?, ?, ?)", (data["body_key"], data["since"], data["items"][0]["first_seen_at"],
                                                    data["items"][0]["first_seen_at"], len(data["items"]),
                                                    len(data["items"]), json.dumps({"imported_from": path.name})))
    ingest_id = db.execute("SELECT MAX(id) FROM ingests WHERE body_key = ?", (data["body_key"],)).fetchone()[0]
    db.executemany(
        "INSERT OR IGNORE INTO collection_items (body_key, affair_id, begin_date, type, title, text_sha256, status, "
        "error, first_ingest, first_seen_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        [(data["body_key"], i["affair_id"], i["begin_date"], i["type"], i["title"], i["text_sha256"], i["status"],
          i["error"], ingest_id, i["first_seen_at"], i["first_seen_at"]) for i in data["items"]])
    rows = [p for p in data["predictions"] if p["run_id"] in new_runs]
    cols = [c for c in rows[0] if c != "id"] if rows else []
    db.executemany(f"INSERT INTO predictions ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                   [[p[c] for c in cols] for p in rows])
    for m in manifests:
        if m.run_id in new_runs:
            n = sum(p["run_id"] == m.run_id for p in rows)
            db.execute("UPDATE runs SET finished_at = ?, n_rows = ? WHERE id = ?", (m.started_at, n, m.run_id))
