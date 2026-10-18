"""Cost and time per affair (docs/06 §6), measured from stored runs; scale-up estimate with stated assumptions."""

from datetime import datetime
from statistics import mean, median

from parltopics.evaluate.metrics import _pct
from parltopics.store import Store


def cost_time(store: Store, run_ids: list[str], concurrency_used: int, target_affairs: int,
              concurrencies: list[int]) -> dict:
    per_run = []
    for run_id in run_ids:
        run = store.run(run_id)
        rows = [r for r in store.predictions(run_id) if r["status"] not in ("lang_missing", "fetch_error")]
        by_affair: dict[int, dict] = {}
        for r in rows:
            a = by_affair.setdefault(r["affair_id"], {"ms": 0, "tin": 0, "tout": 0, "calls": 0})
            a["ms"] += r.get("latency_ms") or 0
            a["tin"] += r.get("tok_in") or 0
            a["tout"] += r.get("tok_out") or 0
            if r.get("latency_ms"):
                a["calls"] += 1 + bool(r.get("evidence_retried"))
        affairs = list(by_affair.values())
        if not affairs:
            continue
        wall = (datetime.fromisoformat(run["finished_at"]) - datetime.fromisoformat(run["started_at"])).total_seconds()
        conc = run["manifest"].get("concurrency") or concurrency_used
        sec = mean(a["ms"] for a in affairs) / 1000
        per_run.append({
            "run_id": run_id, "prompt_template": run["prompt_template"], "model": run["model"], "affairs": len(affairs),
            "model_seconds_per_affair": {"mean": sec, "p50": median(a["ms"] for a in affairs) / 1000,
                                         "p95": _pct([a["ms"] for a in affairs], 0.95) / 1000},
            "tokens_per_affair": {"in": mean(a["tin"] for a in affairs), "out": mean(a["tout"] for a in affairs)},
            "calls_per_affair": mean(a["calls"] for a in affairs),
            "observed": {"wall_seconds": wall, "concurrency": conc,
                         "affairs_per_minute": 60 * len(affairs) / wall if wall else None},
            "estimate": {
                "target_affairs": target_affairs,
                "hours_at_concurrency": {str(c): target_affairs * sec / c / 3600 for c in concurrencies},
                "tokens_in_millions": target_affairs * mean(a["tin"] for a in affairs) / 1e6,
                "tokens_out_millions": target_affairs * mean(a["tout"] for a in affairs) / 1e6,
                "assumptions": "linear scaling of measured mean model time per affair; gateway throughput constant "
                               "at the given concurrency; one topic (ad-hoc) or one scheme (standard) per affair; "
                               "no price per token / GPU-hour known, so no CHF figure",
            },
        })
    return {"runs": per_run, "hardware": "CSCS-hosted Apertus via the Keera gateway (OpenAI-compatible); GPU type not "
                                          "disclosed by the gateway"}
