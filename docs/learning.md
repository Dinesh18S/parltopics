# Learning notes (one section per slice)

## S0 — Scaffold

**What it does.** Sets up an empty but runnable app: one command builds a container and starts a small web server with a `/health` page.

**How it works.** `make run` asks Docker to build a box containing Python and our code, then starts it on port 8080. The secret settings (which model, which server, the key) are read from `.env`, which never leaves your laptop. The `/health` page asks the model server "which models do you serve?" and checks ours is on the list. If yes it says `live`, if not it says `cached` (later: show pre-computed results instead of calling the model).

**What verification showed.** `/health` returned `status: ok`, `mode: live`, and the gateway listed `apertus-v1-5-70b`. With no server configured it correctly said `cached`.

**What could go wrong.** A wrong model name: the server is reachable but every call fails. We'd notice because `/health` would say `cached` instead of `live`. This actually happened (old name in `.env`) and is now fixed.

## S1 — Fetching affairs

**What it does.** Given an affair number from OpenParlData, it collects everything written about it and turns it into one clean block of text, exactly what the model will read.

**How it works.** For federal affairs it takes the title, the submitted text, the authors' reasoning and the Federal Council's answer. For cantonal and city affairs those don't exist, so it takes the text extracted from the PDFs attached to the affair. It removes web formatting, drops duplicate PDFs, keeps one language, and cuts at 12,000 characters. Every download is saved on disk, so we never ask the server twice.

**What verification showed.** DE (federal), FR (Geneva) and IT (Ticino) affairs assemble correctly. All 142 checked ids match the official files. Only 3 of 100 PolitMonitor affairs have just a title.

**What could go wrong.** 27 of 100 texts get cut at 12,000 characters. If the important sentence is past the cut, the model can't see it; we'd notice as misses on long affairs in S4.
