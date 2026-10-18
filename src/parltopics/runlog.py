"""Run manifests and per-call JSONL logs under results/runs/<run_id>/ (gitignored)."""

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from pydantic import BaseModel

from parltopics.classify import Prediction
from parltopics.config import Settings
from parltopics.prompts import Prompt
from parltopics.topics import Topic

LOGGED_FIELDS = (
    "run_id", "affair_id", "lang", "topic", "label", "confidence", "status", "verify_ok", "verify_method",
    "verify_score", "inconsistent", "model", "source_sha256", "latency_ms", "tok_in", "tok_out",
    "tokens_estimated", "repaired", "error",
)


class Fingerprint(BaseModel):
    prompt_version: str  # sha256 over all parts: changes whenever anything that shapes the prompt changes
    parts: dict[str, str]  # template | topic | fewshot | params → sha256 of that part
    params: dict


class RunManifest(BaseModel):
    run_id: str
    started_at: str
    prompt_template: str
    fingerprint: Fingerprint
    topic_name: str
    topic_path: str
    base_url_host: str
    git_commit: str | None
    sample_file: str | None
    notes: str


def _sha(obj: object) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def fingerprint(prompt: Prompt, topic: Topic, settings: Settings, fewshot: list[dict] | None = None) -> Fingerprint:
    params = {
        "model": settings.llm_name,
        "temperature": settings.llm_temperature,
        "max_tokens": settings.llm_max_tokens,
        "json_mode": settings.llm_json_mode,
        "max_input_chars": settings.max_input_chars,
        "title_only_conf_cap": settings.title_only_conf_cap,
    }
    parts = {
        "template": prompt.sha,
        "topic": _sha(topic.model_dump()),
        "fewshot": _sha(fewshot or []),
        "params": _sha(params),
    }
    return Fingerprint(prompt_version=_sha(parts), parts=parts, params=params)


def new_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def git_commit() -> str | None:
    try:
        sha = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return None
    return f"{sha}{'-dirty' if dirty.strip() else ''}"


def start_run(
    results_dir: Path, prompt: Prompt, topic: Topic, topic_path: Path, settings: Settings,
    sample_file: str | None = None, notes: str = "",
) -> RunManifest:
    manifest = RunManifest(
        run_id=new_run_id(),
        started_at=datetime.now(timezone.utc).isoformat(),
        prompt_template=prompt.version,
        fingerprint=fingerprint(prompt, topic, settings),
        topic_name=topic.name,
        topic_path=str(topic_path),
        base_url_host=urlparse(settings.llm_base_url).hostname or "",
        git_commit=git_commit(),
        sample_file=sample_file,
        notes=notes,
    )
    run_dir = results_dir / "runs" / manifest.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "manifest.json").write_text(manifest.model_dump_json(indent=2))
    return manifest


def log_call(results_dir: Path, prediction: Prediction) -> Path:
    path = results_dir / "runs" / prediction.run_id / "calls.jsonl"
    row = {k: getattr(prediction, k) for k in LOGGED_FIELDS}
    row["logged_at"] = datetime.now(timezone.utc).isoformat()
    with path.open("a") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return path
