FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir uv==0.12.18
ENV PYTHONUNBUFFERED=1 UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1 UV_NO_CACHE=1 \
    HF_HOME=/opt/remember/model-cache TOKENIZERS_PARALLELISM=false \
    OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PORT=8000
WORKDIR /opt/remember
# Only these explicit paths reach the image; no app credentials or .env files.
COPY services/backend/pyproject.toml services/backend/uv.lock services/backend/
RUN cd services/backend && uv sync --frozen --no-dev --extra deployment --extra retrieval
COPY services/ai-core/pyproject.toml services/ai-core/uv.lock services/ai-core/
COPY services/ai-core/app services/ai-core/app
COPY services/ai-core/fixtures services/ai-core/fixtures
COPY packages/contracts/schemas packages/contracts/schemas
RUN cd services/ai-core && uv sync --frozen --no-dev
COPY models models
ENV REMEMBER_VOICEPRINT_MODEL_PATH=/opt/remember/models/wespeaker_zh_cnceleb_resnet34.onnx
COPY services/backend/app services/backend/app
COPY services/backend/migrations services/backend/migrations
COPY services/backend/alembic.ini services/backend/alembic.ini
COPY infra/cloudbase/runtime infra/cloudbase/runtime
RUN cd services/backend && .venv/bin/python -c "from app.retrieval import _load_model, DEFAULT_EMBEDDING; _load_model(DEFAULT_EMBEDDING)"
ENV HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
RUN useradd --uid 10001 --create-home remember && mkdir -p /tmp/remember-asr && chown remember:remember /tmp/remember-asr
USER remember
EXPOSE 8000
ENTRYPOINT ["python", "/opt/remember/infra/cloudbase/runtime/launch.py"]
CMD ["serve"]
