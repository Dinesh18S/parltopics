# Decision log

### D1 — Model ids and endpoint: Keera gateway, `apertus-v1-5-70b` (slice S0, 2026-10-18)
- Decision: `LLM_BASE_URL=https://gateway.keera.ch/api/v1`, `LLM_NAME=apertus-v1-5-70b` (main), `apertus-v1-5-8b` for comparison. Never the `-thinking` variants.
- Why: `GET /models` on the gateway returns exactly `apertus-v1-5-70b`, `apertus-v1-5-70b-thinking`, `apertus-v1-5-8b`, `apertus-v1-5-8b-thinking`. The HF-style name `swiss-ai/Apertus-v1.5-70B` (previously in `.env`) is not served there, so every call would have failed. `.env` was corrected (also stripped leading whitespace on each line).
- Alternatives rejected: local vLLM 8B as default (the doc's original plan) — no GPU needed now that the gateway works; still documented in docs/04 as an option.
- Affects: `.env.example`, `docs/04` §3, `config.py` default.
- Revisit if: the gateway renames models or we lose access.

### D2 — Code layout: package at `src/parltopics`, tests at `src/tests` (slice S0, 2026-10-18)
- Decision: standard `src/` layout with hatchling; tests will live under `src/tests/` (not top-level `tests/` as docs/04 §2 shows).
- Why: AGENTS.md and the template require all code in `src/`; docs/04's `tests/` at root conflicts with that.
- Alternatives rejected: root `tests/` — breaks the "all code in src/" rule.
- Affects: `pyproject.toml` (`testpaths`), docs/04 §2 layout (to adjust when tests arrive in S3).
- Revisit if: organisers say tests may sit outside `src/`.

### D3 — `/health` reports model reachability and live/cached mode (slice S0, 2026-10-18)
- Decision: `/health` always returns `status: ok`; it calls `GET {LLM_BASE_URL}/models` (5 s timeout) and reports `mode: live` only if `LLM_NAME` is in the served list, else `mode: cached` with the error type (never the key).
- Why: docs/04 §4.5 ("ok + model reachable?") and §6 (cached mode when the endpoint is unset/unreachable). Checking the model id, not just HTTP 200, catches the D1 mistake.
- Alternatives rejected: fail health when the model is down — judges must be able to run cached mode.
- Affects: `src/parltopics/api.py`.
- Revisit if: `/models` gets slow or rate-limited; then cache the result.

### D4 — Python 3.11 pinned via uv; dependencies added per slice (slice S0, 2026-10-18)
- Decision: `requires-python >=3.11,<3.12`; S0 adds only fastapi, uvicorn, httpx, pydantic(-settings), typer. openai, pandas, rapidfuzz etc. come with the slice that needs them.
- Why: docs/04 §1 says 3.11; the host has 3.14 but uv fetches 3.11, matching the `python:3.11-slim` image.
- Alternatives rejected: adding the full stack now — unused deps, slower image.
- Affects: `pyproject.toml`, `uv.lock`, `Dockerfile`.
- Revisit if: a dependency needs a newer Python.

### D5 — Compose reads `.env` optionally (slice S0, 2026-10-18)
- Decision: `env_file: {path: .env, required: false}`; `.dockerignore` keeps `.env`, `data/`, `results/` out of the image; data/results are mounted as volumes.
- Why: a fresh clone without `.env` must still `make run` (cached mode); the key must never be baked into an image.
- Alternatives rejected: `environment:` passthrough only — clumsier for judges.
- Affects: `docker-compose.yml`, `.dockerignore`.
- Revisit if: judges' compose version lacks `required: false` (needs Compose ≥ 2.24).

### D6 — Single affairs come from the API (cached), not the bulk file (slice S1, 2026-10-18)
- Decision: `get_affair` uses the OpenParlData API for every level, including CHE. The bulk text file is downloaded but not read yet.
- Why: for affair 235308 the API `/texts` returns the same 4 text ids and content as `che_affair_texts.ndjson.gz`; scanning the 232 MB gzip for one affair takes far longer than one cached API call. Cantonal content exists only in the API (`/docs`).
- Alternatives rejected: bulk-first as docs/04 §4.1 says — needs an index over 210k rows that S1 doesn't need. **Proposed doc fix:** docs/04 §4.1 → "API with disk cache for single affairs; bulk files when a step touches > ~500 affairs" (matches docs/03 §2).
- Affects: `sources/api.py`; docs/04 §4.1 (pending your OK).
- Revisit if: S6/S9 need thousands of federal texts (then add a bulk reader/index).

### D7 — Affair language rule (slice S1, 2026-10-18) — superseded by D12
- Decision: requested `lang` → single title language → majority language of docs with text → first of de/fr/it. Stored as `lang_source`.
- Why: the API has no affair language field. Multilingual titles occur for CHE (1,407), BE (171), VS (141), FR (78), GR (17) PolitMonitor rows. Pure "first of de/fr/it" picked DE for French-majority FR/VS affairs; doc majority fixes that (e.g. 236793 → fr). CHE has no docs → DE, so eval samples set `lang` per row.
- Alternatives rejected: a language detector on the title (docs/03 §6) — extra dependency, and the title keys already tell us which languages exist.
- Affects: `sources/assemble.py`, docs/03 §6.
- Revisit if: we find a field for the original submission language.

### D8 — Text assembly details (slice S1, 2026-10-18)
- Decision: HTML stripped with the stdlib parser, entities unescaped, all whitespace collapsed to single spaces. Order: TITLE → TEXT (Eingereichter Text) → REASONING (Begründung) → ANSWER (Antwort BR / Büro) → other text types → DOCUMENT sections (docs in the chosen language or unlabelled, oldest first, exact duplicates dropped). Truncate the joined string at `MAX_INPUT_CHARS`.
- Why: the original submission is usually the oldest doc, so it survives truncation; GR returns duplicate docs (e.g. 165564). Collapsing whitespace makes verbatim evidence easier for the model to copy and for verify to match.
- Alternatives rejected: keeping line breaks — PDF extraction inserts breaks mid-sentence.
- Affects: `sources/assemble.py`; every evidence check runs against this string.
- Revisit if: **27/100 PolitMonitor affairs are truncated at 12,000 chars** — if S4 shows misses caused by truncation, raise `MAX_INPUT_CHARS` (costs tokens) or drop long government reports first.

### D9 — Challenge-file checksums committed (slice S1, 2026-10-18)
- Decision: `parltopics data download` (`make data`) downloads the 9 files to `data/raw/` and compares them with `data/raw_files.sha256` (committed). First run writes that file; a changed or missing file exits 1.
- Why: docs/03 §4 asks for checksums; the challenge files are a dated snapshot (2026-10-18) and may be republished.
- Alternatives rejected: skipping the `*_long.csv` and `.jsonl` duplicates is deliberate — same data as the `.csv` files we use.
- Affects: `sources/bulk.py`, `Makefile`, `data/raw_files.sha256`.
- Revisit if: organisers republish the files (then delete the checksum file, re-download, re-run evals).

### D10 — API client: synchronous, disk cache keyed by sha1(URL with sorted params) (slice S1, 2026-10-18)
- Decision: one `httpx.Client`, 20 s timeout, 3 retries with 1/2/4 s backoff on 429/5xx/transport errors, project User-Agent. Relations paged with `limit=1000`. Concurrency (max 4) is applied by callers with a thread pool.
- Why: docs/03 client rules; no rate-limit headers seen, no 429 in ~450 requests at 4 threads.
- Alternatives rejected: async client — nothing in S1 needs it.
- Affects: `sources/api.py`.
- Revisit if: we see 429s or need > 4 parallel requests.

### D11 — Bulk data goes through a local SQLite table, never per-affair scans (slice S1, 2026-10-18)
- Decision: single affairs and small runs use the API (cached). Runs above ~500 affairs load the bulk file once into a local SQLite table keyed by affair id and read from there. Never scan the file per affair. docs/04 §4.1 updated with this wording.
- Why: your call on D6's proposed doc fix; a 232 MB gzip scan per affair would take minutes per lookup.
- Alternatives rejected: bulk-first for every federal affair (original docs/04) — slow, and needs the index anyway.
- Affects: docs/04 §4.1; the SQLite loader is built in the first slice that exceeds ~500 affairs (S6).
- Revisit if: the API starts rate-limiting small runs.

### D12 — Language rule: requested / body / detected, no silent fallback (slice S1, 2026-10-18)
- Decision: federal (body `type=country`) → language must be requested; cantonal/municipal → the parliament's single official language (`body`) or, for bilingual parliaments, the language with the most doc text by a stopword detector (`detected`); cantonal never takes a language from the sample (error). Missing title/text part in the requested language → `status=lang_missing`, excluded from that language's metrics. Every text is re-checked: `lang_mismatch` when detected ≠ chosen.
- Why: your rules on D7. Data source: `/v1/bodies/` `type`, `languages`, `lang`. Sample of 100 PolitMonitor affairs (federal ×3 languages): 4/132 lang_missing, 3/128 federal mismatches (Curia Vista IT fields that contain French: 160584, 162433, 155310), 0/56 cantonal mismatches.
- Alternatives rejected: a detector library (langdetect/lingua) — extra dependency; a 30-word stopword list per language is deterministic, testable and enough for ≥ a few sentences. Title-only texts (< ~150 chars) stay undetected (`null`), never guessed.
- Affects: `sources/assemble.py`, `sources/langcheck.py`, `data/stopwords.json`, `sources/api.py` (Body), docs/03 §6, `src/tests/test_langcheck.py`.
- Decided (2026-10-18, your OK): `lang_mismatch=true` counts as `lang_missing` in metrics.

### D13 — Federal affairs use Curia Vista texts only, not attached docs (slice S1, 2026-10-18)
- Decision: for translated (federal) affairs the assembler ignores `/docs`.
- Why: federal docs are fedlex links whose extracted text is a trilingual "please enable Javascript" placeholder (e.g. 159814, 162483); it polluted the text and broke language detection. The bulk text file has no docs either, so API and future SQLite paths give identical text.
- Alternatives rejected: filtering placeholder text by pattern — brittle, and real federal docs are not in the challenge data anyway.
- Affects: `sources/assemble.py`. Consequence: Federal Council bills ("Government affairs") are title-only (5/44 federal affairs in the sample), confidence capped by the title-only rule.
- Revisit if: federal recall on bills is poor in S4/S6 — then fetch the Botschaft text from fedlex.

### D14 — Truncation is reported per affair; 40k re-run decides the limit (slice S1, 2026-10-18)
- Decision: `MAX_INPUT_CHARS` stays 12,000 for S4. `SourceText` records `cut_section` (header of the section where the cut falls) and `chars_lost`; S4 output lists them per truncated affair. After S4, re-run only the truncated affairs with `MAX_INPUT_CHARS=40000`; if ≥ 2 labels or evidence results change, raise the limit. Result logged as a new decision.
- Why: your call; 27/100 sampled affairs are truncated.
- Affects: `sources/assemble.py`, S4 report.

### D15 — JSON mode: server-side `json_schema` on the Keera gateway; parse + repair kept as fallback (slice S2, 2026-10-18)
- Decision: `LLM_JSON_MODE=json_schema` (default). The pydantic schema (`extra=forbid` → `additionalProperties: false`, `strict: true`) is sent as `response_format`. The output is always re-validated with pydantic; if invalid: parse the first JSON object, one repair retry, then `status=parse_error`. API errors → `status=llm_error`.
- Why: probe on both models: with a schema forcing `{"fruit": "banana", "n": 41}` on the prompt "Say hello.", both 70B and 8B returned exactly that, so the gateway enforces the schema (guided decoding), not just "tries". Without a schema the model answered `"label": "Yes"` (outside our enum). The fallback is unit-tested with a fake client (`src/tests/test_llm.py`), since the gateway never triggers it.
- Alternatives rejected: `json_object` mode — valid JSON but not our enum.
- Affects: `llm.py`, `classify.py` (AdhocOutput), docs/04 §3.
- Revisit if: a judge's local server lacks `response_format` → set `LLM_JSON_MODE=none`.

### D16 — Prompt files and prompt SHA (slice S2, 2026-10-18) — SHA part superseded by D20
- Decision: each prompt version is two files, `prompts/<version>.system.txt` and `<version>.user.txt` (docs/05 text verbatim). `prompt_sha` = sha256 of the two raw templates; every prediction also stores `source_sha256` of the exact assembled text.
- Why: docs/05 says "SHA of the rendered template"; a fully rendered prompt differs per affair, so it can't identify a prompt version. Template SHA + source SHA together pin down exactly what the model saw. Topic text is in the YAML (versioned in git).
- Alternatives rejected: one file with a separator — easier to break.
- Affects: `prompts/`, `classify.py`, `runlog.py`. Proposed docs/05 §0 wording: "the SHA of the template files is stored on every run".
- Revisit if: we need the topic definition hashed into the run id (S5 manifests can add the topic YAML SHA).

### D17 — Observed in S2, not changed yet: confidence semantics and rationale length (slice S2, 2026-10-18)
- Observation: on `no_match` the 70B model returns `confidence: 0.0` (e.g. 70435, also Covid-19 topic on 235308). It treats confidence as "probability of the topic", not "confidence the label is correct" (docs/05 §2). Rationales run ~35–40 words vs the 25-word rule.
- Decision: no prompt change before S4; one example is not evidence. If S4 confirms it, either (a) redefine confidence in docs/05 as "probability the topic is a main subject" (it works better as a ranking score anyway) or (b) bump to `adhoc_v2`. Rationale length is cosmetic; add `maxLength` only if it costs tokens.
- Affects: threshold tuning and calibration (S6).

### D18 — Verification details (slice S3, 2026-10-18)
- Decision: implemented docs/04 §4.3 as written (25-char / 92 fuzzy, 15-char minimum unless the evidence equals the title, title-only → evidence must be in the title, confidence capped at 0.6). Choices the doc left open:
  - all quote and apostrophe characters map to one `"`, and spaces next to a quote are removed (French `l’« identité »` vs model `l'"identité"` must match);
  - line-break hyphenation `x- y` → `xy` on **both** sides (so `Digitali- sierung` = `Digitalisierung`; a real `Aus- und` also becomes `ausund` on both sides, so it still matches);
  - the title-only cap applies to every label, not only matches;
  - `no_match`/`abstain`/`NONE_OTHER` with evidence: evidence is still checked and recorded, but never changes the status;
  - `span` is in normalised-text coordinates (enough for the UI to highlight via the evidence string; mapping back to raw offsets is not needed yet).
- Why: tests written first (`src/tests/test_verify.py`, 18 cases: exact, quote variants, hyphenation, fuzzy pass/fail, < 25 chars, too short, empty, title-only cap and title-only rejection). Real check: 235308 (de) and 329562 (it) exact; 247811 (fr) fuzzy 93.6 because the PDF has a page footer "M 3088 4/4" inside the quoted sentence — the case fuzzy exists for.
- Alternatives rejected: separate `'` and `"` classes — breaks on French guillemets and typographic apostrophes.
- Affects: `verify.py`, `classify.py` (Prediction gains `verify_ok`, `verify_method`, `verify_score`; status becomes `evidence_failed` on failure), `runlog.py`, `SourceText.title`.
- Revisit if: S4 shows evidence failures that a human would call verbatim.

### D19 — Early signals for S4 (slice S3, 2026-10-18) — observation only
- 247811 (GE, audiovisual fund, a PolitMonitor positive) → `no_match`: PolitMonitor's tag is broad ("covers … digital media", challenge README); our draft definition is not. Partner's include/exclude rules decide this, not a prompt tweak.
- 159814 (federal bill "Revision EPDG", title-only, PolitMonitor positive) → `no_match` with empty evidence. Title-only bills (D13) may be systematic misses; the prompt says "abstain" when the text is too short, and the model didn't. Count both patterns in S4 before changing anything.

### D20 — prompt_version fingerprints every input that shapes the prompt (slice S3, 2026-10-18)
- Decision: run level `prompt_version` = sha256 over part hashes {template files, topic YAML content, few-shot examples, params (model id, temperature, max_tokens, json mode, MAX_INPUT_CHARS, TITLE_ONLY_CONF_CAP)}; parts stored individually. Written to `results/runs/<run_id>/manifest.json` (S5: `runs` table) with git commit (`-dirty` if uncommitted changes) and endpoint host. Call level: `source_sha256` + `run_id` on each prediction. Template name kept as `prompt_template`.
- Why: your rule — the partner rewrites `topics/digitalisation.yaml` today; a changed definition must give a new version. Check: editing the definition changes `prompt_version` (df8e4fa22021 → e60a567845e4, changed part: topic); `MAX_INPUT_CHARS=40000` → b6800f2ccc27 (changed part: params). 4 tests in `src/tests/test_fingerprint.py`.
- Added beyond your list: `MAX_INPUT_CHARS` (changes the text the model sees; needed so the D14 40k re-run is a separate version) and `TITLE_ONLY_CONF_CAP` (changes stored confidence). Topic hash is over the parsed YAML content, so comment/whitespace edits don't create a new version but any field change (incl. keywords, which feed the keyword-absent flag) does.
- Alternatives rejected: hashing the YAML bytes — a reformatted comment would make identical prompts look different.
- Affects: `runlog.py` (fingerprint, start_run, manifest), `classify.py` (Prediction: `run_id`, no prompt fields), `cli.py`, docs/05 "Prompt versioning", docs/04 §4.4/§7.

### D21 — Partner's definition adopted; include/exclude rendered as bullet lists; template → adhoc_v2 (step 1, 2026-10-18)
- Decision: `topics/digitalisation.yaml` now follows `data/gold/digitalisation_definition.md` (11 include, 3 exclude rules, PolitMonitor's broad reading incl. media/SRG, Swiss Post, telecom). `Topic.include/exclude` are lists (a plain string is still accepted); the renderer prints them as `COUNTS AS THIS TOPIC:` / `DOES NOT COUNT:` bullet lists. Template renamed `adhoc_v1` → `adhoc_v2` and the template name is now part of the template hash.
- Why: your instruction; the old loader rejected the list YAML (pydantic `string_type` error). The rule layout is a prompt change, so it gets a new template name even though the .txt text is identical (the rendering lives in code). No number was ever reported under adhoc_v1.
- Alternatives rejected: joining list items into one line — 11 rules on one line are hard for the model to read.
- Affects: `topics.py`, `prompts/__init__.py`, `prompts/adhoc_v2.*`, tests, docs/05 §2 + changelog. New `prompt_version` for every digitalisation run (topic + template parts changed).
- Note: the new keyword lists add broad words (`Daten`, `données`, `dati`, `elektronisch`). They never enter the prompt; they only make the keyword-absent flag stricter (fewer affairs count as "keyword-absent"), which makes that demo claim more conservative.
- Revisit if: S4 shows the model over-tagging via the broad include list (e.g. any Post or SRG affair).

### D22 — Sampling rules: ≥ 2018 for like-for-like, grouped split by title_de, few-shot only from dev, first loop = dev (step 1, 2026-10-18)
- Decision: (1) like-for-like set: `begin_date ≥ 2018-01-01`; (2) dev/test split is by group — affairs with identical `title_de` land in the same split; (3) few-shot examples only from dev, never a test affair; (4) the first-loop affairs are dev (humans read their errors to revise the prompt) and are excluded from every test set.
- Why: your rules; identical titles (same motion in both chambers, cantonal standard questions) would leak between dev and test. (4) is my addition: the same leakage risk via human eyeballing.
- Affects: docs/06 §0 and §2.4, docs/05 few-shot; implemented in `evaluate/samples.py` when the samples are built (S4 first loop, S6 like-for-like), with tests for the grouped split.
- Revisit if: titles are missing for many cantonal affairs (then group by `title_fr`/`title_it` too).

### D23 — Adjudication in both directions, blind, rules frozen first (step 1, 2026-10-18)
- Decision: review all test disagreements in both directions (model yes / PolitMonitor no and model no / PolitMonitor yes; seeded sample per direction if over budget, re-weighted), plus an equal number of random agreements mixed in. The reviewer sees only the affair text, shuffled, never any label. Rules = `digitalisation_definition.md` at a recorded git hash, fixed before results. Before/after metrics; in "after" the reviewer label replaces PolitMonitor's for every reviewed affair.
- Why: your instruction and the partner's note; one-directional review would only ever raise precision.
- Affects: docs/06 §2.4; the adjudication export (S6).

### D24 — Status of D16/D20 (step 1, 2026-10-18)
- `prompt_version` already hashes template + topic YAML content + few-shot + model params (D20, committed in bd7350e); D21 adds the template name to the template hash. Nothing else pending.

### D25 — First-loop sample design (slice S4, 2026-10-18)
- Decision: `parltopics sample first-loop` (seed 42) → `data/samples/first_loop.csv`: 20 PolitMonitor positives with `begin_date ≥ 2018-01-01` and one negative per positive from the **same parliament** and period that is not in the list. 6 federal (scope `ch`, languages spread evenly, `lang` set per row), 14 cantonal from monolingual parliaments spread evenly over their languages → 7 DE / 7 FR / 6 IT on each side, 11 parliaments. Affairs that can't be assembled in the required language (lang_missing / fetch error) are skipped at build time. All rows are `split=dev` (D22).
- Why: docs/06 §1 (mixed DE/FR/IT, in-scope negatives). Same-parliament negatives keep level and language identical between positives and negatives. Languages come from the data (`/v1/bodies/`), not code.
- Alternatives rejected: federal scope `chv` — those 50 rows are federal consultations, not affairs, and have no counterpart in the federal negatives pool; bilingual parliaments — their language is detected, adds noise to a smoke test.
- Affects: `evaluate/samples.py`, `sources/api.py` (`list_affairs_since`: the API has no date filter, so we page newest-first until 2018, cached).
- Revisit if: S6 needs stratification by affair type.

### D26 — Keyword-absent flag: word-start prefix match; partner's broad keywords make it almost never true (slice S4, 2026-10-18)
- Decision: `keyword_absent(text, keywords)` = no keyword of any language starts a word (case-insensitive), so `Daten` hits `Datenschutz` and `Cyber` hits `Cyberangriffe`, but `daten` inside `Kandidaten` does not.
- Finding: with the partner's keyword list (adds `Daten/données/dati`, `elektronisch/électronique/elettronico`, `Cyber`) **0** first-loop matches are keyword-absent; with the old list (`Digitalisierung/digital`, `numérique/numérisation/digital`, `digitalizzazione/digitale`) there were **6** (all PolitMonitor positives, e.g. "Nachtrag zum Datenschutzgesetz", "Dossier électronique du patient"). Every one of the 6 contains a new broad keyword.
- **Amended (your decision, 2026-10-18):** `keywords` = core words only, matching the pitch claim exactly — de: Digitalisierung, digital\*; fr: numérique, numérisation, digital\*; it: digitale, digitalizzazione, digital\*. Daten/données/dati, elektronisch/électronique/elettronico, Cyber moved to `keywords_broad`. Two flags: `keyword_absent` (core; UI filter, pitch claim, keyword-search baseline in docs/06 §2.3) and `tech_vocab_absent` (core + broad; extra badge). Every keyword matches at the start of a word, so "Digitalisierungsstrategie" and "numériques" count as appearances (keeps the claim conservative); a word buried inside a compound ("Verwaltungsdigitalisierung") does not — known edge case. Tests: `src/tests/test_metrics.py`.
- Affects: `topics.py`, report; docs/05 §4.4 definition of the flag.

### D27 — Truncation test result: 2 changes at 40k, but no gain; limit stays 12,000 pending your call (slice S4, 2026-10-18)
- Result (rule from D14): the 15 first-loop affairs truncated at 12k were re-run at 40k (`data/samples/first_loop_truncated.csv`). Label/status changed for **2**: 77719 (gold yes) match/ok → match/evidence_failed (worse: the model's quote from the longer text failed verification), 336119 (gold no) match/evidence_failed → no_match (better). Net accuracy unchanged. Both are still truncated at 40k (49k and 189k chars). 10 more changed only their evidence sentence. Input tokens on these 15: 54,692 → 120,194 (×2.2).
- Control: the same 15 at 12k again → **0** label changes (1 evidence, 2 confidence changes), so the model is effectively deterministic and the 2 changes are caused by the longer input.
- All 15 cuts fall in DOCUMENT sections of cantonal affairs (government reports of 12k–391k chars); no federal affair is truncated, and title + submitted text are never cut.
- Decision: the D14 rule is met literally (2 ≥ 2), but the changes cancel out and cost ×2.2 tokens. **Recommendation: keep 12,000**; re-test on the S6 dev set (larger n). Your call.
- **Amended (your decision, 2026-10-18):** keep 12,000. The "≥ 2 changes" rule is replaced by: on the S6 dev set, compare 12k vs 40k on the truncated affairs by net accuracy change (with n) and tokens; raise the limit only if net accuracy improves meaningfully. Added to docs/06 §2.5.

### D28 — Confidence semantics confirmed: the model returns P(topic), not P(label correct) (slice S4, 2026-10-18)
- Finding (D17 follow-up): 22 of 25 non-match answers have confidence 0.0; matches have 0.6–1.0. So the number behaves as "probability the topic is a main subject", which is exactly what a ranking score / threshold curve needs.
- Proposal: change docs/05 §2 to define `confidence` that way (no prompt change, no new prompt_version). Threshold tuning (S6) then uses it directly. Pending your OK.
- **Amended (your decision, 2026-10-18):** the definition goes into the prompts too — one system line "confidence = how likely it is that the affair is about this topic (0 = certainly not, 1 = certainly)" (`adhoc_v3`; standard mode: per label, how likely that label applies). New prompt_version, before S6. Post-processing adds `inconsistent` (match < 0.5 or no_match > 0.5, on the raw confidence before the title-only cap), counted and reported; it is a flag and does not change `status`. `abstain` keeps its confidence, is counted separately and treated as not-match for P/R. docs/05 §2/§3/§4 updated; tests in `test_verify.py`, `test_metrics.py`. `adhoc_v2` template files removed from the tree (in git history at a5ac49f).

### D29 — First-loop result and error pattern (slice S4, 2026-10-18) — dev observations, not reported numbers
- Partner definition (prompt_version 3e7c090902c6): positives 14/20 matched (70%, CI 48–85%), negatives 19/20 not matched (95%, CI 76–99%), evidence verified 14/15 = 93% (≥ 90% gate from docs/06 §1 passed). Old draft definition: 15/20, 19/20, 15/16. 4 affairs changed between the two (1 fixed, 2 broke, 1 no_match→abstain on a negative). With n=20 the difference is noise.
- Misses: two contradict explicit include rules (64439 media licence fee for SMEs; 229042 access to population-register data for health tasks) → prompt adherence; four are borderline/broad PolitMonitor tags (telework, culture with digital channels, transparency law, electronic water inventory). The one negative error (336119) was caught by verification (evidence_failed, never shown).
- Rationales sometimes come back in German/Italian although the prompt asks for English (cosmetic).
- Next: partner's 10-minute review of these errors (docs/06 §1) before any prompt revision.

### D30 — SQLite store: append-only predictions and reviews, enforced by triggers (slice S5, 2026-10-18)
- Decision: `store.py` implements docs/04 §4.4 with these concrete choices: the exact assembled text is stored once per `text_sha256` in `sources` (so verification and UI highlighting can be replayed); `gold` is copied onto each prediction from the sample file; `lang_missing`/`fetch_error` rows are stored as predictions without a source; topics are keyed by the topic part hash, so an edited definition is a new topic row; the full run manifest is stored as JSON next to the indexed columns. Append-only is enforced by SQLite triggers on UPDATE/DELETE for `predictions` and `reviews`; `correct` reviews must carry a corrected label (CHECK). Batch workers run in threads; rows are written from the main thread as results arrive.
- Why: docs/04 §4.4 rules ("predictions are append-only; reviews never mutate predictions; every prediction points at a run") are now guarantees, not conventions. 6 tests in `src/tests/test_store.py`. Verification: two `make first-loop` runs stored side by side, old run reported and diffed (0 changes, same prompt_version); a direct `UPDATE predictions` is refused ("predictions are append-only").
- Alternatives rejected: keeping `predictions.jsonl` per run as well — two sources of truth. Removed; `calls.jsonl` + `manifest.json` stay (docs/04 §7). The S4 runs before the store exist only as JSONL in `results/runs/` (gitignored) and in `results/first_loop.md`.
- Affects: `store.py`, `batch.py`, `cli.py` (`runs`, `review add|show`, reports from the store), `config.py` (`DB_PATH`), docs/04 §4.4.
- Incident: during verification I added a test review attributed to the partner to the real DB; since reviews are append-only, I deleted the (gitignored, rebuildable) DB and re-ran both first loops, and did the review check on a throwaway copy. The real DB holds 0 reviews.

### D31 — One correctness rule for summary and run diffs (slice S5, 2026-10-18)
- Decision: `metrics.is_correct(row)`: gold yes → shown as match (status ok + label match); gold no → status ok and label ≠ match; any failure status is wrong. Used by the summary and by `compare`.
- Why: `compare` used "shown as match" only and called 336119 (negative, evidence_failed → no_match) "same outcome", while the summary counts evidence_failed as wrong. Test added.
- Affects: `evaluate/metrics.py`, `evaluate/report.py`.

### D32 — adhoc_v3 first-loop result (slice S5, 2026-10-18) — dev observation
- prompt_version d420fc57afb3 (adhoc_v3 + core keywords): positives 14/20, negatives 20/20, evidence 14/14, keyword-absent matches 6 (0 also tech-vocab-absent), 1 abstain, 1 inconsistent (156184 no_match at 0.6). vs adhoc_v2: 1 change (336119 fixed). Confidence now spans 0.2–0.6 for some non-matches instead of always 0.0, which the S6 threshold curve needs.

### D33 — Partner workbooks (step 3, 2026-10-18)
- Decision: `parltopics partner files` writes four workbooks to `data/gold/for_partner/`, each with a plain-English README sheet carrying the priority order (1 politmonitor_list → 2 cv_aps_mapping → 3 aps_gold_30 optional → 4 adjudication later):
  - `politmonitor_list.xlsx`: all 3,433 rows, readable headers, real dates, clickable links, filters on every column, plus `Full text available`, `Keyword-free (core words)` and `Also no tech words`. Keyword flags are computed over the **untruncated** full text, all language versions for federal affairs (`evaluate/keyword_scan.py`, 0 errors): 1,342 keyword-free; 1,186 keyword-free **with** full text (CHE 593, BE 82, VS 70, NE 46 …). Title-only affairs (179) are keyword-free too easily, hence the extra column (my addition).
  - `cv_aps_mapping.xlsx`: 28 Curia Vista areas, pre-filled with my best-guess APS chapters from `data/gold/cv_aps_mapping_draft.csv` (drafted by the AI coding assistant, flagged as such in the README), `Correct? (yes/no)` dropdown and `Correction`; second sheet lists the 22 APS chapters DE/FR with links.
  - `aps_gold_30.xlsx`: 30 affairs from `data/samples/aps_gold.csv` (15 federal 5/5/5 DE/FR/IT, 15 cantonal 5 per language from monolingual parliaments, ≥ 2018, not title-only, first loop excluded, seed 7), title, link, 1,200-char excerpt, dropdowns over the 22 chapters (+ NONE) and 165 topics, optional second label, unsure flag. No model output. Marked optional.
  - `adjudication.xlsx`: template (Review No., Affair ID, Title, Link, Text excerpt, yes/no/unsure dropdown, Note) + a Definition sheet copied from `data/gold/digitalisation_definition.md` with the author line removed (no names in files). S6 fills it.
- Why: your step 3 and priority list. Non-Apertus help: the CV→APS draft was written by the AI coding assistant (Claude); this must be named in the technical report (docs/07).
- Affects: `partner.py`, `evaluate/keyword_scan.py`, `evaluate/samples.py` (`build_aps_gold`), `cli.py`.

### D34 — Federal bulk texts in SQLite, verified identical to the API (step 3, 2026-10-18)
- Decision: `parltopics data load-bulk` loads `che_affairs_keywords.csv` + `che_affair_texts.ndjson.gz` once into `data/cache/bulk.db` (gitignored, 920 MB, 19 s; 70,008 affairs, 210,437 texts). `sources/router.AffairSource` reads federal affairs from it when present, everything else from the cached API (D11).
- Why: the keyword scan (3,433 affairs) and S6 (whole federal slice) exceed ~500 affairs. Check: 30 random federal affairs × DE/FR/IT → 90/90 assembled texts byte-identical (same sha256) between bulk and API.
- Note: bulk affairs carry only the Curia Vista DE link (the CSV has one URL); FR/IT source links fall back to it.

### D35 — S6 like-for-like slice: federal affairs ≥ 2018 without consultations; baseline reproduced (S6 prep, 2026-10-18)
- Decision: population = `che_affairs_keywords.csv` rows with `begin_date ≥ 2018-01-01` and `type_en ≠ Consultation` (27,465 affairs). Positives = PolitMonitor rows with scope `ch` (1,396; π = 0.0508). Consultations are excluded on both sides because PolitMonitor tracks them under a separate scope (`chv`, 50 tagged); keeping them would count tagged consultations as negatives.
- Check (docs/06 §2.2): baseline "Curia Vista area contains Medien und Kommunikation" (area id 34) → precision 40.9 %, recall 80.2 % on the full slice — reproduces the ≈ 41 % / ≈ 81 %. Identical with or without consultations (they carry no Curia Vista areas).
- The baseline area id is passed as data (Makefile/CLI), not hard-coded in Python.
