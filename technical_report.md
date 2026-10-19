# Technical report — Unisono

Unisono is an open topic classifier for Swiss parliamentary affairs, built on Apertus. It finds every
affair about a topic, in German, French and Italian, and shows the sentence that proves it.

- **Challenge:** OpenParlData: Topic classification for Swiss parliaments with Apertus ([challenge page](https://hackapertus.notion.site/openparldata))
- **Event:** On-site Liebefeld
- **Team:** Unisono
- **Demo:** `link to video`

## 1. Summary

Topic monitoring of Swiss parliaments is done by hand today. Monitors such as PolitMonitor tag every
affair one by one, for example as "digitalisation". Keyword search misses affairs that never use the
word, and the parliaments' own subject areas are too broad. Unisono lets a user type a topic name with
a one-line definition (or pick a standard scheme: APS or Curia Vista). Apertus v1.5 70B reads each affair
in its own language and answers with a label, a confidence and **one sentence copied from the affair as
evidence**. Plain Python code then checks that this sentence really appears in the source. A label without
verified evidence is never shown. A human confirms or rejects every suggestion in the app.

We ran it on three whole parliaments since 2018 (federal 27,465 affairs, Bern 5,249, Thurgau 1,447) and
measured it against PolitMonitor's manual digitalisation tags:

- **Federal:** precision **62.9 %**, recall **51.0 %**. The best baselines reach about 41 %: the Curia
  Vista area "Medien und Kommunikation" (40.9 % / 80.2 %) and keyword search (41.3 % / 56.4 %).
- **Bern:** **68.2 % / 67.8 %**, against 32.7 % / 47.4 % for keyword search.
- **Without the keyword:** 269 tagged affairs were found that contain none of the core keywords.
- **Across languages:** the same affair gets the same answer in DE, FR and IT 94 % of the time.
- **Speed:** all federal affairs since 2018 were classified in 98 minutes.

Recall stays below the broad Curia Vista area, so Unisono suggests affairs and a human confirms them. It
does not replace the monitor.

## 2. Architecture

```
OpenParlData API ──► ingest ──► assemble text ──► SQLite store ◄──► FastAPI + web UI ──► reviewer
 (+ challenge bulk files)        (clean, language       (append-only:      (Explore, Standard,      (confirm /
                                  check, 12k chars)      texts, runs,       Review queue, What's     reject, Excel
                                       │                 predictions,       new, Metrics)            export)
                                       ▼                 reviews)
                     Apertus (OpenAI-compatible endpoint) ──► verify evidence (pure Python) ──┘
```

One Python package (`src/parltopics`, command `parltopics`), one SQLite file, one container (`make run`). There is no build step
for the front end: it is vanilla JS, and its fonts are served locally.

- **Ingest** (`parltopics ingest`). Lists every affair of one parliament since a date and fetches it from
  the OpenParlData API (disk-cached). Federal texts come from the challenge bulk file, which we checked is
  byte-identical to the API. The ingest then builds one clean text per affair: title, submitted text,
  reasoning, answer, documents. Each text gets a language rule: the parliament's language, or a language
  detected from the documents for bilingual parliaments, or the first complete official version (DE/FR/IT)
  for federal affairs. Texts are cut at 12,000 characters. A data-quality report counts title-only,
  truncated and language-mismatched texts.
- **Index** (`parltopics index`). Classifies every stored text at concurrency 16. It can resume: affairs
  already done for the same prompt version are skipped, and transient failures are retried.
  **Update** (`parltopics update`) fetches only new affairs and classifies them for every topic already
  indexed on that parliament.
- **Classify.** Strict JSON is enforced by the endpoint (`json_schema` guided decoding) and re-validated
  with pydantic. If the evidence fails, the model gets one retry ("copy one sentence exactly").
- **Verify** (`verify.py`, unit-tested). The evidence must occur in the source text, exactly or with a
  fuzzy score of at least 92. Quotes, hyphenation and whitespace are normalised first. If the text is only
  a title, the evidence must be in the title and confidence is capped at 0.6. Every failure gets an
  explicit status (`evidence_failed`, `parse_error`, `lang_missing` …) and is counted.
- **Store.** Predictions and reviews are append-only, enforced by SQLite triggers. Every run has a
  manifest with model, prompt version, git commit and concurrency. The `prompt_version` is a hash over the
  prompt template, the topic file, the parameters and the model, so a changed definition always gives a
  new version.
- **App.**
  - *Explore:* a topic over a whole parliament, with filters (collection, language, date) and a
    "keyword absent" switch. For a topic not yet indexed it shows an estimate, then runs a background job.
  - *Standard mode:* APS or Curia Vista labels, with a "Shelf" filter for one category.
  - *Review queue:* unreviewed suggestions, keyboard C / R.
  - *What's new:* affairs added since the last visit.
  - *My topics:* saved own topics with their coverage per parliament.
  - *Excel export* and a *Metrics* page written for non-experts.
  - Each row has a detail panel with the highlighted evidence, a source link and, if the affair is not
    in the reviewer's language, the official translation (or an Apertus 8B translation labelled "not
    evidence").
- **Cached mode.** Without a reachable endpoint the app starts with pre-computed results
  (`results/demo/`, `results/collections/`). Browsing, filters, review and export still work.

### Target architecture (mandatory)

Unisono is deployable as **a) on-premise** and **b) air-gapped**. It has also run as **c) sovereign
Swiss cloud**.

- The only model dependency is one OpenAI-compatible endpoint (`LLM_BASE_URL`) serving Apertus. That
  can be local vLLM / Ollama with Apertus 8B or 70B weights, or a Swiss-hosted endpoint. We developed
  against the CSCS-hosted Apertus v1.5 70B through an OpenAI-compatible gateway.
- **Build time:** Docker image (`python:3.11-slim`, dependencies pinned in `uv.lock`), Apertus weights.
- **Runtime, air-gapped:** container + local Apertus + SQLite. Nothing else. No CDN or web fonts, no
  telemetry, no closed model.
- **Runtime, data refresh:** `ingest` / `update` need the public OpenParlData API. In an air-gapped
  installation, run them on a connected machine and move the SQLite file across.

## 3. Use of Apertus

- **Model:** `swiss-ai/Apertus-v1.5-70B` (served as `apertus-v1-5-70b`) for all classification;
  `Apertus-v1.5-8B` for the unofficial reading-aid translation (measured 4.5 s against 166 s on 70B for
  2,000 characters, near-identical German). The `-thinking` variants are not used.
- **How it is used:** inference only (zero-shot, temperature 0, no fine-tuning).
- **Where it runs:** CSCS-hosted endpoint, via an OpenAI-compatible gateway; any local
  OpenAI-compatible server works through `LLM_NAME`, `LLM_BASE_URL`, `LLM_API_KEY`.

**Two modes, prompts in `src/parltopics/prompts/`:**

- **Ad-hoc (`adhoc_v5`).** The system prompt says to:
  - label by topic only, never by party or position;
  - match only when the topic is a *main* subject;
  - check the "counts as this topic" list first;
  - read the affair in its own language;
  - copy one sentence verbatim as evidence;
  - give confidence as the probability that the affair is about the topic;
  - output JSON only.

  A topic is a YAML file with a name, a definition, "counts" and "does not count" lists, and keywords
  (`topics/digitalisation.yaml`). Keywords never enter the prompt: they only drive the "keyword absent"
  flag and the baseline. No topic, scheme or language is hard-coded in Python. A user's own topic from
  the UI becomes such a file. The shown threshold is confidence ≥ 0.9, chosen on dev data only by a
  pre-registered rule (§5).
- **Standard (`standard_v1`).** Up to 3 labels from a closed list, sent as an enum in the JSON schema, so
  the model cannot invent codes. Each label has its own evidence and is verified separately. The task is
  repeated after the affair text. Curia Vista (28 areas) runs in one stage. APS runs in two: 22 chapters
  first, then the 165 topics, but only inside chapters whose evidence verified.

**Prompt history** (each change made on dev errors only; `docs/05`, `docs/decisions.md`):

| Version | Change |
|---|---|
| v2 | Bullet-list include/exclude rules |
| v3 | Defines confidence (D28) |
| v4 / v5 | "Check the include list first" (D42) |
| v6 | Restates the question after the text (D66). Tested and not adopted: it failed its pre-registered adoption rule. |

**Code does the rest.** Fetching, language checks, evidence verification, thresholds, metrics and keyword
flags are deterministic Python.

## 4. Data

- **OpenParlData.ch** API and the challenge bulk files (snapshot 2026-10-18, checksums in
  `data/raw_files.sha256`). Licence **CC BY 4.0**, "Source: OpenParlData.ch". Raw files and caches are
  downloaded by `make data` and never committed.
- **PolitMonitor digitalisation tags** (3,433 affairs, from the challenge files) are the reference labels.
  They are a manual monitor's working tags, not a gold standard: a blind review found them both too broad
  and incomplete (§5).
- **Topic schemes:** Curia Vista subject areas (from the challenge vocabulary, DE/FR/IT) and the
  **Année Politique Suisse** chapters and topics (DE/FR).
- **Committed:** frozen sample id lists with seeds (`data/samples/`), the topic definition, the blind
  review sheet and its key, metrics, and the pre-computed demo and collection results. Each file is at
  most 10 MB.
- **Personal information:** affairs are public parliamentary records and name their authors (members of
  parliament acting in office). Unisono stores no other personal data. The prompt tells the model to
  ignore author, party and position. The blind review was done by a team member. It is described as such
  and collected no data about other people.

## 5. Evaluation

All numbers below are in `results/metrics.json` / `results/metrics.md` and are regenerated by
`parltopics eval …`. Topic: digitalisation, prompt `adhoc_v5`, threshold 0.9.

**5.1 Pre-registered test (federal, since 2018, sample).** Sample of 150 tagged + 850 untagged affairs,
split into dev and test, grouped by title so the same motion never sits in both. Prompt and threshold
were chosen on dev only. The threshold rule (max prevalence-corrected F1, ties → lower) was logged before
the test run, and the test ran once. Because the sample over-represents tagged affairs, precision is
corrected to the population prevalence (5.08 %). 95 % CIs: Wilson for recall, stratified bootstrap for
precision.

| Method | Precision | Recall |
|---|---|---|
| Curia Vista area "Medien und Kommunikation" (full slice, exact) | 40.9 % | 80.2 % |
| Keyword search, core words (full slice, exact) | 41.3 % | 56.4 % |
| **Apertus, test** (101 tagged + 390 untagged) | **69.5 %** (53.0–91.0) | **54.5 %** (44.8–63.8) |

**5.2 Whole parliaments, exact (no sampling).** Every affair since 2018, consultations excluded.
"Model yes" means shown in the app. Affairs the model shows but PolitMonitor did not tag count as false
positives here, so precision is a lower bound.

| Parliament | Affairs | Tagged | Apertus P / R / F1 | Keyword search P / R / F1 |
|---|---|---|---|---|
| Federal (CHE) | 27,465 | 1,396 | **62.9 / 51.0 / 56.3 %** | 41.3 / 56.4 / 47.7 % |
| Federal, the 26,453 affairs never in any sample | 26,453 | 1,240 | 60.6 / 50.9 / 55.3 % | — |
| Bern (BE) | 5,249 | 171 | **68.2 / 67.8 / 68.0 %** | 32.7 / 47.4 / 38.7 % |
| Thurgau (TG) | 1,447 | 33 | 50.0 / 45.5 / 47.6 % | 15.7 / 72.7 / 25.8 % |

Federal Curia Vista area: 40.9 / 80.2 / 54.2 %. The full-population federal result lies inside the
pre-registered test intervals. On the affairs never used during development it gives 60.6 / 50.9 %, so
there is no sign that dev work inflated the result. Tagged affairs found **without any core keyword**:
federal 215, Bern 54. Cantonal keyword baselines use the 12,000-character text the model saw.

**5.3 Blind human review (test split).** One team member (MA student, political science) reviewed
shuffled affairs with no model or PolitMonitor label shown. Both of these were fixed before the review:
the rule ("digital technology present" **and** "the aim, not a side matter") and two readings (strict /
broad). 49 of 90 were answered and 1 was excluded. Findings:

- All 4 reviewed affairs that the model found and PolitMonitor had not tagged were digital.
- 8 of 18 model "misses" were not digital under the rule.
- Strict reading: precision **82.6 %** (47.9–100), recall 37.3 % (15.7–79.5).

So precision rises after review, and recall cannot be pinned down with 22 untagged answers.

**5.4 Cross-language consistency.** 100 federal affairs, each with complete official DE, FR and IT
versions:

- Ad-hoc: all three languages give the same answer in **94.0 %** of affairs (87.5–97.2); Cohen's κ is
  0.88–0.93.
- Recall per language: DE 58 %, FR 56 %, IT 60 %. We found no language bias.
- Standard mode (Curia Vista): the top label is identical in all three languages only 47.5 % of the time
  (37.9–57.2).

**5.5 Standard mode, Curia Vista (federal test, n = 112).**

- At least one correct area: **83.0 %** (75.0–88.9).
- Micro-F1 0.425 (P 0.56 / R 0.34).
- The model names about 2 areas per affair where the parliament names 3.2.

APS accuracy was not measured (no answer key).

**5.6 Quality, speed and scale.**

- **Evidence:** 88 of 92 test matches verified (10 by fuzzy match). The evidence-failure rate falls from
  15.2 % to 4.3 % with the single retry.
- **Measured pace at concurrency 16:**

  | Run | Affairs / min | Input tokens / call | Output tokens / call |
  |---|---|---|---|
  | Federal, ad-hoc | 280 | 1,441 | 131 |
  | Bern, ad-hoc | 192 | 1,974 | 132 |
  | APS (two calls) | 62–83 | — | — |

- **Projection to all 326,397 OpenParlData affairs:**
  - one ad-hoc topic: ≈ **19–28 h** and 470–644 M input tokens;
  - APS: ≈ 65 h.
- No price per token is known, so we report hours and tokens, not CHF.

## 6. Limitations

- **Recall.** Federal recall (51 %) is below the Curia Vista area (80 %). Unisono is a precise
  suggestion list for human review, not a complete one. Federal Council bills that consist of a title
  only were found 0 of 7 times.
- **Reference labels.** PolitMonitor tags are both broader and less complete than a strict reading of
  the topic (§5.3). The review had one reviewer, who is a team member, is not independent and answered
  49 of 90. An independent second reviewer is the next step.
- **Long texts.** Texts are cut at 12,000 characters (Bern 721, Thurgau 565 truncated). On one very long
  affair the model drifts to "is there a clear main subject" and matches unrelated topics. The tested fix
  (`adhoc_v6`) removed the drift in our checks but cost 2 of 45 dev positives. It did not meet the
  adoption rule fixed in advance, so the evaluated prompt keeps this known failure.
- **Standard mode.** APS has no accuracy number. Its per-label evidence failures are 10–18 % (hidden,
  counted). Curia Vista label choice varies across languages (47.5 % identical top label).
- **Data quirks.** About 28 % of sampled federal "Italian" texts are actually French. They are detected
  and excluded, not silently used. `parse_error` repeats at temperature 0 (BE 25, CHE 11).
- **Evaluation history.** Test numbers of an earlier prompt (`adhoc_v3`) were seen before the threshold
  rule was fixed. They were not used for any choice (`docs/decisions.md` D41).
- **Topic coverage.** Only digitalisation has a reference to measure against. Covid-19 and user topics
  have none. A user topic is only as good as its definition. Example: "Wolf" on Thurgau showed 7 affairs,
  4 about wolves and 3 about neighbouring animals that a reviewer rejects.
- **Operations.** At concurrency 32 the shared gateway stalled (connections parked for more than
  9 minutes), so 16 is the default.

## 7. Reproducibility

- **Hardware:** any laptop with Docker; the model runs on the endpoint. Our runs used the CSCS-hosted
  Apertus v1.5 70B (GPU type not disclosed by the gateway).
- **Seeds:** every sample is a frozen CSV with its seed in `data/samples/`. The model runs at
  temperature 0; re-running the first loop gave 0 label changes.
- **Run the app:**

  ```bash
  cp .env.example .env    # LLM_NAME, LLM_BASE_URL, LLM_API_KEY
  make run                # http://localhost:8080; cached mode if the endpoint is unreachable
  make test               # 103 unit tests, no model calls
  ```

- **Rebuild the numbers:**

  ```bash
  make data && uv run parltopics data load-bulk
  make eval RUN="20261018T134630509400Z 20261018T134941952960Z"         # §5.1 from stored runs
  uv run parltopics ingest --body BE --since 2018-01-01
  uv run parltopics index --body BE --topic topics/digitalisation.yaml   # resumable
  uv run parltopics eval collection --body BE --pm-scope be              # §5.2 (CHE: --pm-scope ch --cv-area 34)
  ```

  Run ids, prompt versions and commits for every number are in `results/metrics.json` and the run
  manifests.
- **Exact commit:** `<final commit hash>`.

### Use of non-Apertus models

No non-Apertus model is part of the pipeline. During development, **Claude (Anthropic)** was used as an
AI coding assistant. It wrote code, tests and documentation under the team's direction, and it drafted
the first Curia Vista → APS chapter mapping for the partner to check (`data/gold/cv_aps_mapping_draft.csv`).

### Next steps

- Evaluate `adhoc_v6` on new dev data.
- Add an independent second reviewer on a subset to measure inter-rater agreement.
- Build an answer key for APS.
- Add a per-call deadline for gateway stalls.
- Run `update` on a schedule so monitors get a daily "What's new" feed.

## License

Creative Commons Attribution 4.0 (CC-BY-4.0). All HackApertus projects are open-sourced.

## References

- OpenParlData.ch — Swiss parliamentary data, CC BY 4.0. https://openparldata.ch
- Swiss AI Initiative, Apertus v1.5. https://huggingface.co/swiss-ai
- Année Politique Suisse, topic scheme. https://anneepolitique.swiss
- Curia Vista, Federal Assembly business database. https://www.parlament.ch
- Decision log with every choice, run id and number: `docs/decisions.md` (D1–D78).
