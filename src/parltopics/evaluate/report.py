"""Human-readable reports from runs in the store."""

from parltopics.evaluate.metrics import first_loop_summary, is_correct
from parltopics.store import Store


def load_run(store: Store, run_id: str) -> tuple[dict, list[dict]]:
    run = store.run(run_id)
    rows = store.predictions(run_id)
    return run["manifest"], sorted(rows, key=lambda r: (-r["gold"], r["body_key"], r["affair_id"]))


def _fmt(value: object, width: int) -> str:
    text = "" if value is None else str(value)
    return text[:width].ljust(width)


def table(rows: list[dict]) -> str:
    cols = [("id", 7), ("body", 5), ("lang", 4), ("gold", 4), ("label", 9), ("conf", 4), ("status", 15),
            ("ev", 6), ("flags", 12), ("ms", 6), ("title", 48)]
    lines = ["flags: kw = keyword-absent (core), tech = tech-vocab-absent, T = title-only, ! = inconsistent",
             " ".join(_fmt(c, w) for c, w in cols)]
    for r in rows:
        conf = f"{r['confidence']:.2f}" if r.get("confidence") is not None else ""
        verified = r.get("verify_method", "") if r.get("label") == "match" else ""
        flags = ",".join(name for name, on in (("kw", r.get("keyword_absent")), ("tech", r.get("tech_vocab_absent")),
                                               ("T", r.get("title_only")), ("!", r.get("inconsistent"))) if on)
        values = [r["affair_id"], r["body_key"], r.get("lang"), r["gold"], r.get("label"), conf, r["status"],
                  verified, flags, r.get("latency_ms"), r["title"]]
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
        f"keyword-absent matches: {kw['total']} (gold positive {kw['gold_positive']}, gold negative "
        f"{kw['gold_negative']}; also tech-vocab-absent: {kw['also_tech_vocab_absent']})",
        f"abstain: {s['abstain']}   inconsistent label/confidence: {s['inconsistent']}",
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
            was_right, is_right = is_correct(old), is_correct(r)
            mark = {(False, True): "fixed", (True, False): "broke"}.get((was_right, is_right), "same outcome")
            lines.append(f"  {r['affair_id']:>7} gold={r['gold']} {old.get('label')}/{old['status']} → "
                         f"{r.get('label')}/{r['status']}  [{mark}]  {r['title'][:50]}")
    return f"changed: {len(lines)}\n" + "\n".join(lines)
