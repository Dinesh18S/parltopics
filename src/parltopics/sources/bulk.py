"""Challenge files from files.openparldata.ch/hackapertus: download and checksum."""

import hashlib
from pathlib import Path

import httpx

from parltopics.sources.api import USER_AGENT

CHALLENGE_BASE = "https://files.openparldata.ch/hackapertus"
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
