FROM python:3.12-slim-bookworm AS builder

ENV PIP_NO_CACHE_DIR=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

RUN python -m venv "$VIRTUAL_ENV"

WORKDIR /build
COPY backend/requirements.txt ./requirements.txt
RUN pip install --upgrade pip "setuptools<81" wheel \
    && pip install -r requirements.txt


FROM python:3.12-slim-bookworm

ARG TZ=America/Bogota
ENV TZ=${TZ} \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOST=0.0.0.0 \
    PORT=8000 \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

# Native build tools and FFmpeg are not part of the runtime image. Local audio
# conversion resolves an optional binary from the persistent application data
# directory, while cloud transcription works without it.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata \
    && ln -snf /usr/share/zoneinfo/${TZ} /etc/localtime \
    && echo ${TZ} > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY backend/ ./backend/
RUN mkdir -p /app/data /app/knowledge_data \
    && useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app

WORKDIR /app/backend
USER appuser
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=5 CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=5)"]
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
