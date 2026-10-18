# 06 — Evaluation Harness Checklist

Goal: numbers a judge can reproduce and a Swiss-politics expert can't easily poke holes in. Every number in the pitch comes from `results/metrics.json`, produced by `make eval`.

## 0. Ground rules

- [ ] Every eval set is a frozen CSV of affair IDs in `data/samples/` (committed), built with a fixed seed.
- [ ] Each set is split **dev** (prompt/threshold tuning, few-shot examples) and **test** (reported numbers). Nothing tuned on test. Default split 30/70.
- [ ] Split by group, not by row: affairs with identical `title_de` (e.g. the same motion filed in both chambers, or a canton's standard question) always land in the same split.
- [ ] Few-shot examples come only from dev; never a test-split affair.
- [ ] The first-loop affairs (§1) are looked at by humans and drive prompt revisions, so they count as **dev** and are excluded from every test set.
- [ ] Like-for-like digitalisation set: `begin_date ≥ 2018-01-01` (see §2.1).
- [ ] Each run writes a manifest: model, endpoint host, prompt version + SHA, git commit, sample file, date, threshold.
- [ ] Report `n`, and 95% confidence intervals (Wilson for proportions; bootstrap 1,000× for F1).
- [ ] Count and report every failure status: `parse_error`, `evidence_failed`, `llm_error`, `invalid_label`, truncated inputs. Failures count as wrong predictions (no silent drops).

## 1. First loop (smoke test, today)

- [ ] 20 PolitMonitor positives, mixed DE/FR/IT and affair types → expect mostly `match`
- [ ] 20 in-scope non-tagged affairs → expect mostly `no_match`
- [ ] Table: id, lang, gold, label, confidence, evidence_ok, keyword_absent, latency (+ truncation report: per truncated affair, the cut section and characters lost)
- [ ] Evidence-verified rate ≥ 90% on matches, else fix prompt/verify before scaling
- [ ] Eyeball every error with the partner (10 min) → first prompt revision

## 2. Digitalisation — headline (ad-hoc mode)

### 2.1 Like-for-like slice
Population = federal affairs (`body_key=CHE`), `begin_date ≥ 2018-01-01`, inside `politmonitor_scope`.
- Positives P = PolitMonitor-tagged in the slice; Negatives N = rest of the slice.
- [ ] Record population sizes |P| and |N| (prevalence π = |P| / (|P|+|N|)).

### 2.2 Baseline (no model, exact, full slice)
- [ ] Baseline classifier = "Curia Vista area contains *Medien und Kommunikation*".
- [ ] Compute its precision/recall on the **whole** slice. Must reproduce ≈41% / ≈81%; if not, find out why before comparing.

### 2.3 Our sample
- [ ] Stratified random sample: e.g. 150 from P, 250 from N (budget-driven; see §6), seed fixed.
- [ ] Measure recall = TP/|sample P|, false-positive rate = FP/|sample N|.
- [ ] **Prevalence-corrected precision** (because the sample over-represents positives):
  `precision = (recall · π) / (recall · π + FPR · (1 − π))`
  Report this, not raw sample precision. Show raw too, labelled.
- [ ] Same metrics for keyword search (`Digitalisierung|numérique|digitale` in title/text) on the same slice — a second, intuitive baseline.

### 2.4 Adjudication
- [ ] Rules fixed **before** results are seen: the reviewer decides by `data/gold/digitalisation_definition.md` as committed (record its git hash in the adjudication file). No rule changes after the review starts.
- [ ] Review **both directions**: all test-set disagreements where model = yes / PolitMonitor = no (FP) **and** model = no / PolitMonitor = yes (FN). If there are more than the review budget, a seeded random sample per direction, and the after-numbers are re-weighted by the sampling rate (stated in the report).
- [ ] Mix in an equal number of random agreements (TP and TN) so the reviewer can't infer anything from being asked.
- [ ] The reviewer sees **only the affair text** (title + text + link), in shuffled order: never the model label, confidence, evidence or rationale, and never the PolitMonitor label.
- [ ] Report precision/recall **before** and **after** review. In the after-table the reviewer's label replaces the PolitMonitor label for every reviewed affair (so FPs can become TPs, FNs can become TNs, and reviewed TPs/TNs can flip too).
- [ ] Headline line: "N affairs the model found that the manual list missed (confirmed by expert)".

### 2.5 Breakdowns
- [ ] By language (DE/FR/IT), by affair type, title-only vs full text
- [ ] Keyword-absent matches: count + precision
- [ ] Threshold curve (precision/recall vs `MATCH_THRESHOLD`) on dev; chosen threshold marked

### 2.6 Wider check (not headline)
- [ ] Small cantonal sample from PolitMonitor scope (e.g. 30 pos / 30 neg) to show it works across levels; report as spot-check with CI.

## 3. Standard mode

### 3.1 Curia Vista (direct)
- [ ] Stratified sample over the 28 areas (e.g. 10–15 per area, dev/test split).
- [ ] Metrics: **at-least-one-correct** (any predicted area ∈ gold set), **micro-F1**, also macro-F1 and per-area F1 table.
- [ ] Label cardinality: mean gold labels (~2) vs mean predicted.
- [ ] `NONE_OTHER` rate.

### 3.2 APS via mapping
- [ ] Partner's `gold/cv_aps_mapping.csv` (CV area → APS chapter(s)).
- [ ] Predict APS chapters on the Curia Vista test sample; map gold CV areas → APS chapters; score at-least-one-correct + micro-F1 at chapter level.
- [ ] State the limitation: mapping is many-to-many and hand-made.

### 3.3 APS gold sample
- [ ] ~50 affairs hand-labelled by partner (chapter + topic), labelled **before** seeing model output.
- [ ] Chapter-level and topic-level at-least-one-correct + micro-F1, with CI (n is small; say so).

## 4. Cross-language consistency (main bias check)

- [ ] Federal affairs with full text in DE, FR and IT (from `che_affair_texts`), sample ~100.
- [ ] Classify each language version separately (same prompt, same topic).
- [ ] Report: % of affairs where all three labels agree; pairwise agreement DE–FR, DE–IT, FR–IT; Cohen's κ per pair.
- [ ] For standard mode: agreement on the top label and Jaccard of label sets.
- [ ] Accuracy by language and by level (federal vs cantonal) where gold exists.
- [ ] Party-level analysis: named as next step only.

## 5. Model comparison (when CSCS key arrives)

- [ ] Same frozen test sets, 8B vs 70B: P/R, evidence-verified rate, cross-language agreement, latency.
- [ ] If time: zero-shot vs few-shot on 8B.

## 6. Cost, time, scale

- [ ] Per call: latency (p50/p95), tokens in/out; per affair: calls × that.
- [ ] Hardware noted (GPU type/count or "CSCS endpoint").
- [ ] Throughput at configured concurrency (affairs/min).
- [ ] 300k estimate: `affairs × calls_per_affair × mean_latency / concurrency` → hours; GPU-hours; CHF if a price per GPU-hour or per token is known (state the assumption).
- [ ] Budget check before running: sample sizes above × measured seconds/affair must fit the time left. Shrink samples, never skip CIs.

## 7. Output

- [ ] `results/metrics.json` (machine) + `results/metrics.md` (tables for the report)
- [ ] Error analysis: 10 annotated mistakes (5 FP, 5 FN) with a one-line cause each
- [ ] Copy tables into `technical_report.md` §5 and note the commit hash
- [ ] Metrics tab in the UI reads the same JSON

## 8. Pitch numbers (fill in Sunday)

| Claim | Number | CI | n | Source line in metrics.json |
|---|---|---|---|---|
| Digitalisation precision (corrected), federal ≥2018 | | | | |
| Digitalisation recall, federal ≥2018 | | | | |
| Baseline *Medien und Kommunikation* P / R | 41% / 81% (recomputed: ) | — | full slice | |
| Precision after adjudication | | | | |
| Affairs found that manual list missed | | | | |
| Curia Vista at-least-one-correct / micro-F1 | | | | |
| APS gold chapter accuracy | | | | |
| Cross-language all-three agreement | | | | |
| Seconds per affair / 300k estimate | | | | |
