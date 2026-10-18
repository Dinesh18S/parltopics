# ParlTopics — open topic classifier for Swiss parliamentary affairs

Hack Apertus 2026 (on-site, Liebefeld/Bern) · Challenge: **OpenParlData — topic classification**
Team: Dinesh (build) · Arivinchsa (research & pitch)

ParlTopics suggests topics for any Swiss parliamentary affair, in German, French and Italian, and shows why: a confidence, the exact sentence from the affair, and a source link. A human confirms every suggestion.

- **Standard mode:** APS scheme (chapter → topic) or Curia Vista areas.
- **Ad-hoc mode:** any topic name + one-line definition ("digitalisation", "Covid-19"), no retraining.
- **Sovereign:** runs on open [Apertus](https://huggingface.co/swiss-ai), locally or on Swiss infrastructure, via one OpenAI-compatible endpoint.

We prove it on digitalisation: reproducing DVS's manual PolitMonitor tagging and measuring against it. Results: see [`technical_report.md`](technical_report.md).

> Status: work in progress during the hackathon.

## Run it

Requirements: Docker; an OpenAI-compatible endpoint serving Apertus (local vLLM/Ollama or the CSCS endpoint). Without an endpoint the app starts in cached mode with pre-computed demo results.

```bash
cp .env.example .env        # set LLM_NAME, LLM_BASE_URL, LLM_API_KEY
make run                    # builds and starts the app on http://localhost:8080
```

Other targets: `make data` (download challenge files), `make first-loop`, `make eval`, `make test`.

### Serving Apertus locally (example)

```bash
vllm serve swiss-ai/Apertus-v1.5-8B --port 8000
# then LLM_BASE_URL=http://host.docker.internal:8000/v1
```

## How it works

Fetch affair (OpenParlData API / bulk files) → classify with Apertus (strict JSON: label, confidence, evidence) → verify the evidence appears in the source (plain code) → store → demo UI with human review.

Docs for builders: [`docs/`](docs/) — PRD, requirements, design, data & API notes, pipeline, prompt spec, eval checklist. AI coding agents start at [`AGENTS.md`](AGENTS.md).

## Data

`data/` (≤100 MB) holds only frozen sample IDs and hand labels. Raw files are downloaded by `make data`.

Source: OpenParlData.ch — licensed CC BY 4.0. Challenge files: files.openparldata.ch/hackapertus. APS topic scheme: Année Politique Suisse.

## Submission

Submit via the Hack Apertus website (not Devpost). Deliverables and judging criteria: see the challenge description and the [Getting Started guide](https://hackapertus.notion.site/getting-started-guide-onlinehack). Questions: Discord or hello@hackapertus.ch.

## License

Code: Apache-2.0 (see `LICENSE` at repo root). See Hack Apertus Terms & Conditions §6: https://hackapertus.ch/terms-and-conditions
