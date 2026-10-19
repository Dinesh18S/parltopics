"""Whole-collection evaluation against PolitMonitor (D71): exact counts, no sampling, no prevalence correction."""

from pathlib import Path

import pandas as pd

from parltopics import collection
from parltopics.config import Settings
from parltopics.evaluate.metrics import f1, wilson
from parltopics.store import Store


def is_shown(row: dict | None, threshold: float) -> bool:
    return row is not None and row["status"] == "ok" and row["label"] == "match" and (row["confidence"] or 0) >= threshold


def exact(predicted: dict[int, bool], gold: set[int]) -> dict:
    """predicted: every affair of the population → model yes/no. Gold ids outside the population are ignored."""
    tp = sum(p and a in gold for a, p in predicted.items())
    fp = sum(p and a not in gold for a, p in predicted.items())
    fn = sum(not p and a in gold for a, p in predicted.items())
    tn = len(predicted) - tp - fp - fn
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    return {"n": len(predicted), "tp": tp, "fp": fp, "fn": fn, "tn": tn, "precision": precision, "recall": recall,
            "f1": f1(precision, recall), "precision_ci95": list(wilson(tp, tp + fp)) if tp + fp else None,
            "recall_ci95": list(wilson(tp, tp + fn)) if tp + fn else None}


def politmonitor_ids(settings: Settings, body_key: str, scope: str) -> set[int]:
    pm = pd.read_csv(settings.data_dir / "raw" / "politmonitor_digitalisierung.csv", dtype=str)
    return set(pm[(pm.body_key == body_key) & (pm.politmonitor_scope == scope)].openparldata_id.astype(int))


def evaluate(settings: Settings, store: Store, body_key: str, topic_path: str, scope: str, threshold: float,
             exclude_ids: set[int], baselines: dict | None = None) -> dict:
    target = collection.latest_targets(store, body_key)[topic_path]
    rows = {r["affair_id"]: r for r in store.collection_results(collection.collection_ref(body_key), target["prompt_version"])}
    items = store.items(body_key)
    population = [i["affair_id"] for i in items]
    gold_all = politmonitor_ids(settings, body_key, scope)
    gold = gold_all & set(population)
    shown = {a: is_shown(rows.get(a), threshold) for a in population}
    keyword = {a: rows.get(a) is not None and rows[a]["keyword_absent"] is False for a in population}
    lang = {i["affair_id"]: i["lang"] or "missing" for i in items}
    tp_kw_absent = [a for a in population if shown[a] and a in gold and rows[a]["keyword_absent"] is True]
    untouched = {a: v for a, v in shown.items() if a not in exclude_ids}
    return {
        "body_key": body_key, "pm_scope": scope, "threshold": threshold, "topic": topic_path,
        "prompt_template": target["prompt_template"], "prompt_version": target["prompt_version"],
        "runs": sorted({r["run_id"] for r in rows.values()}),
        "population": {"n": len(population), "politmonitor_tagged": len(gold),
                       "politmonitor_tagged_outside_population": len(gold_all - set(population)),
                       "prevalence": len(gold) / len(population),
                       "no_result": sum(a not in rows for a in population),
                       "status": pd.Series([rows[a]["status"] for a in population if a in rows]).value_counts().to_dict()},
        "model": exact(shown, gold),
        "model_without_sample_affairs": exact(untouched, gold) | {"excluded": len(set(population) & exclude_ids)},
        "keyword_search_core_model_text": exact(keyword, gold),
        "baselines_full_text": baselines,
        "by_language": {l: exact({a: v for a, v in shown.items() if lang[a] == l}, gold)
                        for l in sorted(set(lang.values()))},
        "found_without_core_keyword": {"n": len(tp_kw_absent), "affair_ids": tp_kw_absent[:50]},
    }


def sample_ids(paths: list[Path]) -> set[int]:
    return {int(a) for p in paths for a in pd.read_csv(p).affair_id}
