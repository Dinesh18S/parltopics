"""HTTP API + static demo UI (docs/04 §4.5, docs/02)."""

import csv
import io
import json
import sqlite3
import threading
from pathlib import Path
from urllib.parse import urlparse

import httpx
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from parltopics import demo
from parltopics.batch import iter_classify
from parltopics.llm import LLMClient
from parltopics.config import Settings, get_settings
from parltopics.prompts import load_prompt
from parltopics.runlog import fingerprint, start_run
from parltopics.sources.assemble import TRANSLATED_BODY_TYPES, LangMissing, assemble
from parltopics.sources.router import AffairSource
from parltopics.store import Store
from parltopics.topics import Topic, load_topic
from parltopics.verify import locate

ROOT = Path(__file__).resolve().parents[2]
WEB_DIR = ROOT / "src" / "web"
TOPICS_DIR = ROOT / "topics"
RESULTS_DIR = ROOT / "results"
DEMO_CACHE_DIR = RESULTS_DIR / "demo"
DEMO_POOL = Path("data/samples/demo_pool.csv")  # relative: the same string is stored as runs.sample_file
PROMPT_TEMPLATE = "adhoc_v5"
EXPORT_FIELDS = ("prediction_id", "affair_id", "body_key", "number", "begin_date", "lang", "title", "label",
                 "confidence", "evidence", "verify_method", "keyword_absent", "status", "url", "review_decision",
                 "review_label")

app = FastAPI(title="ParlTopics")


def check_model(settings: Settings) -> dict:
    """Ask the endpoint's /models whether the configured model is served."""
    if not settings.llm_base_url:
        return {"reachable": False, "error": "LLM_BASE_URL not set"}
    try:
        r = httpx.get(
            f"{settings.llm_base_url.rstrip('/')}/models",
            headers={"Authorization": f"Bearer {settings.llm_api_key}"},
            timeout=5,
        )
        r.raise_for_status()
    except httpx.HTTPError as e:
        return {"reachable": False, "error": type(e).__name__}
    served = [m.get("id") for m in r.json().get("data", [])]
    return {"reachable": settings.llm_name in served, "served": served}


class _State:
    store: Store | None = None
    lock = threading.Lock()


def store() -> Store:
    with _State.lock:
        if _State.store is None:
            _State.store = Store(get_settings().db_path)
            for path in sorted(DEMO_CACHE_DIR.glob("*.json")):
                demo.import_cache(_State.store, path)
        return _State.store


def presets() -> dict[str, tuple[Path, Topic]]:
    return {p.stem: (p, load_topic(p)) for p in sorted(TOPICS_DIR.glob("*.yaml"))}


def topic_sha(topic: Topic) -> str:
    return fingerprint(load_prompt(PROMPT_TEMPLATE), topic, get_settings()).parts["topic"]


@app.get("/health")
def health() -> dict:
    settings = get_settings()
    model = check_model(settings)
    return {
        "status": "ok",
        "mode": "live" if model["reachable"] else "cached",
        "model": settings.llm_name,
        "model_check": model,
    }


@app.get("/api/state")
def state() -> dict:
    settings = get_settings()
    model = check_model(settings)
    s = store()
    out = []
    for pid, (_, topic) in presets().items():
        run = s.latest_run(topic_sha(topic), str(DEMO_POOL))
        out.append({"id": pid, **topic.model_dump(), "run": _run_meta(run) if run else None})
    pool = pd.read_csv(ROOT / DEMO_POOL) if (ROOT / DEMO_POOL).exists() else pd.DataFrame()
    return {
        "mode": "live" if model["reachable"] else "cached",
        "model": settings.llm_name,
        "endpoint_host": urlparse(settings.llm_base_url).hostname or "",
        "model_error": model.get("error"),
        "presets": out,
        "pool": {"file": str(DEMO_POOL), "n": len(pool)},
        "prompt_template": PROMPT_TEMPLATE,
        "match_threshold": match_threshold(settings),
        "default_preset": settings.demo_default_preset,
        "review_lang": settings.review_lang,
    }


def match_threshold(settings: Settings) -> float:
    """The threshold fixed on dev by the pre-registered rule (results/metrics.json); config value as fallback."""
    path = RESULTS_DIR / "metrics.json"
    if path.exists():
        block = json.loads(path.read_text()).get("digitalisation_federal_2018", {})
        chosen = block.get("threshold", {}).get("chosen_on_dev")
        if chosen is not None:
            return float(chosen)
    return settings.match_threshold


def _run_meta(run: dict) -> dict:
    return {"run_id": run["id"], "started_at": run["started_at"], "finished_at": run["finished_at"],
            "model": run["model"], "prompt_version": run["prompt_version"], "n": run["n_rows"]}


@app.get("/api/runs/{run_id}")
def run_items(run_id: str) -> dict:
    s = store()
    try:
        run = s.run(run_id)
    except KeyError:
        raise HTTPException(404, "unknown run")
    return {"run": _run_meta(run), "topic_name": run["topic_name"], "items": s.run_items(run_id)}


@app.get("/api/predictions/{prediction_id}")
def prediction(prediction_id: int) -> dict:
    try:
        detail = store().prediction_detail(prediction_id)
    except KeyError:
        raise HTTPException(404, "unknown prediction")
    span = locate(detail["evidence"] or "", detail["text"] or "") if detail.get("verify_ok") else None
    return detail | {"evidence_span": list(span) if span else None}


TRANSLATE_MAX_CHARS = 2000
_translations: dict[tuple[str, str], str] = {}


def _official_version(detail: dict, lang: str) -> str | None:
    """The parliament's own version of the affair in `lang` (translated bodies only), or None."""
    affair = AffairSource(get_settings()).get_affair(detail["affair_id"], detail["body_key"])
    if affair.body.type not in TRANSLATED_BODY_TYPES:
        return None
    try:
        return assemble(affair, get_settings().max_input_chars, lang).text
    except LangMissing:
        return None


@app.get("/api/predictions/{prediction_id}/reading")
def reading_version(prediction_id: int, lang: str) -> dict:
    """Reading aid for a reviewer: the official version in `lang` if the parliament publishes one."""
    try:
        detail = store().prediction_detail(prediction_id)
    except KeyError:
        raise HTTPException(404, "unknown prediction")
    text = _official_version(detail, lang)
    if text is None:
        return {"kind": "none", "lang": lang}
    return {"kind": "official", "lang": lang, "text": text,
            "note": "Official version published by the parliament. The evidence above stays in the original language."}


@app.post("/api/predictions/{prediction_id}/translate")
def translate(prediction_id: int, lang: str) -> dict:
    """Unofficial Apertus translation for reading only; never used as evidence or stored as a label."""
    settings = get_settings()
    if not check_model(settings)["reachable"]:
        raise HTTPException(503, "model endpoint unreachable")
    try:
        detail = store().prediction_detail(prediction_id)
    except KeyError:
        raise HTTPException(404, "unknown prediction")
    key = (detail["source_sha256"], lang)
    if key not in _translations:
        text = detail["text"] or ""
        system = (Path(__file__).parent / "prompts" / "translate_v1.system.txt").read_text()
        model = settings.translate_model or settings.llm_name
        _translations[key] = LLMClient(settings.model_copy(update={"llm_name": model})).complete_text(
            system, f"Target language: {lang}\n\n{text[:TRANSLATE_MAX_CHARS]}", max_tokens=1200)
    model = settings.translate_model or settings.llm_name
    return {"kind": "machine", "lang": lang, "text": _translations[key], "model": model,
            "truncated": len(detail["text"] or "") > TRANSLATE_MAX_CHARS,
            "note": f"Unofficial machine translation by {model}. Not evidence; check the original."}


DEFAULT_DEFINITION = "Affairs whose main subject is {name}."


class TopicIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    definition: str = Field(default="", max_length=2000)
    include: list[str] = []
    exclude: list[str] = []


class SearchIn(BaseModel):
    preset_id: str | None = None
    topic: TopicIn | None = None


def build_topic(body: SearchIn) -> tuple[Topic, str]:
    """The topic exactly as the user gave it: a preset from topics/*.yaml, or a custom name + definition.
    A custom topic never inherits anything from a preset; no definition → neutral default; no keyword lists."""
    if body.preset_id:
        if body.preset_id not in presets():
            raise HTTPException(404, "unknown preset")
        topic_path, topic = presets()[body.preset_id]
        return topic, str(topic_path.relative_to(ROOT))
    if body.topic:
        name = body.topic.name.strip()
        definition = body.topic.definition.strip() or DEFAULT_DEFINITION.format(name=name)
        topic = Topic(name=name, definition=definition, include=body.topic.include, exclude=body.topic.exclude)
        return topic, f"ui:{name}"
    raise HTTPException(422, "preset_id or topic required")


@app.get("/api/pool")
def pool() -> list[dict]:
    """Demo pool rows (for 'Analyzing…' placeholders while a run is in progress)."""
    df = pd.read_csv(ROOT / DEMO_POOL, dtype={"lang": str}, keep_default_na=False)
    return df[["affair_id", "body_key", "lang", "begin_date", "title"]].to_dict("records")


@app.post("/api/search")
def search(body: SearchIn) -> StreamingResponse:
    """Classify the demo pool live; streams NDJSON (run, item…, done). Closing the connection cancels."""
    settings = get_settings()
    if not check_model(settings)["reachable"]:
        raise HTTPException(503, "model endpoint unreachable — cached results only")
    topic, topic_ref = build_topic(body)
    rows = pd.read_csv(ROOT / DEMO_POOL, dtype={"lang": str}, keep_default_na=False).to_dict("records")
    prompt = load_prompt(PROMPT_TEMPLATE)
    s = store()
    run = start_run(RESULTS_DIR, prompt, topic, Path(topic_ref), settings, sample_file=str(DEMO_POOL),
                    notes="ui live search")
    s.add_run(run, topic)
    cancel = threading.Event()

    def stream():
        n = 0
        yield json.dumps({"type": "run", "run_id": run.run_id, "n": len(rows), "topic_name": topic.name,
                          "definition": topic.definition, "include": topic.include, "exclude": topic.exclude,
                          "has_keywords": bool(topic.keywords)}, ensure_ascii=False) + "\n"
        try:
            for record in iter_classify(settings, s, RESULTS_DIR, run, topic, prompt, rows, cancel):
                n += 1
                item = next((i for i in s.run_items(run.run_id) if i["prediction_id"] == record["prediction_id"]))
                yield json.dumps({"type": "item", "done": n, "item": item}, ensure_ascii=False) + "\n"
            yield json.dumps({"type": "done", "done": n}) + "\n"
        finally:
            cancel.set()
            s.finish_run(run.run_id, n)

    return StreamingResponse(stream(), media_type="application/x-ndjson")


class ReviewIn(BaseModel):
    prediction_id: int
    decision: str
    corrected_label: str | None = None
    note: str = ""
    reviewer: str = "ui"


@app.post("/api/reviews")
def add_review(body: ReviewIn) -> dict:
    s = store()
    try:
        review_id = s.add_review(body.prediction_id, body.decision, body.corrected_label, body.reviewer, body.note)
    except sqlite3.Error as e:  # CHECK / FK violations → client error, never silently ignored
        raise HTTPException(422, f"review rejected: {e}")
    return {"review_id": review_id, "reviews": s.reviews(body.prediction_id)}


@app.get("/api/export.json")
def export_json(run_id: str) -> JSONResponse:
    items = store().run_items(run_id)
    return JSONResponse([{k: i.get(k) for k in EXPORT_FIELDS} for i in items])


@app.get("/api/export.csv")
def export_csv(run_id: str) -> Response:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=EXPORT_FIELDS)
    writer.writeheader()
    for i in store().run_items(run_id):
        writer.writerow({k: i.get(k) for k in EXPORT_FIELDS})
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="parltopics_{run_id}.csv"'})


@app.get("/api/metrics")
def metrics() -> JSONResponse:
    path = RESULTS_DIR / "metrics.json"
    if not path.exists():
        raise HTTPException(404, "results/metrics.json not found — run make eval")
    return JSONResponse(json.loads(path.read_text()))


@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


app.mount("/", StaticFiles(directory=WEB_DIR), name="web")
