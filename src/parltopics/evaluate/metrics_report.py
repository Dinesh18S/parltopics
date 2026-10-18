"""results/metrics.json (machine) and results/metrics.md (tables for the report)."""

import json
from pathlib import Path


def update_metrics_json(path: Path, key: str, block: dict) -> None:
    data = json.loads(path.read_text()) if path.exists() else {}
    data[key] = block
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str) + "\n")


def _pct(x: float | None) -> str:
    return "—" if x is None else f"{x:.1%}"


def _ci(ci: list[float] | None) -> str:
    return "—" if not ci else f"{ci[0]:.1%}–{ci[1]:.1%}"


def digitalisation_markdown(m: dict) -> str:
    t, b = m["test"]["at_chosen_threshold"], m["baselines_full_slice"]
    t05, q, pop = m["test"]["at_0.5"], m["test"]["quality"], m["population"]
    lines = [
        "## Digitalisation, federal affairs since 2018 (like-for-like)",
        "",
        f"Population: {pop['n']:,} federal affairs since {pop['since']} (types excluded: "
        f"{', '.join(pop['exclude_types']) or 'none'}), {pop['positives']:,} PolitMonitor-tagged "
        f"(prevalence {pop['prevalence']:.2%}). Model `{m['model']}`, prompt `{m['prompt_template']}` "
        f"(prompt_version `{m['prompt_version'][:12]}`), run `{m['run_id']}`, commit `{m['git_commit']}`.",
        f"Test split: {t['n_pos']} positives, {t['n_neg']} negatives (stratified sample, dev/test grouped by title). "
        f"Threshold {m['threshold']['chosen_on_dev']} chosen on dev ({m['threshold']['rule']}).",
        "",
        "| Method | Precision | 95% CI | Recall | 95% CI | n |",
        "|---|---|---|---|---|---|",
        f"| Curia Vista area '{' / '.join(b['curia_vista_area']['area_names'])}' (full slice, exact) "
        f"| {_pct(b['curia_vista_area']['precision'])} | — "
        f"| {_pct(b['curia_vista_area']['recall'])} | — | {pop['n']:,} |",
        f"| Keyword search, core words (full slice, exact) | {_pct(b['keyword_search_core']['precision'])} | — "
        f"| {_pct(b['keyword_search_core']['recall'])} | — | {pop['n']:,} |",
        f"| **Apertus, prevalence-corrected** (test) | **{_pct(t['precision_corrected'])}** | {_ci(t['precision_corrected_ci95'])} "
        f"| **{_pct(t['recall'])}** | {_ci(t['recall_ci95'])} | {t['n_pos']}+{t['n_neg']} |",
        f"| Apertus at threshold 0.5 (test) | {_pct(t05['precision_corrected'])} | {_ci(t05['precision_corrected_ci95'])} "
        f"| {_pct(t05['recall'])} | {_ci(t05['recall_ci95'])} | {t05['n_pos']}+{t05['n_neg']} |",
        "",
        f"Raw sample precision (not population precision, sample over-represents positives): "
        f"{_pct(t['precision_raw_sample'])}. False-positive rate {_pct(t['fpr'])} ({_ci(t['fpr_ci95'])}). "
        f"Corrected F1 {_pct(t['f1_corrected'])} ({_ci(t['f1_corrected_ci95'])}).",
        f"Evidence verified on model matches: {q['evidence']['verified']}/{q['evidence']['model_matches']} "
        f"({q['evidence']['fuzzy']} fuzzy). Abstain {q['abstain']}, inconsistent {q['inconsistent']}, "
        f"statuses {q['status_counts']}. Excluded: {m['excluded_from_metrics']}.",
        f"Keyword-absent matches shown (core words): {q['keyword_absent_shown']['n']}, of which PolitMonitor-tagged "
        f"{q['keyword_absent_shown']['gold_positive']} (raw precision {_pct(q['keyword_absent_shown']['raw_precision'])}); "
        f"also tech-vocab-absent: {q['keyword_absent_shown']['also_tech_vocab_absent']}.",
        "",
        "| Breakdown (test) | n pos | Recall | n neg | FPR |",
        "|---|---|---|---|---|",
    ]
    for name in ("by_language", "by_type", "by_title_only"):
        for value, s in m["test"][name].items():
            lines.append(f"| {name[3:]}={value} | {s['n_pos']} | {_pct(s['recall'])} | {s['n_neg']} | {_pct(s['fpr'])} |")
    lines += ["", "Dev threshold curve:", "", "| t | recall | FPR | corrected precision | corrected F1 |", "|---|---|---|---|---|"]
    for p in m["threshold"]["dev_curve"]:
        lines.append(f"| {p['threshold']} | {_pct(p['recall'])} | {_pct(p['fpr'])} | {_pct(p['precision_corrected'])} "
                     f"| {_pct(p['f1_corrected'])} |")
    return "\n".join(lines) + "\n"
