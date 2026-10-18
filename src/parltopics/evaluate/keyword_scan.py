"""Keyword flags over the full text of many affairs (all language versions for translated affairs)."""

from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from parltopics.sources.api import OPDError
from parltopics.sources.assemble import TRANSLATED_BODY_TYPES, LangMissing, assemble
from parltopics.sources.router import AffairSource
from parltopics.topics import Topic, keyword_absent, tech_vocab_absent

FULL_TEXT = 10**9


def scan(source: AffairSource, rows: pd.DataFrame, topic: Topic, workers: int) -> pd.DataFrame:
    """Per affair: keyword_absent / tech_vocab_absent over the untruncated text, or scan_error."""

    def one(row: dict) -> dict:
        out = {"affair_id": int(row["openparldata_id"]), "keyword_absent": None, "tech_vocab_absent": None,
               "title_only": None, "text_versions": 0, "scan_error": ""}
        try:
            affair = source.get_affair(out["affair_id"], row["body_key"])
            langs = list(affair.title) if affair.body.type in TRANSLATED_BODY_TYPES else [None]
            sources = []
            for lang in langs:
                try:
                    sources.append(assemble(affair, FULL_TEXT, lang))
                except LangMissing:
                    continue
        except (OPDError, ValueError) as e:
            return out | {"scan_error": str(e)[:200]}
        if not sources:
            return out | {"scan_error": "no text in any language"}
        joined = "\n".join(s.text for s in sources)
        return out | {"keyword_absent": keyword_absent(joined, topic), "tech_vocab_absent": tech_vocab_absent(joined, topic),
                      "title_only": all(s.title_only for s in sources), "text_versions": len(sources)}

    with ThreadPoolExecutor(workers) as pool:
        return pd.DataFrame(list(pool.map(one, rows.to_dict("records"))))
