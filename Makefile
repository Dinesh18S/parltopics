.PHONY: run dev data test

run:
	docker compose up --build

dev:
	uv run parltopics serve

data:
	uv run parltopics data download

test:
	uv run pytest -q
