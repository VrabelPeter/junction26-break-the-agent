FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates git tar gzip \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir fastmcp==2.12.4
RUN useradd -m -u 1001 agent && mkdir -p /app && chown agent:agent /app
WORKDIR /app
