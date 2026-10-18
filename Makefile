.PHONY: run dev data

run:
	docker compose up --build

dev:
	uv run parltopics serve

data:
	uv run parltopics data download
