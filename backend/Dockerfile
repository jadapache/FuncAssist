FROM python:3.12-slim-bookworm
ARG TZ=America/Bogota
ENV TZ=${TZ} PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 HOST=0.0.0.0 PORT=8000
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl ffmpeg gcc libffi-dev libssl-dev tzdata && ln -snf /usr/share/zoneinfo/${TZ} /etc/localtime && echo ${TZ} > /etc/timezone && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY backend/requirements.txt ./backend/requirements.txt
RUN python -m pip install --upgrade pip "setuptools<81" wheel supervisor && pip install -r backend/requirements.txt
COPY backend/ ./backend/
RUN mkdir -p /app/data /app/knowledge_data /var/log/supervisor && useradd --create-home --uid 10001 appuser && chown -R appuser:appuser /app /var/log/supervisor
COPY docker/supervisord.conf /etc/supervisord.conf
WORKDIR /app/backend
USER appuser
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=5 CMD curl -fsS http://127.0.0.1:8000/api/health || exit 1
CMD ["/usr/local/bin/supervisord", "-c", "/etc/supervisord.conf", "-n"]
