# 07 — Submission Checklist (Hack Apertus Liebefeld)

## Repo
- [ ] Created from the Liebefeld template; template files not renamed or moved (README.md, technical_report.md, LICENSE, src/)
- [ ] All code in `src/`
- [ ] Repo set to PUBLIC
- [ ] No `.env`, raw data, caches or weights committed
- [ ] A judge can run it end-to-end from the instructions in technical_report.md (fresh clone, only LLM_NAME / LLM_BASE_URL / LLM_API_KEY set)
- [ ] Works in cached mode if the judge's model endpoint is down

## README.md (template's, filled in)
- [ ] Title: Hack Apertus Liebefeld — OpenParlData: Topic classification for Swiss parliaments with Apertus — <Team name>
- [ ] One-paragraph challenge description
- [ ] 🎯 Challenge title + Notion challenge page URL
- [ ] Project section pasted from docs/README-project-section.md (setup, how it works, data attribution "Source: OpenParlData.ch", CC BY 4.0)

## technical_report.md
- [ ] Team name, members, track/challenge, Demo video URL at the top
- [ ] Architecture, Apertus use (model, where it runs, prompts), data + licences, evaluation tables from results/metrics.json, limitations, reproducibility (run instructions, env vars, commit hash), next steps
- [ ] Any non-Apertus model used in development named and its role described
- [ ] Exported to PDF: `<TeamName>_Report.pdf` in repo root, max 6 pages without references

## Demo video
- [ ] Max 2 minutes: digitalisation search → keyword-absent matches with evidence → second topic live → numbers
- [ ] Uploaded (unlisted YouTube/Vimeo/Drive with public link); link in technical_report.md Demo field

## Submit (website form)
- [ ] Repo URL · PDF · video URL
- [ ] Final commit pushed before deadline; commit hash noted in the report

## Main jury dimensions (0–5 each) — where we show it
| Dimension | Evidence in our submission |
|---|---|
| Purposeful use of AI | Apertus judges language; code fetches, verifies evidence, scores |
| Technical rigour | Like-for-like baseline, prevalence-corrected precision, CIs, adjudication, cross-language check |
| Value, cost & scalability | Supports DVS's manual monitoring; cost/time per affair; 300k estimate |
| Sovereign deployability | One OpenAI-compatible endpoint; local 8B or CSCS 70B; no closed model |
| Implementation feasibility | Thin pipeline, standard tools, runs end-to-end today |
| Pitch & presentation | Live demo + numbers; partner tells the why |
