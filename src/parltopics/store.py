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
CREATE TABLE IF NOT EXISTS ingests (
    id INTEGER PRIMARY KEY AUTOINCREMENT, body_key TEXT NOT NULL, since TEXT NOT NULL, started_at TEXT NOT NULL,
    finished_at TEXT, n_listed INTEGER, n_new INTEGER, report_json TEXT
);
CREATE TABLE IF NOT EXISTS collection_items (
    body_key TEXT NOT NULL, affair_id INTEGER NOT NULL, begin_date TEXT, type TEXT, title TEXT,
    text_sha256 TEXT REFERENCES sources(text_sha256),
    status TEXT NOT NULL CHECK (status IN ('ok', 'lang_missing', 'fetch_error')), error TEXT,
    first_ingest INTEGER NOT NULL REFERENCES ingests(id), first_seen_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    PRIMARY KEY (body_key, affair_id)
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
    "tech_vocab_absent", "evidence_retried", "evidence_recovered", "scheme_code", "rank", "status", "model", "latency_ms", "tok_in", "tok_out", "tokens_estimated", "repaired",
    "error", "raw_json",
)
BOOL_COLUMNS = {"verify_ok", "inconsistent", "evidence_retried", "evidence_recovered", "keyword_absent", "tech_vocab_absent", "tokens_estimated", "repaired",
                "lang_mismatch", "title_only", "truncated"}
# added after S5; migrated on open
ADDED_PREDICTION_COLUMNS = {"evidence_retried": "INTEGER", "evidence_recovered": "INTEGER", "scheme_code": "TEXT",
                            "rank": "INTEGER"}
SOURCE_FIELDS = ("lang_source", "detected_lang", "lang_mismatch", "title_only", "truncated", "cut_section",
                 "chars_lost", "n_chars_full", "url")


RETRY_STATUSES = ("llm_error", "fetch_error")  # transient: retried. parse_error is deterministic at temperature 0 (D67)
_RETRY_SQL = ", ".join(f"'{s}'" for s in RETRY_STATUSES)

ITEMS_SELECT = (
    "SELECT p.id AS prediction_id, p.run_id, p.affair_id, p.lang, p.gold, p.body_key, p.title, p.label, p.confidence, "
    "p.evidence, p.rationale, p.verify_ok, p.verify_method, p.inconsistent, p.keyword_absent, p.tech_vocab_absent, "
    "p.status, p.evidence_recovered, p.scheme_code, p.rank, a.number, a.type, a.begin_date, a.body_type, s.url, "
    "s.title_only, s.truncated, r.decision AS review_decision, r.corrected_label AS review_label, "
    "r.created_at AS reviewed_at "
    "FROM predictions p LEFT JOIN affairs a ON a.id = p.affair_id "
    "LEFT JOIN sources s ON s.text_sha256 = p.source_sha256 "
    "LEFT JOIN reviews r ON r.id = (SELECT MAX(id) FROM reviews WHERE prediction_id = p.id) "
)
# per affair of a collection: the run whose predictions count — newest complete one, else newest
_BEST_RUN_SQL = f"""
WITH cand AS (
    SELECT p.affair_id, p.run_id, r.started_at, SUM(p.status IN ({_RETRY_SQL})) AS n_fail
    FROM predictions p JOIN runs r ON r.id = p.run_id
    WHERE r.sample_file = ? AND r.prompt_version = ? GROUP BY p.affair_id, p.run_id
), best AS (
    SELECT affair_id, run_id, n_fail FROM (
        SELECT *, ROW_NUMBER() OVER (PARTITION BY affair_id ORDER BY n_fail > 0, started_at DESC) AS rn FROM cand
    ) WHERE rn = 1
)"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row(row: sqlite3.Row) -> dict:
    return {k: (bool(row[k]) if k in BOOL_COLUMNS and row[k] is not None else row[k]) for k in row.keys()}


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False, isolation_level=None, timeout=30)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")  # CLI runs and the UI server write the same file
        self.db.executescript(SCHEMA)
        have = {r["name"] for r in self.db.execute("PRAGMA table_info(predictions)")}
        for column, sql_type in ADDED_PREDICTION_COLUMNS.items():
            if column not in have:
                self.db.execute(f"ALTER TABLE predictions ADD COLUMN {column} {sql_type}")
        self.db.execute(  # source links in the text's own language when the affair has one (D60)
            "UPDATE sources SET url = (SELECT json_extract(a.url_external_json, '$.' || sources.lang) FROM affairs a "
            "WHERE a.id = sources.affair_id) WHERE (SELECT json_extract(a.url_external_json, '$.' || sources.lang) "
            "FROM affairs a WHERE a.id = sources.affair_id) IS NOT NULL")
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
                "INSERT INTO sources VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(text_sha256) DO UPDATE SET url = excluded.url",
                (source.sha256, affair.id, source.lang, source.lang_source, source.detected_lang,
                 source.lang_mismatch, source.title, source.title_only, source.truncated, source.cut_section,
                 source.chars_lost, source.n_chars_full, source.url, source.text, _now()),
            )

    def source_text(self, text_sha256: str) -> SourceText:
        """A stored text as the classifier needs it (section headers are not stored)."""
        row = self.db.execute("SELECT * FROM sources WHERE text_sha256 = ?", (text_sha256,)).fetchone()
        if row is None:
            raise KeyError(text_sha256)
        r = _row(row)
        return SourceText(affair_id=r["affair_id"], lang=r["lang"], lang_source=r["lang_source"],
                          detected_lang=r["detected_lang"], lang_mismatch=r["lang_mismatch"], title=r["title"],
                          text=r["text"], sha256=r["text_sha256"], sections=[], title_only=r["title_only"],
                          truncated=r["truncated"], cut_section=r["cut_section"], chars_lost=r["chars_lost"],
                          n_chars_full=r["n_chars_full"], url=r["url"])

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

    def run_items(self, run_id: str) -> list[dict]:
        """Predictions of a run with affair metadata and the latest review (no source text)."""
        rows = self.db.execute(ITEMS_SELECT + "WHERE p.run_id = ? ORDER BY p.id", (run_id,))
        return [_row(r) for r in rows]

    def prediction_detail(self, prediction_id: int) -> dict:
        row = self.db.execute(
            "SELECT p.*, s.text, s.url, s.title_only, a.number, a.type, a.begin_date, a.body_type FROM predictions p "
            "LEFT JOIN sources s ON s.text_sha256 = p.source_sha256 LEFT JOIN affairs a ON a.id = p.affair_id "
            "WHERE p.id = ?", (prediction_id,),
        ).fetchone()
        if row is None:
            raise KeyError(prediction_id)
        return _row(row) | {"reviews": self.reviews(prediction_id)}

    def latest_run(self, topic_sha: str, sample_file: str, min_affairs: int = 0) -> dict | None:
        """Newest finished run for this topic/scheme on this sample that covers at least `min_affairs` affairs
        (cancelled or partial runs are kept in the store but never picked)."""
        row = self.db.execute(
            "SELECT r.id FROM runs r WHERE r.topic_sha = ? AND r.sample_file = ? AND r.finished_at IS NOT NULL "
            "AND (SELECT COUNT(DISTINCT p.affair_id) FROM predictions p WHERE p.run_id = r.id) >= ? "
            "ORDER BY r.started_at DESC LIMIT 1", (topic_sha, sample_file, min_affairs),
        ).fetchone()
        return self.run(row["id"]) if row else None

    def start_ingest(self, body_key: str, since: str, n_listed: int) -> int:
        with self.lock:
            cur = self.db.execute("INSERT INTO ingests (body_key, since, started_at, n_listed) VALUES (?,?,?,?)",
                                  (body_key, since, _now(), n_listed))
        return cur.lastrowid

    def finish_ingest(self, ingest_id: int, n_new: int, report: dict) -> None:
        with self.lock:
            self.db.execute("UPDATE ingests SET finished_at = ?, n_new = ?, report_json = ? WHERE id = ?",
                            (_now(), n_new, json.dumps(report), ingest_id))

    def last_ingest(self, body_key: str) -> dict | None:
        row = self.db.execute("SELECT * FROM ingests WHERE body_key = ? AND finished_at IS NOT NULL "
                              "ORDER BY id DESC LIMIT 1", (body_key,)).fetchone()
        return _row(row) if row else None

    def put_item(self, body_key: str, ingest_id: int, item: dict) -> None:
        """Insert a collection item, or update its status/text; first_ingest and first_seen_at never change."""
        now = _now()
        with self.lock:
            self.db.execute(
                "INSERT INTO collection_items (body_key, affair_id, begin_date, type, title, "
                "text_sha256, status, error, first_ingest, first_seen_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(body_key, affair_id) DO UPDATE SET begin_date = excluded.begin_date, type = excluded.type, "
                "title = excluded.title, text_sha256 = excluded.text_sha256, status = excluded.status, error = excluded.error, "
                "updated_at = excluded.updated_at",
                (body_key, item["affair_id"], item.get("begin_date"), item.get("type"), item.get("title"),
                 item.get("text_sha256"), item["status"], item.get("error"),
                 ingest_id, now, now),
            )

    def items(self, body_key: str) -> list[dict]:
        rows = self.db.execute(
            "SELECT c.*, s.lang, s.lang_mismatch, s.title_only, s.truncated, s.n_chars_full, s.chars_lost "
            "FROM collection_items c LEFT JOIN sources s ON s.text_sha256 = c.text_sha256 "
            "WHERE c.body_key = ? ORDER BY c.affair_id", (body_key,))
        return [_row(r) for r in rows]

    def done_affairs(self, collection: str, prompt_version: str) -> set[int]:
        """Affairs of a collection with a complete result (no transient failure) for this prompt_version."""
        rows = self.db.execute(_BEST_RUN_SQL + " SELECT affair_id FROM best WHERE n_fail = 0",
                               (collection, prompt_version))
        return {r["affair_id"] for r in rows}

    def collection_results(self, collection: str, prompt_version: str) -> list[dict]:
        """Per affair, the predictions of the run that counts for it (see _BEST_RUN_SQL), with metadata + review."""
        rows = self.db.execute(
            _BEST_RUN_SQL + " " + ITEMS_SELECT +
            "JOIN best b ON b.affair_id = p.affair_id AND b.run_id = p.run_id ORDER BY p.affair_id, p.id",
            (collection, prompt_version))
        return [_row(r) for r in rows]

    def collection_targets(self, collection: str) -> list[dict]:
        """Distinct (prompt template, topic/scheme path, prompt_version) that were indexed on a collection."""
        rows = self.db.execute(
            "SELECT prompt_template, prompt_version, json_extract(manifest_json, '$.topic_path') AS topic_path, "
            "MAX(started_at) AS last_started FROM runs WHERE sample_file = ? GROUP BY prompt_version "
            "ORDER BY last_started", (collection,))
        return [_row(r) for r in rows]
