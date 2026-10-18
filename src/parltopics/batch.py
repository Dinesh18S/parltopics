"""Run one topic over a sample file: fetch → assemble → classify → verify → log."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd

from parltopics.classify import classify_adhoc
from parltopics.config import Settings
from parltopics.llm import LLMClient
from parltopics.prompts import load_prompt
from parltopics.runlog import RunManifest, log_call, start_run
from parltopics.sources.api import OPDError
from parltopics.sources.assemble import LangMissing, assemble
from parltopics.sources.router import AffairSource
from parltopics.store import Store
from parltopics.topics import keyword_absent, load_topic, tech_vocab_absent


def run_sample(
    settings: Settings, store: Store, sample_path: Path, topic_path: Path, results_dir: Path,
    prompt_version: str, notes: str = "",
) -> RunManifest:
    sample = pd.read_csv(sample_path, dtype={"lang": str}, keep_default_na=False)
    topic = load_topic(topic_path)
    prompt = load_prompt(prompt_version)
    run = start_run(results_dir, prompt, topic, topic_path, settings, sample_file=str(sample_path), notes=notes)
    store.add_run(run, topic)
    source_of, llm = AffairSource(settings), LLMClient(settings)

    def one(row: dict) -> dict:
        base = {"run_id": run.run_id, "affair_id": int(row["affair_id"]), "body_key": row["body_key"],
                "gold": int(row["gold"]), "title": row["title"], "lang": row["lang"] or None}
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
            "keyword_absent": keyword_absent(source.text, topic),
            "tech_vocab_absent": tech_vocab_absent(source.text, topic),
        }

    n = 0
    with ThreadPoolExecutor(settings.llm_concurrency) as pool:
        for record in pool.map(one, sample.to_dict("records")):
            store.add_prediction(record)
            n += 1
    store.finish_run(run.run_id, n)
    return run
