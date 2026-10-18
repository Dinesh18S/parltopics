.PHONY: run dev data test first-loop eval check-topics status

run:
	docker compose up --build

dev:
	uv run parltopics serve

data:
	uv run parltopics data download

test:
	uv run pytest -q

first-loop:
	uv run parltopics sample first-loop
	@run=$$(uv run parltopics classify --sample data/samples/first_loop.csv --topic topics/digitalisation.yaml \
		--notes first-loop | sed -n 's/^run_id=\([^ ]*\).*/\1/p') && uv run parltopics report first-loop $$run

eval:
	@test -n "$(RUN)" || (echo 'usage: make eval RUN="<dev_run_id> <test_run_id>"  (see docs/decisions.md D45-D46)'; exit 1)
	uv run parltopics eval digitalisation $(RUN) --sample data/samples/digi_federal_2018_v2.csv --cv-area 34

check-topics:
	uv run parltopics check topic Beekeeping --max-matches 2
	uv run parltopics check topic Tamil --max-matches 10

status:
	@uv run parltopics status
