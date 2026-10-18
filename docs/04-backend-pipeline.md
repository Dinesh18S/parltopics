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
  prompts/         # versioned templates: adhoc_v1.txt, standard_v1.txt …
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
tests/
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
LLM_JSON_MODE=json_schema      # json_schema | json_object | none (fallback: parse + repair)
MAX_INPUT_CHARS=12000
TITLE_ONLY_CONF_CAP=0.6
OPD_API_BASE=https://api.openparldata.ch
DATA_DIR=./data
```

Switching 70B ↔ 8B, or gateway ↔ local server, changes only the three `LLM_*` connection vars.

## 4. The five steps

### 4.1 Fetch
- `get_affair(id) -> Affair` — bulk file first (CHE texts), API otherwise; cached.
- `assemble(affair) -> SourceText(text, sha256, sections, title_only: bool, lang)`.

### 4.2 Classify
- `classify_adhoc(source, topic) -> Prediction`
- `classify_standard(source, scheme) -> list[Prediction]`
- Standard mode for APS is **two-stage**: stage 1 picks up to 3 of 22 chapters (or `NONE_OTHER`); stage 2 picks topics only within the chosen chapters. One stage with 165 options is too much for an 8B model and too long a prompt. Curia Vista (28 areas) is one stage.
- Call settings: temperature 0, JSON schema enforcement when the server supports it (vLLM `response_format`/guided JSON; Ollama `format`). Otherwise: parse the first JSON object, validate with pydantic, one repair retry ("Return only valid JSON for this schema…"), then `status=parse_error`.
- Record per call: latency, input/output tokens (from usage, or estimated), model, prompt version hash.

### 4.3 Verify (no model)
`verify_evidence(evidence, source.text) -> VerifyResult(ok, method, span)`
1. Normalise both: Unicode NFKC, lowercase, unify quotes/apostrophes/dashes (’ ' ‘ « » " → one form; – — → -), collapse whitespace, strip soft hyphens and line-break hyphenation.
2. Exact substring → `ok, method=exact`.
3. Else: evidence ≥ 25 chars and best fuzzy window ratio ≥ 0.92 (rapidfuzz `partial_ratio`) → `ok, method=fuzzy` (shown in UI, counted separately in metrics).
4. Else → `ok=False`; prediction stored with `status=evidence_failed`, never shown as a match.
5. Evidence shorter than 15 chars that isn't the title → fail (prevents "Digital" as evidence).
6. `title_only` → evidence must be (part of) the title; confidence = min(conf, `TITLE_ONLY_CONF_CAP`).
7. `abstain`/`no_match`/`NONE_OTHER` may have empty evidence.

Unit tests cover: exact, quote variants, hyphenation, fuzzy pass, fuzzy fail, too-short, title-only cap.

### 4.4 Store (SQLite)

```
affairs(id PK, body_key, number, type, begin_date, lang, title, url, level)
sources(affair_id, text_sha256, title_only, n_chars, assembled_at)
topics(id PK, kind[adhoc|aps|curia_vista], name, definition, scheme_code, lang)
runs(id PK, started_at, model, base_url_host, prompt_version, prompt_sha, git_commit, sample_file, notes)
predictions(id PK, run_id, affair_id, topic_id, label, confidence, evidence, verify_ok, verify_method,
            status[ok|evidence_failed|parse_error|llm_error], latency_ms, tok_in, tok_out, raw_json, created_at)
reviews(id PK, prediction_id, decision[confirm|reject|correct], corrected_label, reviewer, note, created_at)
```

Rules: predictions are append-only; reviews never mutate predictions; every prediction points at a run.

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
- Log one JSONL line per LLM call to `results/runs/<run_id>/calls.jsonl` (ids, latency, tokens, status — not full source text).
- Determinism: temperature 0, sorted inputs, seeds fixed in sampling.
- Keep functions pure where possible (`verify`, `metrics`) so they're testable without network or model.
