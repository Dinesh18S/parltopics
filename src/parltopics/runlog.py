"""Per-run JSONL call log under results/runs/<run_id>/ (gitignored)."""

import json
from datetime import datetime, timezone
from pathlib import Path

from parltopics.classify import Prediction

LOGGED_FIELDS = (
    "affair_id", "lang", "topic", "label", "confidence", "status", "model", "prompt_version",
    "prompt_sha", "source_sha256", "latency_ms", "tok_in", "tok_out", "tokens_estimated", "repaired", "error",
)


def new_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def log_call(results_dir: Path, run_id: str, prediction: Prediction) -> Path:
    path = results_dir / "runs" / run_id / "calls.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {k: getattr(prediction, k) for k in LOGGED_FIELDS}
    row["logged_at"] = datetime.now(timezone.utc).isoformat()
    with path.open("a") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return path
