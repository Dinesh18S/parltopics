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
        f"(prompt_version `{m['prompt_version'][:12]}`), runs `{', '.join(m['run_ids'])}`, commit `{m['git_commit']}`.",
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
        f"({q['evidence']['fuzzy']} fuzzy); evidence-failure rate {_pct(q['evidence']['failure_rate_first_attempt'])} "
        f"before retry → {_pct(q['evidence']['failure_rate_after_retry'])} after ({q['evidence']['recovered']}/"
        f"{q['evidence']['retried']} recovered). Abstain {q['abstain']}, inconsistent {q['inconsistent']}, "
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


def curia_vista_markdown(m: dict) -> str:
    lines = ["## Standard mode — Curia Vista subject areas (federal, since 2018)", "",
             f"Model `{m['model']}`, prompt_version `{m['prompt_version'][:12]}`, runs `{', '.join(m['run_ids'])}`. "
             "Every label with verified evidence counts; stratified sample (≥ 15 affairs per area).", "",
             "| Split | n | At-least-one-correct | 95% CI | Micro-F1 | 95% CI | P | R | Macro-F1 | Labels gold / pred |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for split in ("dev", "test"):
        s = m.get(split)
        if s:
            lines.append(f"| {split} | {s['n']} | {_pct(s['at_least_one_correct']['rate'])} | "
                         f"{_ci(s['at_least_one_correct']['ci95'])} | {s['micro']['f1']:.3f} | "
                         f"{s['micro']['f1_ci95'][0]:.3f}–{s['micro']['f1_ci95'][1]:.3f} | {s['micro']['precision']:.2f} | "
                         f"{s['micro']['recall']:.2f} | {s['macro_f1']:.3f} | {s['cardinality']['gold_mean']:.2f} / "
                         f"{s['cardinality']['pred_mean']:.2f} |")
    return "\n".join(lines) + "\n"


def crosslang_markdown(m: dict) -> str:
    a, s = m["adhoc"], m["standard"]
    lines = ["## Cross-language consistency (same federal affairs, official DE / FR / IT versions)", "",
             f"{a['n']} affairs complete in all three languages ({m['sample']}). Ad-hoc: digitalisation shown as match "
             f"at t = {m['threshold']}. Standard: Curia Vista labels.", "",
             f"Ad-hoc — all three agree: **{_pct(a['all_agree']['rate'])}** ({_ci(a['all_agree']['ci95'])}).", "",
             "| Pair | Agreement (ad-hoc) | Cohen's κ | Top-label agreement (standard) | Jaccard (standard) |",
             "|---|---|---|---|---|"]
    for pair in a["pairs"]:
        p, q = a["pairs"][pair], s["pairs"][pair]
        lines.append(f"| {pair.upper()} | {_pct(p['agreement'])} | {p['kappa']:.2f} | {_pct(q['top_agreement'])} | "
                     f"{q['jaccard_mean']:.2f} |")
    lines += ["", f"Standard — top label identical in all three: **{_pct(s['top_all_agree']['rate'])}** "
                  f"({_ci(s['top_all_agree']['ci95'])}). Ad-hoc match rate by language: "
                  + ", ".join(f"{k.upper()} {_pct(v)}" for k, v in a["positive_rate"].items())
              + ". Recall vs PolitMonitor by language: "
              + ", ".join(f"{k.upper()} {_pct(v)}" for k, v in m["recall_by_lang"].items()) + "."]
    return "\n".join(lines) + "\n"


def cost_markdown(m: dict) -> str:
    lines = ["## Cost and time", "", f"Hardware: {m['hardware']}.", "",
             "| Run | Prompt | Affairs | Model s/affair (mean · p50 · p95) | Tokens in / out per affair | Calls/affair | "
             "Observed affairs/min (concurrency) |", "|---|---|---|---|---|---|---|"]
    for r in m["runs"]:
        s = r["model_seconds_per_affair"]
        lines.append(f"| `{r['run_id']}` | {r['prompt_template']} | {r['affairs']} | {s['mean']:.1f} · {s['p50']:.1f} · "
                     f"{s['p95']:.1f} | {r['tokens_per_affair']['in']:.0f} / {r['tokens_per_affair']['out']:.0f} | "
                     f"{r['calls_per_affair']:.2f} | {r['observed']['affairs_per_minute']:.1f} "
                     f"({r['observed']['concurrency']}) |")
    e = m["runs"][0]["estimate"]
    lines += ["", f"Scale-up for {e['target_affairs']:,} affairs (first run's prompt): "
              + ", ".join(f"{h:.0f} h at concurrency {c}" for c, h in e["hours_at_concurrency"].items())
              + f"; ≈ {e['tokens_in_millions']:.0f} M input / {e['tokens_out_millions']:.0f} M output tokens. "
              f"Assumptions: {e['assumptions']}."]
    return "\n".join(lines) + "\n"


def adjudication_markdown(m: dict) -> str:
    b = m["before"]
    lines = ["## Digitalisation after blind human review (test split)", "",
             f"Reviewer: team member (MA student, political science), blind (no model or PolitMonitor label, shuffled), "
             f"rule fixed before review (D55). Answered {m['answered']} of {m['rows']}; excluded {m['excluded']['affair_ids']} "
             "(seen outside the blind setting, D58). The reviewer's label replaces PolitMonitor's for reviewed affairs; each "
             "confusion cell's rate is scaled to its size in the test split and to the population (D56).", "",
             "| Reading | Precision | 95% CI | Recall | 95% CI | Answers TP / FN / FP / TN | Reviewer-yes rate TP / FN / FP / TN |",
             "|---|---|---|---|---|---|---|",
             f"| before review (PolitMonitor as gold) | {_pct(b['precision'])} | {_ci(b['precision_ci95'])} | {_pct(b['recall'])} | "
             f"{_ci(b['recall_ci95'])} | — | — |"]
    for name, r in m["readings"].items():
        a, q = r["answered"], r["reviewer_yes_rate"]
        lines.append(f"| {name} | {_pct(r['precision'])} | {_ci(r['precision_ci95'])} | {_pct(r['recall'])} | "
                     f"{_ci(r['recall_ci95'])} | {a['TP']} / {a['FN']} / {a['FP']} / {a['TN']} | "
                     f"{q['TP']:.0%} / {q['FN']:.0%} / {q['FP']:.0%} / {q['TN']:.0%} |")
    return "\n".join(lines) + "\n"


def full_markdown(metrics: dict) -> str:
    parts = ["# Metrics\n\nGenerated by `parltopics eval …`; source: results/metrics.json.\n"]
    for key, fn in (("digitalisation_federal_2018", digitalisation_markdown), ("adjudication", adjudication_markdown),
                    ("curia_vista_standard", curia_vista_markdown),
                    ("cross_language", crosslang_markdown), ("cost_time", cost_markdown)):
        if key in metrics:
            parts.append(fn(metrics[key]))
    return "\n".join(parts)
