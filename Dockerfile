# syntax=docker/dockerfile:1
# Pip cache: bind-mount ./.pip-cache so wheels survive "docker builder prune" and layer rebuilds
# (anonymous BuildKit cache mounts are easier to lose on Docker Desktop).
FROM python:3.13-slim

WORKDIR /app

# System deps for sentence-transformers
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc && \
    rm -rf /var/lib/apt/lists/*

# Install Python deps (copy only requirements first so this layer is cached when app code changes)
COPY requirements.txt .
RUN --mount=type=bind,source=.pip-cache,target=/root/.cache/pip \
    pip install -r requirements.txt

# Copy project
COPY . .

# Prevent Keras/TF conflicts
ENV TRANSFORMERS_NO_TF=1
ENV USE_TF=0
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Fly proxy uses [http_service] internal_port — must match what we listen on (default 8000; override with PORT).
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
