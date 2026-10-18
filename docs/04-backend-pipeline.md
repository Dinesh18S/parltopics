# 04 — Backend & Pipeline Guidelines

## 1. Stack

| Concern | Choice | Why |
|---|---|---|
| Language | Python 3.11 | Data + LLM ecosystem |
| Deps | `uv` + `pyproject.toml` (pinned lock) | Fast, reproducible |
| HTTP | `httpx` | Async, timeouts |
| LLM | `openai` SDK pointed at `LLM_BASE_URL` | Works with vLLM, Ollama, llama.cpp server, CSCS |
| Validation | `pydantic` v2 | Schema for LLM JSON and API models |
| Data | `pandas` (+ `openpyxl` for xlsx) | Quick joins and metrics |
| Store | SQLite (`data/parltopics.db`) | Zero setup, ships in Docker |
| API + UI | FastAPI + one static page | One process |
| CLI | `typer` | `parltopics fetch|classify|eval|serve` |
| Tests | `pytest` | Verify and metrics are tested |

## 2. Layout

```
src/parltopics/
  config.py        # env + defaults (pydantic-settings)
  llm.py           # OpenAI-compatible client, JSON mode, retry, timing, token counts
  sources/
    api.py         # OpenParlData client with disk cache
    bulk.py        # challenge files + bulk exports readers
    assemble.py    # build the exact text the model sees
  topics.py        # Topic / Scheme models; loaders for ad-hoc, APS xlsx, Curia Vista
  prompts/         # versioned templates: adhoc_v1.system.txt + adhoc_v1.user.txt, standard_v1.* …
  classify.py      # one affair × one topic/scheme → Prediction
  verify.py        # evidence check (pure functions, no model)
  store.py         # SQLite schema + read/write
  evaluate/
    samples.py     # build and freeze sample files
    metrics.py     # P/R/F1, prevalence correction, CIs, multi-label, agreement
    report.py      # writes results/metrics.json + markdown tables
  api.py           # FastAPI routes
  cli.py
src/web/index.html, app.js, style.css
src/tests/          # all code lives in src/ (template rule)
```

## 3. Configuration

All via env (`.env` locally, never committed):

```
LLM_NAME=apertus-v1-5-70b                      # comparison: apertus-v1-5-8b (never the -thinking variants)
LLM_BASE_URL=https://gateway.keera.ch/api/v1    # Keera gateway (CSCS), OpenAI-compatible
LLM_API_KEY=...                                 # local vLLM/Ollama: LLM_NAME=swiss-ai/Apertus-v1.5-8B, LLM_BASE_URL=http://localhost:8000/v1
LLM_TEMPERATURE=0
LLM_MAX_TOKENS=400
LLM_CONCURRENCY=4
LLM_JSON_MODE=json_schema      # json_schema | json_object | none (fallback: parse + repair). Keera gateway: json_schema enforced (verified S2)
MAX_INPUT_CHARS=12000
TITLE_ONLY_CONF_CAP=0.6
OPD_API_BASE=https://api.openparldata.ch
DATA_DIR=./data
```

Switching 70B ↔ 8B, or gateway ↔ local server, changes only the three `LLM_*` connection vars.

## 4. The five steps

### 4.1 Fetch
- `get_affair(id) -> Affair` — single affairs and small runs: API (cached). Runs above ~500 affairs: load the bulk file once into a local SQLite table keyed by affair id, then read from there. Never scan the file per affair.
- `assemble(affair, lang?) -> SourceText(text, sha256, sections, title_only, lang, lang_source, detected_lang, lang_mismatch, truncated, cut_section, chars_lost)`. Language rule and `lang_missing`: see docs/03 §6.

### 4.2 Classify
- `classify_adhoc(source, topic) -> Prediction`
- `classify_standard(source, scheme) -> list[Prediction]`
- Standard mode for APS is **two-stage**: stage 1 picks up to 3 of 22 chapters (or `NONE_OTHER`); stage 2 picks topics only within the chosen chapters. One stage with 165 options is too much for an 8B model and too long a prompt. Curia Vista (28 areas) is one stage.
- Call settings: temperature 0, JSON schema enforcement when the server supports it (vLLM `response_format`/guided JSON; Ollama `format`). Otherwise: parse the first JSON object, validate with pydantic, one repair retry ("Return only valid JSON for this schema…"), then `status=parse_error`.
- Record per call: latency, input/output tokens (from usage, or estimated), model, `source_sha256`, `run_id`. Prompt version lives on the run (docs/05).

### 4.3 Verify (no model)
`verify_evidence(evidence, source.text, title) -> VerifyResult(ok, method, score, span)` (span = offsets in the normalised text); `check_prediction(...)` turns it into `status` + capped confidence
1. Normalise both: Unicode NFKC, lowercase, unify quotes/apostrophes/dashes (’ ' ‘ « » " → one form; – — → -), collapse whitespace, strip soft hyphens and line-break hyphenation.
2. Exact substring → `ok, method=exact`.
3. Else: evidence ≥ 25 chars and best fuzzy window ratio ≥ 0.92 (rapidfuzz `partial_ratio`) → `ok, method=fuzzy` (shown in UI, counted separately in metrics).
4. Else → `ok=False`; prediction stored with `status=evidence_failed`, never shown as a match.
5. Evidence shorter than 15 chars that isn't the title → fail (prevents "Digital" as evidence).
6. `title_only` → evidence must be (part of) the title; confidence = min(conf, `TITLE_ONLY_CONF_CAP`).
7. `abstain`/`no_match`/`NONE_OTHER` may have empty evidence.

Unit tests cover: exact, quote variants, hyphenation, fuzzy pass, fuzzy fail, too-short, title-only cap.

### 4.4 Store (SQLite)

`data/parltopics.db` (gitignored, path `DB_PATH`). Schema in `src/parltopics/store.py`:

```
affairs(id PK, body_key, body_type, number, type, begin_date, title_json, url_external_json, url_api)
sources(text_sha256 PK, affair_id, lang, lang_source, detected_lang, lang_mismatch, title, title_only, truncated,
        cut_section, chars_lost, n_chars_full, url, text, assembled_at)        # exact text the model saw
topics(id PK = topic part hash, kind, name, definition, topic_json)
runs(id PK, started_at, finished_at, model, base_url_host, prompt_template, prompt_version, template_sha, topic_sha,
     fewshot_sha, params_sha, params_json, topic_name, git_commit, sample_file, notes, n_rows, manifest_json)
predictions(id PK, run_id FK, affair_id, topic_id FK, source_sha256 FK (NULL for lang_missing/fetch_error), lang,
            gold (copied from the sample file), body_key, title, label, confidence, evidence, rationale, verify_ok,
            verify_method, verify_score, inconsistent, keyword_absent, tech_vocab_absent,
            status[ok|evidence_failed|parse_error|llm_error|invalid_label|lang_missing|fetch_error],
            model, latency_ms, tok_in, tok_out, tokens_estimated, repaired, error, raw_json, created_at)
reviews(id PK, prediction_id FK, decision[confirm|reject|correct], corrected_label (required for correct),
        reviewer, note, created_at)
```

Rules (enforced in SQLite, tested): predictions and reviews are append-only (UPDATE/DELETE triggers abort); reviews never mutate predictions (the latest review per prediction counts); every prediction points at a run (FK). Each run also writes `results/runs/<run_id>/manifest.json` + `calls.jsonl`.

### 4.5 Serve

| Method | Path | Does |
|---|---|---|
| GET | `/health` | ok + model reachable? |
| POST | `/classify` | `{affair_id, mode, topic?{name,definition}, scheme?}` → predictions |
| POST | `/search` | `{topic, filters, pool}` → streams predictions for the demo pool (SSE) |
| GET | `/predictions?topic=…&run=…` | stored results |
| POST | `/reviews` | `{prediction_id, decision, corrected_label?, note?}` |
| GET | `/export.csv`, `/export.json` | topic, affair, confidence, evidence, link, review status |
| GET | `/metrics` | `results/metrics.json` |

## 5. CLI

```
parltopics data download
parltopics sample first-loop            # writes data/samples/first_loop.csv
parltopics classify --sample data/samples/first_loop.csv --topic topics/digitalisation.yaml
parltopics eval --run <id>
parltopics serve
```

Topics live as small YAML files (`topics/digitalisation.yaml`, `topics/covid19.yaml`): name, definition (from partner's definition doc), languages for keyword-absent check (`keywords: {de: [Digitalisierung, digital], fr: [numérique, numérisation], it: [digitalizzazione, digitale]}`). **No topic string appears in Python code.**

## 6. Docker / make

- `Dockerfile`: python:3.11-slim, uv sync, copy src, `CMD parltopics serve`.
- `docker-compose.yml`: `app` service; model is **external** via `LLM_BASE_URL` (judges bring CSCS key or local server). Optional profile `local-llm` documents a vLLM/Ollama service for those with a GPU.
- `make run` = `docker compose up --build`; if `LLM_BASE_URL` is unset or unreachable, the app starts in **cached mode** with committed demo results.
- `make data`, `make first-loop`, `make eval`, `make test`.

## 7. Engineering rules (for the AI agent too)

- Build in vertical slices; a slice is done only when its verification command passes on real data (see `AGENTS.md`).
- No topic or scheme hard-coded. No silent fallbacks: every failure gets a status and a count.
- Never commit `.env`, raw data, model weights, or caches.
- Each run writes `results/runs/<run_id>/manifest.json` (prompt_version + part hashes + params, git commit, endpoint host) and one JSONL line per LLM call to `calls.jsonl` (ids, latency, tokens, status — not full source text).
- Determinism: temperature 0, sorted inputs, seeds fixed in sampling.
- Keep functions pure where possible (`verify`, `metrics`) so they're testable without network or model.
