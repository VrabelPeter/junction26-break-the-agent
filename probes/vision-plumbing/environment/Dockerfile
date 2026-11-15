FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates git tar gzip xz-utils coreutils bash \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir fastmcp==2.12.4
RUN useradd -m -u 1001 agent && mkdir -p /app && chown agent:agent /app
# OpenCode preinstalled for the agent user, so Harbor's agent setup finds it and
# does not download Node and OpenCode on every run (slow network at the venue).
USER agent
SHELL ["/bin/bash", "-c"]
RUN curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.2/install.sh | env -u NODE_VERSION bash \
    && export NVM_DIR="$HOME/.nvm" && . "$NVM_DIR/nvm.sh" \
    && nvm install 22 && nvm alias default 22 \
    && npm i -g opencode-ai@latest && opencode --version
USER root
WORKDIR /app
