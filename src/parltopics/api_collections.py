"""HTTP routes for whole collections (docs/08 phase 3): list, results, estimate, background index jobs, export."""

import hashlib
import io
import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yaml
from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import Response
from pydantic import ValidationError

from parltopics import collection
from parltopics.config import get_settings

router = APIRouter(prefix="/api")
CUSTOM_TOPICS_DIR = Path("data/topics_custom")  # relative to the repo root, like topics/ in run manifests
JOB_CONCURRENCY = 16  # D67: 32 stalled the gateway
FALLBACK_RATE = {"adhoc": 200.0, "standard": 80.0}  # affairs/min until a collection run has been measured
LEVEL = {"country": "Federal", "canton": "Cantonal"}


def _api():
    from parltopics import api  # late import: api.py includes this router

    return api


def _kind(target: str) -> str:
    return "standard" if target.startswith(collection.SCHEME_PREFIX) else "adhoc"


def _name(target: str) -> str:
    if _kind(target) == "standard":
        sid = target[len(collection.SCHEME_PREFIX):]
        return _api().SCHEMES.get(sid, sid)
    return collection.load_topic(Path(target)).name


def _body_meta(body_key: str) -> dict:
    row = _api().store().db.execute(
        "SELECT a.body_type, COUNT(*) AS n, SUM(c.status = 'ok') AS ok FROM collection_items c "
        "LEFT JOIN affairs a ON a.id = c.affair_id WHERE c.body_key = ? GROUP BY c.body_key", (body_key,)).fetchone()
    if row is None:
        raise HTTPException(404, f"collection {body_key} not ingested")
    return {"level": LEVEL.get(row["body_type"], "Municipal"), "n": row["n"], "ok": row["ok"]}


def _rate(kind: str) -> tuple[float, bool]:
    """Affairs per minute of the newest finished collection run of this kind with ≥ 200 affairs, and whether it
    was measured (False = FALLBACK_RATE)."""
    rows = _api().store().db.execute(
        "SELECT r.prompt_template, r.started_at, r.finished_at, COUNT(DISTINCT p.affair_id) AS n FROM runs r "
        "JOIN predictions p ON p.run_id = r.id WHERE r.sample_file LIKE 'collection:%' AND r.finished_at IS NOT NULL "
        "GROUP BY r.id HAVING n >= 200 ORDER BY r.started_at DESC LIMIT 20").fetchall()
    for r in rows:
        if r["prompt_template"].startswith("standard") == (kind == "standard"):
            minutes = (datetime.fromisoformat(r["finished_at"]) - datetime.fromisoformat(r["started_at"])).total_seconds() / 60
            if minutes > 0:
                return r["n"] / minutes, True
    return FALLBACK_RATE[kind], False


def _progress(body_key: str, target: str) -> dict:
    settings = get_settings()
    _, _, version = collection.target_version(settings, target)
    done = len(_api().store().done_affairs(collection.collection_ref(body_key), version))
    total = _body_meta(body_key)["ok"]
    rate, measured = _rate(_kind(target))
    return {"target": target, "name": _name(target), "kind": _kind(target), "prompt_version": version,
            "done": done, "total": total, "pending": total - done, "rate_per_min": round(rate), "rate_measured": measured,
            "minutes": round((total - done) / rate) if rate else None}


@router.get("/collections")
def collections() -> list[dict]:
    s = _api().store()
    settings = get_settings()
    out = []
    for (body_key,) in s.db.execute("SELECT DISTINCT body_key FROM collection_items ORDER BY body_key").fetchall():
        last = s.last_ingest(body_key)
        targets = []
        for path, t in collection.latest_targets(s, body_key).items():
            current = collection.target_version(settings, path, t["prompt_template"])[2] == t["prompt_version"]
            if current and (_kind(path) == "standard" or Path(path).exists()):
                targets.append(_progress(body_key, path))
        out.append({"body_key": body_key, **_body_meta(body_key), "since": last["since"] if last else None,
                    "last_ingest": last["finished_at"] if last else None, "targets": targets})
    return out


@router.get("/collections/{body_key}/results")
def results(body_key: str, target: str) -> dict:
    """Ad-hoc: only rows the UI can show (model matches, evidence failures); the rest is counted.
    Standard: every label of every affair."""
    s = _api().store()
    prog = _progress(body_key, target)
    rows = s.collection_results(collection.collection_ref(body_key), prog["prompt_version"])
    if prog["kind"] == "adhoc":
        keep = [r for r in rows if r["label"] == "match" or r["status"] == "evidence_failed"]
        labels = pd.Series([r["label"] or r["status"] for r in rows], dtype=str).value_counts().to_dict()
    else:
        keep = [r for r in rows if r["status"] in ("ok", "evidence_failed")]
        labels = {}
    return {"body_key": body_key, **_body_meta(body_key), **prog, "label_counts": labels, "items": keep}


class _Job:
    def __init__(self, body_key: str, target: str):
        self.id = hashlib.sha1(f"{body_key}{target}{time.time()}".encode()).hexdigest()[:12]
        self.body_key, self.target = body_key, target
        self.status, self.error = "running", None
        self.cancel = threading.Event()
        self.started = time.monotonic()
        self.start_done = _progress(body_key, target)["done"]


class _Jobs:
    current: _Job | None = None
    lock = threading.Lock()


def _custom_target(topic) -> str:
    """A custom UI topic as a YAML file, named by its content, so the same topic resumes the same index."""
    data = topic.model_dump(exclude_defaults=True)
    digest = hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12]
    path = CUSTOM_TOPICS_DIR / f"custom-{digest}.yaml"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False))
    return str(path)


def _target_of(raw: dict) -> str:
    """Request body {preset_id} | {topic: {name, definition, include, exclude}} | {scheme} → index target."""
    try:
        body = _api().SearchIn.model_validate(raw)
    except ValidationError as e:
        raise HTTPException(422, str(e))
    if body.scheme:
        if body.scheme not in _api().SCHEMES:
            raise HTTPException(404, "unknown scheme")
        return f"{collection.SCHEME_PREFIX}{body.scheme}"
    topic, ref = _api().build_topic(body)
    return ref if body.preset_id else _custom_target(topic)


@router.post("/collections/{body_key}/estimate")
def estimate(body_key: str, body: dict = Body(...)) -> dict:
    return _progress(body_key, _target_of(body))


@router.post("/collections/{body_key}/jobs")
def start_job(body_key: str, body: dict = Body(...)) -> dict:
    api = _api()
    settings = get_settings()
    if not api.check_model(settings)["reachable"]:
        raise HTTPException(503, "model endpoint unreachable — cached results only")
    target = _target_of(body)
    with _Jobs.lock:
        if _Jobs.current is not None and _Jobs.current.status == "running":
            raise HTTPException(409, f"a job is already running ({_Jobs.current.body_key} · {_name(_Jobs.current.target)})")
        job = _Jobs.current = _Job(body_key, target)

    def work() -> None:
        try:
            collection.index(settings.model_copy(update={"llm_concurrency": JOB_CONCURRENCY}), api.store(),
                             api.RESULTS_DIR, body_key, target, cancel=job.cancel)
            job.status = "cancelled" if job.cancel.is_set() else "done"
        except Exception as e:  # the job's failure is shown to the user and kept on the job, never swallowed
            job.status, job.error = "failed", f"{type(e).__name__}: {e}"

    threading.Thread(target=work, daemon=True).start()
    return job_status(job.id)


@router.get("/jobs/{job_id}")
def job_status(job_id: str) -> dict:
    job = _Jobs.current
    if job is None or job.id != job_id:
        raise HTTPException(404, "unknown job")
    prog = _progress(job.body_key, job.target)
    minutes = (time.monotonic() - job.started) / 60
    rate = (prog["done"] - job.start_done) / minutes if minutes > 0.2 else None
    eta = round(prog["pending"] / rate) if rate else prog["minutes"]
    return {"job_id": job.id, "body_key": job.body_key, "status": job.status, "error": job.error,
            **prog, "rate_now": round(rate) if rate else None, "eta_min": eta}


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str) -> dict:
    job = _Jobs.current
    if job is None or job.id != job_id:
        raise HTTPException(404, "unknown job")
    job.cancel.set()
    return job_status(job_id)


@router.get("/collections/{body_key}/export.xlsx")
def export(body_key: str, target: str, only: str = "all") -> Response:
    """Excel of a collection's results: all rows, only shown matches, or only confirmed ones."""
    api = _api()
    prog = _progress(body_key, target)
    rows = collection.export_rows(api.store(), body_key, prog["prompt_version"], api.match_threshold(get_settings()))
    if only == "shown":
        rows = [r for r in rows if r["shown_as_match"]]
    elif only == "confirmed":
        rows = [r for r in rows if r["review"] == "confirm" or (r["review"] == "correct" and r["review_label"] == "match")]
    buf = io.BytesIO()
    pd.DataFrame(rows).to_excel(buf, index=False)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    name = f"parltopics_{body_key}_{Path(target).stem.replace('scheme:', '')}_{only}_{stamp}.xlsx"
    return Response(buf.getvalue(), headers={"Content-Disposition": f'attachment; filename="{name}"'},
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
