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
