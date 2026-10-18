# Learning notes (one section per slice)

## S0 — Scaffold

**What it does.** Sets up an empty but runnable app: one command builds a container and starts a small web server with a `/health` page.

**How it works.** `make run` asks Docker to build a box containing Python and our code, then starts it on port 8080. The secret settings (which model, which server, the key) are read from `.env`, which never leaves your laptop. The `/health` page asks the model server "which models do you serve?" and checks ours is on the list. If yes it says `live`, if not it says `cached` (later: show pre-computed results instead of calling the model).

**What verification showed.** `/health` returned `status: ok`, `mode: live`, and the gateway listed `apertus-v1-5-70b`. With no server configured it correctly said `cached`.

**What could go wrong.** A wrong model name: the server is reachable but every call fails. We'd notice because `/health` would say `cached` instead of `live`. This actually happened (old name in `.env`) and is now fixed.
