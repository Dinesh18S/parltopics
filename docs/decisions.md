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

### D16 — Prompt files and prompt SHA (slice S2, 2026-10-18)
- Decision: each prompt version is two files, `prompts/<version>.system.txt` and `<version>.user.txt` (docs/05 text verbatim). `prompt_sha` = sha256 of the two raw templates; every prediction also stores `source_sha256` of the exact assembled text.
- Why: docs/05 says "SHA of the rendered template"; a fully rendered prompt differs per affair, so it can't identify a prompt version. Template SHA + source SHA together pin down exactly what the model saw. Topic text is in the YAML (versioned in git).
- Alternatives rejected: one file with a separator — easier to break.
- Affects: `prompts/`, `classify.py`, `runlog.py`. Proposed docs/05 §0 wording: "the SHA of the template files is stored on every run".
- Revisit if: we need the topic definition hashed into the run id (S5 manifests can add the topic YAML SHA).

### D17 — Observed in S2, not changed yet: confidence semantics and rationale length (slice S2, 2026-10-18)
- Observation: on `no_match` the 70B model returns `confidence: 0.0` (e.g. 70435, also Covid-19 topic on 235308). It treats confidence as "probability of the topic", not "confidence the label is correct" (docs/05 §2). Rationales run ~35–40 words vs the 25-word rule.
- Decision: no prompt change before S4; one example is not evidence. If S4 confirms it, either (a) redefine confidence in docs/05 as "probability the topic is a main subject" (it works better as a ranking score anyway) or (b) bump to `adhoc_v2`. Rationale length is cosmetic; add `maxLength` only if it costs tokens.
- Affects: threshold tuning and calibration (S6).
