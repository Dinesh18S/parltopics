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

### D36 — S6 sample and evaluation design (slice S6, 2026-10-18)
- Decision: `parltopics sample digi-federal --pm-scope ch --exclude-type Consultation --exclude-sample data/samples/first_loop.csv` → `data/samples/digi_federal_2018.csv` + `.meta.json` (population counts for prevalence correction). 150 positives + 250 negatives drawn at random (seed 42) from the D35 slice; language by rotation over the title languages present (DE/FR/IT); dev/test split 30/70 grouped by normalised German title (0 titles straddle the split); first-loop affairs excluded. Result: dev 46 pos / 67 neg, test 104 pos / 183 neg.
- Evaluation (`parltopics eval digitalisation <run> --cv-area 34`, `make eval RUN=…`): both baselines exact on the whole slice; threshold chosen on dev only; test metrics = recall (Wilson CI), FPR (Wilson CI), prevalence-corrected precision and F1 (stratified bootstrap, 1,000×, seed 42), raw sample precision labelled as such; breakdowns by language, type, title-only; `lang_missing` and `lang_mismatch` excluded and counted (D12). Writes `results/metrics.json` (key `digitalisation_federal_2018`) and `results/metrics.md`.
- Federal texts come from the bulk table (D34); batch runs use `AffairSource`.

### D37 — Threshold rule "max corrected F1 on dev" is fragile at this n (slice S6, 2026-10-18) — needs your call
- What happened: on dev, t = 0.9 gave FP = 0/67, so corrected precision 100 % and the highest F1 → chosen. On test, 0.9 gives precision 77.6 % (CI 49–100 %) / recall 40.6 %; 0.5 gives 51.9 % (35–84 %) / 63.4 %. Corrected F1 on test is higher at 0.5 (≈ 57 %) than at 0.9 (53 %).
- Why fragile: with π = 5 %, corrected precision is driven by FPR, and 67 dev / 159 test negatives cannot pin an FPR below ~3 % (test FPR CI 0.1–3.5 %).
- Options: (a) more negatives (e.g. +600 → ~10 min of model time) before choosing; (b) pre-register a fixed operating point (0.5, the docs/05 default) and report the dev curve as information; (c) choose by product goal (human review favours recall). Both thresholds are in metrics.json.

### D38 — S6 first result (slice S6, 2026-10-18)
- Run 20261018T132629077874Z, apertus-v1-5-70b, adhoc_v3, prompt_version d420fc57afb3 (git commit marked -dirty: code changed during the run, prompt/topic/params did not; re-run on a clean commit before reporting).
- Baselines, full slice (27,465): Curia Vista "Medien und Kommunikation" P 40.9 % / R 80.2 %; core-keyword search P 41.3 % / R 56.4 %.
- Model, test (101 pos + 159 neg after exclusions): see D37. Evidence verified 69/76 model matches (3 fuzzy); 7 evidence_failed, 1 parse_error, 1 abstain, 1 inconsistent. Keyword-absent matches shown: 14, all PolitMonitor-tagged.
- Recall by language at t = 0.9: DE 28.6 %, FR 54.5 %, IT 39.4 % (n ≈ 33–35 each; wide CIs). Title-only (federal bills): 0/7.
- Error check (pipeline only, no tuning on test): the dev evidence failures are real paraphrases (match scores 52–71), not a verification bug.
- Recall is the weak side. Any prompt revision must be driven by **dev** errors only (AGENTS.md), then re-run once on test.

### D39 — Curia Vista "Italian" texts are often French (slice S6, 2026-10-18)
- 27 of ~100 sampled federal rows requested in Italian had French in the IT field (title and text): `lang_mismatch`, excluded per D12. Far more than S1 suggested (3/128). Italian federal coverage is therefore thinner than the file README implies; report the exclusion count with every IT number.

### D40 — Review sheet export and key (slice S6, 2026-10-18)
- `parltopics eval digitalisation` fills `data/gold/for_partner/adjudication.xlsx` (blind: Review No., Affair ID, Title, Link, excerpt, yes/no/unsure, Note; shuffled) and writes the key to `results/adjudication_key.csv` (group, PolitMonitor label, model outcome, prediction id). Budget 40 per direction + equal number of agreements. At t = 0.9 the test split has 1 model-yes/PM-no and 60 model-no/PM-yes (40 sampled) → 82 rows. The sheet is regenerated if the threshold changes (D37). The key is committed for reproducibility; the reviewer should not open it before finishing.

### D41 — Pre-registered threshold rule for the final digitalisation evaluation (S6 finish, 2026-10-18) — logged BEFORE running
- Rule (fixed now, before any new run): the decision threshold for "shown as match" is the value in {0.5, 0.6, 0.7, 0.8, 0.9} that **maximises prevalence-corrected F1 on the enlarged dev set**; ties → the lower threshold. It is then applied unchanged to the test split, which is run **once** with the final prompt.
- Order (your plan): adhoc_v4 revised on dev errors only → enlarge the sample with ~600 untagged in-scope federal affairs (2018+, same title grouping, most to dev) → apply this rule on the enlarged dev set → run test once → regenerate the review sheet from that test run.
- Transparency (for the report's limitations): the test numbers of run 20261018T132629077874Z (adhoc_v3; t = 0.9: P_corr 77.6 % / R 40.6 %; t = 0.5: 51.9 % / 63.4 %) **were observed before this rule was fixed** and before adhoc_v4. They are not used for any choice; the test split's affairs stay in the test split, and the final numbers come from the new single test run. I also read some adhoc_v3 test misses (pipeline bug check, D38); none of them is used to drive adhoc_v4.
- Additional output: full precision/recall curve on test (thresholds 0.00–1.00), with the Curia Vista baseline as a single point, saved to metrics.json for the Metrics tab and report.

### D42 — adhoc_v4 → adhoc_v5, driven by dev errors only (S6 finish, 2026-10-18)
- Dev errors of adhoc_v3 (run 20261018T132629077874Z, dev split only, 18 misses / 2 false alarms) were sorted into: (a) genuine misses where the model rejected a case the topic's include list names — 65715 (RSI radio channel, public broadcasting), 201558 (radio/TV licence fee), 155597 (Swiss Post influencers), 154970 (postal tariffs for foreign online-shop parcels); (b) correct match with non-verbatim evidence — 153251, 154847, 334659; (c) likely PolitMonitor noise, not used — 65213 crisis management, 65555 structural policy, 159118 whistleblowers, 201673 genetic resources, 338630 hepa.ch, 235228 ("AI" = Italian for invalidity insurance); borderline, not used — 63553, 155027, 213962, 153612, 154412.
- adhoc_v4 (from (a)): system rule "The lists under COUNTS AS THIS TOPIC and DOES NOT COUNT are part of the definition. If the main subject … is one of the listed cases, it matches, even when the affair never uses the topic's name or the words of the definition." Dev (old 113): positives 27/45 → 30/45, FP 2/64 → 2/64, but none of the four (a) cases fixed; their rationales still argued from the general definition sentence.
- adhoc_v5 (same (a) cases): the rule now says "Check the COUNTS AS THIS TOPIC list first … do not reject it because the general definition sentence seems not to fit or because the affair never uses the topic's name." Dev (old 113): positives 33/45, FP 2/64; fixed 154970 and 153612; 65715, 201558, 155597 still missed. Final prompt = adhoc_v5 (time-box: no further iteration). Both rules are topic-agnostic (no topic words in templates; test enforces it).
- Affects: `prompts/adhoc_v4.*`, `prompts/adhoc_v5.*`, docs/05 changelog.

### D43 — Evidence retry in post-processing (S6 finish, 2026-10-18)
- Decision: when a `match` fails evidence verification, the conversation continues once with "Your evidence was not found verbatim in the text. Copy one sentence exactly as written. Return the same JSON object with the corrected evidence." (file `prompts/adhoc_v5.retry.txt`, part of the template hash). If the new answer verifies, it replaces the first; otherwise the first answer stays `evidence_failed`. Latency and tokens include the retry. New prediction fields `evidence_retried`, `evidence_recovered` (store migrated in place). metrics.json reports the evidence-failure rate before and after retry.
- Dev (old 113): adhoc_v4 recovered 2/3, adhoc_v5 3/4. Tests: `src/tests/test_classify.py` (recovers, fails twice, no retry when verified).

### D44 — Enlarged sample digi_federal_2018_v2 (S6 finish, 2026-10-18)
- Decision: `parltopics sample enlarge-negatives` adds 600 untagged in-scope federal affairs (same population, seed 4242) to the frozen 400: existing rows keep their split; a new row whose German title group already exists inherits that split; new groups go to dev with p = 0.58. First-loop and APS-gold affairs excluded. Result: dev 46 pos / 403 neg, test 104 pos / 447 neg; 0 title groups straddle the split. Files: `data/samples/digi_federal_2018_v2.csv` + `.meta.json`.

### D45 — Threshold fixed by the D41 rule on the enlarged dev set, before the test run (S6 finish, 2026-10-18)
- Dev run 20261018T134630509400Z (adhoc_v5, prompt_version fe05482ef754; 45 pos / 355 neg after excluding 4 lang_missing + 45 lang_mismatch): corrected F1 0.581 (t = 0.5/0.6), 0.568 (0.7), 0.580 (0.8), **0.611 (0.9)** → **threshold 0.9**. Dev FPR at 0.5 is 3.9 % (14/355), at 0.9 1.4 % (5/355).
- Next: the test split runs once with adhoc_v5 and this threshold; no prompt change after it without a new, separately logged evaluation.

### D46 — Final digitalisation result (S6, 2026-10-18) — single test run
- Runs: dev 20261018T134630509400Z + test 20261018T134941952960Z, apertus-v1-5-70b, adhoc_v5, prompt_version fe05482ef754, threshold 0.9 (D45, re-derived identically by `parltopics eval`). Git commit recorded as 5a4f551-dirty: the adhoc_v4/v5, retry and sample code were uncommitted while running and did not change after the runs; the next commit contains exactly that code.
- Test (101 pos + 390 neg after excluding 7 lang_missing + 102 lang_mismatch): **prevalence-corrected precision 69.5 % (95 % CI 53.0–91.0 %), recall 54.5 % (44.8–63.8 %), corrected F1 61.0 % (50.6–71.3 %)**; FPR 1.3 % (0.5–3.0 %); raw sample precision 91.7 % (not a population number). At t = 0.5 (reference, not chosen): 54.4 % / 74.3 %.
- Baselines, full slice: Curia Vista "Medien und Kommunikation" 40.9 % / 80.2 % (F1 54.2 %); core-keyword search 41.3 % / 56.4 % (F1 47.7 %).
- Reading: precision is clearly above both baselines (CI lower bound 53 % > 41 %), recall is below the Curia Vista area's. Corrected F1 is higher than both point estimates but the CI overlaps the area baseline. The docs/01 success criterion "precision clearly above 41 % at comparable or better recall" is met on precision, **not** on recall.
- Quality: evidence verified 88/92 model matches (10 fuzzy); evidence-failure rate 15.2 % before retry → 4.3 % after (10/14 recovered). Abstain 3, inconsistent 3. Keyword-absent matches shown: 21, of which 18 PolitMonitor-tagged; 3 also tech-vocab-absent.
- Breakdowns (wide CIs, n ≈ 33–35 positives each): recall DE 57.1 %, FR 60.6 %, IT 45.5 %; federal bills (title-only) 0/7. 102 test rows had French in the Curia Vista "Italian" fields (D39) and were excluded.
- Review sheet regenerated from this test run: 90 rows = all 5 model-yes/PM-no + 40 of 46 model-no/PM-yes + 45 agreements, shuffled, blind (`data/gold/for_partner/adjudication.xlsx`, key `results/adjudication_key.csv`). After-review numbers come from it (docs/06 §2.4).
- Limitations to state in the report: the adhoc_v3 test numbers were seen before the threshold rule was fixed (D41); prompts were revised on dev only; dev/test come from the same frozen sample; PolitMonitor labels are a lower bound (README of the challenge files).

### D47 — Demo UI follows the private reference; fonts served locally (slice S8, 2026-10-18)
- Decision: the UI (`src/web/index.html`, `style.css`, `app.js`; vanilla JS, no build step) implements the reference screens in `designs/` (gitignored, never committed): explore table, row detail panel, live classification with progress + cancel, metrics tab, empty / model-unreachable / no-matches / rejected states, token sheet. Inter + IBM Plex Mono are served from `src/web/fonts/` (OFL, licences included).
- Why: your reference; docs/02 said "system stack" — changed so the look matches while staying offline/air-gapped capable (no Google Fonts at runtime). docs/02 updated.
- Standard mode shows an honest "built in S7" note; metrics cards for S7/S9 say "pending" instead of the reference's "XX%".

### D48 — Demo pool and cached results (slice S8, 2026-10-18)
- Decision: `parltopics sample demo-pool` (seed 7) → `data/samples/demo_pool.csv`: 200 affairs, ≥ 2018, 35 parliaments, half federal: 60 keyword-free PolitMonitor positives with full text, 40 other positives, 100 in-scope negatives (federal from the bulk table, cantonal 4 per parliament); `lang_mismatch` rows skipped. Both presets pre-computed with adhoc_v5 (runs 20261018T141718036138Z digitalisation, 20261018T141858835540Z covid19) and exported by `parltopics demo export` to `results/demo/<preset>.json` (≈ 1.8 MB each, committed). On start the API imports any cache whose run is not in the store, so a fresh clone without endpoint demos from cache and reviews still work.
- The UI shows a row as "suggested" when status ok + label match + confidence ≥ `MATCH_THRESHOLD` (default 0.9, D45). Matches below the threshold and evidence-failed rows are hidden behind counters ("2 rejected (evidence not found)", "24 below threshold") that expand on click (docs/02 §3).
- Default preset is `DEMO_DEFAULT_PRESET` (.env; `digitalisation` in .env.example) — no topic name in Python.

### D49 — API shape (slice S8, 2026-10-18)
- Decision: routes under `/api/*` (docs/04 §4.5 updated). Live search is `POST /api/search` streaming NDJSON (not SSE: EventSource cannot POST); a client abort cancels pending model calls. The batch runner became a generator (`batch.iter_classify`) shared by CLI and API. Custom UI topics get `keywords = {topic name}` so "keyword absent" still means "the topic's name never appears".
- Evidence highlighting: `verify.locate()` finds the evidence span in the original text (exact, else the best fuzzy window), so fuzzy-verified evidence is highlighted too (test added).

### D50 — S8 verification (slice S8, 2026-10-18)
- docs/02 §7 checks automated with Playwright + local headless Chrome (script kept outside the repo): 9/9 in live mode and 9/9 in cached mode starting from an empty database with no endpoint — default preset loads (45 suggestions), every visible match has verified evidence + link, keyword-absent filter (23 shown, 21 PolitMonitor-tagged), detail panel highlights evidence, keyboard C confirm persists across reload, metrics tab renders, new topic streams + cancel (cached: Classify disabled, banner shown), 1280×720 without page overflow, no JS errors. `make run` (Docker) serves UI, fonts, presets, live mode.
- Open: the recorded backup video (docs/02 §7 item 6).
- Incident: my first UI check ran against the real DB and recorded 2 confirm reviews (reviewer "ui") on demo prediction 1714. Reviews are append-only; they touch no evaluation sample or metric. All later checks used throwaway DB copies. Removing them needs a DB rebuild — your call.

### D51 — Visible review state in the detail panel (S8 follow-up, 2026-10-18)
- Problem (your test): pressing Confirm saved the review (7 reviews were recorded on one affair while testing) but the panel looked unchanged, so it seemed broken.
- Fix: the panel shows "✓ Confirmed by reviewer" / "✕ Rejected by reviewer" next to the topic, the pressed button changes to "✓ Confirmed" / "✕ Rejected" (aria-pressed), and a status line says what was saved and how many reviews are on record (latest counts).

### D52 — Reading aid in the reviewer's language (S8 follow-up, 2026-10-18)
- Decision: `REVIEW_LANG=de` enables a reading aid in the detail panel when the affair is in another language: (1) the parliament's **official** version (federal affairs: Curia Vista DE/FR/IT), else (2) on request an **unofficial Apertus translation** of the first 2,000 characters, labelled "not evidence". Labels and evidence stay on the original text.
- Translation model: `TRANSLATE_MODEL=apertus-v1-5-8b`. Measured on a 2,000-char French cantonal text: 70B 166 s, 8B 4.5 s, near-identical German. Still Apertus only (sovereignty rule); classification stays on 70B.
- Affects: `api.py` (`/api/predictions/{id}/reading`, `/translate`), `llm.complete_text`, `prompts/translate_v1.system.txt`, `app.js`, docs/02 §5.

### D53 — Review sheet shows official German versions (S8 follow-up, 2026-10-18)
- Decision: `adjudication.xlsx` (same 90 affairs, same order and seed) shows title + excerpt in `REVIEW_LANG` when the parliament publishes an official version, prefixed "[Official DE version; original is IT]". Result: 27 originally DE + 61 official DE versions; 2 recent FR affairs have no DE version and stay in French, marked. No machine translation in the review sheet. metrics.json unchanged.
- Why: the reviewer reads German only; official translations are authoritative and need no model.

### D54 — The partner's 5 worked cases vs PolitMonitor and the model (S8 follow-up, 2026-10-18)
- Cases (all federal 2018, all PolitMonitor-tagged, none in the S6 sample; 63243 is in the demo pool): partner yes on 153741 (net neutrality); no on 63243 (Amazon/Post parcel prices); no/unsure on 152976 (Post–Amazon partnership), 62615 (fake news), 62624 (civil service for cybersecurity).
- Model (adhoc_v5, DE): 153741 match 1.00, 63243 no_match 0.20, 152976 match 0.85, 62615 match 0.70, 62624 match 0.95. At the 0.9 threshold the model agrees with the partner on 4/5; PolitMonitor agrees with her on 1/5.
- Conflict to resolve **before the blind review** (D23: rules fixed first): her case rubric ("Ziel oder Nebensache?", "Ohne Digitales sinnvoll?") says no for 62624 and 152976, but her definition says "Cybersecurity → Yes" and counts "parcel deals with online platforms". Either the rubric or the definition must be the rule. Not used for any prompt or threshold change (no tuning on these cases).

### D55 — Review rule = the partner's two questions (S8 follow-up, 2026-10-18)
- Decision (partner, via you): in the blind review each affair gets two answers — "Digitale Technik drin?" (ja/nein/unsicher) and "Ziel oder Nebensache?" (Ziel/Nebensache/unsicher). Entscheid = ja only if ja + Ziel; nein if nein or Nebensache; otherwise unsicher. The sheet computes it (formula column), so the rule is applied identically to every row. Fixed now, before she sees any row (D23). docs/06 §2.4 updated.
- Consequence to state in the report: this rule is **stricter than PolitMonitor's tag and than the prompt's include list** (e.g. civil service for cybersecurity, Post–Amazon partnership: digital present but a side matter → nein). The reported test numbers (D46) used the frozen adhoc_v5 prompt; "after review" numbers will measure the model against her stricter concept. "unsicher" is reported separately and not counted as either side.
- Not changed: the prompt/topic definition (any change now is a new, separately logged evaluation — D41/D46).

### D56 — Two pre-registered readings of the review (S8 follow-up, 2026-10-18) — logged before the review starts
- The sheet records both of the partner's answers, so after-review metrics are reported twice, decided now:
  - **Primary (strict, her rule):** reviewer yes = "Digitale Technik drin? = ja" AND "Ziel oder Nebensache? = Ziel".
  - **Secondary (broad):** reviewer yes = "Digitale Technik drin? = ja" (closer to PolitMonitor's wide tag).
  - "unsicher" in the deciding answer → excluded from that reading and counted.
- Why: the partner is unsure whether the strict rule or a broad reading is right; recording both answers lets us report both without changing the rule after seeing cases. No rule, prompt or threshold change follows from either reading.

### D57 — Who reviews, and how we describe it (S8 follow-up, 2026-10-18)
- The reviewer is the team's partner, a master's student in political science — not an independent DVS/PolitMonitor expert. Wording everywhere: "blind human review by a team member (MA student, political science)", never "expert review" / "confirmed by expert" (docs/06 §2.4 headline line and the Metrics tab fixed; her own definition file still says "blind expert review" — hers to change).
- Limitation for the report: the reviewer is not independent and knows the project's aim. Mitigations: blind sheet (no model or PolitMonitor label, shuffled, agreements mixed in), rule fixed before the review (D55), two pre-registered readings (D56). An independent second reviewer on a subset (inter-rater agreement) is the named next step.

### D58 — Rows seen outside the blind setting are excluded from after-review metrics (S8 follow-up, 2026-10-18) — logged before the review starts
- 65590 (Velomitnahme im Zug) is one of the 90 review rows and the partner already judged it in her own worked cases ("Nein") while picking demo affairs → excluded from all after-review metrics; reported as excluded.
- `politmonitor_list.xlsx` reveals PolitMonitor's tag. Rule: the reviewer writes "bekannt" in the Note column for any affair she recognises; such rows are excluded the same way and counted. Stated as a limitation (team-member reviewer who has seen the positive list).

### D59 — Partner's demo picks added to the demo pool (S8 follow-up, 2026-10-18)
- Added 215092 (Deepfakes regulieren), 153587 (Heimatschein), 253543 (Kinder vor manipulativen Algorithmen), 153741 (Netzneutralität) to `data/samples/demo_pool.csv` (now 204, split `pos_partner_pick`, lang de). Re-ran both presets (digitalisation 20261018T153043165005Z, covid19 20261018T153221289354Z) and re-exported `results/demo/*.json`. All four shown (match ≥ 0.95, exact evidence); 215092 and 153587 are keyword-absent — the demo's "keyword search misses it" examples. Demo now shows 49 suggestions, 25 keyword-absent.
- The demo pool is not an evaluation set; 215092 and 253543 are S6 dev affairs (allowed), none is a test affair.

### D60 — Bug: ad-hoc topic switching reused the preset's definition (S8 fix, 2026-10-18)
- Symptom (your test): typing "Tamil" and pressing Classify returned the digitalisation affairs labelled "Tamil" at 0.95, with rationales about digitalisation; 39/200 "matches".
- Cause: (a) yes — the UI sent the custom name together with the definition and include/exclude lists still loaded from the Digitalisation preset, so the model was asked about "Tamil" *defined as digitalisation*. (b) no — the table showed only the new run, it was a genuine new run with the wrong definition. (c) partly — custom topics got their own name as a keyword list, so every row showed "keyword absent".
- Fix: changing the topic name clears definition and lists; the server builds a custom topic only from what the user gave (`api.build_topic`, tested) and uses the neutral default "Affairs whose main subject is {name}." when no definition is given; the strip shows "Definition used: …". A new run empties the table; every pool affair shows "Analyzing…" until its own result arrives; items from another run id are ignored. Keyword flags are `None` for topics without keyword lists and the UI shows no keyword toggle or badges for them.
- Live check (`parltopics check topic`, `make check-topics`; not a unit test because it calls the model): Beekeeping ≤ 2 shown matches, Tamil ≤ 10 (only genuine Sri Lanka / Tamil / asylum affairs expected). Results below.
- Also in this fix: source links per language for federal affairs (`/de/`, `/fr/`, `/it/` from the Curia Vista URL pattern; test added); keyword rules — `word*` = prefix, plain words and phrases = whole word (so "KI" ≠ "Kinder"); `keywords_broad` extended with KI / IA / künstliche Intelligenz / intelligence artificielle / intelligenza artificiale, Internet, online / en ligne, Algorithm* (Italian "AI" deliberately not added: it means invalidity insurance); core keywords written with `*` so their meaning is unchanged; the UI threshold is read from `results/metrics.json` (chosen on dev, D45), config only as fallback; the amber badge says "Cached results" and appears only in cached mode (no "Sample data" on real results). Demo presets re-computed (topic YAML changed → new prompt_version for the demo; the S6 numbers keep their recorded version fe05482ef754).
- Check results: Beekeeping 1/204 shown, Tamil 1/204 shown → PASS (limits 2 and 10). Digitalisation preset re-run 20261018T154211287752Z (prompt_version 51fab895066d), Covid-19 20261018T154355071245Z.

### D61 — Known failure: topic drift on long inputs (S8 fix, 2026-10-18) — not fixed in the frozen prompt
- The single false match in both checks is the same affair, 199828 (AR, ammonia interpellation, 12,000 chars after truncation): "match 1.00" for Beekeeping and for Tamil; rationales only describe ammonia. Probe: same affair, same prompt → match at 12,000 chars, **no_match at 6,000 and 3,000 chars** for both topics; a more explicit default definition did not help; the text contains no prompt-like content. Reading: with the topic stated once before a very long text, the model judges "is there a clear main subject" instead of "is it this topic".
- Not fixed now: the fix is a prompt change (restate the topic name and the question after the affair text, `adhoc_v6`), which is a new evaluation (D41/D46) → dev first, logged separately. Until then: stated as a limitation; the inconsistency is visible in the UI (rationale contradicts the topic).

### D62 — S7 Curia Vista standard mode: design, dev result, rule fixed before test (slice S7, 2026-10-18)
- Schemes are data (`schemes.py`): 28 Curia Vista areas from `che_topics_vocabulary.csv` (DE/FR/IT), 22 APS chapters and 165 topics from `aps_topics.xlsx` (DE/FR; IT affairs get the `SCHEME_LABEL_FALLBACK=de` label). Codes shown to the model are short local ids (CV01…, C01…, T001…) and are an enum in the JSON schema, so the gateway can only return listed codes.
- Prompt `standard_v1`: docs/05 §3 text + per-label confidence line (D28) + the task **repeated after the affair text** (lesson from D61). One record per chosen label (label = source id), each label's evidence verified separately; NONE_OTHER must stand alone (else dropped and flagged). APS is two-stage: chapters, then topics only within chapters whose evidence verified (implemented, not yet evaluated — needs the partner's mapping / gold).
- Sample `data/samples/curia_vista.csv` (seed 28): federal ≥ 2018 without consultations, ≥ 15 affairs per area (rarest area first), 174 affairs, dev 52 / test 122, grouped by title. Stratifying raises label cardinality: sample 3.23 gold labels per affair vs 2.63 in the population — recall is bounded by the 3-label cap and must be read with that in mind.
- Bug found on dev: first run had 5/52 `parse_error` — JSON cut off at `LLM_MAX_TOKENS=400` (3 labels with evidence + rationale). Fix: `LLM_MAX_TOKENS_STANDARD=900` for standard prompts only (ad-hoc prompt_version unchanged, 51fab895066d). Also fixed: `classify` defaulted to `adhoc_v4`; now `adhoc_v5` (ad-hoc) / `standard_v1` (standard). All reported ad-hoc runs had passed `adhoc_v5` explicitly.
- Dev result (run 20261018T161603708568Z, prompt_version 062b5a8c6489): n = 47 (5 lang excluded), at-least-one-correct 37/47 = 78.7 % (95 % CI 65.1–88.0 %), micro-F1 0.367 (0.295–0.435; P 0.475, R 0.299), macro-F1 0.310, labels/affair gold 3.34 vs predicted 2.11, NONE_OTHER 0 %, evidence_failed 9/119 labels.
- Rule fixed **before** the test run: every label with verified evidence counts (no confidence threshold); evidence_failed labels are dropped; test runs once with standard_v1 as is.
- Incident: the first test attempt (run 20261018T161733353718Z) aborted with "database is locked" because the UI server (`make dev`) was writing the same SQLite file; it stored 106 label records and never finished. It is **excluded and was never evaluated**; the complete test run below is the single evaluated test run. Fix: the store now opens SQLite in WAL mode with a 30 s lock timeout.
- **Test result** (run 20261018T161841410788Z, same prompt_version 062b5a8c6489; n = 112 after 15 lang exclusions): at-least-one-correct **93/112 = 83.0 % (95 % CI 75.0–88.9 %)**, micro-F1 **0.425 (0.380–0.471; P 0.559, R 0.343)**, macro-F1 0.412, labels/affair gold 3.22 vs predicted 1.98, NONE_OTHER 0 %. Saved in `results/metrics.json` → `curia_vista_standard`. Reading: the model usually finds at least one of the parliament's own areas; it names fewer areas than Curia Vista (≈ 2 vs 3.2) — low recall partly by the 3-label cap and the stratified sample's high label count. APS chapter accuracy is still pending (needs the partner's mapping / gold).

### D63 — S9: cross-language consistency, cost/time, 300k estimate, report tables (slice S9, 2026-10-18)
- Cross-language sample `data/samples/crosslang.csv` (seed 3): 100 federal affairs ≥ 2018 (50 PolitMonitor-tagged, 50 not) whose DE, FR **and** IT versions all exist, are complete and are detected in the right language (the 28 % French-in-IT problem, D39, is excluded by construction); one row per affair × language (300). Runs: ad-hoc digitalisation 20261018T162659841331Z (adhoc_v5; prompt_version 51fab895066d — differs from S6's fe05482ef754 only by the topic's keyword lists, which never enter the prompt), standard Curia Vista 20261018T162949819768Z (standard_v1, 062b5a8c6489).
- Ad-hoc (shown as match at t = 0.9): all three agree **94.0 % (87.5–97.2 %)**; pairwise agreement DE–FR 97 %, DE–IT 95 %, FR–IT 96 %; Cohen's κ 0.93 / 0.88 / 0.90. Match rate DE 30 %, FR 29 %, IT 31 %; recall vs PolitMonitor DE 58 %, FR 56 %, IT 60 % → on identical content there is no language bias. (The lower IT recall in S6, 45 %, came from different affairs, n ≈ 33.)
- Standard (Curia Vista): top label identical in all three only **47.5 % (37.9–57.2 %)**; mean Jaccard of label sets 0.39–0.43 per pair. Reading: similar areas, but the choice and order of 1–3 areas from 28 is unstable across languages — a limitation to state; candidates: rank-insensitive comparison, or fixing the number of labels.
- Cost/time (`parltopics eval cost`, from the reported test runs, concurrency 8): ad-hoc 3.2 s model time per affair (p50 3.1, p95 4.9), 1,481 input / 134 output tokens, 1.03 calls (evidence retry), observed 148 affairs/min; standard 5.4 s (p95 8.8), 1,411 / 265 tokens, 86 affairs/min. 300,000 affairs ad-hoc: 67 h at concurrency 4, 33 h at 8, 17 h at 16, 8 h at 32 (observed throughput agrees: 300k / 148 per min ≈ 34 h); ≈ 444 M input / 40 M output tokens. No price per token or GPU-hour is known → no CHF figure (assumption stated in metrics.json). Concurrency is now recorded in run manifests.
- `results/metrics.md` is regenerated from all sections of metrics.json on every eval (digitalisation, Curia Vista, cross-language, cost) — the report tables. Metrics tab shows all of them. `make status` (`parltopics status`) checks slices, success criteria and submission items from the real artefacts.

### D64 — Standard mode in the UI (S8/S7 follow-up, 2026-10-18)
- Decision: the Standard tab follows design screens 07/08: scheme switch APS / Curia Vista, one row per affair with label paths "chapter → topic (confidence)" (Curia Vista: area), evidence of the top label, review state per affair (confirmed / partly / AI suggestion). The detail panel lists every label with its own evidence, "Highlight evidence", Confirm and Reject (reviews stay per label = per prediction). Live classification of the pool with a scheme uses the same `/api/search` stream (`{scheme}`).
- Demo pool pre-computed: Curia Vista 20261018T163929079596Z (454 label records), APS two-stage 20261018T164249890943Z (775), exported to `results/demo/scheme_*.json`; cached mode imports them.
- Fixes found while verifying: (1) a cancelled live Digitalisation run (1 prediction, from the browser) had become "the latest run" and was exported as the demo cache → presets/schemes and `demo export` now only use runs covering the whole pool (`Store.latest_run(min_affairs)`, test added); caches re-exported. (2) Race: switching APS → Curia Vista quickly let the slower load overwrite the newer one → loads are sequenced, only the latest request may write the table. (3) The model can return the same code twice → duplicates dropped in `classify_standard` (test added) and in the UI for already-stored runs. (4) Test hygiene: copies of the WAL database for UI checks are made with SQLite `.backup` (a plain file copy missed the newest runs).
- Not done: APS "IT (unofficial)" gloss (see docs/02); APS accuracy still needs the partner's mapping / gold.
- Verified in headless Chrome, live and cached-from-empty-DB: APS 194 affairs / 310 paths, Curia Vista 194, detail with per-label review persisting after reload, back to ad-hoc 48 rows, 1280×720 without overflow, no JS errors; ad-hoc checklist 9/9.

### D65 — After-review results (2026-10-18, before the scale-up phase)
- Input: `data/gold/adjudication.xlsx` (the reviewer's returned sheet; stored outside `for_partner/` so `make eval` cannot overwrite it). Same sheet version as `results/adjudication_key.csv` (all 90 affair ids match). Answered 49 of 90 (shuffled order → a random mix of all groups); her "Sheet1" draft holds identical answers. No "bekannt" notes; 65590 excluded (D58) → 48 usable answers: TP 4, FN 18, FP 4, TN 22.
- Method (`parltopics eval adjudication`, `evaluate/adjudication.py`, tested): reviewer label replaces PolitMonitor's for reviewed affairs; per confusion cell the reviewer-yes rate is scaled to the cell's size in the test split (TP 55, FN 46, FP 5, TN 385) and to the population (π = 5.08 %); stratified bootstrap 2,000×. Both pre-registered readings (D56).
- Results: before review P_corr 69.5 % (53–91), R 54.5 % (45–64).
  - **Strict (her rule, primary): precision 82.6 % (47.9–100 %), recall 37.3 % (15.7–79.5 %).** Reviewer-yes rates: TP 75 %, FN 56 %, FP 100 %, TN 5 % (1/22).
  - Broad (digital technology present): precision 100 %, recall 17.6 % (10.1–40.7 %); TN 18 % (4/22).
- Reading: (1) every reviewed affair the model found and PolitMonitor had not tagged was confirmed digital (4/4: 287810, 201868, 153262, 161710); (2) 44 % (8/18) of the model's "misses" were not digital under her rule → PolitMonitor over-tags; (3) the reviewer also found digital affairs among untagged ones the model left out (strict 1/22, broad 4/22) — scaled to 26,069 untagged federal affairs this dominates recall and makes it very uncertain (the CI spans 16–80 %). Honest headline: precision goes **up** after review; recall cannot be pinned down with 22 untagged answers.
- 10 real model misses (PolitMonitor yes, reviewer yes, model no) listed in metrics.json for error analysis (e.g. 71058 Post digital inclusion, 69534 Swiss Chip Strategy, 153348 online trade).
- Wording: "blind review by a team member (MA student, political science)", never "expert" (D57).

### D66 — adhoc_v6: restate topic + question after the text; adoption rule (scale-up phase 0, 2026-10-18) — logged BEFORE running
- Change (D61): `adhoc_v6` = `adhoc_v5` with the same system and retry text; the user message adds, after the affair text: "Question: is the topic "{name}", as defined above, a MAIN subject of this affair? Judge only this topic. An affair can have a clear main subject that is not "{name}" - then answer "no_match"." Nothing else changes (model, temperature 0, 12,000-char limit, topic file).
- Dev check (no test data): (1) S6 enlarged dev split of `data/samples/digi_federal_2018_v2.csv`, same topic file, compared with the adhoc_v5 dev run 20261018T134630509400Z; (2) `check topic Beekeeping --max-matches 2` and `Tamil --max-matches 10` on the demo pool (as `make check-topics`); (3) probe affair 199828 at 12,000 chars for Beekeeping and Tamil.
- Adoption rule, fixed now: adopt adhoc_v6 only if **all** hold: (a) applying the D41 rule to the v6 dev run gives a corrected F1 **≥ 0.611** (v5 dev, D45); (b) both topic checks pass; (c) 199828 is not shown as a match (label ≠ match or confidence < 0.9) for either topic. Otherwise adhoc_v5 stays final and D61 stays a stated limitation.
- If adopted: threshold = the D41 rule on the v6 dev run; the S6 test split runs **once** with adhoc_v6 and that threshold, as a separate evaluation stored under its own key in `results/metrics.json`. The D46 numbers stay as reported (first pre-registered test) and are not overwritten; the review sheet and `results/adjudication_key.csv` (basis of D65) are not regenerated. All scale-up runs use the adopted prompt.
- **Result (added after the runs): not adopted — rule (a) fails; (b) and (c) pass.** adhoc_v5 stays the final ad-hoc prompt; no test run with adhoc_v6.
  - (a) Dev run 20261018T175026496585Z (adhoc_v6, prompt_version b2ace8a2b563; same 45 pos / 355 neg, same exclusions 4 + 45): corrected F1 0.538 (t = 0.5–0.8), **0.576 (0.9)** → t = 0.9; P_corr 66.0 % (48–89 %), R 51.1 % (23/45), FP 5/355 — vs v5 0.611, P_corr 67.9 %, R 55.6 % (25/45), FP 5/355.
  - The difference is small: labels agree on 436/449 dev affairs (97.1 %); v6 is slightly more conservative (7 match → no_match/abstain, 1 the other way). Only 6 affairs change "shown at 0.9"; in all 6 both prompts say "match" — 4 differ by confidence crossing 0.9 (e.g. 0.95 → 0.85), 2 by evidence verification (213617 failed under v6, 235121 under v5). Net −2 TP of 45: within noise, but the rule was "at least as good" and it is not.
  - (b) Demo pool, 204 affairs: Beekeeping v5 1 shown (199828) / **v6 0**; Tamil v5 1 (199828) / **v6 0** (runs 20261018T175256354915Z, …175352495784Z, …175448760693Z, …175545553891Z).
  - (c) 199828 at 12,000 chars: v5 "match 1.00" for both topics (reproduces D61); v6 "no_match 0.00" for both, rationales name ammonia as the main subject and say it is not the topic.
- Reading for the report: restating the question after the text removes the D61 drift on our checks, at a small, non-significant recall cost on dev. D61 stays a stated limitation of the evaluated prompt, now with a tested candidate fix. Not re-tested on test (rule). `check topic` gained `--prompt-version` (default adhoc_v5) for this comparison.
- Revisit if: a later, separately pre-registered evaluation (e.g. on Bern, Phase 4) shows drift matters on full collections; then adhoc_v6 is the candidate, evaluated on new dev data first.

### D67 — Collections: ingest / index / update / export (scale-up phase 1, 2026-10-18)
- Decision: a **collection** = all affairs of one body since a date, minus `COLLECTION_EXCLUDE_TYPES` (default: Consultation, as in the federal baseline slice; applies to every body for one rule — TG 1,545 → 1,447). `parltopics ingest` lists the body fresh from the API (listing never served from the cache), fetches + assembles only new or previously failed affairs, stores the text (`sources`) and one row per affair (`collection_items`, first ingest kept), and writes a data-quality report (`ingests`). `index` classifies the **stored** text (no re-fetch, no re-assembly), skips every affair that already has a complete result for the same prompt_version, and runs a second pass for transient failures. `update` = ingest with the first ingest's start date, then index every topic/scheme already indexed on that body (only new + failed affairs get model calls; a target whose topic file changed is skipped and reported — that is a re-index). `export` writes Excel/CSV of the result that counts per affair (newest complete run) with review status → `data/exports/` (gitignored).
- Federal collections take the **first complete official version in the order de, fr, it** (`TRANSLATED_LANG_ORDER`): one language per affair for the whole collection; the cross-language test (D63, 94 % agreement) says the choice barely matters, German suits the German-reading review (D53). Result: de 27,198, fr 245, it 21.
- Transient = `llm_error`, `fetch_error` (retried by the next pass/run). `parse_error` is final: at temperature 0 it repeats (affair 173251 failed identically twice).
- Bugs found on real data and fixed in `list_affairs_since`: (1) the API sorts affairs without begin_date first and the lister stopped at the first one → federal returned 0 affairs (Bern had none, so it had looked fine); now skipped. (2) offset paging sorted only by begin_date repeated some rows and skipped others (Bern 21, Thurgau 2 of the listing; federal 0) → sort `-begin_date,-id`; after the fix BE 5,249 / TG 1,545 / CHE 28,101 listed, all distinct. CHE after excluding consultations = **27,465, the same id set as the bulk table** (0 differences either way). Earlier samples used the old lister for cantonal negatives; they remain valid random samples of what was listed, but a few affairs could never be drawn.
- Ingest (real data): **BE 5,249 ok** (de 4,603 / fr 646; title-only 408; truncated 721; 0 lang mismatch; median 3.4k chars); **TG 1,447 ok** (de; title-only 102; truncated 565; median 9.3k chars); **CHE 27,464 ok + 1 lang_missing** (title-only 1,536; lang mismatch 11; truncated 21). Second ingest fetched only the 21 / 2 missing affairs (idempotent). Ingest speed is bound by our own text cleaning + language check on long PDFs (Bern ≈ 150 affairs/min, 20 min) — left as is: changing the language check would change how existing samples are assembled.
- Index (real data, TG digitalisation, adhoc_v5, prompt_version 51fab895066d): 1,447 affairs over 5 runs, deliberately interrupted: run 1 died on "database is locked" while the federal ingest was writing the same DB from another process (4 stored); run 2 killed with SIGKILL after 343; run 3 stalled at concurrency 32 — all 32 threads blocked on open gateway connections for > 9 min while a fresh call answered in 0.2 s (the 120 s client timeout is per read, not per call) — killed after 610; run 4 at concurrency 16 finished the remaining 490 at ~215/min; pass 2 retried 1. No affair classified twice except that retry. Final: ok 1,435, evidence_failed 11, parse_error 1; 30 shown at t = 0.9. Re-running index: 0 runs; update: 0 new, 0 model calls.
- Defaults from this: `index`/`update` concurrency **16** (32 stalled the gateway tonight; 16 measured 182/min with 0 errors before). Do not run an ingest and an index against the same DB at once.
- Tests (`test_collection.py`, fake source + fake model): ingest idempotent + consultations excluded; fetch errors retried by the next ingest; index resumable (no repeat work, transient failures retried, nothing to do → no run, no call); update classifies only new affairs; update skips a changed topic; export flags shown matches by threshold.
- Revisit if: the gateway keeps parking requests (then add a per-call wall-clock deadline); cantonal users need consultations; a body needs a different language rule.

### D68 — The app on whole collections: collection switch, tasks, estimate → job, export (scale-up phase 3, 2026-10-18)
- Decision: the existing Explore page gets a **Collection** switch (Demo pool · each ingested body with level and size) and a **task** switch: *Find all* · *What's new* · *Review queue*, plus **Export** (Excel: suggested / confirmed / all rows). Same visual language as the private reference; no new screens.
- Indexed collections load from the store (`/api/collections/{body}/results`); for ad-hoc only model matches and evidence failures are sent (the rest is counted per label) — 27k federal rows would be too heavy for the browser. Standard mode sends every label.
- A topic or scheme not yet indexed on a collection shows the **estimate first** (pending affairs, minutes at the last measured collection rate — or "assumed" when no run of that kind exists yet), then *Index now* starts one background job (one at a time, concurrency 16, D67) with progress, ETA and Cancel; cancelled jobs show "n of N classified · Continue". Custom UI topics are stored as `data/topics_custom/custom-<content hash>.yaml` (gitignored), so the same topic always resumes the same index.
- *What's new* = affairs first seen after your previous visit to that collection (browser-local); on a first visit, affairs dated in the last 30 days (stated on screen). *Review queue* = unreviewed shown suggestions, highest confidence first; C / R review and open the next one.
- Verified in Chrome on a `.backup` copy of the DB (server on :8091, real DB: 0 new reviews): collection list (Demo 204, BE 5,249, CHE 27,465, TG 1,447); TG digitalisation loads in < 1 s, 30 suggested / 11 evidence failed / 36 below 0.90 (= CLI export); Covid-19 on TG not indexed → estimate 1,447 ≈ 7 min → job ran (27 done after 25 s) → Cancel → "43 of 1,447 classified · Continue"; queue: 30 → C → next affair opened, queue 29, strip "1 confirmed"; export confirmed → 1 row, the confirmed affair; What's new on first visit → "dated in the last 30 days", none for TG; APS on TG → estimate (assumed 80/min); back to Demo pool → 48 rows as before. API timing: state 0.07 s, collections 0.10 s, TG results 0.35 s (104 kB).
- Not done yet: offline copies of collection results (needs Phase 2 to finish first); the 20-minute user test with the partner (needs the partner).
- Revisit if: federal results are too slow in the browser (then page or pre-filter by year).

### D69 — Identical texts of different affairs (scale-up phase 2, 2026-10-18)
- Found on the Bern run: 11 affairs never became "done". Cause: several affairs have the **same text** (e.g. one motion submitted by several members — "Internationale KI-Sicherheit …" 5×; repeated election items). `sources` is keyed by the text hash, so the shared row keeps the first affair's id and link; `index` built the classifier input from that row and stored the prediction under the other affair's id. Size: BE 11, CHE 506 affairs share a text with another affair.
- Fix: `Store.source_text(sha, affair_id)` uses the listed affair's id and its own link; result rows and the detail view take the link from the affair (`affairs.url_external_json`), not from the shared text row; `collection_results` keeps only affairs of that collection and one ad-hoc record per affair and run. The 11 × (1 + 9 retries) stray Bern records stay in the append-only store and are filtered out. Bern then finished 5,249 / 5,249 (run 20261018T212955923384Z); the federal run started after the fix.
- Affects the demo pool too (links of duplicates now point to the right affair). Not affected: S6/S7/S9 evaluations (sample runs fetch per affair and key by the sample's affair id).

### D70 — Phase 2 runs done; store made fast enough for full collections (scale-up phase 2, 2026-10-19)
- Runs (overnight driver: one step after the other, restart after 5 min without progress — never needed; 0 transient failures in the final runs):

| Collection | Target | Prompt | Affairs | Status | Shown / labelled | Run(s) |
|---|---|---|---|---|---|---|
| BE | digitalisation | adhoc_v5 | 5,249 | ok 5,204 · evidence_failed 20 · parse_error 25 | 170 shown at t = 0.9 (3.2 %) | 20261018T210127267583Z + 11 affairs in 20261018T212955923384Z (D69) |
| CHE | digitalisation | adhoc_v5 | 27,464 | ok 27,332 · evidence_failed 121 · parse_error 11 | 1,132 shown (4.1 %) | 20261018T213016562112Z |
| BE | Covid-19 | adhoc_v5 | 5,249 | ok 5,231 · ef 4 · pe 14 | 102 shown (1.9 %) | 20261018T230840161427Z |
| TG | Covid-19 | adhoc_v5 | 1,447 | ok 1,425 · ef 9 · pe 13 | 57 shown (3.9 %) | 20261018T233120704475Z |
| BE | APS (2 stages) | standard_v1 | 5,249 | 16,289 ok labels · 1,842 evidence_failed · 3 pe | 16,192 labels on 5,070 affairs | 20261018T234041024627Z |
| TG | APS (2 stages) | standard_v1 | 1,447 | 4,647 ok · 1,053 ef · 5 pe | 4,630 labels on 1,303 affairs | 20261019T004402627652Z |
| TG | digitalisation | adhoc_v5 | 1,447 | (D67) | 30 shown (2.1 %) | D67 |

- Throughput: ad-hoc 210–277 affairs/min at concurrency 16 (federal 27,464 in 98 min); APS ≈ 80 affairs/min (two calls). Evidence failures are much more frequent per APS label (≈ 10 % BE, 18 % TG) than for ad-hoc (≤ 0.6 %) — to report next to the APS numbers. No accuracy is claimed here; exact precision/recall vs PolitMonitor is Phase 4.
- Performance bugs found when reading the results back (all fixed, tests green): (1) every `Store()` open re-ran the D60 link repair over all ~34k texts, rewriting the 348 MB table and holding the write lock for 12 s+ (this also explains the D67 "database is locked") → now a one-time migration marked in `PRAGMA user_version`; open ≈ 0.1 s. (2) collection results joined `predictions` without a `(run_id, affair_id)` index → minutes per query on Bern → indexes `predictions_run_affair` and `reviews_prediction`; Bern 0.26 s, federal 1.0 s. (3) The `best`/`cand` CTEs are `MATERIALIZED`.
- Operational: `caffeinate` ended with the driver at 03:07; afterwards the Mac slept between commands, which looked like hanging queries. Long runs keep `caffeinate` alive for the whole session.

### D71 — Full-population evaluation vs PolitMonitor: method fixed before computing (scale-up phase 4, 2026-10-19) — logged BEFORE any number
- Populations = the ingested collections (since 2018-01-01, consultations excluded): CHE 27,465, BE 5,249, TG 1,447. Every affair counts; lang_missing / parse_error / evidence_failed = model "no".
- Model "yes" = shown in the app: status ok, label match, confidence ≥ 0.9 (D45, unchanged), prompt adhoc_v5, runs of D67/D70. Gold = PolitMonitor tag with the body's own scope (`ch`, `be`, `tg`), as in S6. No threshold or prompt choice is made on these numbers.
- Reported: exact counts TP / FP / FN / TN, precision, recall, F1 against PolitMonitor (no prevalence correction needed: whole population). Wilson 95 % intervals are added only for the per-language and subset breakdowns and are labelled indicative.
- Baselines on the same populations: CHE — Curia Vista area 34 and core-keyword search over all language versions (D46 functions, unchanged); BE / TG — core-keyword search on the text the model saw (stored 12,000-char text; full texts are not stored, stated as a limitation). No cantonal-keyword baseline (choosing keywords now would be post-hoc).
- CHE also reported **without** the 1,040 affairs of the S4/S6 samples (prompts were revised on dev, test was seen) → the untouched remainder.
- BE also by language of the affair (DE vs FR, as published by the parliament).
- Reading rule, fixed now: PolitMonitor is a lower bound for precision (D65: all 4 reviewed model-yes/PM-no affairs were confirmed digital), so model-yes/PM-no counts are reported as "not tagged by PolitMonitor", not as errors.
- **Result (added after computing; `parltopics eval collection`, `results/metrics.json` → `full_population`, metrics.md section "Whole collections"):**

| Parliament | Method | Affairs | Tagged | TP | FP | FN | Precision | Recall | F1 |
|---|---|---|---|---|---|---|---|---|---|
| CHE | Apertus (adhoc_v5, t = 0.9) | 27,465 | 1,396 | 712 | 420 | 684 | **62.9 %** | **51.0 %** | **56.3 %** |
| CHE | Apertus, without the 1,012 sample affairs | 26,453 | 1,240 | 631 | 411 | 609 | 60.6 % | 50.9 % | 55.3 % |
| CHE | Curia Vista area "Medien und Kommunikation" | 27,465 | 1,396 | 1,120 | 1,620 | 276 | 40.9 % | 80.2 % | 54.2 % |
| CHE | Keyword search, core words, full text | 27,465 | 1,396 | 788 | 1,121 | 608 | 41.3 % | 56.4 % | 47.7 % |
| BE | Apertus | 5,249 | 171 | 116 | 54 | 55 | **68.2 %** | **67.8 %** | **68.0 %** |
| BE | Keyword search, core words (model text) | 5,249 | 171 | 81 | 167 | 90 | 32.7 % | 47.4 % | 38.7 % |
| TG | Apertus | 1,447 | 33 | 15 | 15 | 18 | 50.0 % | 45.5 % | 47.6 % |
| TG | Keyword search, core words (model text) | 1,447 | 33 | 24 | 129 | 9 | 15.7 % | 72.7 % | 25.8 % |

- Reading: (1) The full federal population confirms the S6 test estimate: precision 62.9 % lies inside the pre-registered test CI (53–91 %, point 69.5 %), recall 51.0 % inside 45–64 % (point 54.5 %); the 26,453 affairs never used in any sample give 60.6 % / 50.9 % — no sign that dev work inflated the result. (2) Federal: precision +22 points over both baselines; recall below the Curia Vista area (51 vs 80 %), F1 slightly above it (56.3 vs 54.2 %). (3) Bern: precision and recall both above keyword search (68 / 68 vs 33 / 47); 54 of the 116 found tagged affairs contain no core keyword (federal: 215 of 712). (4) Thurgau: small (33 tagged) — precision 3× keyword search, recall lower. (5) Language: Bern DE P 70.9 % / R 68.2 % (154 tagged) vs FR P 50.0 % / R 64.7 % (17 tagged; R CI 41–83 %) — FR too small to call a difference; together with D63 (94 % agreement on identical federal texts) no evidence of a language bias. (6) All model-yes/PM-no counts (CHE 420, BE 54, TG 15) are "not tagged by PolitMonitor", a lower bound on precision (D65: 4/4 reviewed were digital).
- The full-text keyword baseline reproduces D46 exactly (41.3 % / 56.4 %) with the refined keyword lists.

### D72 — Offline copies of whole collections; status fix (scale-up phase 3 finish, 2026-10-19)
- Decision: `parltopics demo export-collections` writes one gzipped file per collection and preset ad-hoc topic to `results/collections/` (committed): every collection item and the prediction that counts per affair, but texts, evidence, rationale and affair metadata only for affairs the app can open (model matches + evidence failures); no raw model output. Sizes: CHE digitalisation 5.3 MB, BE 0.9 + 0.7 MB, TG 0.4 + 0.4 MB (all < 10 MB). The server imports them at start (idempotent; a failed import rolls back and removes its runs). APS is not shipped (labels on ~all affairs → nearly every text) — stated.
- Verified as a clean checkout: empty DB, no model endpoint (`LLM_BASE_URL` empty), server on a separate port: first start 3.4 s; collections BE 5,249 / CHE 27,465 / TG 1,447 with all topics done; results for all 5 targets **identical** to the real DB (affair, status, confidence, link: BE 303 + 212, TG 77 + 92, CHE 2,193 rows); detail texts open. Round-trip test added.
- `make status` read the blank review template instead of the returned sheet ("0/90"); now reads `metrics.json` → adjudication (49/90) and shows the full-population federal result.

### D73 — Fixes from the user test (scale-up phase 3, 2026-10-19)
- Found by the builder trying the Bern view as a DVS user: (1) the unofficial translation never showed the proof — it covered only the first 2,000 characters and cannot be highlighted (the quote is verified only against the original) → the quote is now translated separately and shown on top ("Proof sentence, translated"), and the translated passage is the 2,500 characters **around** the verified quote, labelled as a passage; (2) long texts were one block → section headers (TITLE / TEXT / DOCUMENT …) in bold in the original, official and translated versions; (3) "Correct label: this topic / not this topic" duplicated Confirm / Reject in ad-hoc mode → removed (Confirm / Reject / keyboard remain; stored reviews unchanged); (4) collection lists were in affair-id order → newest first (queue stays highest confidence first).
- Verified on a DB copy (:8091) with the live gateway: Bern list starts 2026-09-09; affair 36683 (FR) → "Proof sentence, translated: Digitale Radiologie" (original: "Numérisation de la radiologie"); no "Correct label" control; tests 100 passed.
- Follow-up: the builder's browser kept the old `app.js` after the server restart (no cache header) → UI files (`/`, `.js`, `.css`, `.html`) are now sent with `Cache-Control: no-cache`, so browsers re-check them by ETag on every load.
- Follow-up (builder's second look): the definition box had no clear open/close state and no obvious way to start a new topic → "+ Definition" / "− Definition" toggle, a **"+ New topic"** button (clears name, definition and lists, focuses the name, shows "Name your topic, then press Classify" with the collection-size note), and a one-line hint inside the box (preset: "edit and Classify to run your own version"; new: what to fill in, "English works for affairs in all languages"). Definitions stay in English: every reported number (D46, D63, D71) used English definitions on DE/FR/IT texts.
- Follow-up (builder's run of a new topic "Wolf" on Thurgau, 1,447 affairs ≈ 9 min, 7 suggested): (1) export "All" crashed with `IllegalCharacterError` — control characters from scanned PDFs are not allowed in .xlsx → `collection.export_frame` strips them (app and CLI) and always writes the 20 column headers (an empty "Confirmed" export had none); "Confirmed" with nothing confirmed now explains instead of downloading; (2) an indexed own topic's chip loaded results but kept the old name/definition in the form → the collections API returns each ad-hoc target's definition and lists, the chip fills the form; (3) a new chip made the query row wrap (Classify on its own line, buttons squeezed to two lines) → chips scroll inside their area, buttons keep their size, the topic field shrinks. Verified on a DB copy: TG Wolf export all 1,447 rows, confirmed 0 rows + headers, CHE all 27,464 rows (16 s); test for Excel-safe export added.

### D74 — Explore layout follows the updated design reference (scale-up phase 3, 2026-10-19)
- From the builder's design reference (two screenshots): query row = topic field · + Definition · presets · + New topic · scope badge · Classify; filter row = compact pills (Collection, Parliament and Level only for the mixed demo pool, Language, Date) with the task switch (Find all / What's new / Review queue) on the right; results strip = counts on one line with "Keyword absent" switch and "Export Excel" on the right; notes (keyword-absent explanation, definition used) as a caption under the strip; model badge "Apertus v1.5 70B · <ENDPOINT_LABEL or host>" (id and host in the tooltip; label is a setting, not hard-coded); "Sample data" badge on the demo pool ("Cached results" when offline).
- Whole collections draw 300 rows at a time with "Show 300 more" (keyboard ↓ extends the page): Bern APS 5,073 affairs / 18,131 label records rendered in 2.4 s instead of all at once; evidence column min-width 360 → 260 px and table text 15 → 14 px so the Review column fits at 1,384 px.
- Not done: the reference's "+ APS topic…" picker (choose an APS topic as an ad-hoc topic) — new feature, left for later.

### D75 — Topic dialog instead of the inline definition box; parliament names (scale-up phase 3, 2026-10-19)
- Decision: topics are created and inspected in a dialog, not edited inline. "Definition" on a preset opens it **read-only** (presets stay fixed so their results remain comparable) with "Use as template for a new topic" (pre-filled, name "… (own version)"); "+ New topic" opens an empty form (name, definition, counts / does not count); "Definition" on an own topic opens it editable. Classify (or Enter in the name) closes the dialog and runs the usual flow (estimate first on a collection). Typing another name in the main field still starts a new topic and never edits a preset.
- Why: the builder found the always-editable box cluttered and ambiguous (editing a preset silently made a new topic). A separate page was considered and rejected for time: it needs its own navigation and states; the dialog keeps the one-screen flow.
- Parliament filter showed raw OpenParlData keys (261, 2829 …) → names and levels from the API, stored once in `results/bodies.json` (`parltopics data body-names`, committed so names also show offline); the dropdown is grouped Federal / Cantonal / Municipal and sorted by name ("Zürich (261)"); the table's Parl. cell has the name as tooltip.
- Verified in Chrome on a DB copy: preset dialog read-only with template button; template keeps the definition; Escape closes; New topic empty with focus in the name; "E-voting" + Enter on TG → estimate "1,447 affairs ≈ 7 min"; parliament groups Federal: Schweiz (CHE) / Cantonal: Aargau (AG) … / Municipal: Arbon (4401) ….
