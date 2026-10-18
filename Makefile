.PHONY: run dev data test first-loop eval

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
	@test -n "$(RUN)" || (echo "usage: make eval RUN=<run_id>  (run: parltopics classify --sample data/samples/digi_federal_2018.csv --topic topics/digitalisation.yaml)"; exit 1)
	uv run parltopics eval digitalisation $(RUN) --cv-area 34
