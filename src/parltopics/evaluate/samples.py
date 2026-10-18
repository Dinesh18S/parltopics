"""Build and freeze sample files (affair ids + gold labels) with fixed seeds."""

import random
from pathlib import Path

import pandas as pd

from parltopics.config import Settings
from parltopics.sources.api import Affair, OPDClient, OPDError
from parltopics.sources.assemble import TRANSLATED_BODY_TYPES, LangMissing, assemble, clean_text

SAMPLE_COLUMNS = ["affair_id", "body_key", "lang", "gold", "set", "split", "begin_date", "title"]


def load_positives(raw_dir: Path, since: str) -> pd.DataFrame:
    pm = pd.read_csv(raw_dir / "politmonitor_digitalisierung.csv", dtype=str)
    return pm[pm.begin_date >= since]


def _title(affair: Affair, lang: str) -> str:
    return clean_text(affair.title.get(lang) or next(iter(affair.title.values()), ""))


def _first_usable(client: OPDClient, ids: list[int], max_chars: int, lang: str | None) -> tuple[Affair, str] | None:
    """First affair in `ids` that assembles in the required language (skips lang_missing / fetch errors)."""
    for affair_id in ids:
        try:
            affair = client.get_affair(affair_id)
            source = assemble(affair, max_chars, lang)
        except (LangMissing, OPDError):
            continue
        return affair, source.lang
    return None


def build_first_loop(settings: Settings, n_pos: int, n_federal: int, since: str, seed: int) -> pd.DataFrame:
    """n_pos PolitMonitor positives + one in-scope negative per positive (same parliament, begin_date >= since).

    Federal positives are spread evenly over the languages of the monolingual parliaments in the list;
    the remaining positives are spread evenly over those languages via monolingual parliaments.
    """
    rng = random.Random(seed)
    client = OPDClient(settings)
    raw_dir = settings.data_dir / "raw"
    pm = load_positives(raw_dir, since)
    bodies = {key: client.get_body(key) for key in sorted(pm.body_key.unique())}
    federal = {k for k, b in bodies.items() if b.type in TRANSLATED_BODY_TYPES}
    mono = {k: b.languages[0] for k, b in bodies.items() if k not in federal and len(b.languages) == 1}
    langs = sorted(set(mono.values()))
    pm_ids = set(pm.openparldata_id.astype(int))
    fed_rows = pm[pm.body_key.isin(federal) & (pm.politmonitor_scope == "ch")]

    def shuffled(values: list[int]) -> list[int]:
        values = sorted(values)
        rng.shuffle(values)
        return values

    rows: list[dict] = []
    used: set[int] = set()

    def add(affair: Affair, lang: str, gold: int, requested: str | None) -> None:
        used.add(affair.id)
        rows.append({
            "affair_id": affair.id, "body_key": affair.body.key, "lang": requested or "", "gold": gold,
            "set": "first_loop", "split": "dev", "begin_date": affair.begin_date, "title": _title(affair, lang),
        })

    fed_langs = [langs[i % len(langs)] for i in range(n_federal)]
    fed_pool = shuffled(fed_rows.openparldata_id.astype(int).tolist())
    keywords = pd.read_csv(
        raw_dir / "che_affairs_keywords.csv", dtype=str, usecols=["openparldata_id", "begin_date"], keep_default_na=False
    )
    fed_neg_pool = shuffled([
        int(i) for i, d in zip(keywords.openparldata_id, keywords.begin_date)
        if d >= since and int(i) not in pm_ids
    ])
    for lang in fed_langs:
        pos = _first_usable(client, [i for i in fed_pool if i not in used], settings.max_input_chars, lang)
        neg = _first_usable(client, [i for i in fed_neg_pool if i not in used], settings.max_input_chars, lang)
        if pos is None or neg is None:
            raise RuntimeError(f"no usable federal affair for lang={lang}")
        add(pos[0], lang, 1, lang)
        add(neg[0], lang, 0, lang)

    n_cantonal = n_pos - n_federal
    per_lang = [n_cantonal // len(langs) + (i < n_cantonal % len(langs)) for i in range(len(langs))]
    for lang, count in zip(langs, per_lang):
        pool = shuffled(pm[pm.body_key.isin([k for k, v in mono.items() if v == lang])].openparldata_id.astype(int).tolist())
        added = 0
        for affair_id in pool:
            if added == count:
                break
            if affair_id in used:
                continue
            pos = _first_usable(client, [affair_id], settings.max_input_chars, None)
            if pos is None:
                continue
            body_ids = [int(r["id"]) for r in client.list_affairs_since(pos[0].body.key, since)]
            neg = _first_usable(
                client, shuffled([i for i in body_ids if i not in pm_ids and i not in used]),
                settings.max_input_chars, None,
            )
            if neg is None:
                continue
            add(pos[0], pos[1], 1, None)
            add(neg[0], neg[1], 0, None)
            added += 1
        if added < count:
            raise RuntimeError(f"only {added}/{count} cantonal positives for lang={lang}")

    return pd.DataFrame(rows, columns=SAMPLE_COLUMNS).sort_values(["gold", "affair_id"], ascending=[False, True])
