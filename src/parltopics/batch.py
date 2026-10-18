"""Run one topic over a set of affairs: fetch → assemble → classify → verify → store. Used by CLI and API."""

import threading
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

from parltopics.classify import classify_adhoc
from parltopics.config import Settings
from parltopics.llm import LLMClient
from parltopics.prompts import Prompt, load_prompt
from parltopics.runlog import RunManifest, log_call, start_run
from parltopics.sources.api import OPDError
from parltopics.sources.assemble import LangMissing, assemble
from parltopics.sources.router import AffairSource
from parltopics.store import Store
from parltopics.topics import Topic, keyword_absent, load_topic, tech_vocab_absent


def iter_classify(
    settings: Settings, store: Store, results_dir: Path, run: RunManifest, topic: Topic, prompt: Prompt,
    rows: list[dict], cancel: threading.Event | None = None,
) -> Iterator[dict]:
    """Classify rows (affair_id, body_key, lang, gold, title) in parallel; store and yield each record as it
    finishes. Setting `cancel` stops new work; finished records are kept."""
    source_of, llm = AffairSource(settings), LLMClient(settings)

    def one(row: dict) -> dict:
        base = {"run_id": run.run_id, "affair_id": int(row["affair_id"]), "body_key": row["body_key"],
                "gold": None if row.get("gold") in (None, "") else int(row["gold"]), "title": row["title"],
                "lang": row["lang"] or None}
        if cancel is not None and cancel.is_set():
            return base | {"status": "cancelled"}
        try:
            affair = source_of.get_affair(int(row["affair_id"]), row["body_key"])
            source = assemble(affair, settings.max_input_chars, row["lang"] or None)
        except LangMissing as e:
            return base | {"status": "lang_missing", "error": str(e)}
        except OPDError as e:
            return base | {"status": "fetch_error", "error": str(e)}
        store.add_source(affair, source)
        prediction = classify_adhoc(llm, prompt, source, topic, settings.title_only_conf_cap, run.run_id)
        log_call(results_dir, prediction)
        return base | prediction.model_dump() | {
            "title": source.title,
            "keyword_absent": keyword_absent(source.text, topic),
            "tech_vocab_absent": tech_vocab_absent(source.text, topic),
        }

    pool = ThreadPoolExecutor(settings.llm_concurrency)
    try:
        futures = [pool.submit(one, row) for row in rows]
        for future in as_completed(futures):
            record = future.result()
            if record["status"] == "cancelled":
                continue
            yield record | {"prediction_id": store.add_prediction(record)}
    finally:
        pool.shutdown(wait=False, cancel_futures=True)


def run_sample(
    settings: Settings, store: Store, sample_path: Path, topic_path: Path, results_dir: Path,
    prompt_version: str, notes: str = "", split: str | None = None,
) -> RunManifest:
    sample = pd.read_csv(sample_path, dtype={"lang": str}, keep_default_na=False)
    if split:
        sample = sample[sample.split == split]
        notes = f"{notes} [split={split}]".strip()
    topic = load_topic(topic_path)
    prompt = load_prompt(prompt_version)
    run = start_run(results_dir, prompt, topic, topic_path, settings, sample_file=str(sample_path), notes=notes)
    store.add_run(run, topic)
    n = sum(1 for _ in iter_classify(settings, store, results_dir, run, topic, prompt, sample.to_dict("records")))
    store.finish_run(run.run_id, n)
    return run
