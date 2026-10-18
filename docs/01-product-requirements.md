# 01 — Product Requirements

**Project:** ParlTopics (working name) — open topic classifier for Swiss parliamentary affairs
**Event:** Hack Apertus, on-site, Liebefeld/Bern, 18–19 Oct 2026
**Challenge:** OpenParlData — topic classification
**Team:** Dinesh (build, demo, architecture) · Arivinchsa (Swiss-politics research, adjudication, pitch)
**Status:** v1, derived from PRD v2. If this file and the PRD disagree, the PRD wins; fix this file.

---

## 1. Problem

OpenParlData harmonises 90 Swiss parliaments (federal, cantonal, municipal): 300,000+ affairs in DE/FR/IT (a little RM). There is no shared topic layer. Finding every affair on a subject means manual, multilingual reading, and the result is always incomplete.

- Keyword search misses affairs that never use the word (an e-ID law, a cybersecurity motion, an e-voting interpellation are all "digitalisation").
- Fixed schemes don't answer ad-hoc questions. Curia Vista has no "digitalisation" area. The closest, *Medien und Kommunikation*, has 81% recall but only 41% precision for digitalisation (federal affairs since 2018).
- Cantons use their own schemes (SG, TG, ZG, ZH differ).

## 2. Users

| User | Need |
|---|---|
| DVS / PolitMonitor team (primary) | Find all digitalisation affairs across parliaments without reading everything by hand; review suggestions, not replace their judgement |
| OpenParlData maintainers | A reusable, open classifier they can run on all affairs and expose via their API/export |
| Researchers, journalists, administrations | Query any topic across parliaments and languages, with traceable evidence |

## 3. Product in one line

One engine, two modes. For any affair, suggest topics with a confidence, the exact justifying sentence, and a source link. A human confirms.

- **Standard mode:** classify against a fixed scheme. Target scheme is APS (22 chapters → 165 topics; 8 domains above; DE/FR labels only). The same code also runs the 28 Curia Vista areas (needed for evaluation).
- **Ad-hoc mode:** any topic name + one-line definition ("digitalisation", "Covid-19"). No retraining; the topic is data, not code.

## 4. Functional requirements

| ID | Requirement | Priority |
|---|---|---|
| F1 | Fetch an affair (title + available texts, in its language) from the OpenParlData API or the bulk files, by `openparldata_id` | Must |
| F2 | Ad-hoc classification: input = affair + topic {name, definition}; output = {label ∈ match/no_match/abstain, confidence, evidence, rationale_short} | Must |
| F3 | Standard classification: input = affair + scheme; output = 0–3 labels from the scheme, or `NONE_OTHER`; each label with confidence + evidence | Must |
| F4 | Evidence verification in plain code: the evidence must be found in the source text (after normalisation). Not found → label rejected (`status=evidence_failed`) | Must |
| F5 | Title-only affairs: title counts as evidence, confidence capped (default 0.6), flagged `title_only` | Must |
| F6 | Every stored label carries: topic, confidence, evidence, source link, model name, prompt version, run id | Must |
| F7 | Human review: confirm / reject / correct a suggestion; stored separately from the model output (never overwrites it) | Must |
| F8 | Demo UI: type a topic (+ definition), see matching affairs across parliaments and languages, each with evidence + link + review buttons | Must |
| F9 | Eval harness producing the metrics in `06-eval-harness-checklist.md` from saved samples, reproducibly | Must |
| F10 | Export results as CSV/JSON and serve them from an HTTP API endpoint | Should |
| F11 | Italian affairs in standard mode get the DE/FR APS label plus an unofficial IT gloss, clearly marked "unofficial" | Should |
| F12 | Second topic run live in the demo with zero code change | Should |
| F13 | Cantonal spot-check (a handful of SG/TG/ZG/ZH affairs) | Could |
| F14 | Romansh | Won't (this weekend) |

## 5. Non-functional requirements

- **Sovereign:** only Apertus for classification. Other open models may help in development (e.g. as a judge) but must be named in the technical report.
- **Model-agnostic plumbing:** one OpenAI-compatible client configured only by `LLM_NAME`, `LLM_BASE_URL`, `LLM_API_KEY`. Local 8B ↔ CSCS 70B is a config change.
- **Reproducible:** `make run` from a clean checkout, Docker. Fixed sample IDs saved to disk, fixed seeds, temperature 0, prompt versions hashed into each run.
- **Traceable:** no label without verified evidence and a link.
- **Neutral:** prompts ask only "what is this about", never stance, party or evaluation.
- **Polite to the API:** cache every API response on disk; bulk files for anything over a few hundred affairs.
- **Honest:** report failure modes, sample sizes, confidence intervals, and what was not tested.

## 6. Out of scope

Reviving the 1996–2014 descriptors (mention only). Full per-canton / per-topic coverage. Party-level bias analysis (named next step). An actual 300k run (estimate only). Fine-tuning.

## 7. Success criteria (Sunday)

1. Digitalisation, federal since 2018: precision clearly above the 41% *Medien und Kommunikation* baseline at comparable or better recall, with a confidence interval, before and after adjudication.
2. At least 3 demo affairs where "Digitalisierung"/"numérique"/"digitale" never appears, correctly found, each confirmed in the PolitMonitor list.
3. A second topic runs live in the UI without code changes.
4. Curia Vista multi-label results (at-least-one-correct, micro-F1) and an APS sample check on ~50 hand-labelled affairs.
5. Cross-language agreement rate on the same federal affairs in DE/FR/IT.
6. Cost/time per affair and a 300k estimate.
7. Public repo, `make run` works, technical report filled.

## 8. Rubric mapping

| Rubric line | Feature that hits it |
|---|---|
| Usefulness | DVS digitalisation monitoring; any topic |
| Technical quality & reproducibility | `make run`, saved samples, run manifests |
| Multilingual performance | DE/FR/IT measured; cross-language agreement |
| Innovation | Ad-hoc topics without retraining + code-verified evidence |
| Ease of integration | HTTP endpoint + CSV/JSON export |
| Pitch | Live demo + numbers (partner leads the story) |
| Purposeful use of AI | Apertus judges language; code retrieves, verifies, scores |
| Technical rigour | Like-for-like baseline, prevalence-corrected precision, adjudication, error analysis |
| Value, cost & scalability | Cost/time per affair, 300k estimate |
| Sovereign deployability | One OpenAI-compatible endpoint; local or CSCS |
| Feasibility | Thin pipeline, standard tools |

## 9. Open questions (partner to ask case owner)

1. Is `politmonitor_digitalisierung.csv` the reference, or is there a cleaner one?
2. Representative sample enough, or credible path to 300k+ required?
3. What would make Sunday a success for you: accuracy, coverage, or integrability?
4. Any existing APS ↔ Curia Vista mapping? (Assumed none; partner builds chapter-level mapping.)
5. Written PolitMonitor criteria for digitalisation, especially cybersecurity, media, data protection, post/telecom?

## 10. Glossary

- **Affair (Geschäft / objet / oggetto):** a parliamentary item (motion, postulate, interpellation, bill…).
- **APS:** Année Politique Suisse topic scheme (`aps_topics.xlsx`); `code` there is a file-local join key, not an official id.
- **Curia Vista:** federal parliament's database; its 28 subject areas label the 70,008 federal affairs.
- **PolitMonitor:** DVS's manual digitalisation tracking; our ground truth.
- **Abstain / NONE_OTHER:** the model's explicit "no topic fits / not enough text" output.
