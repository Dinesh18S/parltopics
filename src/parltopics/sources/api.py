"""OpenParlData REST client with an on-disk response cache."""

import hashlib
import json
import time
from pathlib import Path
from urllib.parse import urlencode

import httpx
from pydantic import BaseModel

from parltopics.config import Settings

USER_AGENT = "ParlTopics/0.1 (Hack Apertus 2026; https://github.com/Dinesh18S/parltopics)"
RETRY_STATUS = {429, 500, 502, 503, 504}
MAX_RETRIES = 3
PAGE_LIMIT = 1000


class TextPart(BaseModel):
    id: int
    type: dict[str, str]
    text: dict[str, str | None]


class Doc(BaseModel):
    id: int
    name: str | None
    date: str | None
    language: str | None
    url: str | None
    text: str | None


class Body(BaseModel):
    key: str
    type: str | None
    languages: list[str]
    primary: str | None


class Affair(BaseModel):
    id: int
    body: Body
    number: str | None
    type: str | None
    begin_date: str | None
    title: dict[str, str]
    url_external: dict[str, str]
    url_api: str
    texts: list[TextPart]
    docs: list[Doc]


class OPDError(RuntimeError):
    pass


class OPDClient:
    def __init__(self, settings: Settings):
        self.base = settings.opd_api_base.rstrip("/")
        self.cache_dir = settings.data_dir / "cache" / "api"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.http = httpx.Client(timeout=20, headers={"User-Agent": USER_AGENT})

    def _cache_path(self, url: str) -> Path:
        return self.cache_dir / f"{hashlib.sha1(url.encode()).hexdigest()}.json"

    def get_json(self, path: str, params: dict | None = None) -> dict:
        url = f"{self.base}{path}" + (f"?{urlencode(sorted(params.items()))}" if params else "")
        cached = self._cache_path(url)
        if cached.exists():
            return json.loads(cached.read_text())
        for attempt in range(MAX_RETRIES + 1):
            try:
                r = self.http.get(url)
            except httpx.TransportError as e:
                if attempt == MAX_RETRIES:
                    raise OPDError(f"{url}: {type(e).__name__}") from e
            else:
                if r.status_code == 200:
                    data = r.json()
                    cached.write_text(json.dumps(data, ensure_ascii=False))
                    return data
                if r.status_code not in RETRY_STATUS or attempt == MAX_RETRIES:
                    raise OPDError(f"{url}: HTTP {r.status_code}")
            time.sleep(2**attempt)
        raise AssertionError("unreachable")

    def get_relation(self, affair_id: int, relation: str) -> list[dict]:
        rows: list[dict] = []
        offset = 0
        while True:
            page = self.get_json(
                f"/v1/affairs/{affair_id}/{relation}", {"limit": PAGE_LIMIT, "offset": offset}
            )
            rows.extend(page["data"])
            if not page["meta"]["has_more"]:
                return rows
            offset += PAGE_LIMIT

    def get_body(self, body_key: str) -> Body:
        rows = self.get_json("/v1/bodies/", {"body_key": body_key})["data"]
        if len(rows) != 1:
            raise OPDError(f"body {body_key}: expected 1 row, got {len(rows)}")
        b = rows[0]
        listed = b.get("languages") or b.get("lang") or ""
        return Body(
            key=body_key,
            type=b.get("type"),
            languages=[x.strip().lower() for x in listed.split(",") if x.strip()],
            primary=(b.get("lang") or "").lower() or None,
        )

    def get_affair(self, affair_id: int) -> Affair:
        a = self.get_json(f"/v1/affairs/{affair_id}")
        return Affair(
            id=a["id"],
            body=self.get_body(a["body_key"]),
            number=a.get("number"),
            type=(a.get("type_harmonized") or {}).get("en"),
            begin_date=(a.get("begin_date") or "")[:10] or None,
            title={k: v for k, v in (a.get("title") or {}).items() if v},
            url_external={k: v for k, v in (a.get("url_external") or {}).items() if v},
            url_api=a["url_api"],
            texts=[
                TextPart(id=t["id"], type=t.get("type") or {}, text=t.get("text") or {})
                for t in self.get_relation(affair_id, "texts")
            ],
            docs=[
                Doc(
                    id=d["id"],
                    name=d.get("name"),
                    date=d.get("date"),
                    language=d.get("language"),
                    url=d.get("url"),
                    text=d.get("text"),
                )
                for d in self.get_relation(affair_id, "docs")
            ],
        )
