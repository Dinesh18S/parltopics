# AGENTS.md — instructions for AI coding agents

You are building ParlTopics: an open, topic-agnostic classifier for Swiss parliamentary affairs on Apertus. The human directs; you implement. Read these first, in order (submission rules: `docs/07-submission-checklist.md`):

1. `docs/00-prd.md` — the source of truth for scope
2. `docs/01-product-requirements.md`
3. `docs/04-backend-pipeline.md`
4. `docs/05-prompt-spec.md`
5. `docs/03-data-and-api.md`
6. `docs/06-eval-harness-checklist.md`
7. `docs/02-design-frontend.md` (only when building the UI)

## Hard rules

- **Never write a person's name** (the team's or anyone else's) into any file — docs, code, commit messages, data, reviews — without explicit approval in that moment. Use roles ("builder", "partner", "reviewer") instead.
- **Never commit or push yourself, and never to `main`.** When a slice is ready, show the verification output and a proposed commit message, then ask the human to commit. Only commit if the human explicitly says so in that moment, and then on a feature branch, never `main`.

- Never hard-code a topic, scheme or language in Python. Topics are YAML in `topics/`; schemes are loaded from data files.
- Only Apertus does classification, through the OpenAI-compatible client configured by `LLM_NAME`, `LLM_BASE_URL`, `LLM_API_KEY`. No other model in the pipeline.
- No label without code-verified evidence. Verification is pure Python, never a model call.
- Never commit `.env`, `data/raw/`, `data/cache/`, model weights, or files > 10 MB.
- Every failure gets an explicit status and is counted. No silent `except: pass`.
- Do not tune prompts or thresholds on test samples.
- Keep the project runnable end-to-end on a clean checkout after every slice. All code lives in `src/`. Never rename or move the template files (README.md, technical_report.md, LICENSE, src/).
- When an assumption in `docs/03-data-and-api.md` marked VERIFY is checked, update that file in the same commit.

## Build order (vertical slices)

A slice is **done** only when its verification passes on real data and the output is pasted into the PR/commit message. "It compiles" is not done.

| # | Slice | Verify with |
|---|---|---|
| S0 | Scaffold: pyproject (uv), package layout, config, Dockerfile, compose, Makefile, `/health` | `make run` → `curl localhost:8080/health` returns ok |
| S1 | OpenParlData client + cache + text assembly; resolve all VERIFY items for affairs | `parltopics fetch <id>` prints assembled text for 3 real ids (DE, FR, IT) |
| S2 | LLM client + ad-hoc prompt + JSON validation | one real call returns valid JSON; latency + tokens logged |
| S3 | `verify.py` + tests | `make test` green (exact, quotes, hyphenation, fuzzy, too-short, title-only) |
| S4 | **First loop**: 20 positives + 20 negatives → table + summary | `make first-loop` prints table, evidence-verified rate, accuracy |
| S5 | SQLite store + run manifests + reviews | re-running S4 creates a new run; old one still queryable |
| S6 | Samples + metrics for digitalisation like-for-like (baseline recompute, prevalence correction, CIs) | `make eval` writes `results/metrics.json`; baseline ≈ 41/81 |
| S7 | Standard mode: Curia Vista (1 stage), APS (2 stages) | eval on Curia Vista dev sample prints at-least-one + micro-F1 |
| S8 | API routes + demo UI + cached mode | demo flow in `docs/02` acceptance checklist passes |
| S9 | Cross-language + cost/time + report tables | metrics.json has all §8 rows of the eval checklist |

## Style

- Python 3.11, type hints, pydantic models at boundaries, small pure functions.
- Tests for `verify`, `metrics`, prompt rendering. No tests that call the live model.
- Short, plain README updates whenever a command changes.

## How we work (pstack-style)

- **Plan and design are done.** The docs are the plan. Don't redesign; if a doc is wrong, say so and propose a fix.
- **Smallest change the evidence justifies.** Each slice adds only what its verification needs.
- **Test-first where correctness is the product:** write failing tests for verify.py and metrics.py before implementing them.
- **"It compiles" is not evidence.** A slice is done only when its verification runs on real data and you show the output.
- **Blast radius before changing prompts, thresholds or sampling:** list which reported numbers become stale, re-run them, and note it in the prompt changelog (docs/05 §6).
- **Sanity-check every number** before it goes in results/metrics.json: sample size, CI, does the baseline reproduce, would a domain expert believe it?
- **Clean as you go:** no dead code, no commented-out blocks, no comments that restate the code, no placeholder TODOs left in shipped paths.
- **Before submission:** a review pass that attacks the code and the evaluation: unverified claims, leakage between dev and test, silent failure paths.

## Decision log and learning notes (update with every slice)

### docs/decisions.md — every non-obvious choice
Append one entry per decision, newest at the bottom:

    ### D<n> — <short title> (slice S<x>, <date>)
    - Decision: what we chose
    - Why: the reason, with evidence (test output, data check, doc reference)
    - Alternatives rejected: what else we considered and why not
    - Affects: which files, numbers or docs this touches
    - Revisit if: what would make us change it

Log: library and model choices, prompt changes, thresholds, sampling, any VERIFY item resolved, any deviation from the docs, and anything that failed and what we did instead.

### private/learning.md — plain-English notes + jury prep (PRIVATE, gitignored)
This file is private to the builder. It lives in `private/` (gitignored); never commit it, never move it into `docs/`, never mention it in README or the report. Write in simple English (short sentences, explain every technical word). Keep its three parts up to date after each slice:
- Part 1 — the project in 60 seconds + words to know (add new terms as they appear)
- Part 2 — per slice: what it does (one line), how it works in plain words, what verification showed (key numbers), what could go wrong and how we'd notice
- Part 3 — jury practice: likely questions grouped by the 6 jury dimensions, each with a short answer the builder can say out loud. Add or update questions the new slice makes answerable; mark answers that still need numbers as *(after Sx)*; never state a number that isn't measured yet.

Rules: short and factual, no filler. If you can't explain a choice simply, flag it as a question for me instead of hiding it.