"""Challenge files from files.openparldata.ch/hackapertus: download, checksum, load into SQLite."""

import csv
import gzip
import hashlib
import json
import re
import sqlite3
from pathlib import Path

import httpx

from parltopics.sources.api import USER_AGENT, Affair, Body, TextPart

CHALLENGE_BASE = "https://files.openparldata.ch/hackapertus"
BULK_BODY_KEY = "CHE"  # body of the che_* challenge files (federal parliament)
CHALLENGE_FILES = (
    "README.md",
    "aps_topics.xlsx",
    "politmonitor_digitalisierung.csv",
    "dvs_digitalisierung.csv",
    "che_affairs_keywords.csv",
    "che_topics_vocabulary.csv",
    "che_affair_texts.ndjson.gz",
    "cantonal_affairs_keywords.csv",
    "cantonal_keywords_vocabulary.csv",
)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_checksums(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    return {name: digest for digest, name in (line.split() for line in path.read_text().splitlines() if line)}


def download_challenge_files(raw_dir: Path, force: bool = False) -> list[str]:
    raw_dir.mkdir(parents=True, exist_ok=True)
    fetched = []
    with httpx.Client(timeout=120, headers={"User-Agent": USER_AGENT}, follow_redirects=True) as http:
        for name in CHALLENGE_FILES:
            target = raw_dir / name
            if target.exists() and not force:
                continue
            tmp = target.with_suffix(target.suffix + ".part")
            with http.stream("GET", f"{CHALLENGE_BASE}/{name}") as r:
                r.raise_for_status()
                with tmp.open("wb") as f:
                    for chunk in r.iter_bytes(1 << 20):
                        f.write(chunk)
            tmp.rename(target)
            fetched.append(name)
    return fetched


def check_files(raw_dir: Path, expected: dict[str, str]) -> dict[str, str]:
    """Per file: 'ok', 'missing', 'changed' (differs from committed checksum) or 'new'."""
    status = {}
    for name in CHALLENGE_FILES:
        path = raw_dir / name
        if not path.exists():
            status[name] = "missing"
        elif name not in expected:
            status[name] = "new"
        else:
            status[name] = "ok" if sha256_file(path) == expected[name] else "changed"
    return status


BULK_SCHEMA = """
CREATE TABLE IF NOT EXISTS che_affairs (
    id INTEGER PRIMARY KEY, number TEXT, type_en TEXT, begin_date TEXT, title_json TEXT NOT NULL, url TEXT,
    topic_ids TEXT, topics_de TEXT
);
CREATE TABLE IF NOT EXISTS che_texts (
    text_id INTEGER PRIMARY KEY, affair_id INTEGER NOT NULL, type_json TEXT NOT NULL, text_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS che_texts_affair ON che_texts(affair_id);
"""


def load_bulk(raw_dir: Path, db_path: Path) -> dict[str, int]:
    """Load che_affairs_keywords.csv and che_affair_texts.ndjson.gz once into SQLite (D11)."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = db_path.with_suffix(".part")
    tmp.unlink(missing_ok=True)
    db = sqlite3.connect(tmp)
    db.executescript(BULK_SCHEMA)
    with (raw_dir / "che_affairs_keywords.csv").open(newline="", encoding="utf-8") as f:
        rows = [
            (int(r["openparldata_id"]), r["number"], r["type_en"], r["begin_date"] or None,
             json.dumps({k[len("title_"):]: v for k, v in r.items() if k.startswith("title_") and v},
                        ensure_ascii=False),
             r["url"], r["topic_ids"], r["topics_de"])
            for r in csv.DictReader(f)
        ]
    db.executemany("INSERT INTO che_affairs VALUES (?,?,?,?,?,?,?,?)", rows)
    n_texts = 0
    with gzip.open(raw_dir / "che_affair_texts.ndjson.gz", "rt", encoding="utf-8") as f:
        batch = []
        for line in f:
            t = json.loads(line)
            types = {k[len("type_"):]: v for k, v in t.items() if k.startswith("type_") and v}
            texts = {k[len("text_"):]: v for k, v in t.items() if k.startswith("text_") and k != "text_id"}
            batch.append((t["text_id"], t["openparldata_id"], json.dumps(types, ensure_ascii=False),
                          json.dumps(texts, ensure_ascii=False)))
            if len(batch) == 10_000:
                db.executemany("INSERT INTO che_texts VALUES (?,?,?,?)", batch)
                n_texts += len(batch)
                batch = []
        db.executemany("INSERT INTO che_texts VALUES (?,?,?,?)", batch)
        n_texts += len(batch)
    db.commit()
    db.close()
    tmp.rename(db_path)
    return {"affairs": len(rows), "texts": n_texts}


class BulkReader:
    """Federal affairs from the local bulk table, shaped exactly like the API's Affair."""

    def __init__(self, db_path: Path, body: Body):
        if not db_path.exists():
            raise FileNotFoundError(f"{db_path} missing: run `parltopics data load-bulk`")
        self.db = sqlite3.connect(db_path, check_same_thread=False)
        self.body = body

    def ids(self) -> list[int]:
        return [r[0] for r in self.db.execute("SELECT id FROM che_affairs ORDER BY id")]

    def get_affair(self, affair_id: int) -> Affair:
        row = self.db.execute(
            "SELECT number, type_en, begin_date, title_json, url FROM che_affairs WHERE id = ?", (affair_id,)
        ).fetchone()
        if row is None:
            raise KeyError(affair_id)
        number, type_en, begin_date, title_json, url = row
        texts = [
            TextPart(id=text_id, type=json.loads(types), text=json.loads(body))
            for text_id, types, body in self.db.execute(
                "SELECT text_id, type_json, text_json FROM che_texts WHERE affair_id = ? ORDER BY text_id",
                (affair_id,),
            )
        ]
        titles = json.loads(title_json)
        url_lang = re.search(r"/([a-z]{2})/", url or "")
        urls = ({lang: url.replace(f"/{url_lang.group(1)}/", f"/{lang}/", 1) for lang in titles} | {url_lang.group(1): url}
                if url_lang else {})
        return Affair(
            id=affair_id, body=self.body, number=number, type=type_en, begin_date=begin_date,
            title=titles, url_external=urls,
            url_api=f"https://api.openparldata.ch/v1/affairs/{affair_id}", texts=texts, docs=[],
        )
