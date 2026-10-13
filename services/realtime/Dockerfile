FROM ghcr.io/astral-sh/uv:0.12.18-python3.12-trixie-slim
ENV PYTHONUNBUFFERED=1 UV_NO_CACHE=1
RUN apt-get update && apt-get install -y --no-install-recommends libglib2.0-0 libsndfile1 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY agent.py ./
RUN uv run agent.py download-files
CMD ["uv", "run", "agent.py", "start"]
