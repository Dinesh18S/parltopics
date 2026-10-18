"""Run one topic over a set of affairs: fetch → assemble → classify → verify → store. Used by CLI and API."""

import threading
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

from parltopics.classify import classify_adhoc, classify_standard
from parltopics.config import Settings
from parltopics.llm import LLMClient
from parltopics.prompts import Prompt, load_prompt
from parltopics.runlog import RunManifest, log_call, start_run
from parltopics.schemes import load_aps_chapters, load_aps_topics, load_curia_vista
from parltopics.sources.api import OPDError
from parltopics.sources.assemble import LangMissing, SourceText, assemble
from parltopics.sources.router import AffairSource
from parltopics.store import Store
from parltopics.topics import Topic, keyword_absent, load_topic, tech_vocab_absent


def iter_classify(
    settings: Settings, store: Store, results_dir: Path, run: RunManifest, topic: Topic, prompt: Prompt,
    rows: list[dict], cancel: threading.Event | None = None,
) -> Iterator[dict]:
    """Ad-hoc mode over rows; see iter_records."""
    llm = LLMClient(settings)

    def adhoc(source: SourceText) -> list[dict]:
        prediction = classify_adhoc(llm, prompt, source, topic, settings.title_only_conf_cap, run.run_id)
        log_call(results_dir, prediction)
        return [prediction.model_dump() | {
            "title": source.title,
            "keyword_absent": keyword_absent(source.text, topic),
            "tech_vocab_absent": tech_vocab_absent(source.text, topic),
        }]

    yield from iter_records(settings, store, run, rows, adhoc, cancel)


def iter_records(
    settings: Settings, store: Store, run: RunManifest, rows: list[dict],
    classify_one: Callable[[SourceText], list[dict]], cancel: threading.Event | None = None,
) -> Iterator[dict]:
    """Fetch + assemble each row (affair_id, body_key, lang, gold, title), classify it in parallel, store and yield
    every resulting record as it finishes. Setting `cancel` stops new work; finished records are kept."""
    source_of = AffairSource(settings)

    def one(row: dict) -> list[dict]:
        base = {"run_id": run.run_id, "affair_id": int(row["affair_id"]), "body_key": row["body_key"],
                "gold": int(row["gold"]) if str(row.get("gold", "")).isdigit() else None, "title": row["title"],
                "lang": row["lang"] or None}
        if cancel is not None and cancel.is_set():
            return []
        try:
            affair = source_of.get_affair(int(row["affair_id"]), row["body_key"])
            source = assemble(affair, settings.max_input_chars, row["lang"] or None)
        except LangMissing as e:
            return [base | {"status": "lang_missing", "error": str(e)}]
        except OPDError as e:
            return [base | {"status": "fetch_error", "error": str(e)}]
        store.add_source(affair, source)
        return [base | {"title": source.title} | record for record in classify_one(source)]

    pool = ThreadPoolExecutor(settings.llm_concurrency)
    try:
        futures = [pool.submit(one, row) for row in rows]
        for future in as_completed(futures):
            for record in future.result():
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


def scheme_classifier(settings: Settings, scheme_id: str, prompt: Prompt, run_id: str) -> Callable[[SourceText], list[dict]]:
    """curia_vista: one stage over 28 areas. aps: stage 1 chapters, stage 2 topics only within the chapters whose
    evidence verified (docs/04 §4.2)."""
    raw_dir = settings.data_dir / "raw"
    llm = LLMClient(settings)
    fallback = settings.scheme_label_fallback
    cap = settings.title_only_conf_cap
    tokens = settings.llm_max_tokens_standard
    if scheme_id == "curia_vista":
        scheme = load_curia_vista(raw_dir)
        return lambda source: classify_standard(llm, prompt, source, scheme, fallback, cap, run_id, tokens)
    if scheme_id == "aps":
        chapters = load_aps_chapters(raw_dir)

        def aps(source: SourceText) -> list[dict]:
            stage1 = classify_standard(llm, prompt, source, chapters, fallback, cap, run_id, tokens)
            chosen = [r["label"] for r in stage1 if r["status"] == "ok" and r["label"] not in (None, "NONE_OTHER")]
            if not chosen:
                return stage1
            topics = load_aps_topics(raw_dir, chosen)
            return stage1 + classify_standard(llm, prompt, source, topics, fallback, cap, run_id, tokens)
        return aps
    raise ValueError(f"unknown scheme {scheme_id}")


def scheme_object(settings: Settings, scheme_id: str):
    raw_dir = settings.data_dir / "raw"
    return {"curia_vista": load_curia_vista, "aps": load_aps_chapters}[scheme_id](raw_dir)


def run_standard_sample(
    settings: Settings, store: Store, sample_path: Path, scheme_id: str, results_dir: Path, prompt_version: str,
    notes: str = "", split: str | None = None,
) -> RunManifest:
    sample = pd.read_csv(sample_path, dtype={"lang": str}, keep_default_na=False)
    if split:
        sample = sample[sample.split == split]
        notes = f"{notes} [split={split}]".strip()
    scheme = scheme_object(settings, scheme_id)
    prompt = load_prompt(prompt_version)
    run = start_run(results_dir, prompt, scheme, Path(f"scheme:{scheme_id}"), settings, sample_file=str(sample_path),
                    notes=notes)
    store.add_run(run, scheme)
    classify_one = scheme_classifier(settings, scheme_id, prompt, run.run_id)
    n = sum(1 for _ in iter_records(settings, store, run, sample.to_dict("records"), classify_one))
    store.finish_run(run.run_id, n)
    return run
