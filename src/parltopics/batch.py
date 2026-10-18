"""Run one topic over a sample file: fetch → assemble → classify → verify → log."""

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd

from parltopics.classify import classify_adhoc
from parltopics.config import Settings
from parltopics.llm import LLMClient
from parltopics.prompts import load_prompt
from parltopics.runlog import RunManifest, log_call, start_run
from parltopics.sources.api import OPDClient, OPDError
from parltopics.sources.assemble import LangMissing, assemble
from parltopics.topics import keyword_absent, load_topic


def run_sample(
    settings: Settings, sample_path: Path, topic_path: Path, results_dir: Path, prompt_version: str, notes: str = ""
) -> RunManifest:
    sample = pd.read_csv(sample_path, dtype={"lang": str}, keep_default_na=False)
    topic = load_topic(topic_path)
    prompt = load_prompt(prompt_version)
    run = start_run(results_dir, prompt, topic, topic_path, settings, sample_file=str(sample_path), notes=notes)
    client, llm = OPDClient(settings), LLMClient(settings)

    def one(row: dict) -> dict:
        base = {"run_id": run.run_id, "affair_id": int(row["affair_id"]), "body_key": row["body_key"],
                "gold": int(row["gold"]), "title": row["title"]}
        try:
            source = assemble(client.get_affair(int(row["affair_id"])), settings.max_input_chars, row["lang"] or None)
        except LangMissing as e:
            return base | {"status": "lang_missing", "label": None, "lang": row["lang"], "error": str(e)}
        except OPDError as e:
            return base | {"status": "fetch_error", "label": None, "lang": row["lang"], "error": str(e)}
        prediction = classify_adhoc(llm, prompt, source, topic, settings.title_only_conf_cap, run.run_id)
        log_call(results_dir, prediction)
        return base | prediction.model_dump(exclude={"raw_json"}) | {
            "lang_source": source.lang_source,
            "lang_mismatch": source.lang_mismatch,
            "title_only": source.title_only,
            "truncated": source.truncated,
            "cut_section": source.cut_section,
            "chars_lost": source.chars_lost,
            "n_chars_full": source.n_chars_full,
            "keyword_absent": keyword_absent(source.text, topic.keywords),
            "url": source.url,
        }

    with ThreadPoolExecutor(settings.llm_concurrency) as pool:
        records = list(pool.map(one, sample.to_dict("records")))
    out = results_dir / "runs" / run.run_id / "predictions.jsonl"
    out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records))
    return run
