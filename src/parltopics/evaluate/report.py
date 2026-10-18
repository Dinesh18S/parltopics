"""Human-readable reports from a run directory."""

import json
from pathlib import Path

from parltopics.evaluate.metrics import first_loop_summary, is_predicted_match


def load_run(results_dir: Path, run_id: str) -> tuple[dict, list[dict]]:
    run_dir = results_dir / "runs" / run_id
    manifest = json.loads((run_dir / "manifest.json").read_text())
    rows = [json.loads(line) for line in (run_dir / "predictions.jsonl").read_text().splitlines() if line]
    return manifest, sorted(rows, key=lambda r: (-r["gold"], r["body_key"], r["affair_id"]))


def _fmt(value: object, width: int) -> str:
    text = "" if value is None else str(value)
    return text[:width].ljust(width)


def table(rows: list[dict]) -> str:
    cols = [("id", 7), ("body", 5), ("lang", 4), ("gold", 4), ("label", 9), ("conf", 4), ("status", 15),
            ("ev", 6), ("kw_abs", 6), ("t_only", 6), ("ms", 6), ("title", 48)]
    lines = [" ".join(_fmt(c, w) for c, w in cols)]
    for r in rows:
        conf = f"{r['confidence']:.2f}" if r.get("confidence") is not None else ""
        verified = r.get("verify_method", "") if r.get("label") == "match" else ""
        values = [r["affair_id"], r["body_key"], r.get("lang"), r["gold"], r.get("label"), conf, r["status"],
                  verified, "yes" if r.get("keyword_absent") else "", "yes" if r.get("title_only") else "",
                  r.get("latency_ms"), r["title"]]
        lines.append(" ".join(_fmt(v, w) for v, (_, w) in zip(values, cols)))
    return "\n".join(lines)


def truncation_report(rows: list[dict]) -> str:
    cut = [r for r in rows if r.get("truncated")]
    lines = [f"truncated: {len(cut)}/{len(rows)}"]
    for r in sorted(cut, key=lambda r: -r["chars_lost"]):
        lines.append(f"  {r['affair_id']:>7} {r['body_key']:<5} cut in {r['cut_section'][:60]:<60} "
                     f"lost {r['chars_lost']:>7,} of {r['n_chars_full']:>7,} chars")
    return "\n".join(lines)


def _pct(rate: float | None) -> str:
    return "n/a" if rate is None else f"{rate:.0%}"


def summary_text(manifest: dict, rows: list[dict]) -> str:
    s = first_loop_summary(rows)
    pos, neg, ev, kw = s["positives"], s["negatives"], s["evidence"], s["keyword_absent_matches"]
    fp = manifest["fingerprint"]
    return "\n".join([
        f"run {manifest['run_id']}  model={fp['params']['model']}  prompt_version={fp['prompt_version'][:12]} "
        f"({manifest['prompt_template']})  topic={manifest['topic_name']}",
        f"statuses: {s['status_counts']}  (lang_missing excluded: {s['excluded_lang_missing']})",
        f"positives → match:     {pos['correct']}/{pos['n']} = {_pct(pos['rate'])}  "
        f"95% CI {pos['ci95'][0]:.0%}–{pos['ci95'][1]:.0%}",
        f"negatives → not match: {neg['correct']}/{neg['n']} = {_pct(neg['rate'])}  "
        f"95% CI {neg['ci95'][0]:.0%}–{neg['ci95'][1]:.0%}",
        f"accuracy (all):        {pos['correct'] + neg['correct']}/{pos['n'] + neg['n']}",
        f"evidence verified:     {ev['verified']}/{ev['model_matches']} model matches = {_pct(ev['rate'])}",
        f"keyword-absent matches: {kw['total']} (gold positive {kw['gold_positive']}, gold negative {kw['gold_negative']})",
        f"latency p50/p95: {s['latency_ms']['p50']}/{s['latency_ms']['p95']} ms   "
        f"tokens in/out: {s['tokens']['in']:,}/{s['tokens']['out']:,}",
    ])


def compare(rows_a: list[dict], rows_b: list[dict]) -> str:
    """Affairs whose shown-as-match outcome or label changed between two runs on the same sample."""
    a = {r["affair_id"]: r for r in rows_a}
    lines = []
    for r in rows_b:
        old = a.get(r["affair_id"])
        if old is None:
            continue
        if (old.get("label"), old["status"]) != (r.get("label"), r["status"]):
            was_right = is_predicted_match(old) == bool(old["gold"])
            is_right = is_predicted_match(r) == bool(r["gold"])
            mark = {(False, True): "fixed", (True, False): "broke"}.get((was_right, is_right), "same outcome")
            lines.append(f"  {r['affair_id']:>7} gold={r['gold']} {old.get('label')}/{old['status']} → "
                         f"{r.get('label')}/{r['status']}  [{mark}]  {r['title'][:50]}")
    return f"changed: {len(lines)}\n" + "\n".join(lines)
