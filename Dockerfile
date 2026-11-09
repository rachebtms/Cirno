ARG CIRNO_VARIANT=slim

# The browser bundle is architecture-independent; never run Node under QEMU.
FROM --platform=$BUILDPLATFORM node:24-bookworm-slim AS webui-builder

WORKDIR /app/sources/cirno-web
COPY sources/cirno-web/package.json sources/cirno-web/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci --prefer-offline
COPY sources/cirno-web/ ./
COPY sources/cirno-core/src/cirno_core/agent/tools/names.json /app/sources/cirno-core/src/cirno_core/agent/tools/names.json
RUN npm run build

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS slim-base

RUN apt-get update && \
    apt-get install -y --no-install-recommends ca-certificates curl git bubblewrap openssh-client libmagic1 && \
    rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 1000 -s /bin/bash cirno
ENV HOME=/home/cirno CIRNO_SHELL_VENV=/app/.venv

# Ubuntu 24.04 meets Homebrew's supported glibc baseline on both architectures.
# BuildKit skips this stage entirely for the default slim variant.
FROM ubuntu:24.04 AS full-base
ARG DEBIAN_FRONTEND=noninteractive
ARG HOMEBREW_VERSION=7.0.12
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl git build-essential file procps locales patch bzip2 xz-utils unzip \
    openssh-client bubblewrap libmagic1 util-linux && \
    rm -rf /var/lib/apt/lists/* && \
    userdel ubuntu && useradd -m -u 1000 -s /bin/bash cirno && \
    mkdir -p /home/linuxbrew/.linuxbrew /opt/cirno/bin /opt/cirno/node-tools /opt/cirno/python-tools /opt/cirno/models /opt/nvm && \
    chown -R cirno:cirno /home/linuxbrew /opt/cirno && \
    curl --fail --location --retry 5 --retry-all-errors \
      https://github.com/nvm-sh/nvm/archive/refs/tags/v0.40.8.tar.gz -o /tmp/nvm.tar.gz && \
    echo '7c5b2c4c78e6447b518860ead1f365056e9a03b3562903439bb401607b05a2ef  /tmp/nvm.tar.gz' | sha256sum -c - && \
    tar -xzf /tmp/nvm.tar.gz -C /opt/nvm --strip-components=1 && rm /tmp/nvm.tar.gz
ENV HOME=/home/cirno \
    HOMEBREW_PREFIX=/home/linuxbrew/.linuxbrew \
    HOMEBREW_NO_ANALYTICS=1 HOMEBREW_NO_AUTO_UPDATE=1 \
    HOMEBREW_NO_INSTALL_CLEANUP=1 \
    PATH="/home/linuxbrew/.linuxbrew/opt/python@3.12/libexec/bin:/home/linuxbrew/.linuxbrew/bin:/home/linuxbrew/.linuxbrew/sbin:/opt/cirno/bin:/opt/cirno/node-tools/bin:$PATH"
COPY sources/deployment/full-image.Brewfile /tmp/full-image.Brewfile
COPY sources/deployment/full-image-python.txt /tmp/full-image-python.txt
COPY sources/deployment/install_full_tools.sh /tmp/install_full_tools.sh
COPY sources/deployment/bundle_embedding.py /tmp/bundle_embedding.py
USER cirno
RUN --mount=type=cache,target=/home/cirno/.cache,uid=1000,gid=1000 \
    git clone --depth 1 --branch "$HOMEBREW_VERSION" https://github.com/Homebrew/brew /home/linuxbrew/.linuxbrew/Homebrew && \
    mkdir -p /home/linuxbrew/.linuxbrew/bin && \
    ln -s ../Homebrew/bin/brew /home/linuxbrew/.linuxbrew/bin/brew && \
    bash /tmp/install_full_tools.sh
USER root
COPY sources/deployment/full-image-shell.sh /etc/profile.d/cirno-tools.sh
ENV CIRNO_FULL_IMAGE=1 \
    CIRNO_SHELL_VENV=/home/cirno/.cirno/state/tools/python \
    TEA_CONFIG_DIR=/home/cirno/.cirno/state/cli/config/tea \
    PIP_CACHE_DIR=/home/cirno/.cirno/state/cli/cache/pip \
    NPM_CONFIG_CACHE=/home/cirno/.cirno/state/cli/cache/npm \
    NPM_CONFIG_USERCONFIG=/home/cirno/.cirno/state/cli/config/npmrc \
    BASH_ENV=/etc/profile.d/cirno-tools.sh \
    CIRNO_BUNDLED_EMBEDDING_DIR=/opt/cirno/models/bge-small-zh-v1.5 \
    XDG_CONFIG_HOME=/home/cirno/.cirno/state/cli/config \
    XDG_DATA_HOME=/home/cirno/.cirno/state/cli/data \
    XDG_CACHE_HOME=/home/cirno/.cirno/state/cli/cache \
    HF_HOME=/home/cirno/.cirno/state/cli/huggingface \
    GOPATH=/home/cirno/.cirno/state/tools/go \
    GOBIN=/home/cirno/.cirno/state/tools/bin \
    BUN_INSTALL=/home/cirno/.cirno/state/tools/bun \
    GH_CONFIG_DIR=/home/cirno/.cirno/state/cli/config/gh \
    GIT_CONFIG_GLOBAL=/home/cirno/.cirno/state/cli/gitconfig \
    NPM_CONFIG_PREFIX=/home/cirno/.cirno/state/tools/npm \
    UV_TOOL_DIR=/home/cirno/.cirno/state/tools/uv \
    UV_TOOL_BIN_DIR=/home/cirno/.cirno/state/tools/bin \
    PIPX_HOME=/home/cirno/.cirno/state/tools/pipx \
    PIPX_BIN_DIR=/home/cirno/.cirno/state/tools/bin \
    NVM_DIR=/home/cirno/.cirno/state/tools/nvm \
    PATH="/home/cirno/.cirno/state/tools/bin:/home/cirno/.cirno/state/tools/npm/bin:/home/cirno/.cirno/state/tools/bun/bin:$PATH" \
    CIRNO_EXTRAS_DEFAULT=memory-embedding,azure,bedrock,olostep \
    CIRNO_CHANNELS_DEFAULT=telegram

FROM ${CIRNO_VARIANT}-base AS runtime

WORKDIR /app

# Keep the runtime environment writable by the non-root cirno user. Enabled
# channels may install their manifest-declared dependencies at startup.
ENV VIRTUAL_ENV=/app/.venv
ENV PATH="$CIRNO_SHELL_VENV/bin:/app/.venv/bin:$PATH"
RUN uv venv --seed "$VIRTUAL_ENV"

# Build the local distributions together; none is fetched from PyPI.
ARG CIRNO_EXTRAS=
COPY pyproject.toml README.md LICENSE THIRD_PARTY_NOTICES.md ./
COPY documents/ documents/
COPY sources/cirno/ sources/cirno/
COPY sources/cirno-memory/ sources/cirno-memory/
COPY sources/cirno-usage/ sources/cirno-usage/
COPY sources/cirno-vault/ sources/cirno-vault/
COPY sources/cirno-core/ sources/cirno-core/
COPY sources/cirno-server/ sources/cirno-server/
COPY sources/deployment/install_channel_dependencies.py scripts/
COPY --from=webui-builder /app/build/webui/ build/webui/
RUN extras="${CIRNO_EXTRAS:-${CIRNO_EXTRAS_DEFAULT:-}}" && \
    if [ -n "$extras" ]; then project=".[$extras]"; else project="."; fi && \
    CIRNO_SKIP_WEBUI_BUILD=1 uv pip install --python "$VIRTUAL_ENV/bin/python" --no-cache \
    ./sources/cirno-memory ./sources/cirno-usage ./sources/cirno-vault ./sources/cirno-core ./sources/cirno-server "$project"

# Preinstall selected channel dependencies from their manifests. A comma-separated
# list selects dependencies for the included channels.
ARG CIRNO_CHANNELS=
RUN for channel in $(printf '%s' "${CIRNO_CHANNELS:-${CIRNO_CHANNELS_DEFAULT:-}}" | tr ',' ' '); do \
        python -m scripts.install_channel_dependencies "$channel"; \
    done


# Hand ownership of the writable virtualenv to the Cirno user.
RUN mkdir -p /home/cirno/.cirno && \
    chown -R cirno:cirno /home/cirno /app/.venv

COPY sources/deployment/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN sed -i 's/\r$//' /usr/local/bin/entrypoint.sh && chmod +x /usr/local/bin/entrypoint.sh

# Start as root so the entrypoint can chown a mounted data directory
# before dropping to the non-root
# cirno user via setpriv. The entrypoint drops privileges on every root start
# and fails closed if it cannot, so the agent never runs as root (see
# entrypoint.sh).
USER root
ENV HOME=/home/cirno
# Include Python crash diagnostics in container logs.
ENV PYTHONUNBUFFERED=1 PYTHONFAULTHANDLER=1
ENV VIRTUAL_ENV=$CIRNO_SHELL_VENV
ENV PATH="$CIRNO_SHELL_VENV/bin:$PATH"

# Service health endpoint and Web UI/WebSocket port
EXPOSE 18790 8765

ENTRYPOINT ["entrypoint.sh"]
CMD []
