"""Measured speed and tokens of whole-collection runs, and the projection to every OpenParlData affair (D77)."""

from datetime import datetime

from parltopics.store import Store


def run_stats(store: Store, run_id: str) -> dict:
    """Wall-clock throughput of one run: first to last stored prediction (the run's own pace, gateway included)."""
    row = store.db.execute(
        "SELECT COUNT(DISTINCT affair_id) AS n, MIN(created_at) AS first, MAX(created_at) AS last, "
        "AVG(tok_in) AS tok_in, AVG(tok_out) AS tok_out, COUNT(*) AS calls FROM predictions WHERE run_id = ?",
        (run_id,)).fetchone()
    run = store.run(run_id)
    minutes = (datetime.fromisoformat(row["last"]) - datetime.fromisoformat(row["first"])).total_seconds() / 60
    return {"run_id": run_id, "collection": run["sample_file"], "topic": run["topic_name"],
            "prompt_template": run["prompt_template"], "concurrency": run["manifest"].get("concurrency"),
            "affairs": row["n"], "minutes": round(minutes, 1), "affairs_per_min": round(row["n"] / minutes, 1),
            "records_per_affair": round(row["calls"] / row["n"], 2),
            "tokens_in_per_record": round(row["tok_in"]), "tokens_out_per_record": round(row["tok_out"])}


def projection(stats: dict, n_affairs: int) -> dict:
    """Hours and tokens to classify n_affairs at the measured pace and token use."""
    per_affair = stats["records_per_affair"]
    return {"affairs": n_affairs, "hours": round(n_affairs / stats["affairs_per_min"] / 60, 1),
            "tokens_in_millions": round(n_affairs * per_affair * stats["tokens_in_per_record"] / 1e6),
            "tokens_out_millions": round(n_affairs * per_affair * stats["tokens_out_per_record"] / 1e6)}
