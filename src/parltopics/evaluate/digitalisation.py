"""Like-for-like ad-hoc evaluation against PolitMonitor (docs/06 §2): baselines, sample metrics, review export."""

import json
import random
from collections import Counter
from pathlib import Path

import pandas as pd

from parltopics.config import Settings
from parltopics.evaluate.keyword_scan import scan
from parltopics.evaluate.metrics import (
    bootstrap_corrected, corrected_precision, f1, is_predicted_match, threshold_curve, wilson,
)
from parltopics.evaluate.samples import federal_slice
from parltopics.sources.bulk import BULK_BODY_KEY
from parltopics.sources.router import AffairSource
from parltopics.store import Store
from parltopics.topics import Topic

EXCLUDED_STATUSES = {"lang_missing"}


def _exact(predicted: pd.Series, gold: pd.Series) -> dict:
    tp = int((predicted & gold).sum())
    n_pred, n_gold = int(predicted.sum()), int(gold.sum())
    return {"tp": tp, "predicted": n_pred, "gold": n_gold,
            "precision": tp / n_pred if n_pred else None, "recall": tp / n_gold if n_gold else None,
            "f1": f1(tp / n_pred if n_pred else None, tp / n_gold if n_gold else None)}


def baselines(settings: Settings, population: pd.DataFrame, topic: Topic, cv_area_ids: list[str],
              cache_dir: Path, topic_sha: str) -> dict:
    """Both baselines on the whole slice (no model): Curia Vista area(s) and core-keyword search over the
    full text of all language versions."""
    gold = population.gold.astype(bool)
    cv = population.topic_ids.map(lambda ids: any(i in cv_area_ids for i in ids))
    cache = cache_dir / f"keyword_slice_{topic_sha[:12]}_{len(population)}.csv"
    if cache.exists():
        flags = pd.read_csv(cache, keep_default_na=False)
    else:
        rows = population.assign(openparldata_id=population.affair_id, body_key=BULK_BODY_KEY)
        flags = scan(AffairSource(settings), rows, topic, workers=4)
        flags.to_csv(cache, index=False)
    flags = flags.set_index("affair_id").reindex(population.affair_id)
    keyword_hit = flags.keyword_absent.astype(str).eq("False").to_numpy()
    vocab = pd.read_csv(settings.data_dir / "raw" / "che_topics_vocabulary.csv", dtype=str).set_index("topic_id")
    names = [vocab.loc[i].iloc[0] if i in vocab.index else i for i in cv_area_ids]
    return {
        "curia_vista_area": {"area_ids": cv_area_ids, "area_names": names, **_exact(cv, gold)},
        "keyword_search_core": {"keywords": topic.keywords, "scan_errors": int((flags.scan_error != "").sum()),
                                **_exact(pd.Series(keyword_hit, index=gold.index), gold)},
    }


def _rows(store: Store, run_id: str, sample: pd.DataFrame) -> tuple[list[dict], dict]:
    meta = sample.set_index("affair_id")[["split", "type"]].to_dict("index")
    rows, excluded = [], {"lang_missing": 0, "lang_mismatch": 0}
    for r in store.predictions(run_id):
        if r["status"] in EXCLUDED_STATUSES:
            excluded["lang_missing"] += 1
            continue
        if r.get("lang_mismatch"):
            excluded["lang_mismatch"] += 1
            continue
        rows.append(r | meta[r["affair_id"]])
    return rows, excluded


def _shown(row: dict, threshold: float) -> bool:
    return is_predicted_match(row) and (row.get("confidence") or 0) >= threshold


def _sample_metrics(rows: list[dict], threshold: float, prevalence: float, n_boot: int, seed: int) -> dict:
    pos = [r for r in rows if r["gold"] == 1]
    neg = [r for r in rows if r["gold"] == 0]
    pos_hits = [_shown(r, threshold) for r in pos]
    neg_hits = [_shown(r, threshold) for r in neg]
    tp, fp = sum(pos_hits), sum(neg_hits)
    recall = tp / len(pos) if pos else None
    fpr = fp / len(neg) if neg else None
    precision = corrected_precision(recall, fpr, prevalence) if pos and neg else None
    ci = bootstrap_corrected(pos_hits, neg_hits, prevalence, n_boot, seed) if pos and neg else {}
    return {
        "n_pos": len(pos), "n_neg": len(neg), "tp": tp, "fn": len(pos) - tp, "fp": fp, "tn": len(neg) - fp,
        "recall": recall, "recall_ci95": list(wilson(tp, len(pos))),
        "fpr": fpr, "fpr_ci95": list(wilson(fp, len(neg))),
        "precision_corrected": precision, "precision_corrected_ci95": ci.get("precision"),
        "f1_corrected": f1(precision, recall), "f1_corrected_ci95": ci.get("f1"),
        "precision_raw_sample": tp / (tp + fp) if tp + fp else None,
    }


def _breakdown(rows: list[dict], key: str, threshold: float) -> dict:
    out = {}
    for value in sorted({str(r.get(key)) for r in rows}):
        sub = [r for r in rows if str(r.get(key)) == value]
        pos = [r for r in sub if r["gold"] == 1]
        neg = [r for r in sub if r["gold"] == 0]
        tp, fp = sum(_shown(r, threshold) for r in pos), sum(_shown(r, threshold) for r in neg)
        out[value] = {"n_pos": len(pos), "n_neg": len(neg),
                      "recall": tp / len(pos) if pos else None, "recall_ci95": list(wilson(tp, len(pos))),
                      "fpr": fp / len(neg) if neg else None, "fpr_ci95": list(wilson(fp, len(neg)))}
    return out


def _quality(rows: list[dict], threshold: float) -> dict:
    matches = [r for r in rows if r.get("label") == "match"]
    shown = [r for r in rows if _shown(r, threshold)]
    kw = [r for r in shown if r.get("keyword_absent")]
    return {
        "status_counts": dict(Counter(r["status"] for r in rows)),
        "abstain": sum(r.get("label") == "abstain" for r in rows),
        "inconsistent": sum(bool(r.get("inconsistent")) for r in rows),
        "evidence": {"model_matches": len(matches), "verified": sum(bool(r["verify_ok"]) for r in matches),
                     "fuzzy": sum(r.get("verify_method") == "fuzzy" for r in matches),
                     "rate": sum(bool(r["verify_ok"]) for r in matches) / len(matches) if matches else None},
        "keyword_absent_shown": {"n": len(kw), "gold_positive": sum(r["gold"] == 1 for r in kw),
                                 "raw_precision": sum(r["gold"] == 1 for r in kw) / len(kw) if kw else None,
                                 "also_tech_vocab_absent": sum(bool(r.get("tech_vocab_absent")) for r in kw)},
        "truncated": sum(bool(r.get("truncated")) for r in rows),
    }


def evaluate(settings: Settings, store: Store, run_id: str, sample_path: Path, topic: Topic,
             cv_area_ids: list[str], thresholds: list[float], n_boot: int, seed: int) -> dict:
    sample = pd.read_csv(sample_path, keep_default_na=False)
    meta = json.loads(sample_path.with_suffix(".meta.json").read_text())
    pop_meta = meta["population"]
    prevalence = pop_meta["prevalence"]
    run = store.run(run_id)
    rows, excluded = _rows(store, run_id, sample)
    dev = [r for r in rows if r["split"] == "dev"]
    test = [r for r in rows if r["split"] == "test"]

    curve = threshold_curve(dev, thresholds, prevalence)
    best = max(curve, key=lambda p: (p["f1_corrected"] or 0, -p["threshold"]))
    chosen = best["threshold"]

    population = federal_slice(settings, pop_meta["since"], pop_meta["exclude_types"], pop_meta["pm_scope"])
    if len(population) != pop_meta["n"] or int(population.gold.sum()) != pop_meta["positives"]:
        raise RuntimeError("population differs from the sample's meta file; rebuild the sample")
    return {
        "set": "digi_federal_2018",
        "run_id": run_id,
        "model": run["model"],
        "prompt_template": run["prompt_template"],
        "prompt_version": run["prompt_version"],
        "git_commit": run["git_commit"],
        "sample_file": str(sample_path),
        "population": pop_meta,
        "excluded_from_metrics": excluded,
        "baselines_full_slice": baselines(settings, population, topic, cv_area_ids,
                                          settings.data_dir / "cache", run["topic_sha"]),
        "threshold": {"grid": thresholds, "chosen_on_dev": chosen, "rule": "max corrected F1 on dev",
                      "dev_curve": curve},
        "test": {"at_chosen_threshold": _sample_metrics(test, chosen, prevalence, n_boot, seed),
                 "at_0.5": _sample_metrics(test, 0.5, prevalence, n_boot, seed),
                 "quality": _quality(test, chosen),
                 "by_language": _breakdown(test, "lang", chosen),
                 "by_type": _breakdown(test, "type", chosen),
                 "by_title_only": _breakdown(test, "title_only", chosen)},
        "dev": {"at_chosen_threshold": _sample_metrics(dev, chosen, prevalence, n_boot, seed),
                "quality": _quality(dev, chosen)},
    }


def review_rows(store: Store, run_id: str, sample_path: Path, threshold: float, budget: int, seed: int,
                excerpt) -> tuple[list[list], list[dict]]:
    """Blind review set from the test split: disagreements in both directions (up to `budget` each) plus as many
    random agreements, shuffled. Returns sheet rows (no labels) and the key (kept away from the reviewer)."""
    rng = random.Random(seed)
    sample = pd.read_csv(sample_path, keep_default_na=False)
    rows, _ = _rows(store, run_id, sample)
    test = [r for r in rows if r["split"] == "test"]
    groups = {
        "model_yes_pm_no": [r for r in test if _shown(r, threshold) and r["gold"] == 0],
        "model_no_pm_yes": [r for r in test if not _shown(r, threshold) and r["gold"] == 1],
        "agree": [r for r in test if _shown(r, threshold) == bool(r["gold"])],
    }
    picked = []
    for name in ("model_yes_pm_no", "model_no_pm_yes"):
        pool = sorted(groups[name], key=lambda r: r["affair_id"])
        chosen = rng.sample(pool, min(budget, len(pool)))
        picked += [(name, r, len(pool)) for r in chosen]
    n_disagree = len(picked)
    agree_pool = sorted(groups["agree"], key=lambda r: r["affair_id"])
    picked += [("agree", r, len(agree_pool)) for r in rng.sample(agree_pool, min(n_disagree, len(agree_pool)))]
    rng.shuffle(picked)
    sheet, key = [], []
    texts = {s["text_sha256"]: s for s in store.db.execute("SELECT text_sha256, text, url FROM sources")}
    for i, (name, r, pool_size) in enumerate(picked, start=1):
        src = texts[r["source_sha256"]]
        sheet.append([i, r["affair_id"], r["title"], src["url"], excerpt(src["text"]), "", ""])
        key.append({"review_no": i, "affair_id": r["affair_id"], "group": name, "group_size_in_test": pool_size,
                    "model_shown_match": _shown(r, threshold), "politmonitor": r["gold"], "lang": r["lang"],
                    "prediction_id": r["id"]})
    return sheet, key
