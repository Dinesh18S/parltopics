FROM python:3.11-slim
COPY --from=ghcr.io/astral-sh/uv:0.13.0 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
COPY topics ./topics
RUN uv sync --frozen --no-dev
ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8080
CMD ["parltopics", "serve"]
