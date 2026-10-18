"""Build and freeze sample files (affair ids + gold labels) with fixed seeds."""

import json
import random
import sqlite3
from pathlib import Path

import pandas as pd

from parltopics.config import Settings
from parltopics.evaluate.metrics import grouped_split
from parltopics.sources.api import Affair, OPDClient, OPDError
from parltopics.sources.assemble import TRANSLATED_BODY_TYPES, LangMissing, assemble, clean_text
from parltopics.sources.bulk import BULK_BODY_KEY
from parltopics.sources.router import AffairSource

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


def build_aps_gold(
    settings: Settings, per_lang_federal: int, per_lang_cantonal: int, since: str, seed: int, exclude: set[int],
) -> pd.DataFrame:
    """Blind APS gold sample: federal (bulk) + cantonal (monolingual parliaments of the PolitMonitor list),
    evenly over their languages, since `since`, with more than a title, excluding `exclude`."""
    rng = random.Random(seed)
    source = AffairSource(settings)
    raw_dir = settings.data_dir / "raw"
    pm = load_positives(raw_dir, since)
    bodies = {key: source.api.get_body(key) for key in sorted(pm.body_key.unique())}
    mono = {k: b.languages[0] for k, b in bodies.items() if b.type not in TRANSLATED_BODY_TYPES and len(b.languages) == 1}
    langs = sorted(set(mono.values()))
    rows: list[dict] = []
    used = set(exclude)

    def take(affair: Affair, lang: str | None) -> bool:
        try:
            src = assemble(affair, settings.max_input_chars, lang)
        except LangMissing:
            return False
        if src.title_only:
            return False
        used.add(affair.id)
        rows.append({"affair_id": affair.id, "body_key": affair.body.key, "lang": lang or "", "gold": "",
                     "set": "aps_gold", "split": "gold", "begin_date": affair.begin_date, "title": src.title})
        return True

    keywords = pd.read_csv(raw_dir / "che_affairs_keywords.csv", dtype=str, usecols=["openparldata_id", "begin_date"],
                           keep_default_na=False)
    federal_ids = sorted(int(i) for i, d in zip(keywords.openparldata_id, keywords.begin_date) if d >= since)
    rng.shuffle(federal_ids)
    for lang in langs:
        added = 0
        for affair_id in federal_ids:
            if added == per_lang_federal:
                break
            if affair_id not in used and take(source.get_affair(affair_id, BULK_BODY_KEY), lang):
                added += 1
    for lang in langs:
        lang_bodies = sorted(k for k, v in mono.items() if v == lang)
        added, attempts = 0, 0
        while added < per_lang_cantonal:
            attempts += 1
            if attempts > 200:
                raise RuntimeError(f"not enough cantonal affairs for lang={lang}")
            body = rng.choice(lang_bodies)
            ids = sorted(int(r["id"]) for r in source.api.list_affairs_since(body, since))
            if not ids:
                continue
            affair_id = rng.choice(ids)
            if affair_id in used:
                continue
            try:
                affair = source.get_affair(affair_id, body)
            except OPDError:
                continue
            added += take(affair, None)
    return pd.DataFrame(rows, columns=SAMPLE_COLUMNS)


def federal_slice(settings: Settings, since: str, exclude_types: list[str], pm_scope: str) -> pd.DataFrame:
    """Like-for-like population: federal affairs since `since` (bulk table), with the PolitMonitor flag."""
    db = sqlite3.connect(settings.bulk_db_path)
    df = pd.read_sql_query(
        "SELECT id AS affair_id, number, type_en, begin_date, title_json, topic_ids FROM che_affairs "
        "WHERE begin_date >= ?", db, params=(since,),
    )
    df = df[~df.type_en.isin(exclude_types)].copy()
    pm = pd.read_csv(settings.data_dir / "raw" / "politmonitor_digitalisierung.csv", dtype=str)
    positives = set(pm[(pm.body_key == BULK_BODY_KEY) & (pm.politmonitor_scope == pm_scope)]
                    .openparldata_id.astype(int))
    df["gold"] = df.affair_id.isin(positives).astype(int)
    df["titles"] = df.title_json.map(json.loads)
    df["topic_ids"] = df.topic_ids.fillna("").map(lambda s: [t.strip() for t in s.split("|") if t.strip()])
    return df.drop(columns="title_json").reset_index(drop=True)


def build_digi_federal(
    population: pd.DataFrame, n_pos: int, n_neg: int, seed: int, dev_share: float, exclude: set[int],
) -> pd.DataFrame:
    """Stratified random sample (n_pos positives, n_neg negatives), language by rotation over the title
    languages present, dev/test split grouped by title (identical titles share a split)."""
    rng = random.Random(seed)
    langs = sorted({lang for titles in population.titles for lang in titles})
    rows = []
    for gold, n in ((1, n_pos), (0, n_neg)):
        pool = sorted(i for i in population[population.gold == gold].affair_id if i not in exclude)
        picked = set(rng.sample(pool, n))
        sub = population[population.affair_id.isin(picked)].sort_values("affair_id")
        order = list(sub.index)
        rng.shuffle(order)
        for k, idx in enumerate(order):
            r = population.loc[idx]
            rotation = langs[k % len(langs):] + langs[:k % len(langs)]
            lang = next(l for l in rotation if l in r.titles)
            title_key = r.titles.get(langs[0]) or next(iter(r.titles.values()))
            rows.append({"affair_id": int(r.affair_id), "body_key": BULK_BODY_KEY, "lang": lang, "gold": gold,
                         "set": "digi_federal_2018", "split": "", "begin_date": r.begin_date,
                         "title": clean_text(r.titles.get(lang, "")), "type": r.type_en, "group_key": title_key})
    df = pd.DataFrame(rows)
    df["split"] = grouped_split(df.group_key.tolist(), dev_share, seed)
    return df.drop(columns="group_key").sort_values(["split", "gold", "affair_id"], ascending=[True, False, True])


def enlarge_negatives(
    existing: pd.DataFrame, population: pd.DataFrame, n_new: int, seed: int, dev_share: float, exclude: set[int],
) -> pd.DataFrame:
    """Add n_new random negatives not yet sampled. A new row whose title group already exists keeps that split;
    other new groups go to dev with probability dev_share (same title grouping as build_digi_federal)."""
    rng = random.Random(seed)
    langs = sorted({lang for titles in population.titles for lang in titles})
    titles = population.set_index("affair_id").titles
    key_of = {i: titles[i].get(langs[0]) or next(iter(titles[i].values())) for i in population.affair_id}
    known = {" ".join(key_of[int(a)].lower().split()): s for a, s in zip(existing.affair_id, existing.split)}
    taken = set(existing.affair_id.astype(int)) | exclude
    pool = sorted(i for i in population[population.gold == 0].affair_id if i not in taken)
    picked = sorted(rng.sample(pool, n_new))
    rng.shuffle(picked)
    fresh = grouped_split([key_of[i] for i in picked], dev_share, seed)
    rows = []
    types = population.set_index("affair_id").type_en
    dates = population.set_index("affair_id").begin_date
    for k, (affair_id, split) in enumerate(zip(picked, fresh)):
        t = titles[affair_id]
        rotation = langs[k % len(langs):] + langs[:k % len(langs)]
        lang = next(l for l in rotation if l in t)
        rows.append({"affair_id": affair_id, "body_key": BULK_BODY_KEY, "lang": lang, "gold": 0,
                     "set": "digi_federal_2018", "split": known.get(" ".join(key_of[affair_id].lower().split()), split),
                     "begin_date": dates[affair_id], "title": clean_text(t.get(lang, "")), "type": types[affair_id]})
    out = pd.concat([existing, pd.DataFrame(rows)], ignore_index=True)
    return out.sort_values(["split", "gold", "affair_id"], ascending=[True, False, True])


def build_demo_pool(settings: Settings, scan: pd.DataFrame, since: str, seed: int,
                    n_kw_free: int, n_other_pos: int, n_neg: int) -> pd.DataFrame:
    """Demo pool (docs/02 §4): PolitMonitor positives (keyword-free with full text, and others) plus in-scope
    negatives from the same parliaments; federal and cantonal halves; federal languages by rotation."""
    rng = random.Random(seed)
    source = AffairSource(settings)
    pm = load_positives(settings.data_dir / "raw", since)
    pm = pm.assign(affair_id=pm.openparldata_id.astype(int)).merge(scan, on="affair_id")
    good = pm[(pm.keyword_absent.astype(str) == "True") & (pm.title_only.astype(str) == "False")]
    other = pm[~pm.affair_id.isin(good.affair_id)]
    langs = sorted({lang for b in pm.body_key.unique() for lang in source.api.get_body(b).languages})
    rows: list[dict] = []

    def add(affair_ids: list[int], body_of: dict[int, str], gold: int, n: int, kind: str) -> None:
        added = 0
        for affair_id in affair_ids:
            if added == n:
                return
            body = body_of[affair_id]
            lang = langs[len(rows) % len(langs)] if body == BULK_BODY_KEY else None
            try:
                affair = source.get_affair(affair_id, body)
                src = assemble(affair, settings.max_input_chars, lang)
            except (LangMissing, OPDError, KeyError, ValueError):
                continue
            if src.lang_mismatch:
                continue
            rows.append({"affair_id": affair_id, "body_key": body, "lang": lang or "", "gold": gold, "set": "demo_pool",
                         "split": kind, "begin_date": affair.begin_date, "title": src.title})
            added += 1

    for frame, n, kind in ((good, n_kw_free, "pos_keyword_free"), (other, n_other_pos, "pos_other")):
        for federal in (True, False):
            part = frame[(frame.body_key == BULK_BODY_KEY) == federal]
            ids = sorted(part.affair_id)
            rng.shuffle(ids)
            add(ids, dict(zip(part.affair_id, part.body_key)), 1, n // 2, kind)
    pm_ids = set(pm.affair_id)
    bulk_db = sqlite3.connect(settings.bulk_db_path)
    fed = [i for (i,) in bulk_db.execute("SELECT id FROM che_affairs WHERE begin_date >= ? ORDER BY id", (since,))
           if i not in pm_ids]
    rng.shuffle(fed)
    add(fed, {i: BULK_BODY_KEY for i in fed}, 0, n_neg // 2, "neg")
    cantonal_bodies = sorted(b for b in pm.body_key.unique() if b != BULK_BODY_KEY)
    cand: list[int] = []
    body_of: dict[int, str] = {}
    for body in cantonal_bodies:
        ids = [int(r["id"]) for r in source.api.list_affairs_since(body, since) if int(r["id"]) not in pm_ids]
        picked = rng.sample(sorted(ids), min(4, len(ids)))
        cand += picked
        body_of |= {i: body for i in picked}
    rng.shuffle(cand)
    add(cand, body_of, 0, n_neg - n_neg // 2, "neg")
    return pd.DataFrame(rows, columns=SAMPLE_COLUMNS)
