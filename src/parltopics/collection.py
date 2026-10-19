"""Whole collections: every affair of one parliament since a date (docs/08 phase 1).

ingest → fetch and assemble every affair once (data-quality report); index → classify every ingested affair for a
topic or scheme, resumable per prompt_version; update → ingest again, classify only what is new (or failed)."""

import statistics
import threading
import time
from collections import Counter
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE

from parltopics.batch import iter_classify, iter_records, scheme_classifier, scheme_object
from parltopics.config import Settings
from parltopics.evaluate.metrics import is_predicted_match
from parltopics.prompts import load_prompt
from parltopics.runlog import fingerprint, start_run
from parltopics.sources.api import Affair, OPDError
from parltopics.sources.assemble import TRANSLATED_BODY_TYPES, LangMissing, SourceText, assemble
from parltopics.sources.router import AffairSource
from parltopics.store import RETRY_STATUSES, Store
from parltopics.topics import load_topic

SCHEME_PREFIX = "scheme:"


def collection_ref(body_key: str) -> str:
    """The runs' sample_file for a collection; results are found by it."""
    return f"collection:{body_key}"


def assemble_for_collection(settings: Settings, affair: Affair) -> SourceText:
    """Cantonal: the parliament's language. Federal (translated): the first complete official version (D67)."""
    if affair.body.type not in TRANSLATED_BODY_TYPES:
        return assemble(affair, settings.max_input_chars)
    errors = []
    for lang in settings.translated_lang_order:
        try:
            return assemble(affair, settings.max_input_chars, lang)
        except LangMissing as e:
            errors.append(str(e))
    raise LangMissing("; ".join(errors))


def quality_report(items: list[dict]) -> dict:
    ok = [i for i in items if i["status"] == "ok"]
    chars = sorted(i["n_chars_full"] for i in ok)
    return {
        "affairs": len(items),
        "status": dict(Counter(i["status"] for i in items)),
        "lang": dict(Counter(i["lang"] for i in ok)),
        "title_only": sum(bool(i["title_only"]) for i in ok),
        "lang_mismatch": sum(bool(i["lang_mismatch"]) for i in ok),
        "truncated": sum(bool(i["truncated"]) for i in ok),
        "median_chars": statistics.median(chars) if chars else None,
        "p90_chars": chars[int(0.9 * (len(chars) - 1))] if chars else None,
    }


def ingest(settings: Settings, store: Store, body_key: str, since: str, source_of: AffairSource | None = None,
           workers: int = 8) -> dict:
    """List the body's affairs (fresh, not from cache), fetch + assemble new and previously failed ones."""
    source_of = source_of or AffairSource(settings)
    listed = [r for r in source_of.api.list_affairs_since(body_key, since, fresh=True)
              if r["type_en"] not in settings.collection_exclude_types]
    known = {i["affair_id"]: i["status"] for i in store.items(body_key)}
    todo = [r for r in listed if known.get(r["id"]) != "ok"]
    ingest_id = store.start_ingest(body_key, since, len(listed))

    def one(row: dict) -> dict:
        item = {"affair_id": row["id"], "begin_date": row["begin_date"], "type": row["type_en"]}
        try:
            affair = source_of.get_affair(row["id"], body_key)
        except OPDError as e:
            return item | {"status": "fetch_error", "error": str(e)}
        try:
            source = assemble_for_collection(settings, affair)
        except LangMissing as e:
            return item | {"status": "lang_missing", "error": str(e), "title": next(iter(affair.title.values()), "")}
        store.add_source(affair, source)
        return item | {"status": "ok", "title": source.title, "text_sha256": source.sha256}

    with ThreadPoolExecutor(workers) as pool:
        for item in pool.map(one, todo):
            store.put_item(body_key, ingest_id, item)
    new_ids = [r["id"] for r in listed if r["id"] not in known]
    report = {"body_key": body_key, "since": since, "listed": len(listed), "fetched": len(todo),
              "new": len(new_ids), "excluded_types": settings.collection_exclude_types,
              "quality": quality_report(store.items(body_key))}
    store.finish_ingest(ingest_id, len(new_ids), report)
    return report | {"ingest_id": ingest_id, "new_ids": new_ids}


def target_version(settings: Settings, target: str, template: str | None = None) -> tuple:
    """target = 'topics/<id>.yaml' (ad-hoc) or 'scheme:<id>' → (prompt, topic or scheme, prompt_version)."""
    if target.startswith(SCHEME_PREFIX):
        prompt = load_prompt(template or "standard_v1")
        obj = scheme_object(settings, target[len(SCHEME_PREFIX):])
    else:
        prompt = load_prompt(template or "adhoc_v5")
        obj = load_topic(Path(target))
    return prompt, obj, fingerprint(prompt, obj, settings).prompt_version


class Progress:
    """Counts affairs (a standard-mode affair yields several records); reports every `every` affairs."""

    def __init__(self, total: int, report: Callable[[str], None] | None, every: int = 250):
        self.total, self.report, self.every = total, report, every
        self.affairs: set[int] = set()
        self.records = self.failed = self.tok_in = self.tok_out = 0
        self.started = time.monotonic()

    def add(self, record: dict) -> None:
        self.records += 1
        self.tok_in += record.get("tok_in") or 0
        self.tok_out += record.get("tok_out") or 0
        self.failed += record["status"] in RETRY_STATUSES
        before = len(self.affairs)
        self.affairs.add(record["affair_id"])
        if self.report and len(self.affairs) > before and (len(self.affairs) % self.every == 0
                                                           or len(self.affairs) == self.total):
            self.report(self.line())

    def line(self) -> str:
        n, minutes = len(self.affairs), (time.monotonic() - self.started) / 60
        rate = n / minutes if minutes else 0
        eta = (self.total - n) / rate if rate else 0
        return (f"{n}/{self.total} affairs  {rate:.0f}/min  ETA {eta:.0f} min  "
                f"tokens in {self.tok_in:,} out {self.tok_out:,}  transient failures {self.failed}")


def index(settings: Settings, store: Store, results_dir: Path, body_key: str, target: str,
          template: str | None = None, only: set[int] | None = None, passes: int = 2,
          report: Callable[[str], None] | None = None, cancel: threading.Event | None = None) -> dict:
    """Classify every ingested affair of the body that has no complete result for this prompt_version yet.
    A second pass retries transient failures. Re-running continues where the last run stopped.
    The model sees the text stored at ingest (no re-fetch). Setting `cancel` stops after the calls in flight."""
    prompt, obj, version = target_version(settings, target, template)
    ref = collection_ref(body_key)
    items = [i for i in store.items(body_key) if i["status"] == "ok" and (only is None or i["affair_id"] in only)]
    ids = {i["affair_id"] for i in items}

    def stored(row: dict) -> SourceText:
        return store.source_text(row["text_sha256"], row["affair_id"])

    run_ids = []
    for attempt in range(1, passes + 1):
        done = store.done_affairs(ref, version)
        rows = [{"affair_id": i["affair_id"], "body_key": body_key, "lang": i["lang"], "gold": "",
                 "title": i["title"] or "", "text_sha256": i["text_sha256"]} for i in items if i["affair_id"] not in done]
        if not rows:
            break
        run = start_run(results_dir, prompt, obj, Path(target), settings, sample_file=ref,
                        notes=f"index {body_key} {target} pass {attempt}")
        store.add_run(run, obj)
        if target.startswith(SCHEME_PREFIX):
            classify_one = scheme_classifier(settings, target[len(SCHEME_PREFIX):], prompt, run.run_id)
            records = iter_records(settings, store, run, rows, classify_one, cancel, stored_source=stored)
        else:
            records = iter_classify(settings, store, results_dir, run, obj, prompt, rows, cancel, stored_source=stored)
        progress = Progress(len(rows), report)
        for record in records:
            progress.add(record)
        store.finish_run(run.run_id, progress.records)
        run_ids.append(run.run_id)
        if report:
            report(f"pass {attempt} run {run.run_id}: {progress.line()}")
        if cancel is not None and cancel.is_set():
            break
    done = store.done_affairs(ref, version) & ids
    return {"body_key": body_key, "target": target, "prompt_template": prompt.version, "prompt_version": version,
            "runs": run_ids, "affairs": len(ids), "done": len(done), "not_done": len(ids - done)}


def latest_targets(store: Store, body_key: str) -> dict[str, dict]:
    """topic_path → its most recent indexed run (template + prompt_version)."""
    return {t["topic_path"]: t for t in store.collection_targets(collection_ref(body_key))}


def update(settings: Settings, store: Store, results_dir: Path, body_key: str,
           report: Callable[[str], None] | None = None, source_of: AffairSource | None = None) -> dict:
    """Ingest again with the first ingest's start date, then index every target already indexed on this body.
    Only affairs without a complete result are classified: the new ones and earlier transient failures.
    A target whose topic file changed since is skipped (that is a full re-index, not an update)."""
    last = store.last_ingest(body_key)
    if last is None:
        raise ValueError(f"{body_key}: nothing ingested yet; run `parltopics ingest` first")
    ingested = ingest(settings, store, body_key, last["since"], source_of)
    new_ids = set(ingested["new_ids"])
    targets, skipped = [], []
    for path, t in latest_targets(store, body_key).items():
        if target_version(settings, path, t["prompt_template"])[2] != t["prompt_version"]:
            skipped.append(path)
            continue
        targets.append(index(settings, store, results_dir, body_key, path, t["prompt_template"], report=report))
    return {"ingest": ingested, "new_ids": sorted(new_ids), "indexed": targets, "skipped_changed": skipped}


EXPORT_COLUMNS = ("affair_id", "number", "type", "date", "title", "lang", "url", "label", "scheme_code", "confidence",
                  "shown_as_match", "evidence", "evidence_verified", "rationale", "status", "review", "review_label",
                  "reviewed_at", "prediction_id", "run_id")


def export_frame(rows: list[dict]) -> pd.DataFrame:
    """Rows as an Excel-safe table: fixed headers (also when empty), and control characters from scanned PDFs
    (not allowed in .xlsx) removed from text cells."""
    clean = [{k: ILLEGAL_CHARACTERS_RE.sub("", v) if isinstance(v, str) else v for k, v in r.items()} for r in rows]
    return pd.DataFrame(clean, columns=list(EXPORT_COLUMNS))


def export_rows(store: Store, body_key: str, prompt_version: str, threshold: float) -> list[dict]:
    """One row per prediction (standard mode: per label) of the run that counts for each affair."""
    out = []
    for r in store.collection_results(collection_ref(body_key), prompt_version):
        out.append({
            "affair_id": r["affair_id"], "number": r["number"], "type": r["type"], "date": r["begin_date"],
            "title": r["title"], "lang": r["lang"], "url": r["url"],
            "label": r["label"], "scheme_code": r["scheme_code"], "confidence": r["confidence"],
            "shown_as_match": is_predicted_match(r) and r["scheme_code"] is None
            and (r["confidence"] or 0) >= threshold,
            "evidence": r["evidence"], "evidence_verified": r["verify_ok"], "rationale": r["rationale"],
            "status": r["status"], "review": r["review_decision"] or "", "review_label": r["review_label"] or "",
            "reviewed_at": r["reviewed_at"] or "", "prediction_id": r["prediction_id"], "run_id": r["run_id"],
        })
    return out
