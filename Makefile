.PHONY: run dev

run:
	docker compose up --build

dev:
	uv run parltopics serve
