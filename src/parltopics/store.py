"""SQLite store. Predictions and reviews are append-only; reviews never touch predictions."""

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from parltopics.runlog import RunManifest
from parltopics.sources.api import Affair
from parltopics.sources.assemble import SourceText
from parltopics.topics import Topic

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS affairs (
    id INTEGER PRIMARY KEY, body_key TEXT NOT NULL, body_type TEXT, number TEXT, type TEXT,
    begin_date TEXT, title_json TEXT NOT NULL, url_external_json TEXT NOT NULL, url_api TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sources (
    text_sha256 TEXT PRIMARY KEY, affair_id INTEGER NOT NULL REFERENCES affairs(id), lang TEXT NOT NULL,
    lang_source TEXT NOT NULL, detected_lang TEXT, lang_mismatch INTEGER NOT NULL, title TEXT NOT NULL,
    title_only INTEGER NOT NULL, truncated INTEGER NOT NULL, cut_section TEXT, chars_lost INTEGER NOT NULL,
    n_chars_full INTEGER NOT NULL, url TEXT NOT NULL, text TEXT NOT NULL, assembled_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS topics (
    id TEXT PRIMARY KEY, kind TEXT NOT NULL, name TEXT NOT NULL, definition TEXT NOT NULL, topic_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY, started_at TEXT NOT NULL, finished_at TEXT, model TEXT NOT NULL, base_url_host TEXT,
    prompt_template TEXT NOT NULL, prompt_version TEXT NOT NULL, template_sha TEXT NOT NULL,
    topic_sha TEXT NOT NULL REFERENCES topics(id), fewshot_sha TEXT NOT NULL, params_sha TEXT NOT NULL,
    params_json TEXT NOT NULL, topic_name TEXT NOT NULL, git_commit TEXT, sample_file TEXT, notes TEXT,
    n_rows INTEGER, manifest_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL REFERENCES runs(id),
    affair_id INTEGER NOT NULL, topic_id TEXT NOT NULL REFERENCES topics(id),
    source_sha256 TEXT REFERENCES sources(text_sha256), lang TEXT, gold INTEGER, body_key TEXT, title TEXT,
    label TEXT, confidence REAL, evidence TEXT, rationale TEXT, verify_ok INTEGER, verify_method TEXT,
    verify_score REAL, inconsistent INTEGER, keyword_absent INTEGER, tech_vocab_absent INTEGER,
    status TEXT NOT NULL CHECK (status IN
        ('ok', 'evidence_failed', 'parse_error', 'llm_error', 'invalid_label', 'lang_missing', 'fetch_error')),
    model TEXT, latency_ms INTEGER, tok_in INTEGER, tok_out INTEGER, tokens_estimated INTEGER, repaired INTEGER,
    error TEXT, raw_json TEXT, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS predictions_run ON predictions(run_id);
CREATE TABLE IF NOT EXISTS reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT, prediction_id INTEGER NOT NULL REFERENCES predictions(id),
    decision TEXT NOT NULL CHECK (decision IN ('confirm', 'reject', 'correct')),
    corrected_label TEXT CHECK (decision != 'correct' OR corrected_label IS NOT NULL),
    reviewer TEXT, note TEXT, created_at TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS predictions_no_update BEFORE UPDATE ON predictions
    BEGIN SELECT RAISE(ABORT, 'predictions are append-only'); END;
CREATE TRIGGER IF NOT EXISTS predictions_no_delete BEFORE DELETE ON predictions
    BEGIN SELECT RAISE(ABORT, 'predictions are append-only'); END;
CREATE TRIGGER IF NOT EXISTS reviews_no_update BEFORE UPDATE ON reviews
    BEGIN SELECT RAISE(ABORT, 'reviews are append-only'); END;
CREATE TRIGGER IF NOT EXISTS reviews_no_delete BEFORE DELETE ON reviews
    BEGIN SELECT RAISE(ABORT, 'reviews are append-only'); END;
"""

PREDICTION_COLUMNS = (
    "run_id", "affair_id", "source_sha256", "lang", "gold", "body_key", "title", "label", "confidence", "evidence",
    "rationale", "verify_ok", "verify_method", "verify_score", "inconsistent", "keyword_absent",
    "tech_vocab_absent", "status", "model", "latency_ms", "tok_in", "tok_out", "tokens_estimated", "repaired",
    "error", "raw_json",
)
BOOL_COLUMNS = {"verify_ok", "inconsistent", "keyword_absent", "tech_vocab_absent", "tokens_estimated", "repaired",
                "lang_mismatch", "title_only", "truncated"}
SOURCE_FIELDS = ("lang_source", "detected_lang", "lang_mismatch", "title_only", "truncated", "cut_section",
                 "chars_lost", "n_chars_full", "url")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row(row: sqlite3.Row) -> dict:
    return {k: (bool(row[k]) if k in BOOL_COLUMNS and row[k] is not None else row[k]) for k in row.keys()}


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        self.lock = threading.Lock()

    def add_run(self, manifest: RunManifest, topic: Topic) -> None:
        fp = manifest.fingerprint
        with self.lock:
            self.db.execute(
                "INSERT OR IGNORE INTO topics VALUES (?, 'adhoc', ?, ?, ?)",
                (fp.parts["topic"], topic.name, topic.definition, topic.model_dump_json()),
            )
            self.db.execute(
                "INSERT INTO runs VALUES (?,?,NULL,?,?,?,?,?,?,?,?,?,?,?,?,?,NULL,?)",
                (manifest.run_id, manifest.started_at, fp.params["model"], manifest.base_url_host,
                 manifest.prompt_template, fp.prompt_version, fp.parts["template"], fp.parts["topic"],
                 fp.parts["fewshot"], fp.parts["params"], json.dumps(fp.params), manifest.topic_name,
                 manifest.git_commit, manifest.sample_file, manifest.notes, manifest.model_dump_json()),
            )

    def finish_run(self, run_id: str, n_rows: int) -> None:
        with self.lock:
            self.db.execute("UPDATE runs SET finished_at = ?, n_rows = ? WHERE id = ?", (_now(), n_rows, run_id))

    def add_source(self, affair: Affair, source: SourceText) -> None:
        with self.lock:
            self.db.execute(
                "INSERT OR REPLACE INTO affairs VALUES (?,?,?,?,?,?,?,?,?)",
                (affair.id, affair.body.key, affair.body.type, affair.number, affair.type, affair.begin_date,
                 json.dumps(affair.title, ensure_ascii=False), json.dumps(affair.url_external), affair.url_api),
            )
            self.db.execute(
                "INSERT OR IGNORE INTO sources VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (source.sha256, affair.id, source.lang, source.lang_source, source.detected_lang,
                 source.lang_mismatch, source.title, source.title_only, source.truncated, source.cut_section,
                 source.chars_lost, source.n_chars_full, source.url, source.text, _now()),
            )

    def add_prediction(self, record: dict) -> int:
        run = self.db.execute("SELECT topic_sha FROM runs WHERE id = ?", (record["run_id"],)).fetchone()
        if run is None:
            raise sqlite3.IntegrityError(f"unknown run {record['run_id']}")
        values = [record.get(c) for c in PREDICTION_COLUMNS]
        with self.lock:
            cur = self.db.execute(
                f"INSERT INTO predictions ({', '.join(PREDICTION_COLUMNS)}, topic_id, created_at) "
                f"VALUES ({', '.join('?' * len(PREDICTION_COLUMNS))}, ?, ?)",
                (*values, run["topic_sha"], _now()),
            )
        return cur.lastrowid

    def add_review(
        self, prediction_id: int, decision: str, corrected_label: str | None = None,
        reviewer: str = "", note: str = "",
    ) -> int:
        with self.lock:
            cur = self.db.execute(
                "INSERT INTO reviews (prediction_id, decision, corrected_label, reviewer, note, created_at) "
                "VALUES (?,?,?,?,?,?)",
                (prediction_id, decision, corrected_label, reviewer, note, _now()),
            )
        return cur.lastrowid

    def runs(self) -> list[dict]:
        rows = self.db.execute(
            "SELECT r.id, r.started_at, r.finished_at, r.model, r.prompt_template, r.prompt_version, r.topic_name, "
            "r.sample_file, r.n_rows, r.notes, COUNT(p.id) AS n_predictions FROM runs r "
            "LEFT JOIN predictions p ON p.run_id = r.id GROUP BY r.id ORDER BY r.started_at DESC, r.id DESC"
        )
        return [_row(r) for r in rows]

    def run(self, run_id: str) -> dict:
        row = self.db.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            raise KeyError(run_id)
        out = _row(row)
        out["manifest"] = json.loads(out.pop("manifest_json"))
        return out

    def predictions(self, run_id: str) -> list[dict]:
        rows = self.db.execute(
            f"SELECT p.*, {', '.join('s.' + f for f in SOURCE_FIELDS)} FROM predictions p "
            "LEFT JOIN sources s ON s.text_sha256 = p.source_sha256 WHERE p.run_id = ? ORDER BY p.id",
            (run_id,),
        )
        return [_row(r) for r in rows]

    def reviews(self, prediction_id: int) -> list[dict]:
        rows = self.db.execute("SELECT * FROM reviews WHERE prediction_id = ? ORDER BY id", (prediction_id,))
        return [_row(r) for r in rows]
